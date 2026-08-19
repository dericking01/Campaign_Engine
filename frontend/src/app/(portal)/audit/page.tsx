"use client";

import { useEffect, useState } from "react";
import { History, Lock } from "lucide-react";
import { api, ApiError } from "@/services/api";
import type { AuditLogEntry } from "@/types";
import { PageHeader } from "@/components/PageHeader";
import { Card, EmptyState, Table, TBody, TD, TH, THead, TR } from "@/components/ui";

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLogEntry[] | "forbidden" | null>(null);

  useEffect(() => {
    api
      .auditLogs()
      .then(setLogs)
      .catch((err) => {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          setLogs("forbidden");
        } else {
          setLogs([]);
        }
      });
  }, []);

  return (
    <>
      <PageHeader
        title="Audit Log"
        description="Who did what, when — import approvals, campaign start/pause/stop, configuration changes."
      />
      <Card padded={false}>
        {logs === "forbidden" ? (
          <EmptyState
            icon={<Lock />}
            title="Access restricted"
            description="Sign in with an authorized role to view the audit log."
          />
        ) : !logs ? (
          <div className="p-6 text-[13.5px] text-ink-muted">Loading...</div>
        ) : logs.length === 0 ? (
          <EmptyState icon={<History />} title="No audit events yet" />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>When</TH>
                <TH>Action</TH>
                <TH>Entity</TH>
                <TH>Change</TH>
              </TR>
            </THead>
            <TBody>
              {logs.map((l) => (
                <TR key={l.id}>
                  <TD className="text-ink-muted">{new Date(l.created_at).toLocaleString()}</TD>
                  <TD className="font-medium">{l.action}</TD>
                  <TD>
                    {l.entity_type}
                    {l.entity_id ? ` #${l.entity_id}` : ""}
                  </TD>
                  <TD className="max-w-md">
                    {!l.old_value && !l.new_value ? (
                      <span className="text-ink-faint">—</span>
                    ) : (
                      <span className="font-mono text-[11.5px] leading-relaxed text-ink-muted">
                        {l.old_value && <span className="text-red-600">{JSON.stringify(l.old_value)}</span>}
                        {l.old_value && l.new_value && " → "}
                        {l.new_value && <span className="text-lime-700">{JSON.stringify(l.new_value)}</span>}
                      </span>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}
