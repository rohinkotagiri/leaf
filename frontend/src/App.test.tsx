import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App';
import { api } from './services/api';

// Mock the API layer
vi.mock('./services/api', () => ({
  api: {
    getAccounts: vi.fn(() => Promise.resolve([])),
    getSyncStatus: vi.fn(() => Promise.resolve([])),
    getBackfillStatus: vi.fn(() => Promise.resolve({ is_running: false })),
    getEmails: vi.fn(() => Promise.resolve({ emails: [], next_cursor: null, has_more: false })),
    getEmailDetail: vi.fn(() => Promise.resolve(null)),
    getEmailThread: vi.fn(() => Promise.resolve([])),
  },
}));

// Mock useEmailSocket hook
vi.mock('./hooks/useEmailSocket', () => ({
  useEmailSocket: () => ({ isConnected: true, ping: vi.fn() }),
}));

describe('LeafMail AI Client App Integration Tests', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders loading state initially', async () => {
    // Return a hanging promise to stay in loading state
    (api.getAccounts as any).mockReturnValue(new Promise(() => {}));
    
    render(<App />);
    
    expect(screen.getByText(/Starting LeafMail AI Client.../i)).toBeInTheDocument();
  });

  it('renders OnboardingFlow when no accounts exist', async () => {
    // Return no connected accounts
    (api.getAccounts as any).mockResolvedValue([]);
    
    render(<App />);
    
    // Wait for the loader to clear and onboarding to mount
    const header = await screen.findByText(/Select Provider/i);
    expect(header).toBeInTheDocument();
    
    expect(screen.getByText(/Google Gmail/i)).toBeInTheDocument();
    expect(screen.getByText(/Microsoft Outlook/i)).toBeInTheDocument();
    expect(screen.getByText(/Other IMAP Server/i)).toBeInTheDocument();
  });

  it('renders AppLayout three-column view when accounts exist', async () => {
    // Return a connected account
    (api.getAccounts as any).mockResolvedValue([
      {
        id: 'acc_123',
        email_address: 'user@example.com',
        provider: 'generic',
        display_name: 'Main Mailbox',
        sync_enabled: true,
        last_sync_at: null,
      },
    ]);
    
    render(<App />);
    
    // Check that Layout sidebar brand and mailbox labels are rendered
    const brand = await screen.findByText(/^LeafMail AI$/i);
    expect(brand).toBeInTheDocument();
    
    expect(await screen.findByText('Inbox')).toBeInTheDocument();
    expect(await screen.findByText('Archive')).toBeInTheDocument();
    expect(await screen.findByText('Trash')).toBeInTheDocument();
  });
});
