"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Megaphone, Plus, Rocket, Users, X } from "lucide-react";
import { api, ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import type {
  AudienceMembersPage,
  CampaignBaseSummary,
  CampaignRun,
  CampaignSummary,
  ChannelConfigItem,
  DndListSummary,
  ZoneConfig,
} from "@/types";
import { PageHeader } from "@/components/PageHeader";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  Checkbox,
  EmptyState,
  Input,
  Select,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";

const CHANNELS = ["SMS", "IVR", "DOCTOR"] as const;
const RUN_ACTIVE_STATUSES = ["PENDING", "AUDIENCE_GENERATING"];
const today = () => new Date().toISOString().slice(0, 10);

export default function CampaignsPage() {
  const { can } = useAuth();
  const [campaigns, setCampaigns] = useState<CampaignSummary[] | null>(null);
  const [bases, setBases] = useState<CampaignBaseSummary[]>([]);
  const [zones, setZones] = useState<ZoneConfig[]>([]);
  const [dndLists, setDndLists] = useState<DndListSummary[]>([]);
  const [channelConfigs, setChannelConfigs] = useState<ChannelConfigItem[]>([]);

  const [showForm, setShowForm] = useState(false);
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [channels, setChannels] = useState<Set<string>>(new Set(["SMS"]));
  const [baseId, setBaseId] = useState("");
  const [zoneQuotaMode, setZoneQuotaMode] = useState<"PERCENT" | "ABSOLUTE">("PERCENT");
  const [dailyTarget, setDailyTarget] = useState("");
  const [zoneAllocations, setZoneAllocations] = useState<Record<string, string>>({});
  const [productExclusionCodes, setProductExclusionCodes] = useState("");
  const [dndListId, setDndListId] = useState("");
  const [cooldownDays, setCooldownDays] = useState("7");
  const [cooldownCategory, setCooldownCategory] = useState("");
  const [messageTemplate, setMessageTemplate] = useState("");
  const [priority, setPriority] = useState("100");
  const [senderId, setSenderId] = useState("");
  const [includeStaffNotifications, setIncludeStaffNotifications] = useState(false);

  const [selectedCampaign, setSelectedCampaign] = useState<CampaignSummary | null>(null);
  const [runs, setRuns] = useState<CampaignRun[] | null>(null);
  const [runDate, setRunDate] = useState(today());
  const [runMessage, setRunMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);
  const [membersRunId, setMembersRunId] = useState<number | null>(null);
  const [membersPage, setMembersPage] = useState<AudienceMembersPage | null>(null);
  const [membersOffset, setMembersOffset] = useState(0);

  const refreshCampaigns = useCallback(() => {
    api.campaigns().then(setCampaigns).catch(() => setCampaigns([]));
  }, []);

  useEffect(() => {
    refreshCampaigns();
    api.bases().then((data) => setBases(data as CampaignBaseSummary[])).catch(() => setBases([]));
    api.zones().then(setZones).catch(() => setZones([]));
    api.dndLists().then(setDndLists).catch(() => setDndLists([]));
    api.channels().then(setChannelConfigs).catch(() => setChannelConfigs([]));
  }, [refreshCampaigns]);

  const refreshRuns = useCallback((campaignId: number) => {
    api
      .campaignRuns()
      .then((all) => setRuns(all.filter((r) => r.campaign_id === campaignId).sort((a, b) => b.run_date.localeCompare(a.run_date))))
      .catch(() => setRuns([]));
  }, []);

  useEffect(() => {
    if (selectedCampaign) refreshRuns(selectedCampaign.id);
  }, [selectedCampaign, refreshRuns]);

  useEffect(() => {
    if (!selectedCampaign || !runs) return;
    if (!runs.some((r) => RUN_ACTIVE_STATUSES.includes(r.status))) return;
    const interval = setInterval(() => refreshRuns(selectedCampaign.id), 3000);
    return () => clearInterval(interval);
  }, [selectedCampaign, runs, refreshRuns]);

  useEffect(() => {
    if (membersRunId == null) {
      setMembersPage(null);
      return;
    }
    api
      .audienceMembers(membersRunId, 100, membersOffset)
      .then(setMembersPage)
      .catch(() => setMembersPage(null));
  }, [membersRunId, membersOffset]);

  const totalAllocation = useMemo(
    () => Object.values(zoneAllocations).reduce((sum, v) => sum + (parseFloat(v) || 0), 0),
    [zoneAllocations]
  );

  const senderIdHint = useMemo(() => {
    const defaults = Array.from(channels)
      .map((ch) => channelConfigs.find((c) => c.channel === ch)?.sender_id)
      .filter((v): v is string => !!v);
    const distinct = Array.from(new Set(defaults));
    if (distinct.length === 0) return "Leave blank to use each channel's default sender ID.";
    if (distinct.length === 1) return `Leave blank to use the default for ${Array.from(channels).join("/")}: "${distinct[0]}".`;
    return `Selected channels have different defaults (${channelConfigs
      .filter((c) => channels.has(c.channel))
      .map((c) => `${c.channel}="${c.sender_id}"`)
      .join(", ")}) - leave blank to use each channel's own default, or set one value to override all of them.`;
  }, [channels, channelConfigs]);

  function toggleChannel(channel: string) {
    setChannels((prev) => {
      const next = new Set(prev);
      if (next.has(channel)) next.delete(channel);
      else next.add(channel);
      return next;
    });
  }

  function resetForm() {
    setName("");
    setDescription("");
    setChannels(new Set(["SMS"]));
    setBaseId("");
    setZoneQuotaMode("PERCENT");
    setDailyTarget("");
    setZoneAllocations({});
    setProductExclusionCodes("");
    setDndListId("");
    setCooldownDays("7");
    setCooldownCategory("");
    setMessageTemplate("");
    setPriority("100");
    setSenderId("");
    setIncludeStaffNotifications(false);
    setFormMessage(null);
  }

  async function onCreateCampaign(e: React.FormEvent) {
    e.preventDefault();
    setFormMessage(null);

    const allocations = Object.entries(zoneAllocations)
      .filter(([, v]) => v.trim() !== "" && parseFloat(v) > 0)
      .map(([zone_code, v]) => ({ zone_code, allocation_value: parseFloat(v) }));

    if (!name.trim()) return setFormMessage("Name is required.");
    if (channels.size === 0) return setFormMessage("Select at least one channel.");
    if (!baseId) return setFormMessage("Select a base.");
    if (allocations.length === 0) return setFormMessage("Set at least one zone allocation.");
    if (zoneQuotaMode === "PERCENT" && (!dailyTarget || Number(dailyTarget) <= 0)) {
      return setFormMessage("Daily target is required for percentage-mode allocation.");
    }

    setSubmitting(true);
    try {
      const created = await api.createCampaign({
        name: name.trim(),
        description: description.trim() || undefined,
        channels: Array.from(channels),
        base_id: Number(baseId),
        zone_allocations: allocations,
        zone_quota_mode: zoneQuotaMode,
        daily_target: dailyTarget ? Number(dailyTarget) : undefined,
        product_exclusion_codes: productExclusionCodes
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean),
        dnd_list_id: dndListId ? Number(dndListId) : undefined,
        cooldown_days: Number(cooldownDays) || 7,
        cooldown_category: cooldownCategory.trim() || undefined,
        message_template: messageTemplate.trim() || undefined,
        priority: Number(priority) || 100,
        sender_id: senderId.trim() || undefined,
        include_staff_notifications: includeStaffNotifications,
      });
      resetForm();
      setShowForm(false);
      refreshCampaigns();
      setSelectedCampaign(created);
    } catch (err) {
      setFormMessage(err instanceof ApiError ? err.message : "Could not create campaign");
    } finally {
      setSubmitting(false);
    }
  }

  async function onTriggerRun() {
    if (!selectedCampaign) return;
    setRunMessage(null);
    try {
      await api.createCampaignRun(selectedCampaign.id, runDate);
      setRunMessage({ text: `Audience generation triggered for ${runDate}.`, tone: "success" });
      refreshRuns(selectedCampaign.id);
    } catch (err) {
      setRunMessage({ text: err instanceof ApiError ? err.message : "Could not trigger run", tone: "error" });
    }
  }

  function onSelectCampaign(c: CampaignSummary) {
    setSelectedCampaign(selectedCampaign?.id === c.id ? null : c);
    setMembersRunId(null);
    setRunMessage(null);
  }

  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Create, configure, and preview campaign audiences before scheduling."
        action={
          can("campaign:create") ? (
            <Button icon={showForm ? <X /> : <Plus />} onClick={() => setShowForm((v) => !v)}>
              {showForm ? "Cancel" : "New Campaign"}
            </Button>
          ) : undefined
        }
      />

      {showForm && (
        <Card className="mb-5 animate-slide-up">
          <CardHeader
            title="New campaign"
            description="Configure the base, exclusions, and per-zone quotas. Audience generation runs separately once you trigger a run."
          />
          <form onSubmit={onCreateCampaign} className="space-y-5">
            {formMessage && <Alert tone="error">{formMessage}</Alert>}

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. August ARPU Re-engagement" />
              <Input
                label="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>

            <div>
              <p className="mb-1.5 text-[13px] font-medium text-ink-muted">Channels</p>
              <div className="flex gap-5">
                {CHANNELS.map((c) => (
                  <Checkbox key={c} label={c} checked={channels.has(c)} onChange={() => toggleChannel(c)} />
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Select label="Base" value={baseId} onChange={(e) => setBaseId(e.target.value)}>
                <option value="">Select a base...</option>
                {bases.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
              <Select
                label="DND list (optional)"
                value={dndListId}
                onChange={(e) => setDndListId(e.target.value)}
              >
                <option value="">None</option>
                {dndLists.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </Select>
            </div>

            <div>
              <p className="mb-1.5 text-[13px] font-medium text-ink-muted">Zone quota mode</p>
              <div className="inline-flex rounded-lg border border-line-strong bg-surface-subtle p-1">
                {(["PERCENT", "ABSOLUTE"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setZoneQuotaMode(mode)}
                    className={
                      zoneQuotaMode === mode
                        ? "rounded-md bg-white px-4 py-1.5 text-[13px] font-medium text-brand-800 shadow-soft"
                        : "rounded-md px-4 py-1.5 text-[13px] font-medium text-ink-muted hover:text-ink"
                    }
                  >
                    {mode === "PERCENT" ? "Percent of daily target" : "Absolute per-zone count"}
                  </button>
                ))}
              </div>
            </div>

            {zoneQuotaMode === "PERCENT" && (
              <Input
                label="Daily target (total customers per run, across all zones)"
                type="number"
                min={1}
                value={dailyTarget}
                onChange={(e) => setDailyTarget(e.target.value)}
                placeholder="e.g. 2000000"
              />
            )}

            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <p className="text-[13px] font-medium text-ink-muted">
                  Zone allocations {zoneQuotaMode === "PERCENT" ? "(%)" : "(row count)"}
                </p>
                {zoneQuotaMode === "PERCENT" && (
                  <span className={totalAllocation > 100 ? "text-[12px] text-red-600" : "text-[12px] text-ink-faint"}>
                    {totalAllocation}% allocated
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {zones.map((z) => (
                  <Input
                    key={z.code}
                    label={z.label}
                    type="number"
                    min={0}
                    value={zoneAllocations[z.code] ?? ""}
                    onChange={(e) => setZoneAllocations((prev) => ({ ...prev, [z.code]: e.target.value }))}
                    placeholder="0"
                  />
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Input
                label="Excluded product codes (comma-separated)"
                value={productExclusionCodes}
                onChange={(e) => setProductExclusionCodes(e.target.value)}
                placeholder="AFYACALL_SUBSCRIBER"
              />
              <Input
                label="Cooldown days"
                type="number"
                min={0}
                value={cooldownDays}
                onChange={(e) => setCooldownDays(e.target.value)}
              />
              <Input
                label="Cooldown category (optional)"
                value={cooldownCategory}
                onChange={(e) => setCooldownCategory(e.target.value)}
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Input
                label="Message template (optional)"
                value={messageTemplate}
                onChange={(e) => setMessageTemplate(e.target.value)}
                className="sm:col-span-2"
              />
              <Input label="Priority" type="number" value={priority} onChange={(e) => setPriority(e.target.value)} />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Input
                label="Sender ID (optional override)"
                value={senderId}
                onChange={(e) => setSenderId(e.target.value)}
                placeholder='e.g. AFYACALL or 15723'
                hint={senderIdHint}
              />
              <div className="flex items-end pb-3">
                <Checkbox
                  label="Include staff notifications (send every message to the Staff Directory too, for compliance)"
                  checked={includeStaffNotifications}
                  onChange={(e) => setIncludeStaffNotifications(e.target.checked)}
                />
              </div>
            </div>

            <div className="flex justify-end border-t border-line pt-5">
              <Button type="submit" loading={submitting} icon={<Plus />}>
                Create Campaign
              </Button>
            </div>
          </form>
        </Card>
      )}

      <Card padded={false}>
        {!campaigns ? (
          <div className="p-6 text-[13.5px] text-ink-muted">Loading...</div>
        ) : campaigns.length === 0 ? (
          <EmptyState
            icon={<Megaphone />}
            title="No campaigns yet"
            description="Create a campaign to configure its base, exclusions, and zone quotas."
          />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Channels</TH>
                <TH>Status</TH>
                <TH>Priority</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {campaigns.map((c) => (
                <TR key={c.id} className={selectedCampaign?.id === c.id ? "bg-brand-50/60" : undefined}>
                  <TD className="font-medium">{c.name}</TD>
                  <TD className="text-ink-muted">{c.channels.join(", ")}</TD>
                  <TD>
                    <Badge>{c.status}</Badge>
                  </TD>
                  <TD>{c.priority}</TD>
                  <TD>
                    <Button size="sm" variant="ghost" onClick={() => onSelectCampaign(c)}>
                      {selectedCampaign?.id === c.id ? "Hide" : "View"}
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>

      {selectedCampaign && (
        <Card className="mt-5 animate-slide-up">
          <CardHeader
            title={selectedCampaign.name}
            description="Trigger audience generation for a run date, then inspect the resulting members once ready."
            action={<Badge>{selectedCampaign.status}</Badge>}
          />

          <div className="mb-5 flex flex-wrap gap-2">
            <Badge tone="neutral">Sender ID: {selectedCampaign.sender_id || "channel default"}</Badge>
            {selectedCampaign.include_staff_notifications && (
              <Badge tone="brand">Staff notifications included</Badge>
            )}
          </div>

          <div className="flex flex-col gap-3 border-b border-line pb-5 sm:flex-row sm:items-end">
            <div className="w-full sm:w-56">
              <Input label="Run date" type="date" value={runDate} onChange={(e) => setRunDate(e.target.value)} />
            </div>
            <Button icon={<Rocket />} onClick={onTriggerRun} disabled={!can("campaign:configure")}>
              Generate Audience
            </Button>
          </div>

          {runMessage && (
            <Alert tone={runMessage.tone === "success" ? "success" : "error"} className="mt-4">
              {runMessage.text}
            </Alert>
          )}

          <div className="mt-5">
            {!runs ? (
              <p className="text-[13.5px] text-ink-muted">Loading runs...</p>
            ) : runs.length === 0 ? (
              <EmptyState icon={<Rocket />} title="No runs yet for this campaign" />
            ) : (
              <Table>
                <THead>
                  <TR>
                    <TH>Run date</TH>
                    <TH>Status</TH>
                    <TH />
                  </TR>
                </THead>
                <TBody>
                  {runs.map((r) => (
                    <TR key={r.id}>
                      <TD className="font-medium">{r.run_date}</TD>
                      <TD>
                        <Badge>{r.status}</Badge>
                      </TD>
                      <TD>
                        {r.status === "READY" && (
                          <Button
                            size="sm"
                            variant="outline"
                            icon={<Users />}
                            onClick={() => {
                              setMembersRunId(membersRunId === r.id ? null : r.id);
                              setMembersOffset(0);
                            }}
                          >
                            {membersRunId === r.id ? "Hide Members" : "View Members"}
                          </Button>
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </div>

          {membersRunId != null && membersPage && (
            <div className="mt-6 border-t border-line pt-6">
              <p className="mb-3 text-[12.5px] font-semibold uppercase tracking-wide text-ink-faint">
                Audience members — {membersPage.total.toLocaleString()} total
              </p>
              <Table>
                <THead>
                  <TR>
                    <TH>MSISDN</TH>
                    <TH>Zone</TH>
                  </TR>
                </THead>
                <TBody>
                  {membersPage.items.map((m) => (
                    <TR key={m.customer_msisdn}>
                      <TD className="font-mono text-[13px]">{m.customer_msisdn}</TD>
                      <TD className="text-ink-muted">{m.zone}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <div className="mt-4 flex items-center justify-between">
                <span className="text-[12.5px] text-ink-faint">
                  Showing {membersPage.offset + 1}–{membersPage.offset + membersPage.items.length} of{" "}
                  {membersPage.total.toLocaleString()}
                </span>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={membersOffset === 0}
                    onClick={() => setMembersOffset((o) => Math.max(0, o - 100))}
                  >
                    Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={membersPage.offset + membersPage.items.length >= membersPage.total}
                    onClick={() => setMembersOffset((o) => o + 100)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </div>
          )}
        </Card>
      )}
    </>
  );
}
