"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, KeyRound, Lock, ShieldCheck, User } from "lucide-react";
import { api, ApiError } from "@/services/api";
import { AuthHeroPanel } from "@/features/auth/AuthHeroPanel";
import { OtpInput } from "@/components/OtpInput";
import { Button, Input, PasswordInput, Alert } from "@/components/ui";

type Step = "identify" | "reset" | "done";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("identify");
  const [identifier, setIdentifier] = useState("");
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [otpReset, setOtpReset] = useState(0);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function requestCode(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.forgotPasswordRequest(identifier.trim());
      setPendingToken(res.pending_token);
      setStep("reset");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitReset(e?: React.FormEvent) {
    e?.preventDefault();
    if (!pendingToken) return;
    if (code.length !== 4) {
      setError("Enter the 4-character code sent to your phone");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.forgotPasswordReset(pendingToken, code, newPassword);
      setStep("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed");
      setCode("");
      setOtpReset((n) => n + 1);
    } finally {
      setSubmitting(false);
    }
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
            <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-brand-50 text-brand-700">
              {step === "done" ? <ShieldCheck className="h-5 w-5" /> : <KeyRound className="h-5 w-5" />}
            </div>

            {step === "identify" && (
              <>
                <h2 className="text-[22px] font-semibold tracking-tight text-ink">Reset your password</h2>
                <p className="mt-1.5 text-[14px] text-ink-muted">
                  Enter your email or phone number and we&apos;ll send a verification code to your
                  registered phone.
                </p>
              </>
            )}
            {step === "reset" && (
              <>
                <h2 className="text-[22px] font-semibold tracking-tight text-ink">Check your phone</h2>
                <p className="mt-1.5 text-[14px] text-ink-muted">
                  Enter the 4-character code and choose a new password.
                </p>
              </>
            )}
            {step === "done" && (
              <>
                <h2 className="text-[22px] font-semibold tracking-tight text-ink">Password updated</h2>
                <p className="mt-1.5 text-[14px] text-ink-muted">
                  You can now sign in with your new password.
                </p>
              </>
            )}
          </div>

          {step === "identify" && (
            <form onSubmit={requestCode} className="space-y-4" noValidate>
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

              {error && <Alert tone="error">{error}</Alert>}

              <Button type="submit" size="lg" loading={submitting} className="w-full">
                {submitting ? "Sending code" : "Send verification code"}
              </Button>

              <Link
                href="/login"
                className="flex w-full items-center justify-center gap-1.5 text-[13px] font-medium text-ink-muted hover:text-ink"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Back to sign in
              </Link>
            </form>
          )}

          {step === "reset" && (
            <form onSubmit={submitReset} className="space-y-5" noValidate>
              <OtpInput
                key={otpReset}
                reset={otpReset}
                disabled={submitting}
                onChange={setCode}
                onComplete={() => {}}
              />

              <PasswordInput
                label="New password"
                icon={<Lock />}
                placeholder="At least 8 characters"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
              />
              <PasswordInput
                label="Confirm new password"
                icon={<Lock />}
                placeholder="Re-enter password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />

              {error && <Alert tone="error">{error}</Alert>}

              <Button
                type="submit"
                size="lg"
                loading={submitting}
                className="w-full"
                disabled={code.length !== 4}
              >
                {submitting ? "Resetting" : "Reset password"}
              </Button>

              <button
                type="button"
                onClick={() => {
                  setStep("identify");
                  setPendingToken(null);
                  setCode("");
                  setError(null);
                }}
                className="flex w-full items-center justify-center gap-1.5 text-[13px] font-medium text-ink-muted hover:text-ink"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Use a different email or phone
              </button>
            </form>
          )}

          {step === "done" && (
            <Button size="lg" className="w-full" onClick={() => router.push("/login")}>
              Go to sign in
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
