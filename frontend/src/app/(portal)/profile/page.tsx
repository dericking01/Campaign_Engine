"use client";

import { useState } from "react";
import { ArrowLeft, KeyRound, Lock, Mail, Phone, ShieldCheck, User } from "lucide-react";
import { api, ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import { PageHeader } from "@/components/PageHeader";
import { OtpInput } from "@/components/OtpInput";
import { Alert, Button, Card, CardHeader, Input, PasswordInput } from "@/components/ui";
import { cn } from "@/lib/cn";

const PHONE_RE = /^255[0-9]{9}$/;

function Toggle({ checked, disabled, onChange }: { checked: boolean; disabled?: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onChange}
      className={cn(
        "relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition-colors duration-150",
        checked ? "bg-brand-800" : "bg-line-strong",
        disabled && "cursor-not-allowed opacity-50"
      )}
    >
      <span
        className={cn(
          "inline-block h-5 w-5 transform rounded-full bg-white shadow-soft transition-transform duration-150",
          checked ? "translate-x-6" : "translate-x-1"
        )}
      />
    </button>
  );
}

export default function ProfilePage() {
  const auth = useAuth();

  // --- Profile details ---
  const [fullName, setFullName] = useState(auth.user?.full_name ?? "");
  const [email, setEmail] = useState(auth.user?.email ?? "");
  const [phone, setPhone] = useState(auth.user?.phone ?? "");
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileMessage, setProfileMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);

  // --- 2FA toggle ---
  const [togglingTwoFactor, setTogglingTwoFactor] = useState(false);
  const [twoFactorMessage, setTwoFactorMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);

  // --- Change password (OTP-gated) ---
  type PwStep = "idle" | "otp";
  const [pwStep, setPwStep] = useState<PwStep>("idle");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwPendingToken, setPwPendingToken] = useState<string | null>(null);
  const [pwCode, setPwCode] = useState("");
  const [pwOtpReset, setPwOtpReset] = useState(0);
  const [requestingPwOtp, setRequestingPwOtp] = useState(false);
  const [confirmingPw, setConfirmingPw] = useState(false);
  const [pwMessage, setPwMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);

  if (!auth.user) {
    return null;
  }

  async function onSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    setProfileMessage(null);
    if (phone.trim() && !PHONE_RE.test(phone.trim())) {
      setProfileMessage({ text: "Phone must be in 255XXXXXXXXX format.", tone: "error" });
      return;
    }
    setSavingProfile(true);
    try {
      await api.updateProfile({
        full_name: fullName.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
      });
      setProfileMessage({ text: "Profile updated.", tone: "success" });
    } catch (err) {
      setProfileMessage({ text: err instanceof ApiError ? err.message : "Could not update profile", tone: "error" });
    } finally {
      setSavingProfile(false);
    }
  }

  async function onToggleTwoFactor() {
    if (!auth.user) return;
    const next = !auth.user.two_factor_enabled;
    if (next && !auth.user.phone) {
      setTwoFactorMessage({ text: "Add a phone number before enabling 2FA.", tone: "error" });
      return;
    }
    setTogglingTwoFactor(true);
    setTwoFactorMessage(null);
    try {
      await api.updateTwoFactor(next);
      setTwoFactorMessage({ text: next ? "Two-factor authentication enabled." : "Two-factor authentication disabled.", tone: "success" });
      window.location.reload();
    } catch (err) {
      setTwoFactorMessage({ text: err instanceof ApiError ? err.message : "Could not update 2FA", tone: "error" });
    } finally {
      setTogglingTwoFactor(false);
    }
  }

  async function onRequestPasswordOtp(e: React.FormEvent) {
    e.preventDefault();
    setPwMessage(null);
    if (!currentPassword) {
      setPwMessage({ text: "Enter your current password.", tone: "error" });
      return;
    }
    if (newPassword.length < 8) {
      setPwMessage({ text: "New password must be at least 8 characters.", tone: "error" });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPwMessage({ text: "New passwords do not match.", tone: "error" });
      return;
    }
    setRequestingPwOtp(true);
    try {
      const res = await api.requestPasswordChange(currentPassword);
      setPwPendingToken(res.pending_token);
      setPwStep("otp");
    } catch (err) {
      setPwMessage({ text: err instanceof ApiError ? err.message : "Could not send verification code", tone: "error" });
    } finally {
      setRequestingPwOtp(false);
    }
  }

  async function confirmPasswordChange(code: string) {
    if (!pwPendingToken || code.length !== 4) return;
    setConfirmingPw(true);
    setPwMessage(null);
    try {
      await api.confirmPasswordChange(pwPendingToken, code, newPassword);
      setPwMessage({ text: "Password changed successfully.", tone: "success" });
      setPwStep("idle");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPwPendingToken(null);
      setPwCode("");
    } catch (err) {
      setPwMessage({ text: err instanceof ApiError ? err.message : "Verification failed", tone: "error" });
      setPwCode("");
      setPwOtpReset((n) => n + 1);
    } finally {
      setConfirmingPw(false);
    }
  }

  return (
    <>
      <PageHeader title="My Profile" description="Update your account details, security preferences and password." />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title="Profile details" description="Your name, email and registered phone number." />
          <form onSubmit={onSaveProfile} className="space-y-4">
            <Input label="Full name" icon={<User />} value={fullName} onChange={(e) => setFullName(e.target.value)} />
            <Input label="Email" type="email" icon={<Mail />} value={email} onChange={(e) => setEmail(e.target.value)} />
            <Input
              label="Phone number"
              icon={<Phone />}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="255XXXXXXXXX"
              hint="Used for login verification codes and password resets"
            />
            {profileMessage && <Alert tone={profileMessage.tone === "success" ? "success" : "error"}>{profileMessage.text}</Alert>}
            <Button type="submit" loading={savingProfile}>
              Save changes
            </Button>
          </form>
        </Card>

        <div className="flex flex-col gap-5">
          <Card>
            <CardHeader title="Two-factor authentication" description="Require a code sent to your phone every time you sign in." />
            <div className="flex items-center justify-between gap-4 rounded-lg border border-line bg-surface-sunken/50 px-4 py-3.5">
              <div className="flex items-center gap-3">
                <ShieldCheck className={cn("h-5 w-5", auth.user.two_factor_enabled ? "text-brand-700" : "text-ink-faint")} />
                <div>
                  <p className="text-[13.5px] font-medium text-ink">
                    {auth.user.two_factor_enabled ? "Enabled" : "Disabled"}
                  </p>
                  <p className="text-[12.5px] text-ink-faint">
                    {auth.user.phone ? `Codes are sent to ${auth.user.phone}` : "Add a phone number to enable this"}
                  </p>
                </div>
              </div>
              <Toggle
                checked={auth.user.two_factor_enabled}
                disabled={togglingTwoFactor || !auth.user.phone}
                onChange={onToggleTwoFactor}
              />
            </div>
            {twoFactorMessage && (
              <Alert tone={twoFactorMessage.tone === "success" ? "success" : "error"} className="mt-4">
                {twoFactorMessage.text}
              </Alert>
            )}
            <p className="mt-4 text-[12.5px] text-ink-faint">
              Even with 2FA disabled, resetting a forgotten password always requires a verification code sent to
              your registered phone.
            </p>
          </Card>

          <Card>
            <CardHeader title="Change password" description="Confirmed via a verification code sent to your phone." />
            {pwStep === "idle" ? (
              <form onSubmit={onRequestPasswordOtp} className="space-y-4">
                <PasswordInput
                  label="Current password"
                  icon={<Lock />}
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
                <PasswordInput
                  label="New password"
                  icon={<Lock />}
                  autoComplete="new-password"
                  placeholder="At least 8 characters"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
                <PasswordInput
                  label="Confirm new password"
                  icon={<Lock />}
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
                {pwMessage && <Alert tone={pwMessage.tone === "success" ? "success" : "error"}>{pwMessage.text}</Alert>}
                <Button type="submit" loading={requestingPwOtp} icon={<KeyRound />} disabled={!auth.user.phone}>
                  Send verification code
                </Button>
                {!auth.user.phone && (
                  <p className="text-[12.5px] text-ink-faint">Add a phone number above before changing your password.</p>
                )}
              </form>
            ) : (
              <div className="space-y-5">
                <p className="text-[13.5px] text-ink-muted">
                  Enter the 4-character code sent to {auth.user.phone}.
                </p>
                <OtpInput
                  key={pwOtpReset}
                  reset={pwOtpReset}
                  disabled={confirmingPw}
                  onChange={setPwCode}
                  onComplete={confirmPasswordChange}
                />
                {pwMessage && <Alert tone={pwMessage.tone === "success" ? "success" : "error"}>{pwMessage.text}</Alert>}
                <Button
                  loading={confirmingPw}
                  disabled={pwCode.length !== 4}
                  icon={<ShieldCheck />}
                  onClick={() => confirmPasswordChange(pwCode)}
                >
                  Confirm
                </Button>
                <button
                  type="button"
                  onClick={() => {
                    setPwStep("idle");
                    setPwPendingToken(null);
                    setPwCode("");
                    setPwMessage(null);
                  }}
                  className="flex items-center gap-1.5 text-[13px] font-medium text-ink-muted hover:text-ink"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  Cancel
                </button>
              </div>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
