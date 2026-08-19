"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { Activity, PauseCircle, PlayCircle, Rocket, StopCircle } from "lucide-react";
import { api, ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import type { CampaignRun, CampaignSummary, MessageStatusSummary } from "@/types";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, Card, EmptyState, Table, TBody, TD, TH, THead, TR } from "@/components/ui";

const STARTABLE_STATUSES = ["READY", "SCHEDULED"];
const ACTIVE_STATUSES = ["RUNNING", "PAUSED"];

type RunAction = "start" | "pause" | "resume" | "stop";

export default function ExecutionMonitorPage() {
  const { can } = useAuth();
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [runs, setRuns] = useState<CampaignRun[] | null>(null);
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);
  const [summaries, setSummaries] = useState<Record<number, MessageStatusSummary>>({});
  const [message, setMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);
  const [actingOn, setActingOn] = useState<number | null>(null);

  const campaignName = useCallback(
    (campaignId: number) => campaigns.find((c) => c.id === campaignId)?.name ?? `Campaign #${campaignId}`,
    [campaigns]
  );

  const refreshRuns = useCallback(() => {
    api.campaignRuns().then(setRuns).catch(() => setRuns([]));
  }, []);

  useEffect(() => {
    api.campaigns().then(setCampaigns).catch(() => setCampaigns([]));
    refreshRuns();
  }, [refreshRuns]);

  useEffect(() => {
    // This page's whole purpose is a live view - always poll while it's
    // open rather than trying to guess "is anything active right now"
    // from the last-fetched snapshot. That guess is unreliable right
    // after clicking Start: the endpoint only writes an outbox event and
    // returns immediately, so the very next refresh can still show the
    // pre-start status (e.g. READY) before worker-scheduler catches up -
    // a status-gated poll would see nothing "active" yet and never poll
    // again, leaving the page stuck showing a stale status indefinitely.
    const interval = setInterval(refreshRuns, 3000);
    return () => clearInterval(interval);
  }, [refreshRuns]);

  useEffect(() => {
    if (expandedRunId == null) return;
    const poll = () =>
      api
        .messageStatusSummary(expandedRunId)
        .then((s) => setSummaries((prev) => ({ ...prev, [expandedRunId]: s })));
    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, [expandedRunId]);

  async function act(runId: number, action: RunAction) {
    setActingOn(runId);
    setMessage(null);
    try {
      const fn = { start: api.startRun, pause: api.pauseRun, resume: api.resumeRun, stop: api.stopRun }[action];
      const result = await fn(runId);
      setMessage({ text: result.detail, tone: "success" });
      refreshRuns();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : `Could not ${action} run`, tone: "error" });
    } finally {
      setActingOn(null);
    }
  }

  const sortedRuns = runs
    ? [...runs].sort((a, b) => {
        const rank = (s: string) => (ACTIVE_STATUSES.includes(s) ? 0 : STARTABLE_STATUSES.includes(s) ? 1 : 2);
        const byRank = rank(a.status) - rank(b.status);
        return byRank !== 0 ? byRank : b.run_date.localeCompare(a.run_date);
      })
    : [];

  return (
    <>
      <PageHeader
        title="Execution Monitor"
        description="Live campaign run status and per-status message counts, with start/pause/resume/stop controls."
      />

      {message && (
        <Alert tone={message.tone === "success" ? "success" : "error"} className="mb-5">
          {message.text}
        </Alert>
      )}

      <Card padded={false}>
        {!runs ? (
          <div className="p-6 text-[13.5px] text-ink-muted">Loading...</div>
        ) : runs.length === 0 ? (
          <EmptyState
            icon={<Activity />}
            title="No campaign runs yet"
            description="Trigger a run from the Campaigns page to see it here."
          />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Campaign</TH>
                <TH>Run date</TH>
                <TH>Status</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {sortedRuns.map((r) => (
                <Fragment key={r.id}>
                  <TR className={expandedRunId === r.id ? "bg-brand-50/60" : undefined}>
                    <TD className="font-medium">{campaignName(r.campaign_id)}</TD>
                    <TD className="text-ink-muted">{r.run_date}</TD>
                    <TD>
                      <Badge>{r.status}</Badge>
                    </TD>
                    <TD>
                      <div className="flex justify-end gap-2">
                        {can("campaign:start_stop") && STARTABLE_STATUSES.includes(r.status) && (
                          <Button
                            size="sm"
                            icon={<Rocket />}
                            loading={actingOn === r.id}
                            onClick={() => act(r.id, "start")}
                          >
                            Start
                          </Button>
                        )}
                        {can("campaign:start_stop") && r.status === "RUNNING" && (
                          <Button
                            size="sm"
                            variant="outline"
                            icon={<PauseCircle />}
                            loading={actingOn === r.id}
                            onClick={() => act(r.id, "pause")}
                          >
                            Pause
                          </Button>
                        )}
                        {can("campaign:start_stop") && r.status === "PAUSED" && (
                          <Button
                            size="sm"
                            icon={<PlayCircle />}
                            loading={actingOn === r.id}
                            onClick={() => act(r.id, "resume")}
                          >
                            Resume
                          </Button>
                        )}
                        {can("campaign:start_stop") && ACTIVE_STATUSES.includes(r.status) && (
                          <Button
                            size="sm"
                            variant="danger"
                            icon={<StopCircle />}
                            loading={actingOn === r.id}
                            onClick={() => act(r.id, "stop")}
                          >
                            Stop
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setExpandedRunId(expandedRunId === r.id ? null : r.id)}
                        >
                          {expandedRunId === r.id ? "Hide" : "Details"}
                        </Button>
                      </div>
                    </TD>
                  </TR>
                  {expandedRunId === r.id && (
                    <TR className="hover:bg-transparent">
                      <TD colSpan={4} className="bg-surface-subtle p-4">
                        {!summaries[r.id] ? (
                          <p className="text-[13px] text-ink-muted">Loading message counts...</p>
                        ) : Object.keys(summaries[r.id].counts).length === 0 ? (
                          <p className="text-[13px] text-ink-muted">No messages queued yet for this run.</p>
                        ) : (
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(summaries[r.id].counts).map(([status, count]) => (
                              <div
                                key={status}
                                className="flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2"
                              >
                                <Badge>{status}</Badge>
                                <span className="text-[13px] font-semibold text-ink">
                                  {count.toLocaleString()}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </TD>
                    </TR>
                  )}
                </Fragment>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}
