"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, LogIn, ShieldCheck, User } from "lucide-react";
import { ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import { AuthHeroPanel } from "@/features/auth/AuthHeroPanel";
import { OtpInput } from "@/components/OtpInput";
import { Button, Input, PasswordInput, Checkbox, Alert } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const { user, loading, login, verifyOtp } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Step 2: only entered once /auth/login reports requires_otp: true.
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [otpReset, setOtpReset] = useState(0);
  const [verifying, setVerifying] = useState(false);

  // Already signed in (e.g. navigated back to /login manually) - bounce to
  // the portal instead of showing the form again.
  useEffect(() => {
    if (!loading && user) {
      router.replace("/");
    }
  }, [loading, user, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await login(identifier, password, remember);
      if (result.requires_otp && result.pending_token) {
        setPendingToken(result.pending_token);
      } else {
        router.push("/");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitOtp(code: string) {
    if (!pendingToken || code.length !== 4 || verifying) return;
    setVerifying(true);
    setError(null);
    try {
      await verifyOtp(pendingToken, code, remember);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Verification failed");
      setOtpCode("");
      setOtpReset((n) => n + 1);
    } finally {
      setVerifying(false);
    }
  }

  function backToCredentials() {
    setPendingToken(null);
    setOtpCode("");
    setError(null);
  }

  if (loading || user) {
    return <div className="h-screen w-screen bg-surface-subtle" />;
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      <AuthHeroPanel />

      <div className="flex min-h-screen flex-col items-center justify-center bg-surface-subtle px-6 py-12 sm:px-10">
        <div className="w-full max-w-[380px] animate-scale-in">
          <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
            <Image
              src="/afyacall-logo.png"
              alt="AfyaCall"
              width={148}
              height={56}
              priority
              className="mb-7 h-9 w-auto lg:hidden"
            />
            {pendingToken ? (
              <>
                <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-brand-50 text-brand-700">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <h2 className="text-[22px] font-semibold tracking-tight text-ink">Verify it&apos;s you</h2>
                <p className="mt-1.5 text-[14px] text-ink-muted">
                  Enter the 4-character code sent to your registered phone number.
                </p>
              </>
            ) : (
              <>
                <h2 className="text-[22px] font-semibold tracking-tight text-ink">Welcome back</h2>
                <p className="mt-1.5 text-[14px] text-ink-muted">
                  Sign in to the Campaign Engine control plane.
                </p>
              </>
            )}
          </div>

          {pendingToken ? (
            <div className="space-y-5">
              <OtpInput
                key={otpReset}
                reset={otpReset}
                disabled={verifying}
                onChange={setOtpCode}
                onComplete={submitOtp}
              />

              {error && <Alert tone="error">{error}</Alert>}

              <Button
                type="button"
                size="lg"
                loading={verifying}
                icon={<ShieldCheck />}
                className="w-full"
                disabled={otpCode.length !== 4}
                onClick={() => submitOtp(otpCode)}
              >
                {verifying ? "Verifying" : "Confirm"}
              </Button>

              <button
                type="button"
                onClick={backToCredentials}
                className="flex w-full items-center justify-center gap-1.5 text-[13px] font-medium text-ink-muted hover:text-ink"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Back to sign in
              </button>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4" noValidate>
              <Input
                label="Email or phone number"
                type="text"
                icon={<User />}
                placeholder="you@afyacall.co.tz or 255XXXXXXXXX"
                autoComplete="username"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                required
              />
              <PasswordInput
                label="Password"
                placeholder="••••••••"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />

              <div className="flex items-center justify-between pt-0.5">
                <Checkbox
                  label="Remember me"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                />
                <Link href="/forgot-password" className="text-[13px] font-medium text-brand-700 hover:text-brand-800">
                  Forgot password?
                </Link>
              </div>

              {error && <Alert tone="error">{error}</Alert>}

              <Button
                type="submit"
                size="lg"
                loading={submitting}
                icon={<LogIn />}
                className="w-full"
              >
                {submitting ? "Signing in" : "Sign in"}
              </Button>
            </form>
          )}

          <p className="mt-8 text-center text-[13px] text-ink-faint lg:text-left">
            Access is provisioned by your AfyaCall administrator.
          </p>
        </div>
      </div>
    </div>
  );
}
