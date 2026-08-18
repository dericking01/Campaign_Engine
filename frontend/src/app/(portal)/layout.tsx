import NavShell from "@/components/NavShell";
import RequireAuth from "@/features/auth/RequireAuth";

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <NavShell>{children}</NavShell>
    </RequireAuth>
  );
}
