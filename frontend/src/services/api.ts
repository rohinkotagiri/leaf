import axios from 'axios';
import type {
  Account,
  Email,
  SearchResponse,
  SearchSuggestions,
  BackfillStatus,
  SyncStatusItem,
  FeedbackMetrics,
  ProviderType,
} from '../types';

const API_BASE_URL = 'http://localhost:8000';

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const api = {
  // Health
  getHealth: async () => {
    const res = await client.get('/api/health');
    return res.data;
  },

  // Accounts
  getAccounts: async (): Promise<Account[]> => {
    const res = await client.get('/api/accounts');
    return res.data;
  },

  addAccount: async (payload: {
    email_address: string;
    provider: ProviderType;
    imap_server?: string;
    imap_port?: number;
    smtp_server?: string;
    smtp_port?: number;
    use_ssl?: boolean;
    credentials_json?: string;
    password?: string;
  }): Promise<Account> => {
    const res = await client.post('/api/accounts', payload);
    return res.data;
  },

  deleteAccount: async (id: string): Promise<void> => {
    await client.delete(`/api/accounts/${id}`);
  },

  testAccount: async (id: string): Promise<{ success: boolean; message: string }> => {
    const res = await client.post(`/api/accounts/${id}/test`);
    return res.data;
  },

  // Emails
  getEmails: async (params: {
    account_id?: string;
    folder?: string;
    category?: string;
    is_read?: boolean;
    priority_min?: number;
    date_from?: string;
    date_to?: string;
    after?: string;
    limit?: number;
  }): Promise<{ emails: Email[]; next_cursor: string | null; has_more: boolean }> => {
    const res = await client.get('/api/emails', { params });
    return res.data;
  },

  getEmailDetail: async (id: string): Promise<Email> => {
    const res = await client.get(`/api/emails/${id}`);
    return res.data;
  },

  updateEmail: async (
    id: string,
    updates: { is_read?: boolean; is_starred?: boolean; is_important?: boolean; labels?: string[] }
  ): Promise<Email> => {
    const res = await client.patch(`/api/emails/${id}`, updates);
    return res.data;
  },

  triggerEmailAction: async (
    id: string,
    action: 'archive' | 'delete' | 'mark_important'
  ): Promise<{ message: string }> => {
    const res = await client.post(`/api/emails/${id}/action`, { action });
    return res.data;
  },

  getEmailThread: async (id: string): Promise<Email[]> => {
    const res = await client.get(`/api/emails/${id}/thread`);
    return res.data;
  },

  getEmailSummary: async (id: string): Promise<{ summary?: string; detail?: string; status?: number }> => {
    try {
      const res = await client.get(`/api/emails/${id}/summary`);
      return { summary: res.data.summary, status: res.status };
    } catch (err: any) {
      if (err.response && err.response.status === 202) {
        return { detail: err.response.data.detail, status: 202 };
      }
      throw err;
    }
  },

  // Search
  searchEmails: async (
    query: string,
    filters: { account_id?: string; folder?: string; limit?: number } = {}
  ): Promise<SearchResponse> => {
    const res = await client.post('/api/search', { query, filters });
    return res.data;
  },

  getSearchSuggestions: async (query: string): Promise<SearchSuggestions> => {
    const res = await client.get('/api/search/suggestions', { params: { query } });
    return res.data;
  },

  // Feedback
  submitFeedback: async (payload: {
    email_id: string;
    category_correction?: string;
    priority_correction?: number;
    spam_correction?: boolean;
    feedback_notes?: string;
  }): Promise<{ message: string; metrics: FeedbackMetrics }> => {
    const res = await client.post('/api/feedback', payload);
    return res.data;
  },

  getFeedbackMetrics: async (): Promise<FeedbackMetrics> => {
    const res = await client.get('/api/feedback/metrics');
    return res.data;
  },

  // Sync
  getSyncStatus: async (): Promise<SyncStatusItem[]> => {
    const res = await client.get('/api/sync/status');
    return res.data;
  },

  triggerSync: async (accountId: string): Promise<{ message: string }> => {
    const res = await client.post(`/api/sync/${accountId}`);
    return res.data;
  },

  startBackfill: async (): Promise<{ message: string }> => {
    const res = await client.post('/api/sync/backfill');
    return res.data;
  },

  getBackfillStatus: async (): Promise<BackfillStatus> => {
    const res = await client.get('/api/sync/backfill-status');
    return res.data;
  },
};
