export type ProviderType = 'gmail' | 'outlook' | 'generic';

export interface Recipient {
  name: string;
  email: string;
}

export interface Account {
  id: string;
  email_address: string;
  provider: ProviderType;
  sync_enabled: boolean;
  last_sync_at: string | null;
  sync_cursor: string | null;
  is_running?: boolean;
  is_idle_active?: boolean;
}

export interface Email {
  id: string;
  account_id: string;
  thread_id: string | null;
  message_id: string;
  subject: string;
  sender_name: string;
  sender_email: string;
  recipients: Recipient[];
  date: string | null;
  body_text?: string;
  body_html?: string;
  folder: string;
  is_read: boolean;
  is_starred: boolean;
  is_important: boolean;
  has_attachments: boolean;
  attachment_names?: string[];
  category?: string | null;
  priority_score?: number | null;
  spam_score?: number | null;
  is_phishing?: boolean;
  analysis?: EmailAnalysis | null;
}

export interface EmailAnalysis {
  id?: string;
  email_id: string;
  category: string;
  priority_score: number;
  spam_score: number;
  is_phishing: boolean;
  summary: string;
  action_items: string[];
  extracted_dates?: string[];
  extracted_entities?: Record<string, any>;
  is_pending: boolean;
}

export interface ParsedQuery {
  keywords: string[];
  date_from: string | null;
  date_to: string | null;
  sender_filter: string | null;
  category_filter: string | null;
  has_attachments: boolean | null;
  is_unread: boolean | null;
}

export interface SearchResult {
  id: string;
  subject: string;
  sender_name: string;
  sender_email: string;
  date: string;
  folder: string;
  is_read: boolean;
  category: string | null;
  priority_score: number | null;
  score: number;
}

export interface SearchResponse {
  results: Email[];
  parsed_query: ParsedQuery;
  latency_ms: number;
}

export interface SearchSuggestions {
  recent_subjects: string[];
  frequent_senders: string[];
  recommended_searches: string[];
}

export interface BackfillStatus {
  is_running: boolean;
  total_emails: number;
  processed_emails: number;
  started_at: string | null;
  completed_at: string | null;
  errors: Record<string, string>;
}

export interface SyncStatusItem {
  account_id: string;
  email_address: string;
  sync_enabled: boolean;
  is_running: boolean;
  is_idle_active: boolean;
  last_sync_at: string | null;
  sync_cursor: string | null;
}

export interface FeedbackMetrics {
  total_corrections: number;
  category_accuracy: number;
  priority_mae: number;
}
