import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ParsedQuery, Email } from '../types';

export interface AppSettings {
  preferredModel: string;
  syncIntervalMinutes: number;
  darkMode: boolean;
}

interface EmailState {
  // Navigation & Filtering
  selectedAccountId: string; // 'all' or specific account id
  selectedFolder: string; // 'INBOX', 'Archive', 'Trash'
  selectedCategory: string; // 'all' or specific category
  selectedPriority: string; // 'all', 'urgent', 'today', 'week'
  
  // Selection
  selectedEmailId: string | null;
  selectedEmailIds: string[]; // for multi-select

  // Search
  searchQuery: string;
  searchResults: Email[] | null;
  parsedQuery: ParsedQuery | null;
  searchHistory: string[];
  isCommandPaletteOpen: boolean;

  // Settings
  settings: AppSettings;

  // Actions
  setSelectedAccountId: (id: string) => void;
  setSelectedFolder: (folder: string) => void;
  setSelectedCategory: (category: string) => void;
  setSelectedPriority: (priority: string) => void;
  setSelectedEmailId: (id: string | null) => void;
  setSelectedEmailIds: (ids: string[] | ((prev: string[]) => string[])) => void;
  setSearchQuery: (query: string) => void;
  setSearchResults: (results: Email[] | null) => void;
  setParsedQuery: (parsed: ParsedQuery | null) => void;
  addSearchHistory: (query: string) => void;
  clearSearchHistory: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  updateSettings: (updates: Partial<AppSettings>) => void;
  resetSearch: () => void;
}

export const useEmailStore = create<EmailState>()(
  persist(
    (set) => ({
      // Navigation & Filtering
      selectedAccountId: 'all',
      selectedFolder: 'INBOX',
      selectedCategory: 'all',
      selectedPriority: 'all',

      // Selection
      selectedEmailId: null,
      selectedEmailIds: [],

      // Search
      searchQuery: '',
      searchResults: null,
      parsedQuery: null,
      searchHistory: [],
      isCommandPaletteOpen: false,

      // Settings
      settings: {
        preferredModel: 'mistral:7b',
        syncIntervalMinutes: 15,
        darkMode: true,
      },

      // Actions
      setSelectedAccountId: (id) =>
        set({ selectedAccountId: id, selectedEmailId: null, selectedEmailIds: [] }),
      
      setSelectedFolder: (folder) =>
        set({ selectedFolder: folder, selectedEmailId: null, selectedEmailIds: [] }),

      setSelectedCategory: (category) =>
        set({ selectedCategory: category, selectedEmailId: null, selectedEmailIds: [] }),

      setSelectedPriority: (priority) =>
        set({ selectedPriority: priority, selectedEmailId: null, selectedEmailIds: [] }),

      setSelectedEmailId: (id) => set({ selectedEmailId: id }),

      setSelectedEmailIds: (ids) =>
        set((state) => ({
          selectedEmailIds: typeof ids === 'function' ? ids(state.selectedEmailIds) : ids,
        })),

      setSearchQuery: (query) => set({ searchQuery: query }),

      setSearchResults: (results) => set({ searchResults: results }),

      setParsedQuery: (parsed) => set({ parsedQuery: parsed }),

      addSearchHistory: (query) =>
        set((state) => {
          if (!query.trim()) return state;
          const filtered = state.searchHistory.filter((q) => q !== query);
          return { searchHistory: [query, ...filtered].slice(0, 10) }; // Keep top 10
        }),

      clearSearchHistory: () => set({ searchHistory: [] }),

      setCommandPaletteOpen: (open) => set({ isCommandPaletteOpen: open }),

      updateSettings: (updates) =>
        set((state) => ({
          settings: { ...state.settings, ...updates },
        })),

      resetSearch: () =>
        set({ searchQuery: '', searchResults: null, parsedQuery: null }),
    }),
    {
      name: 'releaf-email-store',
      partialize: (state) => ({
        searchHistory: state.searchHistory,
        settings: state.settings,
      }),
    }
  )
);
