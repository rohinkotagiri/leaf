import { useQuery } from '@tanstack/react-query';
import { useEmailStore } from '../../stores/useEmailStore';
import { api } from '../../services/api';
import { 
  Inbox, 
  Archive, 
  Trash2, 
  Briefcase, 
  User, 
  DollarSign, 
  Newspaper, 
  ShoppingBag, 
  Plane, 
  ShieldAlert, 
  AlertTriangle, 
  Folder, 
  Clock, 
  Settings, 
  ChevronDown,
  Layers
} from 'lucide-react';

interface CategorySidebarProps {
  onOpenSettings: () => void;
}

export function CategorySidebar({ onOpenSettings }: CategorySidebarProps) {
  const {
    selectedAccountId,
    selectedFolder,
    selectedCategory,
    selectedPriority,
    setSelectedAccountId,
    setSelectedFolder,
    setSelectedCategory,
    setSelectedPriority,
  } = useEmailStore();

  // Fetch registered accounts
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.getAccounts(),
  });

  // Folder Nav Configuration
  const folders = [
    { id: 'INBOX', label: 'Inbox', icon: Inbox },
    { id: 'Archive', label: 'Archive', icon: Archive },
    { id: 'Trash', label: 'Trash', icon: Trash2 },
  ];

  // Category Configuration
  const categories = [
    { id: 'work', label: 'Work', icon: Briefcase, color: 'text-indigo-400 bg-indigo-500/10' },
    { id: 'personal', label: 'Personal', icon: User, color: 'text-emerald-400 bg-emerald-500/10' },
    { id: 'finance', label: 'Finance', icon: DollarSign, color: 'text-amber-400 bg-amber-500/10' },
    { id: 'newsletter', label: 'Newsletters', icon: Newspaper, color: 'text-cyan-400 bg-cyan-500/10' },
    { id: 'shopping', label: 'Shopping', icon: ShoppingBag, color: 'text-pink-400 bg-pink-500/10' },
    { id: 'travel', label: 'Travel', icon: Plane, color: 'text-sky-400 bg-sky-500/10' },
    { id: 'security', label: 'Security', icon: ShieldAlert, color: 'text-rose-400 bg-rose-500/10' },
    { id: 'spam', label: 'Spam', icon: AlertTriangle, color: 'text-yellow-400 bg-yellow-500/10' },
    { id: 'other', label: 'Other', icon: Folder, color: 'text-slate-400 bg-slate-500/10' },
  ];

  // Priority Quick-Filters
  const priorities = [
    { id: 'urgent', label: 'Urgent Priority', icon: Clock, color: 'text-rose-400' },
    { id: 'today', label: 'Due Today', icon: Clock, color: 'text-orange-400' },
    { id: 'week', label: 'Due This Week', icon: Clock, color: 'text-amber-400' },
  ];

  return (
    <div className="w-60 bg-slate-950 border-r border-slate-900 flex flex-col h-full select-none">
      {/* App Brand Title */}
      <div className="p-4 flex items-center gap-2 border-b border-slate-900">
        <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-600/30">
          L
        </div>
        <div>
          <h1 className="font-semibold text-sm tracking-tight text-white">LeafMail AI</h1>
          <p className="text-[10px] text-slate-500 font-medium">Private AI Agent</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {/* Account Selector */}
        <div className="space-y-1">
          <label className="px-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
            Email Accounts
          </label>
          <div className="relative group">
            <select
              value={selectedAccountId}
              onChange={(e) => setSelectedAccountId(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 font-medium appearance-none focus:outline-none focus:border-indigo-600 cursor-pointer pr-8"
            >
              <option value="all">All Accounts ({accounts.length})</option>
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.email_address}
                </option>
              ))}
            </select>
            <ChevronDown className="w-4 h-4 text-slate-500 absolute right-3 top-2.5 pointer-events-none" />
          </div>
        </div>

        {/* Folder Navigation */}
        <div className="space-y-1">
          <label className="px-2 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
            Mailboxes
          </label>
          <div className="space-y-0.5">
            {folders.map((f) => {
              const Icon = f.icon;
              const isActive = selectedFolder === f.id;
              return (
                <button
                  key={f.id}
                  onClick={() => {
                    setSelectedFolder(f.id);
                    setSelectedCategory('all');
                    setSelectedPriority('all');
                  }}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                    isActive
                      ? 'bg-indigo-600/10 text-indigo-400 border-l-2 border-indigo-500'
                      : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{f.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Priority Quick-Filters */}
        <div className="space-y-1">
          <div className="flex items-center justify-between px-2">
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
              Priority Focus
            </label>
            {selectedPriority !== 'all' && (
              <button
                onClick={() => setSelectedPriority('all')}
                className="text-[9px] font-semibold text-indigo-500 hover:text-indigo-400"
              >
                Clear
              </button>
            )}
          </div>
          <div className="space-y-0.5">
            {priorities.map((p) => {
              const Icon = p.icon;
              const isActive = selectedPriority === p.id;
              return (
                <button
                  key={p.id}
                  onClick={() => {
                    setSelectedPriority(isActive ? 'all' : p.id);
                    setSelectedCategory('all');
                  }}
                  className={`w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    isActive
                      ? 'bg-indigo-600/10 text-indigo-400 border-l-2 border-indigo-500'
                      : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${p.color}`} />
                  <span>{p.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Smart Category Folders */}
        <div className="space-y-1">
          <div className="flex items-center justify-between px-2">
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
              AI Smart Categories
            </label>
            {selectedCategory !== 'all' && (
              <button
                onClick={() => setSelectedCategory('all')}
                className="text-[9px] font-semibold text-indigo-500 hover:text-indigo-400"
              >
                Clear
              </button>
            )}
          </div>
          <div className="space-y-0.5 max-h-[220px] overflow-y-auto pr-1 scrollbar-thin">
            <button
              onClick={() => setSelectedCategory('all')}
              className={`w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                selectedCategory === 'all'
                  ? 'bg-indigo-600/10 text-indigo-400 border-l-2 border-indigo-500'
                  : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
              }`}
            >
              <Layers className="w-3.5 h-3.5 text-indigo-400" />
              <span>All Categories</span>
            </button>
            {categories.map((c) => {
              const Icon = c.icon;
              const isActive = selectedCategory === c.id;
              return (
                <button
                  key={c.id}
                  onClick={() => {
                    setSelectedCategory(isActive ? 'all' : c.id);
                    setSelectedPriority('all');
                  }}
                  className={`w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    isActive
                      ? 'bg-indigo-600/10 text-indigo-400 border-l-2 border-indigo-500'
                      : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                  }`}
                >
                  <span className={`p-0.5 rounded-md ${c.color}`}>
                    <Icon className="w-3 h-3" />
                  </span>
                  <span className="capitalize">{c.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Settings Footer */}
      <div className="p-3 border-t border-slate-900 bg-slate-950/60 flex items-center justify-between">
        <button
          onClick={onOpenSettings}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-bold text-slate-400 hover:text-slate-200 hover:bg-slate-900 transition-colors"
        >
          <Settings className="w-4 h-4 animate-hoverSpin" />
          Settings Dashboard
        </button>
      </div>
    </div>
  );
}
