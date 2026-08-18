// Roles are now GUI-configurable (campaign.roles), not a fixed set - see
// the Roles & Permissions page. Kept as a `string` alias (not a union)
// so existing call sites don't need updating just because the set of
// valid values is no longer known at build time.
export type Role = string;

export interface CurrentUser {
  id: number;
  email: string;
  role: Role;
  full_name: string | null;
  permissions: string[];
}

export interface CampaignBaseSummary {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
}

export interface CampaignSummary {
  id: number;
  name: string;
  channels: string[];
  status: string;
  priority: number;
  sender_id: string | null;
  include_staff_notifications: boolean;
}

export interface ZoneAllocationInput {
  zone_code: string;
  allocation_value: number;
}

export interface CreateCampaignPayload {
  name: string;
  description?: string;
  channels: string[];
  base_id: number;
  zone_allocations: ZoneAllocationInput[];
  zone_quota_mode: "PERCENT" | "ABSOLUTE";
  daily_target?: number;
  product_exclusion_codes: string[];
  dnd_list_id?: number;
  cooldown_days: number;
  cooldown_category?: string;
  message_template?: string;
  priority: number;
  sender_id?: string;
  include_staff_notifications: boolean;
}

export interface CampaignRun {
  id: number;
  campaign_id: number;
  run_date: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface AudienceMember {
  customer_msisdn: string;
  zone: string;
  eligible: boolean;
}

export interface AudienceMembersPage {
  items: AudienceMember[];
  total: number;
  limit: number;
  offset: number;
}

export interface DndListSummary {
  id: number;
  name: string;
  is_active: boolean;
}

export interface MessageStatusSummary {
  counts: Record<string, number>;
}

export interface ImportSummary {
  id: number;
  source_type: "UPLOAD" | "SERVER_DROP";
  import_kind: "BASE" | "DND";
  original_filename: string | null;
  status: string;
  total_rows: number | null;
  valid_rows: number | null;
  invalid_rows: number | null;
  duplicate_rows: number | null;
  created_at: string;
}

export interface EligibilityPreview {
  total_candidates: number;
  dnd_excluded: number;
  subscriber_excluded: number;
  cooldown_excluded: number;
  final_eligible: number;
  zone_breakdown: Record<string, number>;
}

export interface ZoneConfig {
  id: number;
  code: string;
  label: string;
  parent_zone_id: number | null;
  is_active: boolean;
}

export interface ChannelConfigItem {
  channel: string;
  sender_id: string;
  tps_allocation: number;
  is_active: boolean;
}

export interface ChannelRate {
  channel: string;
  tps_allocation: number;
  current_tps: number;
}

export interface RateLimitStatus {
  global_tps_limit: number;
  global_current_tps: number;
  channels: ChannelRate[];
}

export interface DropFile {
  filename: string;
  size_bytes: number;
  modified_at: string;
  detected_format: string;
}

export interface ImportPreview {
  id: number;
  import_kind: "BASE" | "DND";
  status: string;
  total_rows: number | null;
  valid_rows: number | null;
  invalid_rows: number | null;
  duplicate_rows: number | null;
  zone_distribution: Record<string, number> | null;
  sample_rows: {
    valid: Record<string, string>[];
    rejected: { row_number: number; raw: Record<string, string>; validation_status: string; rejection_reason: string }[];
  } | null;
}

export interface AuditLogEntry {
  id: number;
  created_at: string;
  actor_id: number | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
}

export interface StaffContact {
  id: number;
  name: string;
  msisdn: string;
  is_active: boolean;
}

export interface UserAccount {
  id: number;
  email: string;
  role: Role;
  full_name: string | null;
  is_active: boolean;
}

export interface RoleDetail {
  code: string;
  label: string;
  description: string | null;
  is_system: boolean;
  actions: string[];
}

export interface ActionCatalogItem {
  value: string;
  label: string;
}

export interface CoreMetrics {
  campaign_id: number;
  campaign_name: string;
  run_status: string;
  run_date: string;
  total_audience: number;
  unique_customers_messaged: number;
  status_counts: Record<string, number>;
  success_rate: number | null;
  duration_seconds: number | null;
  actual_tps: number | null;
  zone_breakdown: Record<string, Record<string, number>>;
  channel_breakdown: Record<string, Record<string, number>>;
  demographic_breakdown: {
    by_gender: Record<string, Record<string, number>>;
    by_arpu_segment: Record<string, Record<string, number>>;
  } | null;
}

export interface ChatEngagement {
  apu: number;
  hgu: number;
  engagement_rate: number | null;
  avg_messages_per_user: number | null;
  avg_active_days_per_user: number | null;
  days_active_distribution: Record<string, number>;
}

export interface ProviderEngagement {
  audience_size: number;
  engaged_count: number;
  engagement_rate: number | null;
  total_events: number;
}

export interface AnalyticsRollup {
  campaign_run_id: number;
  computed_at: string;
  core_metrics: CoreMetrics;
  chat_engagement: ChatEngagement | null;
  provider_engagement: ProviderEngagement | null;
}

export interface ConversionResult {
  audience_size: number;
  subscribed_count: number;
  conversion_rate: number | null;
  product_code: string;
}

export interface CampaignAnalyticsSummary {
  campaign_id: number;
  total_runs: number;
  rolled_up_runs: number;
  total_sent: number;
  total_dead: number;
  total_failed_unconfirmed: number;
  total_audience: number;
  avg_success_rate: number | null;
  avg_engagement_rate: number | null;
}

export interface ReadyCheck {
  // Driven by live backend dependency checks - kept as a plain string
  // rather than a narrow literal union so the UI degrades gracefully if
  // the backend ever reports an additional status value.
  status: string;
  checks: Record<string, string>;
}
