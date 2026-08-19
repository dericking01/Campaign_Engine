"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  FolderSearch,
  RefreshCcw,
  UploadCloud,
} from "lucide-react";
import { api, ApiError } from "@/services/api";
import { useAuth } from "@/features/auth/AuthProvider";
import type { DropFile, ImportPreview, ImportSummary } from "@/types";
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
import { cn } from "@/lib/cn";

const STAT_LABELS: { key: keyof ImportPreview; label: string; tone: string }[] = [
  { key: "total_rows", label: "Total rows", tone: "text-ink" },
  { key: "valid_rows", label: "Valid", tone: "text-lime-700" },
  { key: "invalid_rows", label: "Invalid", tone: "text-red-600" },
  { key: "duplicate_rows", label: "Duplicates", tone: "text-amber-600" },
];

const RETRIABLE_STATUSES = ["IMPORT_CREATED", "UPLOADED", "VALIDATING", "FAILED"];

export default function ImportsPage() {
  const { can } = useAuth();
  const [imports, setImports] = useState<ImportSummary[] | null>(null);
  const [dropFiles, setDropFiles] = useState<DropFile[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ text: string; tone: "success" | "error" } | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [newBaseName, setNewBaseName] = useState("");
  const [dndListName, setDndListName] = useState("");
  const [uploadKind, setUploadKind] = useState<"BASE" | "DND">("BASE");

  const refreshImports = useCallback(() => {
    api.imports().then((data) => setImports(data as ImportSummary[])).catch(() => setImports([]));
  }, []);

  useEffect(() => {
    refreshImports();
  }, [refreshImports]);

  useEffect(() => {
    if (selectedId == null) {
      setPreview(null);
      return;
    }
    const poll = () => api.previewImport(selectedId).then((p) => setPreview(p as ImportPreview));
    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, [selectedId]);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMessage(null);
    try {
      const result = await api.uploadImport(file, uploadKind);
      setMessage({
        text: `Upload accepted as import #${result.id} (${uploadKind}) — staging in progress.`,
        tone: "success",
      });
      refreshImports();
      setSelectedId(result.id);
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Upload failed", tone: "error" });
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function onScanDropPath() {
    try {
      const files = await api.scanDropPath();
      setDropFiles(files as DropFile[]);
    } catch (err) {
      setMessage({
        text: err instanceof ApiError ? err.message : "Could not scan drop path",
        tone: "error",
      });
    }
  }

  async function onCreateFromDrop(filename: string) {
    try {
      const result = await api.createFromDrop(filename, uploadKind);
      setMessage({
        text: `Import #${result.id} (${uploadKind}) created from ${filename} — staging in progress.`,
        tone: "success",
      });
      refreshImports();
      setSelectedId(result.id);
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Could not create import", tone: "error" });
    }
  }

  async function onApprove() {
    if (selectedId == null || preview == null) return;
    try {
      if (preview.import_kind === "DND") {
        if (!dndListName.trim()) return;
        await api.approveImport(selectedId, { dnd_list_name: dndListName.trim() });
        setMessage({
          text: `Import #${selectedId} approved — committing to DND list "${dndListName}".`,
          tone: "success",
        });
      } else {
        if (!newBaseName.trim()) return;
        await api.approveImport(selectedId, { new_base_name: newBaseName.trim() });
        setMessage({
          text: `Import #${selectedId} approved — committing to base "${newBaseName}".`,
          tone: "success",
        });
      }
      refreshImports();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Approve failed", tone: "error" });
    }
  }

  async function onRetryStaging() {
    if (selectedId == null) return;
    try {
      await api.retryStaging(selectedId);
      setMessage({
        text: `Import #${selectedId} staging retriggered — any partial data from an interrupted attempt is discarded and the file is re-streamed from scratch.`,
        tone: "success",
      });
      refreshImports();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Retry failed", tone: "error" });
    }
  }

  async function onReject() {
    if (selectedId == null) return;
    try {
      await api.rejectImport(selectedId);
      setMessage({ text: `Import #${selectedId} rejected.`, tone: "success" });
      refreshImports();
    } catch (err) {
      setMessage({ text: err instanceof ApiError ? err.message : "Reject failed", tone: "error" });
    }
  }

  return (
    <>
      <PageHeader
        title="Data Imports"
        description="Upload a TXT/CSV base or DND file, or trigger a controlled server-drop import. Nothing commits to production data until you explicitly approve it."
      />

      {message && (
        <Alert tone={message.tone === "success" ? "success" : "error"} className="mb-5">
          {message.text}
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Import kind"
            description="Applies to both upload and server-drop below. DND reuses the exact same staging pipeline — only the commit target differs."
          />
          <div className="inline-flex rounded-lg border border-line-strong bg-surface-subtle p-1">
            {(["BASE", "DND"] as const).map((kind) => (
              <button
                key={kind}
                onClick={() => setUploadKind(kind)}
                className={cn(
                  "rounded-md px-4 py-1.5 text-[13px] font-medium transition-all",
                  uploadKind === kind ? "bg-white text-brand-800 shadow-soft" : "text-ink-muted hover:text-ink"
                )}
              >
                {kind === "BASE" ? "Base" : "DND"}
              </button>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader title="Upload a file" description="CSV or TXT, streamed directly — no size surprises." />
          {can("import:create") ? (
            <label
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
                uploading
                  ? "border-line bg-surface-sunken"
                  : "border-line-strong hover:border-brand-300 hover:bg-brand-50/50"
              )}
            >
              <UploadCloud className={cn("h-7 w-7", uploading ? "text-ink-faint" : "text-brand-500")} />
              <span className="text-[13.5px] font-medium text-ink">
                {uploading ? "Uploading..." : "Click to choose a file"}
              </span>
              <span className="text-[12px] text-ink-faint">.csv or .txt</span>
              <input
                type="file"
                accept=".csv,.txt"
                onChange={onUpload}
                disabled={uploading}
                className="hidden"
              />
            </label>
          ) : (
            <EmptyState icon={<UploadCloud />} title="Restricted" description="Your role cannot create imports." />
          )}
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader
          title="Server drop path"
          description="Files placed in the controlled incoming directory — nothing processes automatically."
          action={
            can("import:create") ? (
              <Button variant="outline" size="sm" icon={<FolderSearch />} onClick={onScanDropPath}>
                Scan Incoming Files
              </Button>
            ) : undefined
          }
        />
        {dropFiles && dropFiles.length === 0 && (
          <EmptyState icon={<FolderSearch />} title="No files found in the drop directory" />
        )}
        {dropFiles && dropFiles.length > 0 && (
          <Table>
            <THead>
              <TR>
                <TH>File</TH>
                <TH>Size</TH>
                <TH>Modified</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {dropFiles.map((f) => (
                <TR key={f.filename}>
                  <TD className="font-medium">{f.filename}</TD>
                  <TD className="text-ink-muted">{(f.size_bytes / (1024 * 1024)).toFixed(1)} MB</TD>
                  <TD className="text-ink-muted">{new Date(f.modified_at).toLocaleString()}</TD>
                  <TD>
                    {can("import:create") && (
                      <Button size="sm" variant="outline" onClick={() => onCreateFromDrop(f.filename)}>
                        Create Import
                      </Button>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>

      <Card className="mt-5" padded={false}>
        <div className="p-6 pb-0">
          <CardHeader title="Import history" />
        </div>
        {!imports ? (
          <div className="px-6 pb-6 text-[13.5px] text-ink-muted">Loading...</div>
        ) : imports.length === 0 ? (
          <EmptyState icon={<FileText />} title="No imports yet" />
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>File</TH>
                <TH>Kind</TH>
                <TH>Source</TH>
                <TH>Status</TH>
                <TH>Rows (valid/invalid/dup)</TH>
                <TH>Created</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {imports.map((i) => (
                <TR key={i.id} className={selectedId === i.id ? "bg-brand-50/60" : undefined}>
                  <TD className="font-medium">{i.original_filename ?? "—"}</TD>
                  <TD>
                    <Badge tone="neutral">{i.import_kind}</Badge>
                  </TD>
                  <TD className="text-ink-muted">{i.source_type}</TD>
                  <TD>
                    <Badge>{i.status}</Badge>
                  </TD>
                  <TD className="text-ink-muted">
                    {i.valid_rows ?? "—"} / {i.invalid_rows ?? "—"} / {i.duplicate_rows ?? "—"}
                  </TD>
                  <TD className="text-ink-muted">{new Date(i.created_at).toLocaleString()}</TD>
                  <TD>
                    <Button size="sm" variant="ghost" onClick={() => setSelectedId(i.id)}>
                      View
                    </Button>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>

      {selectedId != null && preview && (
        <Card className="mt-5 animate-slide-up">
          <CardHeader
            title={`Import #${selectedId}`}
            action={<Badge>{preview.status}</Badge>}
          />

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {STAT_LABELS.map(({ key, label, tone }) => (
              <div key={key} className="rounded-lg border border-line bg-surface-subtle px-3.5 py-3">
                <p className={cn("text-[19px] font-semibold leading-none", tone)}>
                  {(preview[key] as number | null)?.toLocaleString() ?? "—"}
                </p>
                <p className="mt-1.5 text-[11.5px] text-ink-faint">{label}</p>
              </div>
            ))}
          </div>

          {preview.zone_distribution && (
            <div className="mt-6">
              <p className="mb-2.5 text-[12.5px] font-semibold uppercase tracking-wide text-ink-faint">
                Zone distribution
              </p>
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                {Object.entries(preview.zone_distribution).map(([zone, n]) => (
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

          {preview.sample_rows && (
            <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
              <div>
                <p className="mb-2.5 flex items-center gap-1.5 text-[12.5px] font-semibold uppercase tracking-wide text-ink-faint">
                  <CheckCircle2 className="h-3.5 w-3.5 text-lime-600" /> Sample valid rows
                </p>
                <div className="scrollbar-thin max-h-56 overflow-y-auto rounded-lg border border-line bg-surface-subtle p-3 font-mono text-[11.5px] leading-relaxed text-ink-muted">
                  {preview.sample_rows.valid.slice(0, 10).map((r, idx) => (
                    <div key={idx} className="truncate">
                      {JSON.stringify(r)}
                    </div>
                  ))}
                </div>
              </div>

              {preview.sample_rows.rejected.length > 0 && (
                <div>
                  <p className="mb-2.5 flex items-center gap-1.5 text-[12.5px] font-semibold uppercase tracking-wide text-ink-faint">
                    <AlertTriangle className="h-3.5 w-3.5 text-amber-500" /> Sample rejected rows
                  </p>
                  <div className="scrollbar-thin max-h-56 overflow-y-auto rounded-lg border border-line bg-surface-subtle p-3 text-[12px] leading-relaxed text-ink-muted">
                    {preview.sample_rows.rejected.slice(0, 10).map((r) => (
                      <div key={r.row_number} className="truncate">
                        row {r.row_number}: <span className="text-ink">{r.validation_status}</span>{" "}
                        ({r.rejection_reason})
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {can("import:create") && RETRIABLE_STATUSES.includes(preview.status) && (
            <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
              <p className="text-[13px] text-amber-900">
                {preview.status === "VALIDATING"
                  ? "Still staging — if this seems stuck (e.g. the worker was interrupted), retry re-streams the file from scratch; any partial data is discarded first."
                  : "Staging hasn't started or didn't complete."}
              </p>
              <Button size="sm" variant="outline" icon={<RefreshCcw />} className="mt-3" onClick={onRetryStaging}>
                Retry Staging
              </Button>
            </div>
          )}

          {can("import:approve") && preview.status === "PREVIEW_READY" && preview.import_kind === "DND" && (
            <div className="mt-6 border-t border-line pt-6">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                <div className="flex-1">
                  <Input
                    label="Approve into DND list (name)"
                    value={dndListName}
                    onChange={(e) => setDndListName(e.target.value)}
                    placeholder="e.g. National DND"
                  />
                </div>
                <div className="flex gap-2">
                  <Button onClick={onApprove}>Approve &amp; Commit</Button>
                  <Button variant="danger" onClick={onReject}>
                    Reject
                  </Button>
                </div>
              </div>
            </div>
          )}

          {can("import:approve") && preview.status === "PREVIEW_READY" && preview.import_kind === "BASE" && (
            <div className="mt-6 border-t border-line pt-6">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                <div className="flex-1">
                  <Input
                    label="Approve into base (name)"
                    value={newBaseName}
                    onChange={(e) => setNewBaseName(e.target.value)}
                    placeholder="e.g. National Base 2026-08"
                  />
                </div>
                <div className="flex gap-2">
                  <Button onClick={onApprove}>Approve &amp; Commit</Button>
                  <Button variant="danger" onClick={onReject}>
                    Reject
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
