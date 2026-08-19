"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { LogIn, Mail } from "lucide-react";
import { ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import { AuthHeroPanel } from "@/features/auth/AuthHeroPanel";
import { Button, Input, PasswordInput, Checkbox, Alert } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const { user, loading, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
      await login(email, password, remember);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
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
            <h2 className="text-[22px] font-semibold tracking-tight text-ink">Welcome back</h2>
            <p className="mt-1.5 text-[14px] text-ink-muted">
              Sign in to the Campaign Engine control plane.
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <Input
              label="Email"
              type="email"
              icon={<Mail />}
              placeholder="you@afyacall.co.tz"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
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
              <a href="#" className="text-[13px] font-medium text-brand-700 hover:text-brand-800">
                Forgot password?
              </a>
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

          <p className="mt-8 text-center text-[13px] text-ink-faint lg:text-left">
            Access is provisioned by your AfyaCall administrator.
          </p>
        </div>
      </div>
    </div>
  );
}
