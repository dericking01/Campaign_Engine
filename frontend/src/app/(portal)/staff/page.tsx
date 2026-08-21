"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2, Users, X } from "lucide-react";
import { api, ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import type { StaffContact } from "@/types";
import { PageHeader } from "@/components/PageHeader";
import { Alert, Badge, Button, Card, CardHeader, Checkbox, EmptyState, Input, Table, TBody, TD, TH, THead, TR } from "@/components/ui";

export default function StaffPage() {
  const { can } = useAuth();
  const [staff, setStaff] = useState<StaffContact[] | null>(null);
  const [message, setMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [msisdn, setMsisdn] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editMsisdn, setEditMsisdn] = useState("");
  const [editActive, setEditActive] = useState(true);

  const refresh = useCallback(() => {
    api.staff().then(setStaff).catch(() => setStaff([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setMessage(null);
    if (!name.trim() || !msisdn.trim()) {
      setMessage({ text: "Name and MSISDN are required.", tone: "error" });
      return;
    }
    setSubmitting(true);
    try {
      await api.createStaff(name.trim(), msisdn.trim());
      setName("");
      setMsisdn("");
      setShowForm(false);
      setMessage({ text: "Staff contact added.", tone: "success" });
      refresh();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not add staff contact", tone: "error" });
    } finally {
      setSubmitting(false);
    }
  }

  function startEdit(s: StaffContact) {
    setEditingId(s.id);
    setEditName(s.name);
    setEditMsisdn(s.msisdn);
    setEditActive(s.is_active);
  }

  async function onSaveEdit(id: number) {
    setMessage(null);
    try {
      await api.updateStaff(id, { name: editName.trim(), msisdn: editMsisdn.trim(), is_active: editActive });
      setEditingId(null);
      setMessage({ text: "Staff contact updated.", tone: "success" });
      refresh();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not update staff contact", tone: "error" });
    }
  }

  async function onDelete(id: number, contactName: string) {
    setMessage(null);
    try {
      await api.deleteStaff(id);
      setMessage({ text: `Removed "${contactName}" from the staff list.`, tone: "success" });
      refresh();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not remove staff contact", tone: "error" });
    }
  }

  return (
    <>
      <PageHeader
        title="Staff Directory"
        description="Internal staff MSISDNs. When a campaign has &ldquo;include staff notifications&rdquo; enabled, everyone active here receives every message that campaign sends, for compliance."
        action={
          can("staff:manage") ? (
            <Button icon={showForm ? <X /> : <Plus />} onClick={() => setShowForm((v) => !v)}>
              {showForm ? "Cancel" : "Add Staff Contact"}
            </Button>
          ) : undefined
        }
      />

      {message && (
        <Alert tone={message.tone === "success" ? "success" : "error"} className="mb-5">
          {message.text}
        </Alert>
      )}

      {showForm && (
        <Card className="mb-5 animate-slide-up">
          <CardHeader title="New staff contact" />
          <form onSubmit={onCreate} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Jane Mwakasege" />
            </div>
            <div className="flex-1">
              <Input
                label="MSISDN"
                value={msisdn}
                onChange={(e) => setMsisdn(e.target.value)}
                placeholder="255712345678"
              />
            </div>
            <Button type="submit" loading={submitting} icon={<Plus />}>
              Add
            </Button>
          </form>
        </Card>
      )}

      <Card padded={false}>
        {!can("staff:manage") ? (
          <EmptyState icon={<Users />} title="Restricted" description="Your role cannot manage the staff directory." />
        ) : !staff ? (
          <div className="p-6 text-[13.5px] text-ink-muted">Loading...</div>
        ) : staff.length === 0 ? (
          <EmptyState
            icon={<Users />}
            title="No staff contacts yet"
            description="Add staff MSISDNs here so they can be included on any campaign's dispatch for compliance."
          />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>MSISDN</TH>
                <TH>Status</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {staff.map((s) =>
                editingId === s.id ? (
                  <TR key={s.id} className="bg-brand-50/60">
                    <TD>
                      <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
                    </TD>
                    <TD>
                      <Input value={editMsisdn} onChange={(e) => setEditMsisdn(e.target.value)} />
                    </TD>
                    <TD>
                      <Checkbox
                        label="Active"
                        checked={editActive}
                        onChange={(e) => setEditActive(e.target.checked)}
                      />
                    </TD>
                    <TD>
                      <div className="flex justify-end gap-2">
                        <Button size="sm" onClick={() => onSaveEdit(s.id)}>
                          Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                          Cancel
                        </Button>
                      </div>
                    </TD>
                  </TR>
                ) : (
                  <TR key={s.id}>
                    <TD className="font-medium">{s.name}</TD>
                    <TD className="font-mono text-[13px]">{s.msisdn}</TD>
                    <TD>
                      <Badge tone={s.is_active ? "success" : "neutral"}>{s.is_active ? "Active" : "Inactive"}</Badge>
                    </TD>
                    <TD>
                      <div className="flex justify-end gap-2">
                        {can("staff:manage") && (
                          <>
                            <Button size="sm" variant="ghost" icon={<Pencil />} onClick={() => startEdit(s)}>
                              Edit
                            </Button>
                            <Button
                              size="sm"
                              variant="danger"
                              icon={<Trash2 />}
                              onClick={() => onDelete(s.id, s.name)}
                            >
                              Remove
                            </Button>
                          </>
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
