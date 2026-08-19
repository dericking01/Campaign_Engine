"use client";

import { useEffect, useState } from "react";
import { ShieldOff } from "lucide-react";
import { api } from "@/services/api";
import { PageHeader } from "@/components/PageHeader";
import { Badge, Card, EmptyState, Table, TBody, TD, TH, THead, TR } from "@/components/ui";

interface DndListItem {
  id: number;
  name: string;
  version: number;
  is_active: boolean;
  record_count: number;
}

export default function DndPage() {
  const [lists, setLists] = useState<DndListItem[] | null>(null);

  useEffect(() => {
    api.dndLists().then((data) => setLists(data as DndListItem[])).catch(() => setLists([]));
  }, []);

  return (
    <>
      <PageHeader
        title="DND"
        description={`Do-not-disturb lists, versioned and auditable. "On DND" is the union of all active lists. Import a new DND file from Data Imports (choose kind DND) to add one.`}
      />
      <Card padded={false}>
        {!lists ? (
          <div className="p-6 text-[13.5px] text-ink-muted">Loading...</div>
        ) : lists.length === 0 ? (
          <EmptyState
            icon={<ShieldOff />}
            title="No DND lists yet"
            description={`Import one from Data Imports with import kind "DND".`}
          />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Version</TH>
                <TH>Records</TH>
                <TH>Status</TH>
              </TR>
            </THead>
            <TBody>
              {lists.map((l) => (
                <TR key={l.id}>
                  <TD className="font-medium">{l.name}</TD>
                  <TD className="text-ink-muted">v{l.version}</TD>
                  <TD>{l.record_count.toLocaleString()}</TD>
                  <TD>
                    <Badge tone={l.is_active ? "success" : "neutral"}>
                      {l.is_active ? "Active" : "Inactive"}
                    </Badge>
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
