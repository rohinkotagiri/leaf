import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';
import { useEmailStore } from '../../stores/useEmailStore';
import { RefreshCw, CheckCircle, Database } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface SyncStatusBarProps {
  wsConnected: boolean;
}

export function SyncStatusBar({ wsConnected }: SyncStatusBarProps) {
  const { selectedAccountId } = useEmailStore();
  const queryClient = useQueryClient();

  // Query sync statuses of all accounts
  const { data: syncStatuses = [] } = useQuery({
    queryKey: ['sync-status'],
    queryFn: () => api.getSyncStatus(),
    refetchInterval: 15000, // Refresh status every 15s
  });

  // Query backfill progress
  const { data: backfillStatus } = useQuery({
    queryKey: ['backfill-status'],
    queryFn: () => api.getBackfillStatus(),
    refetchInterval: (data: any) => (data?.is_running ? 3000 : 30000), // Poll faster when running
  });

  // Mutation to trigger sync
  const syncMutation = useMutation({
    mutationFn: (id: string) => api.triggerSync(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sync-status'] });
      queryClient.invalidateQueries({ queryKey: ['emails'] });
    },
  });

  const selectedAccountStatus = syncStatuses.find((s) => s.account_id === selectedAccountId);
  
  // Determine displayed last sync time
  let lastSyncText = 'Never synced';
  if (selectedAccountId === 'all') {
    const dates = syncStatuses
      .map((s) => (s.last_sync_at ? new Date(s.last_sync_at) : null))
      .filter((d): d is Date => d !== null);
    if (dates.length > 0) {
      const mostRecent = new Date(Math.max(...dates.map((d) => d.getTime())));
      lastSyncText = `Last synced ${formatDistanceToNow(mostRecent, { addSuffix: true })}`;
    }
  } else if (selectedAccountStatus?.last_sync_at) {
    lastSyncText = `Last synced ${formatDistanceToNow(new Date(selectedAccountStatus.last_sync_at), {
      addSuffix: true,
    })}`;
  }

  const handleSyncClick = () => {
    if (selectedAccountId !== 'all') {
      syncMutation.mutate(selectedAccountId);
    } else {
      // Sync all accounts
      syncStatuses.forEach((acc) => {
        syncMutation.mutate(acc.account_id);
      });
    }
  };

  const isSyncingAny = syncStatuses.some((s) => s.is_running);

  return (
    <div className="h-9 bg-slate-950 border-t border-slate-900 flex items-center justify-between px-4 text-[10px] text-slate-500 font-medium select-none select-none">
      {/* Left section: WebSocket connection + last sync */}
      <div className="flex items-center gap-4">
        {/* WebSocket Connection indicator */}
        <div className="flex items-center gap-1.5">
          <span className="relative flex h-2 w-2">
            {wsConnected && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            )}
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                wsConnected ? 'bg-emerald-500' : 'bg-rose-500'
              }`}
            ></span>
          </span>
          <span className="text-slate-400 capitalize">
            {wsConnected ? 'Agent Online' : 'Agent Reconnecting'}
          </span>
        </div>

        <div className="h-3 w-[1px] bg-slate-900" />

        {/* Sync state description */}
        <div className="flex items-center gap-1.5">
          {isSyncingAny ? (
            <RefreshCw className="w-3 h-3 text-indigo-400 animate-spin" />
          ) : (
            <CheckCircle className="w-3 h-3 text-emerald-500" />
          )}
          <span>{isSyncingAny ? 'Syncing mailboxes...' : lastSyncText}</span>
        </div>
      </div>

      {/* Center section: Backfill progress bar if active */}
      {backfillStatus?.is_running && (
        <div className="flex items-center gap-3 bg-slate-900/50 border border-slate-900 px-3 py-1 rounded-md max-w-sm">
          <Database className="w-3 h-3 text-indigo-400" />
          <span className="text-slate-400 font-semibold text-[9px]">
            AI Backfill Indexing: {backfillStatus.processed_emails} / {backfillStatus.total_emails}
          </span>
          <div className="w-20 bg-slate-950 h-1.5 rounded-full overflow-hidden border border-slate-800/60">
            <div
              className="bg-indigo-500 h-full rounded-full transition-all duration-300"
              style={{
                width: `${
                  backfillStatus.total_emails
                    ? Math.min(
                        (backfillStatus.processed_emails / backfillStatus.total_emails) * 100,
                        100
                      )
                    : 0
                }%`,
              }}
            />
          </div>
        </div>
      )}

      {/* Right section: Manual Sync trigger */}
      <div>
        <button
          onClick={handleSyncClick}
          disabled={isSyncingAny || syncMutation.isPending}
          className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-900 border border-slate-850 hover:bg-slate-800 hover:text-slate-200 active:scale-95 disabled:opacity-50 disabled:scale-100 transition-all text-slate-400 font-bold"
        >
          <RefreshCw
            className={`w-3 h-3 ${isSyncingAny || syncMutation.isPending ? 'animate-spin' : ''}`}
          />
          Sync Now
        </button>
      </div>
    </div>
  );
}
