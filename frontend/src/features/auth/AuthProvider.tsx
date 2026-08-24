"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, login as apiLogin, verifyLoginOtp as apiVerifyLoginOtp } from "@/services/api";
import { clearToken, getToken } from "@/services/tokenStorage";
import type { CurrentUser, LoginResult } from "@/types";
import { AUTH_EXPIRED_EVENT } from "./constants";
import { SessionTimeoutModal } from "@/components/SessionTimeoutModal";

// How often to check for recent activity and, if there was any, "touch"
// the session (any authenticated request extends it server-side - see
// app.core.deps.get_current_user). Well under the server-side idle
// timeout so an active user's session never lapses mid-work.
const HEARTBEAT_INTERVAL_MS = 60_000;
// How often to recompute local elapsed idle time against the
// server-configured timeout (user.session_idle_timeout_minutes). This is
// the piece that actually enforces "auto logged out while inactive": a
// purely idle tab sends no requests at all, so the server-side check
// inside get_current_user (which only runs when a request arrives) never
// gets a chance to fire - nothing tells the browser its session went
// stale until the user acts again. Checking elapsed wall-clock time
// locally closes that gap instead of waiting on a round trip that may
// never happen. Runs every second (not just every 15s) so the warning
// modal's on-screen countdown is smooth, not choppy.
const IDLE_TICK_INTERVAL_MS = 1_000;
// The warning modal appears once this much idle time remains before the
// real auto-logout - capped at 30s, but never more than half the
// configured timeout, so a short test/staging timeout still gets a
// sensible (if brief) warning instead of the modal eating most of it.
const WARNING_BEFORE_TIMEOUT_MS = 30_000;
const ACTIVITY_EVENTS = ["mousemove", "keydown", "click", "scroll", "touchstart"] as const;

interface AuthState {
  user: CurrentUser | null;
  loading: boolean;
  login: (identifier: string, password: string, remember?: boolean) => Promise<LoginResult>;
  verifyOtp: (pendingToken: string, code: string, remember: boolean) => Promise<void>;
  logout: () => void;
  can: (action: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const activeSinceLastTick = useRef(false);
  const lastActivityAt = useRef(Date.now());
  const [idleWarningSecondsLeft, setIdleWarningSecondsLeft] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onExpired = () => {
      clearToken();
      setUser(null);
      router.replace("/login");
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [router]);

  // Session activity heartbeat + idle-timeout enforcement. Two jobs, one
  // shared listener set: (1) if there was real activity since the last
  // tick, ping the server so it extends the session (get_current_user
  // bumps last_activity_at); (2) independent of any request, watch the
  // *local* elapsed idle time, surface the warning modal once inside
  // WARNING_BEFORE_TIMEOUT_MS of the cutoff, and force a logout once it's
  // crossed - this is what actually makes "logged out after N minutes
  // idle" true for a tab that never triggers a request while inactive.
  useEffect(() => {
    if (!user) return;

    lastActivityAt.current = Date.now();
    setIdleWarningSecondsLeft(null);
    const idleTimeoutMs = user.session_idle_timeout_minutes * 60_000;
    const warningMs = Math.min(WARNING_BEFORE_TIMEOUT_MS, idleTimeoutMs / 2);

    const markActive = () => {
      activeSinceLastTick.current = true;
      lastActivityAt.current = Date.now();
    };
    ACTIVITY_EVENTS.forEach((evt) => window.addEventListener(evt, markActive, { passive: true }));

    function tick() {
      const remainingMs = idleTimeoutMs - (Date.now() - lastActivityAt.current);
      if (remainingMs <= 0) {
        setIdleWarningSecondsLeft(null);
        logout();
        return;
      }
      // Always (re)compute rather than reading prior state, to avoid a
      // stale closure - this effect only re-runs on [user], not on every
      // tick, so a value captured once and conditionally reused here
      // would go stale after the first warning/dismiss cycle.
      setIdleWarningSecondsLeft(remainingMs <= warningMs ? Math.ceil(remainingMs / 1000) : null);
    }
    // Also re-check the moment the tab regains focus/visibility - a
    // backgrounded or suspended tab may not have run its interval at all
    // while away, so without this a user returning after a long idle
    // stretch would see stale "still logged in" UI until the next tick.
    document.addEventListener("visibilitychange", tick);
    window.addEventListener("focus", tick);
    const idleInterval = setInterval(tick, IDLE_TICK_INTERVAL_MS);

    const heartbeatInterval = setInterval(() => {
      if (activeSinceLastTick.current) {
        activeSinceLastTick.current = false;
        api.me().catch(() => {
          // A failure here (401) already triggers AUTH_EXPIRED_EVENT via
          // apiFetch - nothing else to do.
        });
      }
    }, HEARTBEAT_INTERVAL_MS);

    return () => {
      ACTIVITY_EVENTS.forEach((evt) => window.removeEventListener(evt, markActive));
      document.removeEventListener("visibilitychange", tick);
      window.removeEventListener("focus", tick);
      clearInterval(idleInterval);
      clearInterval(heartbeatInterval);
    };
  }, [user]);

  function staySignedIn() {
    lastActivityAt.current = Date.now();
    activeSinceLastTick.current = true;
    setIdleWarningSecondsLeft(null);
  }

  async function login(identifier: string, password: string, remember = true): Promise<LoginResult> {
    const result = await apiLogin(identifier, password, remember);
    if (!result.requires_otp) {
      await refresh();
    }
    return result;
  }

  async function verifyOtp(pendingToken: string, code: string, remember: boolean) {
    await apiVerifyLoginOtp(pendingToken, code, remember);
    await refresh();
  }

  function logout() {
    clearToken();
    setUser(null);
    router.push("/login");
  }

  function can(action: string) {
    return user?.permissions.includes(action) ?? false;
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, verifyOtp, logout, can }}>
      {children}
      {idleWarningSecondsLeft !== null && (
        <SessionTimeoutModal
          secondsRemaining={idleWarningSecondsLeft}
          onStaySignedIn={staySignedIn}
          onSignOutNow={logout}
        />
      )}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
