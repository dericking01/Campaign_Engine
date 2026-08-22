"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Lock, Plus, ShieldCheck, Trash2, X } from "lucide-react";
import { api, ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import type { ActionCatalogItem, RoleDetail } from "@/types";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, Card, CardHeader, Checkbox, EmptyState, Input, Table, TBody, TD, TH, THead, TR } from "@/components/ui";
import { cn } from "@/lib/cn";

export default function RolesPage() {
  const { can } = useAuth();
  const [roles, setRoles] = useState<RoleDetail[] | null>(null);
  const [actions, setActions] = useState<ActionCatalogItem[] | null>(null);
  const [message, setMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);
  const [savingCell, setSavingCell] = useState<string | null>(null);
  const [deletingCode, setDeletingCode] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [newCode, setNewCode] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newActions, setNewActions] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);

  const refresh = useCallback(() => {
    api.roles().then(setRoles).catch(() => setRoles([]));
    api.roleActions().then(setActions).catch(() => setActions([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function toggleCell(role: RoleDetail, action: string) {
    if (role.code === "SUPER_ADMIN") return;
    const key = `${role.code}:${action}`;
    setSavingCell(key);
    setMessage(null);
    const nextActions = role.actions.includes(action)
      ? role.actions.filter((a) => a !== action)
      : [...role.actions, action];
    try {
      await api.updateRole(role.code, { actions: nextActions });
      refresh();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not update permission", tone: "error" });
    } finally {
      setSavingCell(null);
    }
  }

  function toggleNewAction(action: string) {
    setNewActions((prev) => {
      const next = new Set(prev);
      if (next.has(action)) next.delete(action);
      else next.add(action);
      return next;
    });
  }

  async function onCreateRole(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    if (!newCode.trim() || !newLabel.trim()) {
      setMessage({ text: "Code and label are required.", tone: "error" });
      return;
    }
    setCreating(true);
    try {
      await api.createRole({
        code: newCode.trim(),
        label: newLabel.trim(),
        description: newDescription.trim() || undefined,
        actions: Array.from(newActions),
      });
      setNewCode("");
      setNewLabel("");
      setNewDescription("");
      setNewActions(new Set());
      setShowForm(false);
      setMessage({ text: "Role created.", tone: "success" });
      refresh();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not create role", tone: "error" });
    } finally {
      setCreating(false);
    }
  }

  async function onDeleteRole(role: RoleDetail) {
    setMessage(null);
    try {
      await api.deleteRole(role.code);
      setMessage({ text: `Role "${role.label}" deleted.`, tone: "success" });
      setDeletingCode(null);
      refresh();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not delete role", tone: "error" });
    }
  }

  if (!can("user:manage")) {
    return (
      <>
        <PageHeader title="Roles & Permissions" description="Define which actions each role can perform." />
        <Card>
          <EmptyState icon={<Lock />} title="Restricted" description="Your role cannot manage roles & permissions." />
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Roles & Permissions"
        description="Click a cell to grant or revoke a permission. SUPER_ADMIN always has every permission and can't be edited, so there's always a way to fix a mistake."
        action={
          <Button icon={showForm ? <X /> : <Plus />} onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "New Role"}
          </Button>
        }
      />

      {message && (
        <Alert tone={message.tone === "success" ? "success" : "error"} className="mb-5">
          {message.text}
        </Alert>
      )}

      {showForm && actions && (
        <Card className="mb-5 animate-slide-up">
          <CardHeader title="New role" description="Pick a unique code and grant its starting permissions - you can change these anytime." />
          <form onSubmit={onCreateRole} className="space-y-5">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Input
                label="Code"
                value={newCode}
                onChange={(e) => setNewCode(e.target.value)}
                placeholder="e.g. REGIONAL_MANAGER"
                hint="Letters, numbers, underscores"
              />
              <Input label="Label" value={newLabel} onChange={(e) => setNewLabel(e.target.value)} placeholder="e.g. Regional Manager" />
              <Input
                label="Description (optional)"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
              />
            </div>
            <div>
              <p className="mb-2 text-[13px] font-medium text-ink-muted">Permissions</p>
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                {actions.map((a) => (
                  <Checkbox
                    key={a.value}
                    label={a.label}
                    checked={newActions.has(a.value)}
                    onChange={() => toggleNewAction(a.value)}
                  />
                ))}
              </div>
            </div>
            <div className="flex justify-end border-t border-line pt-5">
              <Button type="submit" loading={creating} icon={<Plus />}>
                Create Role
              </Button>
            </div>
          </form>
        </Card>
      )}

      <Card padded={false}>
        {!roles || !actions ? (
          <div className="p-6 text-[13.5px] text-ink-muted">Loading...</div>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Permission</TH>
                {roles.map((r) => (
                  <TH key={r.code} className="text-center">
                    <div className="flex flex-col items-center gap-1">
                      <span className="normal-case text-[13px] font-semibold text-ink">{r.label}</span>
                      <div className="flex items-center gap-1.5">
                        {r.is_system && (
                          <Badge tone="neutral" className="gap-1">
                            <ShieldCheck className="h-3 w-3" /> System
                          </Badge>
                        )}
                        {!r.is_system &&
                          (deletingCode === r.code ? (
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => onDeleteRole(r)}
                                className="text-[11px] font-medium text-red-600 hover:underline"
                              >
                                Confirm
                              </button>
                              <button
                                onClick={() => setDeletingCode(null)}
                                className="text-[11px] text-ink-faint hover:underline"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => setDeletingCode(r.code)}
                              aria-label={`Delete ${r.label}`}
                              className="text-ink-faint hover:text-red-600"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          ))}
                      </div>
                    </div>
                  </TH>
                ))}
              </TR>
            </THead>
            <TBody>
              {actions.map((a) => (
                <TR key={a.value}>
                  <TD className="font-medium">{a.label}</TD>
                  {roles.map((r) => {
                    const granted = r.actions.includes(a.value);
                    const key = `${r.code}:${a.value}`;
                    const locked = r.code === "SUPER_ADMIN";
                    return (
                      <TD key={r.code} className="text-center">
                        <button
                          onClick={() => toggleCell(r, a.value)}
                          disabled={locked || savingCell === key}
                          aria-label={`${granted ? "Revoke" : "Grant"} ${a.label} for ${r.label}`}
                          className={cn(
                            "mx-auto flex h-7 w-7 items-center justify-center rounded-md border transition-colors",
                            granted
                              ? "border-brand-700 bg-brand-800 text-white"
                              : "border-line-strong bg-white text-transparent hover:border-brand-300",
                            locked ? "cursor-not-allowed opacity-70" : "cursor-pointer",
                            savingCell === key && "animate-pulse"
                          )}
                        >
                          <Check className="h-4 w-4" />
                        </button>
                      </TD>
                    );
                  })}
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}
