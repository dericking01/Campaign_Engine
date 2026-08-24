"use client";

import { useCallback, useEffect, useState } from "react";
import { MapPin, Pencil, RefreshCw, Zap } from "lucide-react";
import { api, ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import type { ChannelConfigItem, ZoneConfig } from "@/types";
import { PageHeader } from "@/components/PageHeader";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Input,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";

export default function SettingsPage() {
  const { can } = useAuth();
  const [zones, setZones] = useState<ZoneConfig[] | null>(null);
  const [channels, setChannels] = useState<ChannelConfigItem[] | null>(null);
  const [editingChannel, setEditingChannel] = useState<string | null>(null);
  const [editSenderId, setEditSenderId] = useState("");
  const [channelMessage, setChannelMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);
  const [productCode, setProductCode] = useState("AFYACALL_SUBSCRIBER");
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncOk, setSyncOk] = useState(true);

  const refreshChannels = useCallback(() => {
    api.channels().then(setChannels).catch(() => setChannels([]));
  }, []);

  useEffect(() => {
    api.zones().then((data) => setZones(data as ZoneConfig[])).catch(() => setZones([]));
    refreshChannels();
  }, [refreshChannels]);

  function startEditChannel(c: ChannelConfigItem) {
    setEditingChannel(c.channel);
    setEditSenderId(c.sender_id);
    setChannelMessage(null);
  }

  async function onSaveChannelSenderId(channel: string) {
    try {
      await api.updateChannelSenderId(channel, editSenderId.trim());
      setEditingChannel(null);
      setChannelMessage({ text: `Default sender ID for ${channel} updated to "${editSenderId.trim()}".`, tone: "success" });
      refreshChannels();
    } catch (err) {
      setChannelMessage({
        text: err instanceof ApiError ? err.message : "Could not update sender ID",
        tone: "error",
      });
    }
  }

  async function onSync() {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await api.syncSubscriptions(productCode);
      setSyncOk(true);
      setSyncMessage(
        `Synced "${result.product_code}": ${result.upserted.toLocaleString()} upserted, ${result.unsubscribed.toLocaleString()} flagged unsubscribed.`
      );
    } catch (err) {
      setSyncOk(false);
      setSyncMessage(err instanceof ApiError ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  return (
    <>
      <PageHeader title="System Configuration" description="Zones, channel gateway allocation and subscriber sync." />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card padded={false}>
          <div className="p-6 pb-0">
            <CardHeader title="Zones" />
          </div>
          {!zones ? (
            <div className="px-6 pb-6 text-[13.5px] text-ink-muted">Loading...</div>
          ) : zones.length === 0 ? (
            <EmptyState
              icon={<MapPin />}
              title="No zones configured yet"
              description="Seed via the campaign.zone_configs table."
            />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Code</TH>
                  <TH>Label</TH>
                  <TH>Status</TH>
                </TR>
              </THead>
              <TBody>
                {zones.map((z) => (
                  <TR key={z.id}>
                    <TD className="font-medium">{z.code}</TD>
                    <TD className="text-ink-muted">{z.label}</TD>
                    <TD>
                      <Badge tone={z.is_active ? "success" : "neutral"}>
                        {z.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </Card>

        <Card>
          <CardHeader
            title="Subscriber sync"
            description="Set-based sync of customer_subscription_state against the live subscription.subscribers table — never a per-row or in-memory diff."
          />
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Input
                label="Product code"
                value={productCode}
                onChange={(e) => setProductCode(e.target.value)}
              />
            </div>
            <Button onClick={onSync} loading={syncing} icon={<RefreshCw />} disabled={!can("system:configure")}>
              {syncing ? "Syncing" : "Run Sync"}
            </Button>
          </div>
          {syncMessage && (
            <Alert tone={syncOk ? "success" : "error"} className="mt-4">
              {syncMessage}
            </Alert>
          )}
        </Card>

        <Card padded={false}>
          <div className="p-6 pb-0">
            <CardHeader
              title="Channels &amp; sender IDs"
              description="Default sender ID per channel (a campaign can still override this) and its share of the global 200 TPS ceiling."
            />
          </div>
          {channelMessage && (
            <div className="px-6">
              <Alert tone={channelMessage.tone === "success" ? "success" : "error"} className="mb-4">
                {channelMessage.text}
              </Alert>
            </div>
          )}
          {!channels ? (
            <div className="px-6 pb-6 text-[13.5px] text-ink-muted">Loading...</div>
          ) : channels.length === 0 ? (
            <EmptyState icon={<Zap />} title="No channels configured" />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Channel</TH>
                  <TH>Default sender ID</TH>
                  <TH>TPS allocation</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {channels.map((c) => (
                  <TR key={c.channel}>
                    <TD className="font-medium">{c.channel}</TD>
                    <TD>
                      {editingChannel === c.channel ? (
                        <Input value={editSenderId} onChange={(e) => setEditSenderId(e.target.value)} />
                      ) : (
                        <span className="font-mono text-[13px]">{c.sender_id}</span>
                      )}
                    </TD>
                    <TD className="text-ink-muted">{c.tps_allocation} TPS</TD>
                    <TD>
                      {editingChannel === c.channel ? (
                        <div className="flex justify-end gap-2">
                          <Button size="sm" onClick={() => onSaveChannelSenderId(c.channel)}>
                            Save
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingChannel(null)}>
                            Cancel
                          </Button>
                        </div>
                      ) : can("system:configure") ? (
                        <div className="flex justify-end">
                          <Button size="sm" variant="ghost" icon={<Pencil />} onClick={() => startEditChannel(c)}>
                            Edit
                          </Button>
                        </div>
                      ) : null}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </Card>

      </div>
    </>
  );
}
