"use client";

import { useCallback, useEffect, useState } from "react";
import { MapPin, Pencil, Plus, RefreshCw, Trash2, Users, X, Zap } from "lucide-react";
import { api, ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import type { ChannelConfigItem, RoleDetail, UserAccount, ZoneConfig } from "@/types";
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

export default function SettingsPage() {
  const { user: currentUser, can } = useAuth();
  const [zones, setZones] = useState<ZoneConfig[] | null>(null);
  const [roles, setRoles] = useState<RoleDetail[]>([]);
  const [channels, setChannels] = useState<ChannelConfigItem[] | null>(null);
  const [editingChannel, setEditingChannel] = useState<string | null>(null);
  const [editSenderId, setEditSenderId] = useState("");
  const [channelMessage, setChannelMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);
  const [productCode, setProductCode] = useState("AFYACALL_SUBSCRIBER");
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncOk, setSyncOk] = useState(true);

  const [users, setUsers] = useState<UserAccount[] | null>(null);
  const [showUserForm, setShowUserForm] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<string>("VIEWER");
  const [newFullName, setNewFullName] = useState("");
  const [userMessage, setUserMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);
  const [creatingUser, setCreatingUser] = useState(false);
  const [editingUserId, setEditingUserId] = useState<number | null>(null);
  const [editRole, setEditRole] = useState("");
  const [editFullName, setEditFullName] = useState("");
  const [editActive, setEditActive] = useState(true);

  const refreshChannels = useCallback(() => {
    api.channels().then(setChannels).catch(() => setChannels([]));
  }, []);

  const refreshUsers = useCallback(() => {
    if (!can("user:manage")) return;
    api.users().then(setUsers).catch(() => setUsers([]));
    api.roles().then(setRoles).catch(() => setRoles([]));
  }, [can]);

  useEffect(() => {
    api.zones().then((data) => setZones(data as ZoneConfig[])).catch(() => setZones([]));
    refreshChannels();
    refreshUsers();
  }, [refreshChannels, refreshUsers]);

  async function onCreateUser(e: React.FormEvent) {
    e.preventDefault();
    setUserMessage(null);
    if (!newEmail.trim() || newPassword.length < 8) {
      setUserMessage({ text: "Email is required and password must be at least 8 characters.", tone: "error" });
      return;
    }
    setCreatingUser(true);
    try {
      await api.createUser({
        email: newEmail.trim(),
        password: newPassword,
        role: newRole,
        full_name: newFullName.trim() || undefined,
      });
      setNewEmail("");
      setNewPassword("");
      setNewFullName("");
      setNewRole("VIEWER");
      setShowUserForm(false);
      setUserMessage({ text: "User created.", tone: "success" });
      refreshUsers();
    } catch (err) {
      setUserMessage({ text: err instanceof ApiError ? err.message : "Could not create user", tone: "error" });
    } finally {
      setCreatingUser(false);
    }
  }

  function startEditUser(u: UserAccount) {
    setEditingUserId(u.id);
    setEditRole(u.role);
    setEditFullName(u.full_name ?? "");
    setEditActive(u.is_active);
    setUserMessage(null);
  }

  async function onSaveUser(id: number) {
    try {
      await api.updateUser(id, { role: editRole, full_name: editFullName.trim(), is_active: editActive });
      setEditingUserId(null);
      setUserMessage({ text: "User updated.", tone: "success" });
      refreshUsers();
    } catch (err) {
      setUserMessage({ text: err instanceof ApiError ? err.message : "Could not update user", tone: "error" });
    }
  }

  async function onDeleteUser(id: number, email: string) {
    setUserMessage(null);
    try {
      await api.deleteUser(id);
      setUserMessage({ text: `Removed "${email}".`, tone: "success" });
      refreshUsers();
    } catch (err) {
      setUserMessage({ text: err instanceof ApiError ? err.message : "Could not remove user", tone: "error" });
    }
  }

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
      <PageHeader title="System Configuration" description="Zones, channel gateway allocation, users and roles." />

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

      <Card padded={false} className="mt-5">
        <div className="flex items-start justify-between p-6 pb-0">
          <CardHeader
            title="Users & roles"
            description="Assign a role to each user - see the Roles &amp; Permissions page to define what each role can do. Enforced by the API on every request; this panel is ergonomics only."
          />
          {can("user:manage") && (
            <Button icon={showUserForm ? <X /> : <Plus />} onClick={() => setShowUserForm((v) => !v)}>
              {showUserForm ? "Cancel" : "Add User"}
            </Button>
          )}
        </div>

        {userMessage && (
          <div className="px-6">
            <Alert tone={userMessage.tone === "success" ? "success" : "error"} className="mb-4">
              {userMessage.text}
            </Alert>
          </div>
        )}

        {showUserForm && (
          <form onSubmit={onCreateUser} className="mb-2 grid grid-cols-1 gap-3 px-6 pb-6 sm:grid-cols-2 lg:grid-cols-4">
            <Input label="Email" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
            <Input
              label="Password"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              hint="At least 8 characters"
            />
            <Input label="Full name (optional)" value={newFullName} onChange={(e) => setNewFullName(e.target.value)} />
            <div className="flex items-end gap-2">
              <div className="flex-1">
                <Select label="Role" value={newRole} onChange={(e) => setNewRole(e.target.value)}>
                  {roles.map((r) => (
                    <option key={r.code} value={r.code}>
                      {r.label}
                    </option>
                  ))}
                </Select>
              </div>
              <Button type="submit" loading={creatingUser} icon={<Plus />}>
                Create
              </Button>
            </div>
          </form>
        )}

        {!can("user:manage") ? (
          <EmptyState icon={<Users />} title="Restricted" description="Your role cannot manage user accounts." />
        ) : !users ? (
          <div className="px-6 pb-6 text-[13.5px] text-ink-muted">Loading...</div>
        ) : users.length === 0 ? (
          <EmptyState icon={<Users />} title="No users yet" />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Email</TH>
                <TH>Full name</TH>
                <TH>Role</TH>
                <TH>Status</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {users.map((u) =>
                editingUserId === u.id ? (
                  <TR key={u.id} className="bg-brand-50/60">
                    <TD className="text-ink-muted">{u.email}</TD>
                    <TD>
                      <Input value={editFullName} onChange={(e) => setEditFullName(e.target.value)} />
                    </TD>
                    <TD>
                      <Select value={editRole} onChange={(e) => setEditRole(e.target.value)} disabled={u.id === currentUser?.id}>
                        {roles.map((r) => (
                          <option key={r.code} value={r.code}>
                            {r.label}
                          </option>
                        ))}
                      </Select>
                    </TD>
                    <TD>
                      <Checkbox
                        label="Active"
                        checked={editActive}
                        disabled={u.id === currentUser?.id}
                        onChange={(e) => setEditActive(e.target.checked)}
                      />
                    </TD>
                    <TD>
                      <div className="flex justify-end gap-2">
                        <Button size="sm" onClick={() => onSaveUser(u.id)}>
                          Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditingUserId(null)}>
                          Cancel
                        </Button>
                      </div>
                    </TD>
                  </TR>
                ) : (
                  <TR key={u.id}>
                    <TD className="font-medium">
                      {u.email}
                      {u.id === currentUser?.id && <span className="ml-2 text-[11.5px] text-ink-faint">(you)</span>}
                    </TD>
                    <TD className="text-ink-muted">{u.full_name ?? "—"}</TD>
                    <TD>
                      <Badge tone="brand">{u.role.replace(/_/g, " ")}</Badge>
                    </TD>
                    <TD>
                      <Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "Active" : "Inactive"}</Badge>
                    </TD>
                    <TD>
                      <div className="flex justify-end gap-2">
                        <Button size="sm" variant="ghost" icon={<Pencil />} onClick={() => startEditUser(u)}>
                          Edit
                        </Button>
                        {u.id !== currentUser?.id && (
                          <Button
                            size="sm"
                            variant="danger"
                            icon={<Trash2 />}
                            onClick={() => onDeleteUser(u.id, u.email)}
                          >
                            Remove
                          </Button>
                        )}
                      </div>
                    </TD>
                  </TR>
                )
              )}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}
