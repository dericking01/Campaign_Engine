"use client";

import { useCallback, useEffect, useState } from "react";
import { BarChart3, Gauge, RefreshCw, TrendingUp } from "lucide-react";
import { api, ApiError } from "@/services/api";
import type { AnalyticsRollup, CampaignAnalyticsSummary, CampaignRun, CampaignSummary, ConversionResult } from "@/types";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Input, Select } from "@/components/ui";
import { BarRow, StackedBarChart } from "@/components/charts/StackedBarChart";
import { SINGLE_SERIES_HUE, statusColor } from "@/components/charts/palette";
import { cn } from "@/lib/cn";

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface-subtle px-3.5 py-3">
      <p className={cn("text-[19px] font-semibold leading-none", tone ?? "text-ink")}>{value}</p>
      <p className="mt-1.5 text-[11.5px] leading-tight text-ink-faint">{label}</p>
    </div>
  );
}

function pct(n: number | null | undefined): string {
  return n == null ? "—" : `${(n * 100).toFixed(1)}%`;
}

function breakdownToRows(breakdown: Record<string, Record<string, number>>): { rows: BarRow[]; statuses: string[] } {
  const statusSet = new Set<string>();
  for (const statuses of Object.values(breakdown)) {
    for (const s of Object.keys(statuses)) statusSet.add(s);
  }
  const statuses = Array.from(statusSet);
  const rows: BarRow[] = Object.entries(breakdown).map(([category, statusCounts]) => ({
    category,
    segments: statuses.map((s) => ({ key: s, label: s, value: statusCounts[s] ?? 0, color: statusColor(s) })),
  }));
  return { rows, statuses };
}

export default function ReportsPage() {
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string>("");
  const [campaignSummary, setCampaignSummary] = useState<CampaignAnalyticsSummary | null>(null);

  const [runs, setRuns] = useState<CampaignRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [rollup, setRollup] = useState<AnalyticsRollup | null>(null);
  const [loadingRollup, setLoadingRollup] = useState(false);
  const [rollupError, setRollupError] = useState<string | null>(null);

  const [productCode, setProductCode] = useState("AFYACALL_SUBSCRIBER");
  const [conversion, setConversion] = useState<ConversionResult | null>(null);
  const [conversionError, setConversionError] = useState<string | null>(null);

  useEffect(() => {
    api.campaigns().then(setCampaigns).catch(() => setCampaigns([]));
  }, []);

  useEffect(() => {
    if (!selectedCampaignId) {
      setCampaignSummary(null);
      setRuns([]);
      return;
    }
    api.campaignAnalyticsSummary(Number(selectedCampaignId)).then(setCampaignSummary).catch(() => setCampaignSummary(null));
    api
      .campaignRuns()
      .then((all) =>
        setRuns(
          all
            .filter((r) => r.campaign_id === Number(selectedCampaignId))
            .sort((a, b) => b.run_date.localeCompare(a.run_date))
        )
      )
      .catch(() => setRuns([]));
    setSelectedRunId("");
    setRollup(null);
    setConversion(null);
  }, [selectedCampaignId]);

  const loadRollup = useCallback((runId: number, refresh = false) => {
    setLoadingRollup(true);
    setRollupError(null);
    api
      .runRollup(runId, refresh)
      .then(setRollup)
      .catch((err) => setRollupError(err instanceof ApiError ? err.message : "Could not load analytics"))
      .finally(() => setLoadingRollup(false));
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      setRollup(null);
      return;
    }
    loadRollup(Number(selectedRunId));
    setConversion(null);
  }, [selectedRunId, loadRollup]);

  async function onCheckConversion() {
    if (!selectedRunId) return;
    setConversionError(null);
    try {
      const result = await api.runConversion(Number(selectedRunId), productCode.trim());
      setConversion(result);
    } catch (err) {
      setConversionError(err instanceof ApiError ? err.message : "Could not compute conversion");
    }
  }

  const core = rollup?.core_metrics;
  const zone = core ? breakdownToRows(core.zone_breakdown) : null;
  const channel = core ? breakdownToRows(core.channel_breakdown) : null;
  const byGender = core?.demographic_breakdown ? breakdownToRows(core.demographic_breakdown.by_gender) : null;
  const byArpu = core?.demographic_breakdown ? breakdownToRows(core.demographic_breakdown.by_arpu_segment) : null;

  const daysActiveRows: BarRow[] | null = rollup?.chat_engagement
    ? Object.entries(rollup.chat_engagement.days_active_distribution)
        .sort((a, b) => Number(a[0]) - Number(b[0]))
        .map(([days, users]) => ({
          category: `${days} day${days === "1" ? "" : "s"}`,
          segments: [{ key: "users", label: "users", value: users, color: SINGLE_SERIES_HUE }],
        }))
    : null;

  return (
    <>
      <PageHeader
        title="Reports & Analytics"
        description="Campaign, zone, channel and demographic performance; APU/HGU/engagement primitives; subscription attribution — without sending files to an analyst."
      />

      <Card className="mb-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Select label="Campaign" value={selectedCampaignId} onChange={(e) => setSelectedCampaignId(e.target.value)}>
            <option value="">Select a campaign...</option>
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
          <Select
            label="Run"
            value={selectedRunId}
            onChange={(e) => setSelectedRunId(e.target.value)}
            disabled={!selectedCampaignId || runs.length === 0}
          >
            <option value="">{runs.length === 0 ? "No runs yet" : "Select a run..."}</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.run_date} — {r.status}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      {!selectedCampaignId ? (
        <Card>
          <EmptyState icon={<BarChart3 />} title="Select a campaign to view its analytics" />
        </Card>
      ) : (
        <>
          {campaignSummary && (
            <Card className="mb-5">
              <CardHeader
                title="Campaign summary"
                description={`Aggregated across ${campaignSummary.rolled_up_runs} of ${campaignSummary.total_runs} run(s) with computed analytics.`}
              />
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                <Stat label="Total audience" value={campaignSummary.total_audience.toLocaleString()} />
                <Stat label="Total sent" value={campaignSummary.total_sent.toLocaleString()} tone="text-lime-700" />
                <Stat label="Total dead" value={campaignSummary.total_dead.toLocaleString()} tone="text-red-600" />
                <Stat
                  label="Failed unconfirmed"
                  value={campaignSummary.total_failed_unconfirmed.toLocaleString()}
                  tone="text-amber-600"
                />
                <Stat label="Avg success rate" value={pct(campaignSummary.avg_success_rate)} />
                <Stat label="Avg engagement rate" value={pct(campaignSummary.avg_engagement_rate)} />
              </div>
            </Card>
          )}

          {selectedRunId && (
            <>
              {rollupError && (
                <Alert tone="error" className="mb-5">
                  {rollupError}
                </Alert>
              )}
              {loadingRollup && !rollup ? (
                <Card>
                  <div className="p-2 text-[13.5px] text-ink-muted">Loading...</div>
                </Card>
              ) : (
                core && (
                  <>
                    <Card className="mb-5">
                      <CardHeader
                        title={core.campaign_name}
                        description={`Run ${core.run_date} — computed ${new Date(rollup!.computed_at).toLocaleString()}`}
                        action={
                          <div className="flex items-center gap-2">
                            <Badge>{core.run_status}</Badge>
                            <Button
                              size="sm"
                              variant="outline"
                              icon={<RefreshCw />}
                              onClick={() => loadRollup(Number(selectedRunId), true)}
                            >
                              Refresh
                            </Button>
                          </div>
                        }
                      />
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                        <Stat label="Total audience" value={core.total_audience.toLocaleString()} />
                        <Stat label="Unique customers messaged" value={core.unique_customers_messaged.toLocaleString()} />
                        <Stat label="Success rate" value={pct(core.success_rate)} tone="text-lime-700" />
                        <Stat label="Actual TPS" value={core.actual_tps?.toFixed(2) ?? "—"} />
                        <Stat
                          label="Duration"
                          value={core.duration_seconds != null ? `${Math.round(core.duration_seconds)}s` : "—"}
                        />
                        <Stat
                          label="Sent / Dead / Unconfirmed"
                          value={`${core.status_counts.SENT ?? 0} / ${core.status_counts.DEAD ?? 0} / ${core.status_counts.FAILED_UNCONFIRMED ?? 0}`}
                        />
                      </div>
                    </Card>

                    <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
                      {zone && zone.rows.length > 0 && (
                        <Card>
                          <CardHeader title="Zone performance" />
                          <StackedBarChart
                            rows={zone.rows}
                            legend={zone.statuses.map((s) => ({ key: s, label: s, value: 0, color: statusColor(s) }))}
                          />
                        </Card>
                      )}
                      {channel && channel.rows.length > 0 && (
                        <Card>
                          <CardHeader title="Channel performance" />
                          <StackedBarChart
                            rows={channel.rows}
                            legend={channel.statuses.map((s) => ({ key: s, label: s, value: 0, color: statusColor(s) }))}
                          />
                        </Card>
                      )}
                      {byGender && byGender.rows.length > 0 && (
                        <Card>
                          <CardHeader title="Performance by gender" />
                          <StackedBarChart
                            rows={byGender.rows}
                            legend={byGender.statuses.map((s) => ({ key: s, label: s, value: 0, color: statusColor(s) }))}
                          />
                        </Card>
                      )}
                      {byArpu && byArpu.rows.length > 0 && (
                        <Card>
                          <CardHeader title="Performance by ARPU segment" />
                          <StackedBarChart
                            rows={byArpu.rows}
                            legend={byArpu.statuses.map((s) => ({ key: s, label: s, value: 0, color: statusColor(s) }))}
                          />
                        </Card>
                      )}
                    </div>

                    {rollup!.chat_engagement && (
                      <Card className="mt-5">
                        <CardHeader
                          title="Chatbot engagement"
                          description="APU (Active Promo Users) / HGU (Highly Engaged Users, >5 SMS) / Engagement Rate = HGU / APU — reusable primitives, not one-off report columns."
                        />
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                          <Stat label="APU" value={rollup!.chat_engagement.apu.toLocaleString()} tone="text-brand-700" />
                          <Stat label="HGU" value={rollup!.chat_engagement.hgu.toLocaleString()} tone="text-brand-700" />
                          <Stat label="Engagement rate" value={pct(rollup!.chat_engagement.engagement_rate)} />
                          <Stat
                            label="Avg messages / user"
                            value={rollup!.chat_engagement.avg_messages_per_user?.toFixed(1) ?? "—"}
                          />
                          <Stat
                            label="Avg active days / user"
                            value={rollup!.chat_engagement.avg_active_days_per_user?.toFixed(1) ?? "—"}
                          />
                        </div>
                        {daysActiveRows && daysActiveRows.length > 0 && (
                          <div className="mt-6">
                            <p className="mb-3 text-[12.5px] font-semibold uppercase tracking-wide text-ink-faint">
                              Days active distribution
                            </p>
                            <StackedBarChart rows={daysActiveRows} legend={[]} />
                          </div>
                        )}
                      </Card>
                    )}

                    {rollup!.provider_engagement && (
                      <Card className="mt-5">
                        <CardHeader
                          title="Provider (doctor discovery) engagement"
                          description="Customers who had a provider surfaced or viewed during the run window — the closest real proxy available to “doctor calls”; no telephony call log exists to attribute to."
                        />
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                          <Stat label="Audience" value={rollup!.provider_engagement.audience_size.toLocaleString()} />
                          <Stat label="Engaged" value={rollup!.provider_engagement.engaged_count.toLocaleString()} />
                          <Stat label="Engagement rate" value={pct(rollup!.provider_engagement.engagement_rate)} />
                          <Stat label="Total events" value={rollup!.provider_engagement.total_events.toLocaleString()} />
                        </div>
                      </Card>
                    )}

                    <Card className="mt-5">
                      <CardHeader
                        title="Subscription conversion"
                        description="Parameterized by product code (a campaign isn't tied to one promoted product in this schema) - reports correlation among the audience, not proven causation."
                      />
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                        <div className="flex-1">
                          <Input label="Product code" value={productCode} onChange={(e) => setProductCode(e.target.value)} />
                        </div>
                        <Button icon={<TrendingUp />} onClick={onCheckConversion}>
                          Check Conversion
                        </Button>
                      </div>
                      {conversionError && (
                        <Alert tone="error" className="mt-4">
                          {conversionError}
                        </Alert>
                      )}
                      {conversion && (
                        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
                          <Stat label="Audience" value={conversion.audience_size.toLocaleString()} />
                          <Stat label="Subscribed" value={conversion.subscribed_count.toLocaleString()} tone="text-lime-700" />
                          <Stat label="Conversion rate" value={pct(conversion.conversion_rate)} />
                        </div>
                      )}
                    </Card>
                  </>
                )
              )}
            </>
          )}

          {selectedCampaignId && !selectedRunId && (
            <Card>
              <EmptyState icon={<Gauge />} title="Select a run to see its full analytics" />
            </Card>
          )}
        </>
      )}
    </>
  );
}
