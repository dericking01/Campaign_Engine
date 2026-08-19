"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  UploadCloud,
  Database,
  ShieldOff,
  Megaphone,
  Activity,
  BarChart3,
  History,
  Settings,
  Users,
  KeyRound,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { useAuth } from "@/features/auth/AuthProvider";
import { cn } from "@/lib/cn";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/imports", label: "Data Imports", icon: UploadCloud },
  { href: "/bases", label: "Bases", icon: Database },
  { href: "/dnd", label: "DND", icon: ShieldOff },
  { href: "/campaigns", label: "Campaigns", icon: Megaphone },
  { href: "/runs", label: "Execution Monitor", icon: Activity },
  { href: "/reports", label: "Reports & Analytics", icon: BarChart3 },
  { href: "/audit", label: "Audit Log", icon: History },
  { href: "/staff", label: "Staff Directory", icon: Users },
  { href: "/roles", label: "Roles & Permissions", icon: KeyRound },
  { href: "/settings", label: "System Configuration", icon: Settings },
];

function initialsOf(email: string): string {
  const name = email.split("@")[0];
  return name.slice(0, 2).toUpperCase();
}

function SidebarContent({ onNavigate, onClose }: { onNavigate?: () => void; onClose?: () => void }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 shrink-0 items-center justify-between px-5">
        <Image src="/afyacall-logo.png" alt="AfyaCall" width={132} height={50} className="h-7 w-auto" />
        {onClose && (
          <button
            onClick={onClose}
            aria-label="Close menu"
            className="flex h-9 w-9 items-center justify-center rounded-lg text-ink-muted hover:bg-surface-sunken"
          >
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      <nav className="scrollbar-thin flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname?.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={cn(
                "group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] font-medium transition-colors",
                active
                  ? "bg-brand-800 text-white shadow-soft"
                  : "text-ink-muted hover:bg-surface-sunken hover:text-ink"
              )}
            >
              <Icon
                className={cn(
                  "h-[17px] w-[17px] shrink-0 transition-colors",
                  active ? "text-lime-300" : "text-ink-faint group-hover:text-brand-600"
                )}
              />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {user && (
        <div className="shrink-0 border-t border-line p-3">
          <div className="flex items-center gap-2.5 rounded-lg px-2 py-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[12px] font-semibold text-brand-800">
              {initialsOf(user.email)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-ink">{user.email}</p>
              <p className="text-[11.5px] text-ink-faint">{user.role.replace(/_/g, " ")}</p>
            </div>
            <button
              onClick={logout}
              aria-label="Sign out"
              title="Sign out"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-ink-faint transition-colors hover:bg-red-50 hover:text-red-600"
            >
              <LogOut className="h-[15px] w-[15px]" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function NavShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-surface-subtle lg:flex">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex lg:w-64 lg:shrink-0 lg:flex-col lg:border-r lg:border-line lg:bg-white">
        <SidebarContent />
      </aside>

      {/* Mobile top bar + drawer - sticky so the menu trigger stays reachable
          while scrolling a long page (Roles & Permissions' matrix, a long
          campaign list, ...), not just at the very top. */}
      <div className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-line bg-white px-4 lg:hidden">
        <Image src="/afyacall-logo.png" alt="AfyaCall" width={116} height={44} className="h-6 w-auto" />
        <button
          onClick={() => setMobileOpen(true)}
          aria-label="Open menu"
          className="flex h-11 w-11 items-center justify-center rounded-lg border border-line-strong text-ink-muted transition-colors hover:border-brand-300 hover:bg-brand-50 active:bg-brand-100"
        >
          <Menu className="h-5 w-5" />
        </button>
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-brand-950/40 backdrop-blur-[2px] animate-fade-in"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] animate-slide-up bg-white shadow-lifted">
            <SidebarContent onNavigate={() => setMobileOpen(false)} onClose={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-[1400px] px-5 py-8 sm:px-8 lg:px-10">{children}</div>
      </main>
    </div>
  );
}
