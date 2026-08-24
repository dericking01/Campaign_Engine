"use client";

import { useCallback, useEffect, useState } from "react";
import { KeyRound, Pencil, Plus, ShieldCheck, ShieldOff, Trash2, Users, X } from "lucide-react";
import { api, ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import type { RoleDetail, UserAccount } from "@/types";
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

const PHONE_RE = /^255[0-9]{9}$/;

function formatTimestamp(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function ManageUsersPage() {
  const { user: currentUser, can } = useAuth();
  const [users, setUsers] = useState<UserAccount[] | null>(null);
  const [roles, setRoles] = useState<RoleDetail[]>([]);
  const [message, setMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newFullName, setNewFullName] = useState("");
  const [newRole, setNewRole] = useState("VIEWER");
  const [creating, setCreating] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editRole, setEditRole] = useState("");
  const [editFullName, setEditFullName] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [resettingId, setResettingId] = useState<number | null>(null);

  const refresh = useCallback(() => {
    api.users().then(setUsers).catch(() => setUsers([]));
    api.roles().then(setRoles).catch(() => setRoles([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    if (!newEmail.trim() || !PHONE_RE.test(newPhone.trim())) {
      setMessage({ text: "A valid email and phone (255XXXXXXXXX) are required.", tone: "error" });
      return;
    }
    setCreating(true);
    try {
      await api.createUser({
        email: newEmail.trim(),
        phone: newPhone.trim(),
        role: newRole,
        full_name: newFullName.trim() || undefined,
      });
      setNewEmail("");
      setNewPhone("");
      setNewFullName("");
      setNewRole("VIEWER");
      setShowForm(false);
      setMessage({ text: "User created — their login details were sent by SMS.", tone: "success" });
      refresh();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not create user", tone: "error" });
    } finally {
      setCreating(false);
    }
  }

  function startEdit(u: UserAccount) {
    setEditingId(u.id);
    setEditRole(u.role);
    setEditFullName(u.full_name ?? "");
    setEditPhone(u.phone ?? "");
    setEditActive(u.is_active);
    setMessage(null);
  }

  async function onSave(id: number) {
    if (editPhone && !PHONE_RE.test(editPhone.trim())) {
      setMessage({ text: "Phone must be in 255XXXXXXXXX format.", tone: "error" });
      return;
    }
    try {
      await api.updateUser(id, {
        role: editRole,
        full_name: editFullName.trim(),
        phone: editPhone.trim() || undefined,
        is_active: editActive,
      });
      setEditingId(null);
      setMessage({ text: "User updated.", tone: "success" });
      refresh();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not update user", tone: "error" });
    }
  }

  async function onDelete(id: number, email: string) {
    setMessage(null);
    try {
      await api.deleteUser(id);
      setMessage({ text: `Removed "${email}".`, tone: "success" });
      refresh();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not remove user", tone: "error" });
    }
  }

  async function onResetPassword(u: UserAccount) {
    setMessage(null);
    setResettingId(u.id);
    try {
      await api.resetUserPassword(u.id);
      setMessage({ text: `A new temporary password was sent to ${u.email} by SMS.`, tone: "success" });
      refresh();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not reset password", tone: "error" });
    } finally {
      setResettingId(null);
    }
  }

  if (!can("user:manage")) {
    return (
      <>
        <PageHeader title="Manage Users" description="Create, edit and deactivate portal accounts." />
        <Card>
          <EmptyState icon={<Users />} title="Restricted" description="Your role cannot manage user accounts." />
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Manage Users"
        description="Create, edit and deactivate portal accounts. Assign a role — see Roles &amp; Permissions to define what each role can do."
        action={
          <Button icon={showForm ? <X /> : <Plus />} onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "Add User"}
          </Button>
        }
      />

      {message && (
        <Alert tone={message.tone === "success" ? "success" : "error"} className="mb-5">
          {message.text}
        </Alert>
      )}

      <Card padded={false}>
        {showForm && (
          <form onSubmit={onCreate} className="grid grid-cols-1 gap-3 border-b border-line p-6 sm:grid-cols-2 lg:grid-cols-4">
            <Input label="Email" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
            <Input
              label="Phone number"
              value={newPhone}
              onChange={(e) => setNewPhone(e.target.value)}
              placeholder="255XXXXXXXXX"
              hint="Used for the welcome SMS, login OTP and password resets"
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
              <Button type="submit" loading={creating} icon={<Plus />}>
                Create
              </Button>
            </div>
            <p className="col-span-full text-[13px] text-ink-faint">
              A temporary password is generated automatically and sent by SMS with the portal link — no
              password is set here.
            </p>
          </form>
        )}

        {!users ? (
          <div className="px-6 py-6 text-[13.5px] text-ink-muted">Loading...</div>
        ) : users.length === 0 ? (
          <EmptyState icon={<Users />} title="No users yet" />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH>Email</TH>
                  <TH>Full name</TH>
                  <TH>Phone</TH>
                  <TH>Role</TH>
                  <TH>2FA</TH>
                  <TH>Status</TH>
                  <TH>Last login</TH>
                  <TH>Browser / IP</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {users.map((u) =>
                  editingId === u.id ? (
                    <TR key={u.id} className="bg-brand-50/60">
                      <TD className="text-ink-muted">{u.email}</TD>
                      <TD>
                        <Input value={editFullName} onChange={(e) => setEditFullName(e.target.value)} />
                      </TD>
                      <TD>
                        <Input value={editPhone} onChange={(e) => setEditPhone(e.target.value)} placeholder="255XXXXXXXXX" />
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
                      <TD className="text-ink-faint">—</TD>
                      <TD>
                        <Checkbox
                          label="Active"
                          checked={editActive}
                          disabled={u.id === currentUser?.id}
                          onChange={(e) => setEditActive(e.target.checked)}
                        />
                      </TD>
                      <TD className="text-ink-faint">—</TD>
                      <TD className="text-ink-faint">—</TD>
                      <TD>
                        <div className="flex justify-end gap-2">
                          <Button size="sm" onClick={() => onSave(u.id)}>
                            Save
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
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
                      <TD className="font-mono text-[13px] text-ink-muted">{u.phone ?? "—"}</TD>
                      <TD>
                        <Badge tone="brand">{u.role.replace(/_/g, " ")}</Badge>
                      </TD>
                      <TD>
                        {u.two_factor_enabled ? (
                          <Badge tone="success">
                            <ShieldCheck className="mr-1 inline h-3 w-3" />
                            On
                          </Badge>
                        ) : (
                          <Badge tone="neutral">
                            <ShieldOff className="mr-1 inline h-3 w-3" />
                            Off
                          </Badge>
                        )}
                      </TD>
                      <TD>
                        <Badge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "Active" : "Inactive"}</Badge>
                      </TD>
                      <TD className="whitespace-nowrap text-ink-muted">{formatTimestamp(u.last_login_at)}</TD>
                      <TD className="text-ink-faint">
                        {u.last_login_browser || u.last_login_ip ? (
                          <span>
                            {u.last_login_browser ?? "Unknown"}
                            {u.last_login_ip && <span className="font-mono"> · {u.last_login_ip}</span>}
                          </span>
                        ) : (
                          "—"
                        )}
                      </TD>
                      <TD>
                        <div className="flex justify-end gap-2">
                          <Button
                            size="sm"
                            variant="ghost"
                            icon={<KeyRound />}
                            loading={resettingId === u.id}
                            disabled={!u.phone}
                            title={u.phone ? "Send a new temporary password by SMS" : "No phone on file"}
                            onClick={() => onResetPassword(u)}
                          >
                            Reset
                          </Button>
                          <Button size="sm" variant="ghost" icon={<Pencil />} onClick={() => startEdit(u)}>
                            Edit
                          </Button>
                          {u.id !== currentUser?.id && (
                            <Button size="sm" variant="danger" icon={<Trash2 />} onClick={() => onDelete(u.id, u.email)}>
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
          </div>
        )}
      </Card>
    </>
  );
}
