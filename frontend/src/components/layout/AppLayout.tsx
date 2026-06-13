import { useState } from 'react';
import { CategorySidebar } from './CategorySidebar';
import { SearchBar } from '../search/SearchBar';
import { EmailList } from '../email/EmailList';
import { EmailPane } from '../email/EmailPane';
import { SyncStatusBar } from './SyncStatusBar';
import { SettingsPage } from '../settings/SettingsPage';
import { useEmailSocket } from '../../hooks/useEmailSocket';

export function AppLayout() {
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  
  // Establish real-time sync WebSocket connection
  const { isConnected } = useEmailSocket();

  return (
    <div className="h-screen w-screen bg-slate-950 text-slate-100 flex flex-col overflow-hidden font-sans select-none antialiased">
      {/* Main body split into sidebar and central views */}
      <div className="flex-1 flex overflow-hidden w-full">
        {/* Left Column: Sidebar folder navigation */}
        <CategorySidebar onOpenSettings={() => setIsSettingsOpen(true)} />

        {/* Middle & Right columns wrapper */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header Search Bar */}
          <SearchBar />

          {/* List + Reading Pane Split */}
          <div className="flex-1 flex overflow-hidden">
            {/* Center Column: Virtualized Email Cards List */}
            <EmailList />

            {/* Right Column: Full email body details & AI Analysis panel */}
            <EmailPane />
          </div>
        </div>
      </div>

      {/* Bottom Status bar */}
      <SyncStatusBar wsConnected={isConnected} />

      {/* Settings Dashboard Modal */}
      {isSettingsOpen && <SettingsPage onClose={() => setIsSettingsOpen(false)} />}
    </div>
  );
}
