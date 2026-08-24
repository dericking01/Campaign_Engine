"use client";

import { AlarmClock } from "lucide-react";
import { Button } from "@/components/ui";

/** Centered warning shown shortly before the sliding-session idle
 * timeout fires (see AuthProvider) - gives an inactive-but-present user
 * a chance to stay signed in before they're auto logged out, rather
 * than just silently dropping them. Any real activity (including
 * clicking "Stay signed in") extends the session and this closes on its
 * own; doing nothing lets the countdown reach the real auto-logout. */
export function SessionTimeoutModal({
  secondsRemaining,
  onStaySignedIn,
  onSignOutNow,
}: {
  secondsRemaining: number;
  onStaySignedIn: () => void;
  onSignOutNow: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" role="alertdialog" aria-live="assertive">
      <div className="absolute inset-0 bg-brand-950/40 backdrop-blur-[2px] animate-fade-in" />
      <div className="relative w-full max-w-sm animate-scale-in rounded-2xl bg-white p-6 shadow-lifted">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-amber-50 text-amber-600">
          <AlarmClock className="h-6 w-6" />
        </div>
        <h3 className="text-[17px] font-semibold text-ink">Still there?</h3>
        <p className="mt-1.5 text-[14px] text-ink-muted">
          You&apos;ve been inactive. For your security, you&apos;ll be signed out in{" "}
          <span className="font-semibold text-ink">{secondsRemaining}s</span>.
        </p>
        <div className="mt-5 flex gap-2">
          <Button variant="outline" className="flex-1" onClick={onSignOutNow}>
            Sign out now
          </Button>
          <Button className="flex-1" onClick={onStaySignedIn}>
            Stay signed in
          </Button>
        </div>
      </div>
    </div>
  );
}
