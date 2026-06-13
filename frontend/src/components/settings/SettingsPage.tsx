import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';
import { useEmailStore } from '../../stores/useEmailStore';
import { Trash2, AlertTriangle, X, Database } from 'lucide-react';

interface SettingsPageProps {
  onClose: () => void;
}

export function SettingsPage({ onClose }: SettingsPageProps) {
  const { settings, updateSettings } = useEmailStore();
  const queryClient = useQueryClient();

  // Fetch accounts list
  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.getAccounts(),
  });

  // Mutations
  const deleteAccountMutation = useMutation({
    mutationFn: (id: string) => api.deleteAccount(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      queryClient.invalidateQueries({ queryKey: ['emails'] });
    },
  });

  // Wipes all data by deleting all registered accounts sequentially
  const wipeAllDataMutation = useMutation({
    mutationFn: async () => {
      await Promise.all(accounts.map((acc) => api.deleteAccount(acc.id)));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] });
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      window.location.reload(); // reload app to enter onboarding flow cleanly
    },
  });

  const handleDeleteAccount = (id: string) => {
    if (confirm('Are you absolutely sure you want to remove this account? All associated emails, summaries, and vector embeddings will be permanently deleted.')) {
      deleteAccountMutation.mutate(id);
    }
  };

  const handleWipeAll = () => {
    if (confirm('WARNING: This will permanently delete all registered email accounts, downloaded message indices, and AI models caching. This action CANNOT be undone. Proceed?')) {
      wipeAllDataMutation.mutate();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm" onClick={onClose} />

      {/* Main card */}
      <div className="relative w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] text-slate-100 font-sans select-none">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60 backdrop-blur-md shrink-0">
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-indigo-400" />
            <h2 className="font-bold text-sm text-white uppercase tracking-wider">
              Settings & Account Dashboard
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-slate-500 hover:text-slate-350 hover:bg-slate-800 rounded-lg transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Scrollable contents */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin">
          {/* Section 1: Account Management */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest pb-1 border-b border-slate-850">
              Connected Accounts
            </h3>
            {isLoading ? (
              <p className="text-xs text-slate-500 font-semibold">Loading accounts list...</p>
            ) : accounts.length === 0 ? (
              <p className="text-xs text-slate-500 italic">No email accounts connected.</p>
            ) : (
              <div className="space-y-2">
                {accounts.map((acc) => (
                  <div
                    key={acc.id}
                    className="p-3 bg-slate-950 border border-slate-850 rounded-lg flex items-center justify-between"
                  >
                    <div>
                      <h4 className="text-xs font-bold text-slate-200">{acc.email_address}</h4>
                      <p className="text-[10px] text-slate-500 mt-0.5">{acc.provider}</p>
                      <span className="inline-block mt-1.5 px-1.5 py-0.5 rounded text-[8px] font-bold bg-indigo-950 text-indigo-400 border border-indigo-900 capitalize">
                        {acc.provider}
                      </span>
                    </div>

                    <button
                      onClick={() => handleDeleteAccount(acc.id)}
                      disabled={deleteAccountMutation.isPending}
                      className="p-2 text-slate-500 hover:text-red-400 bg-slate-900 hover:bg-red-950/10 border border-slate-800 hover:border-red-900 rounded-lg transition-all"
                      title="Remove Account"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section 2: AI Settings */}
          <div className="space-y-4">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest pb-1 border-b border-slate-850">
              AI Processing Settings
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Local LLM Selector */}
              <div className="space-y-1.5">
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  Preferred AI Model
                </label>
                <div className="relative">
                  <select
                    value={settings.preferredModel}
                    onChange={(e) => updateSettings({ preferredModel: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 font-semibold appearance-none focus:outline-none focus:border-indigo-600 cursor-pointer pr-8"
                  >
                    <option value="mistral:7b">Mistral 7B (Default - Recommended)</option>
                    <option value="llama3.2:3b">Llama 3.2 3B (Fast - Lightweight)</option>
                  </select>
                  <X className="w-4 h-4 text-slate-500 absolute right-3 top-2.5 pointer-events-none hidden" />
                </div>
                <p className="text-[9px] text-slate-500 font-semibold leading-relaxed">
                  Controls the model running classification, query parsing, and email synthesis via Ollama.
                </p>
              </div>

              {/* Sync Interval */}
              <div className="space-y-1.5">
                <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  Sync Frequency
                </label>
                <div className="relative">
                  <select
                    value={settings.syncIntervalMinutes}
                    onChange={(e) => updateSettings({ syncIntervalMinutes: parseInt(e.target.value) })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 font-semibold appearance-none focus:outline-none focus:border-indigo-600 cursor-pointer pr-8"
                  >
                    <option value={5}>Every 5 minutes</option>
                    <option value={15}>Every 15 minutes</option>
                    <option value={30}>Every 30 minutes</option>
                    <option value={60}>Every hour</option>
                  </select>
                </div>
                <p className="text-[9px] text-slate-500 font-semibold leading-relaxed">
                  Scheduled backdrop polling frequency. Note that IMAP IDLE connections push new arrivals instantly.
                </p>
              </div>
            </div>
          </div>

          {/* Section 3: Visual Settings */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest pb-1 border-b border-slate-850">
              Aesthetics & Theme
            </h3>
            <div className="flex items-center justify-between p-3 bg-slate-950 border border-slate-850 rounded-lg">
              <div>
                <h4 className="text-xs font-bold text-slate-200">Force Dark Mode</h4>
                <p className="text-[10px] text-slate-500 mt-0.5">Maintain premium dark glass theme</p>
              </div>
              <button
                onClick={() => updateSettings({ darkMode: !settings.darkMode })}
                className={`w-10 h-6 rounded-full p-1 transition-all ${
                  settings.darkMode ? 'bg-indigo-600 flex justify-end' : 'bg-slate-800 flex justify-start'
                }`}
              >
                <span className="w-4 h-4 rounded-full bg-white shadow-md" />
              </button>
            </div>
          </div>

          {/* Section 4: System Actions (Dangerous) */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold text-rose-500 uppercase tracking-widest pb-1 border-b border-rose-950/40">
              Dangerous Settings Wipes
            </h3>
            <div className="p-4 bg-rose-950/10 border border-rose-900/30 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-1">
                <h4 className="text-xs font-bold text-rose-400 flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  Wipe Database & Reset
                </h4>
                <p className="text-[9px] text-slate-400 font-semibold max-w-sm leading-relaxed">
                  This permanently removes all mailboxes, stored authentication tokens, vector indexes, and AI feedback tables.
                </p>
              </div>
              <button
                onClick={handleWipeAll}
                disabled={wipeAllDataMutation.isPending}
                className="px-3 py-2 bg-red-950/20 hover:bg-red-900 border border-red-900 text-red-400 hover:text-white font-bold rounded-lg text-xs transition-colors shrink-0 flex justify-center gap-1.5"
              >
                Clear Database
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
