"use client";

import { Fragment, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Database, Filter, ShieldOff, UserX, Users } from "lucide-react";
import { api, ApiError } from "@/services/api";
import type { CampaignBaseSummary, EligibilityPreview } from "@/types";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Input, Table, TBody, TD, TH, THead, TR } from "@/components/ui";

interface BaseVersionItem {
  id: number;
  base_id: number;
  member_count: number | null;
  is_current: boolean;
  committed_at: string | null;
}

const STAT_CARDS: {
  key: keyof EligibilityPreview;
  label: string;
  icon: React.ElementType;
  tone: string;
}[] = [
  { key: "total_candidates", label: "Total candidates", icon: Users, tone: "text-ink" },
  { key: "dnd_excluded", label: "DND excluded", icon: ShieldOff, tone: "text-amber-600" },
  { key: "subscriber_excluded", label: "Subscriber excluded", icon: UserX, tone: "text-amber-600" },
  { key: "cooldown_excluded", label: "Cooldown excluded", icon: Filter, tone: "text-amber-600" },
  { key: "final_eligible", label: "Final eligible", icon: Users, tone: "text-lime-700" },
];

export default function BasesPage() {
  const [bases, setBases] = useState<CampaignBaseSummary[] | null>(null);
  const [versionsByBase, setVersionsByBase] = useState<Record<number, BaseVersionItem[]>>({});
  const [expanded, setExpanded] = useState<number | null>(null);
  const [previewVersionId, setPreviewVersionId] = useState<number | null>(null);
  const [excludedProducts, setExcludedProducts] = useState("AFYACALL_SUBSCRIBER");
  const [preview, setPreview] = useState<EligibilityPreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api.bases().then((data) => setBases(data as CampaignBaseSummary[])).catch(() => setBases([]));
  }, []);

  async function onExpand(baseId: number) {
    setExpanded(expanded === baseId ? null : baseId);
    if (!versionsByBase[baseId]) {
      const versions = await api.baseVersions(baseId);
      setVersionsByBase((prev) => ({ ...prev, [baseId]: versions as BaseVersionItem[] }));
    }
  }

  async function onPreviewEligibility(versionId: number) {
    setPreviewVersionId(versionId);
    setPreview(null);
    setMessage(null);
    try {
      const codes = excludedProducts
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);
      const result = await api.previewEligibility(versionId, codes);
      setPreview(result);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Eligibility preview failed");
    }
  }

  return (
    <>
      <PageHeader
        title="Bases"
        description="Logical customer base populations and their committed versions. Expand a base to drill into versions and run an eligibility (audience) preview."
      />

      <Card padded={false}>
        {!bases ? (
          <div className="p-6 text-[13.5px] text-ink-muted">Loading...</div>
        ) : bases.length === 0 ? (
          <EmptyState
            icon={<Database />}
            title="No bases yet"
            description="Bases are created by approving a BASE-kind import from Data Imports."
          />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Description</TH>
                <TH>Status</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {bases.map((b) => (
                <Fragment key={b.id}>
                  <TR>
                    <TD className="font-medium">{b.name}</TD>
                    <TD className="text-ink-muted">{b.description ?? "—"}</TD>
                    <TD>
                      <Badge tone={b.is_active ? "success" : "neutral"}>
                        {b.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TD>
                    <TD>
                      <Button variant="ghost" size="sm" onClick={() => onExpand(b.id)}>
                        {expanded === b.id ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                        Versions
                      </Button>
                    </TD>
                  </TR>
                  {expanded === b.id && (
                    <TR className="hover:bg-transparent">
                      <TD colSpan={4} className="bg-surface-subtle p-0">
                        {!versionsByBase[b.id] ? (
                          <div className="p-4 text-[13px] text-ink-muted">Loading versions...</div>
                        ) : (
                          <div className="p-4">
                            <Table>
                              <THead>
                                <TR>
                                  <TH>Version</TH>
                                  <TH>Members</TH>
                                  <TH>Current</TH>
                                  <TH>Committed</TH>
                                  <TH />
                                </TR>
                              </THead>
                              <TBody>
                                {versionsByBase[b.id].map((v) => (
                                  <TR key={v.id}>
                                    <TD>#{v.id}</TD>
                                    <TD className="font-medium">
                                      {v.member_count?.toLocaleString() ?? "—"}
                                    </TD>
                                    <TD>
                                      {v.is_current ? <Badge tone="brand">Current</Badge> : "—"}
                                    </TD>
                                    <TD className="text-ink-muted">
                                      {v.committed_at ? new Date(v.committed_at).toLocaleString() : "—"}
                                    </TD>
                                    <TD>
                                      <Button size="sm" variant="outline" onClick={() => onPreviewEligibility(v.id)}>
                                        Preview Eligibility
                                      </Button>
                                    </TD>
                                  </TR>
                                ))}
                              </TBody>
                            </Table>
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

      {previewVersionId != null && (
        <Card className="mt-5 animate-slide-up">
          <CardHeader
            title={`Eligibility preview — base version #${previewVersionId}`}
            description="Set-based DND / subscriber / cooldown anti-join, computed live."
          />

          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Input
                label="Excluded product codes (comma-separated)"
                value={excludedProducts}
                onChange={(e) => setExcludedProducts(e.target.value)}
              />
            </div>
            <Button variant="outline" onClick={() => onPreviewEligibility(previewVersionId)}>
              Refresh
            </Button>
          </div>

          {message && (
            <Alert tone="error" className="mt-4">
              {message}
            </Alert>
          )}

          {preview && (
            <>
              <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-5">
                {STAT_CARDS.map(({ key, label, icon: Icon, tone }) => (
                  <div key={key} className="rounded-lg border border-line bg-surface-subtle px-3.5 py-3">
                    <Icon className={`mb-2 h-4 w-4 ${tone}`} />
                    <p className={`text-[19px] font-semibold leading-none ${tone}`}>
                      {(preview[key] as number).toLocaleString()}
                    </p>
                    <p className="mt-1.5 text-[11.5px] leading-tight text-ink-faint">{label}</p>
                  </div>
                ))}
              </div>

              {Object.keys(preview.zone_breakdown).length > 0 && (
                <div className="mt-6">
                  <p className="mb-2.5 text-[12.5px] font-semibold uppercase tracking-wide text-ink-faint">
                    Zone breakdown (eligible only)
                  </p>
                  <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                    {Object.entries(preview.zone_breakdown).map(([zone, n]) => (
                      <div
                        key={zone}
                        className="flex items-center justify-between rounded-lg border border-line px-3.5 py-2.5"
                      >
                        <span className="text-[13px] text-ink-muted">{zone}</span>
                        <span className="text-[13px] font-semibold text-ink">{n.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </Card>
      )}
    </>
  );
}
