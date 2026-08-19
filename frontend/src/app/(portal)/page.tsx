"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Database, Gauge, Megaphone, Server, XCircle, Zap } from "lucide-react";
import { api } from "@/services/api";
import type { RateLimitStatus, ReadyCheck } from "@/types";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardHeader, EmptyState, Skeleton } from "@/components/ui";
import { cn } from "@/lib/cn";

const DEP_ICONS: Record<string, React.ElementType> = {
  postgres: Database,
  redis: Zap,
  kafka: Server,
};

export default function DashboardPage() {
  const [ready, setReady] = useState<ReadyCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rate, setRate] = useState<RateLimitStatus | null>(null);

  useEffect(() => {
    api
      .ready()
      .then(setReady)
      .catch(() => setError("Could not reach the control-plane API"));
  }, []);

  useEffect(() => {
    const poll = () => api.rateLimitStatus().then(setRate).catch(() => setRate(null));
    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Today's campaigns, execution progress, and platform health."
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Platform status"
            description="Live health of the services this control plane depends on."
          />
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13.5px] text-red-700">
              <XCircle className="h-4 w-4 shrink-0" /> {error}
            </div>
          )}
          {!ready && !error && (
            <div className="space-y-2.5">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          )}
          {ready && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {Object.entries(ready.checks).map(([name, status]) => {
                const ok = status === "ok";
                const Icon = DEP_ICONS[name] ?? Server;
                return (
                  <div
                    key={name}
                    className={cn(
                      "rounded-lg border px-4 py-3.5",
                      ok ? "border-line bg-surface-subtle" : "border-red-200 bg-red-50"
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <Icon className={cn("h-4 w-4", ok ? "text-brand-600" : "text-red-500")} />
                      {ok ? (
                        <CheckCircle2 className="h-4 w-4 text-lime-600" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-500" />
                      )}
                    </div>
                    <p className="mt-2.5 text-[13px] font-medium capitalize text-ink">{name}</p>
                    <p className={cn("text-[12px]", ok ? "text-ink-faint" : "text-red-600")}>
                      {ok ? "Operational" : status}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="Global rate limit" description="SMS + IVR + Doctor, combined. Live, polled every 3s." />
          <div className="flex flex-col items-center py-4 text-center">
            <Gauge className="mb-3 h-8 w-8 text-brand-300" />
            <p className="text-[28px] font-semibold leading-none text-ink">
              {rate ? rate.global_current_tps : "—"}
              <span className="text-[15px] font-normal text-ink-faint"> / {rate?.global_tps_limit ?? 200}</span>
            </p>
            <p className="mt-1 text-[12.5px] text-ink-faint">current / ceiling TPS</p>
          </div>
          {rate && (
            <div className="mt-1 space-y-2 border-t border-line pt-4">
              {rate.channels.map((c) => (
                <div key={c.channel} className="flex items-center gap-3">
                  <span className="w-14 shrink-0 text-[12px] font-medium text-ink-muted">{c.channel}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-sunken">
                    <div
                      className="h-full rounded-full bg-brand-600"
                      style={{ width: `${Math.min(100, (c.current_tps / c.tps_allocation) * 100)}%` }}
                    />
                  </div>
                  <span className="w-16 shrink-0 text-right text-[12px] text-ink-faint">
                    {c.current_tps}/{c.tps_allocation}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader title="Today's campaigns" />
        <EmptyState
          icon={<Megaphone />}
          title="No campaign runs yet"
          description="Once campaigns and scheduling ship, active runs and their progress will appear here."
        />
      </Card>
    </>
  );
}
