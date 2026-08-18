"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { PageLoading } from "@/components/ui";

/** Wraps the protected route group - redirects to /login if there's no
 * valid session, renders nothing while that's still being determined so
 * a protected page never flashes its (possibly sensitive) content before
 * the redirect fires. */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface-subtle">
        <PageLoading />
      </div>
    );
  }

  return <>{children}</>;
}
