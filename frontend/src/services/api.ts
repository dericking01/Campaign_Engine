// Thin typed client over the FastAPI control-plane API. The backend base URL
// is server-side only (nginx proxies /api/ to backend-api) - no secret or
// backend-only credential is ever embedded in this bundle, per the security
// requirement that no secrets appear in the frontend build output.

import { AUTH_EXPIRED_EVENT } from "@/features/auth/constants";
import { getToken, setToken } from "./tokenStorage";
import type {
  ActionCatalogItem,
  AnalyticsRollup,
  AudienceMembersPage,
  AuditLogEntry,
  CampaignAnalyticsSummary,
  CampaignRun,
  CampaignSummary,
  ChannelConfigItem,
  CreateCampaignPayload,
  CurrentUser,
  DndListSummary,
  DropFile,
  EligibilityPreview,
  ConversionResult,
  ImportPreview,
  ImportSummary,
  MessageStatusSummary,
  RateLimitStatus,
  ReadyCheck,
  RoleDetail,
  StaffContact,
  UserAccount,
  ZoneConfig,
} from "@/types";

const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_PREFIX}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // 401 always means "not authenticated" (app.core.deps.get_current_user
    // is the only source of it) - broadcast so AuthProvider can clear state
    // and redirect from wherever the app currently is, e.g. a token that
    // expired mid-session. 403 (authenticated but not permitted) is a
    // normal error the calling page handles itself, not a session issue.
    if (res.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => apiFetch<{ status: string }>("/health"),
  ready: () => apiFetch<ReadyCheck>("/ready"),
  me: () => apiFetch<CurrentUser>("/auth/me"),
  bases: () => apiFetch("/bases"),
  baseVersions: (baseId: number) => apiFetch(`/bases/${baseId}/versions`),
  campaigns: () => apiFetch<CampaignSummary[]>("/campaigns"),
  imports: () => apiFetch("/imports"),
  zones: () => apiFetch<ZoneConfig[]>("/system/zones"),
  channels: () => apiFetch<ChannelConfigItem[]>("/system/channels"),
  rateLimitStatus: () => apiFetch<RateLimitStatus>("/system/rate-limit-status"),

  updateChannelSenderId: (channel: string, senderId: string) =>
    apiFetch<ChannelConfigItem>(`/system/channels/${channel}/sender-id`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sender_id: senderId }),
    }),

  staff: () => apiFetch<StaffContact[]>("/staff"),

  createStaff: (name: string, msisdn: string) =>
    apiFetch<StaffContact>("/staff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, msisdn }),
    }),

  updateStaff: (id: number, patch: { name?: string; msisdn?: string; is_active?: boolean }) =>
    apiFetch<StaffContact>(`/staff/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  deleteStaff: (id: number) => apiFetch<void>(`/staff/${id}`, { method: "DELETE" }),

  users: () => apiFetch<UserAccount[]>("/users"),

  createUser: (payload: { email: string; password: string; role: string; full_name?: string }) =>
    apiFetch<UserAccount>("/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  updateUser: (
    id: number,
    patch: { role?: string; full_name?: string; is_active?: boolean; password?: string }
  ) =>
    apiFetch<UserAccount>(`/users/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  deleteUser: (id: number) => apiFetch<void>(`/users/${id}`, { method: "DELETE" }),

  roles: () => apiFetch<RoleDetail[]>("/roles"),

  roleActions: () => apiFetch<ActionCatalogItem[]>("/roles/actions"),

  createRole: (payload: { code: string; label: string; description?: string; actions: string[] }) =>
    apiFetch<RoleDetail>("/roles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  updateRole: (code: string, patch: { label?: string; description?: string; actions?: string[] }) =>
    apiFetch<RoleDetail>(`/roles/${code}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }),

  deleteRole: (code: string) => apiFetch<void>(`/roles/${code}`, { method: "DELETE" }),

  runRollup: (runId: number, refresh = false) =>
    apiFetch<AnalyticsRollup>(`/analytics/runs/${runId}${refresh ? "?refresh=true" : ""}`),

  runConversion: (runId: number, productCode: string) =>
    apiFetch<ConversionResult>(`/analytics/runs/${runId}/conversion?product_code=${encodeURIComponent(productCode)}`),

  campaignAnalyticsSummary: (campaignId: number) =>
    apiFetch<CampaignAnalyticsSummary>(`/analytics/campaigns/${campaignId}/summary`),

  createCampaign: (payload: CreateCampaignPayload) =>
    apiFetch<CampaignSummary>("/campaigns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  campaignRuns: () => apiFetch<CampaignRun[]>("/campaign-runs"),

  getCampaignRun: (id: number) => apiFetch<CampaignRun>(`/campaign-runs/${id}`),

  createCampaignRun: (campaignId: number, runDate: string) =>
    apiFetch<CampaignRun>("/campaign-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ campaign_id: campaignId, run_date: runDate }),
    }),

  audienceMembers: (runId: number, limit = 100, offset = 0) =>
    apiFetch<AudienceMembersPage>(`/audience/runs/${runId}/members?limit=${limit}&offset=${offset}`),

  messageStatusSummary: (runId: number) =>
    apiFetch<MessageStatusSummary>(`/messages/runs/${runId}/summary`),

  startRun: (runId: number) => apiFetch<{ detail: string }>(`/campaign-runs/${runId}/start`, { method: "POST" }),
  pauseRun: (runId: number) => apiFetch<{ detail: string }>(`/campaign-runs/${runId}/pause`, { method: "POST" }),
  resumeRun: (runId: number) => apiFetch<{ detail: string }>(`/campaign-runs/${runId}/resume`, { method: "POST" }),
  stopRun: (runId: number) => apiFetch<{ detail: string }>(`/campaign-runs/${runId}/stop`, { method: "POST" }),

  uploadImport: async (file: File, importKind: "BASE" | "DND" = "BASE"): Promise<ImportSummary> => {
    const token = getToken();
    const form = new FormData();
    form.append("file", file);
    form.append("import_kind", importKind);
    const res = await fetch(`${API_PREFIX}/imports/upload`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new ApiError(res.status, body.detail ?? res.statusText);
    }
    return res.json();
  },

  scanDropPath: () => apiFetch<DropFile[]>("/imports/drop-path/scan"),

  createFromDrop: (filename: string, importKind: "BASE" | "DND" = "BASE") =>
    apiFetch<ImportSummary>("/imports/drop-path/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, import_kind: importKind }),
    }),

  previewImport: (id: number) => apiFetch<ImportPreview>(`/imports/${id}/preview`),

  approveImport: (
    id: number,
    body: { base_id?: number; new_base_name?: string; dnd_list_name?: string }
  ) =>
    apiFetch<ImportSummary>(`/imports/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  rejectImport: (id: number) => apiFetch<ImportSummary>(`/imports/${id}/reject`, { method: "POST" }),

  retryStaging: (id: number) =>
    apiFetch<ImportSummary>(`/imports/${id}/retry-staging`, { method: "POST" }),

  dndLists: () => apiFetch<DndListSummary[]>("/dnd/lists"),

  syncSubscriptions: (productCode: string) =>
    apiFetch<{ product_code: string; upserted: number; unsubscribed: number }>(
      "/subscriptions/sync",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_code: productCode }),
      }
    ),

  auditLogs: () => apiFetch<AuditLogEntry[]>("/audit"),

  previewEligibility: (baseVersionId: number, excludedProductCodes: string[]) =>
    apiFetch<EligibilityPreview>("/audience/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_version_id: baseVersionId,
        excluded_product_codes: excludedProductCodes,
      }),
    }),
};

export async function login(email: string, password: string, remember = true): Promise<void> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API_PREFIX}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail ?? "Login failed");
  }
  const data = await res.json();
  setToken(data.access_token, remember);
}
