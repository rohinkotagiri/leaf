import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useEmailStore } from '../../stores/useEmailStore';
import { api } from '../../services/api';
import { Search, Sparkles, Clock, X, SearchCode, Command, ArrowRight } from 'lucide-react';

export function SearchBar() {
  const {
    selectedAccountId,
    selectedFolder,
    searchQuery,
    isCommandPaletteOpen,
    searchHistory,
    parsedQuery,
    setSearchResults,
    setParsedQuery,
    addSearchHistory,
    clearSearchHistory,
    setCommandPaletteOpen,
    resetSearch,
  } = useEmailStore();

  const [inputVal, setInputVal] = useState(searchQuery);
  const [debouncedVal, setDebouncedVal] = useState(searchQuery);
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);

  // Debounce input value
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedVal(inputVal);
    }, 300);
    return () => clearTimeout(handler);
  }, [inputVal]);

  // Bind Ctrl+K / Cmd+K Command Palette trigger
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setCommandPaletteOpen(!isCommandPaletteOpen);
      }
      if (e.key === 'Escape') {
        setCommandPaletteOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isCommandPaletteOpen]);

  // Focus input when Command Palette is opened
  useEffect(() => {
    if (isCommandPaletteOpen) {
      setTimeout(() => {
        inputRef.current?.focus();
        setActiveIndex(-1);
      }, 50);
    }
  }, [isCommandPaletteOpen]);

  // Fetch search suggestions
  const { data: suggestions } = useQuery({
    queryKey: ['suggestions', debouncedVal],
    queryFn: () => (debouncedVal.trim() ? api.getSearchSuggestions(debouncedVal) : null),
    enabled: !!debouncedVal.trim() && isCommandPaletteOpen,
  });

  // Execute Search Mutation
  const searchMutation = useMutation({
    mutationFn: (q: string) =>
      api.searchEmails(q, {
        account_id: selectedAccountId === 'all' ? undefined : selectedAccountId,
        folder: selectedFolder,
        limit: 100,
      }),
    onSuccess: (data) => {
      setSearchResults(data.results);
      setParsedQuery(data.parsed_query);
      if (data.results.length > 0) {
        addSearchHistory(debouncedVal);
      }
    },
  });

  // Automatically execute search when debounced value changes
  useEffect(() => {
    if (debouncedVal.trim()) {
      searchMutation.mutate(debouncedVal);
    } else {
      resetSearch();
    }
  }, [debouncedVal]);

  const handleRunSearch = (q: string) => {
    setInputVal(q);
    setDebouncedVal(q);
    setCommandPaletteOpen(false);
  };

  const handleClear = () => {
    setInputVal('');
    setDebouncedVal('');
    resetSearch();
  };

  // Build combined list of suggestions for keyboard navigation
  const listItems: string[] = [];
  if (suggestions) {
    listItems.push(...(suggestions.recommended_searches || []));
    listItems.push(...(suggestions.recent_subjects || []));
    listItems.push(...(suggestions.frequent_senders || []));
  } else {
    listItems.push(...searchHistory);
  }

  // Keyboard navigation inside Command Palette list
  const handleKeyDownList = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => Math.min(prev + 1, listItems.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex >= 0 && listItems[activeIndex]) {
        handleRunSearch(listItems[activeIndex]);
      } else {
        setCommandPaletteOpen(false);
      }
    }
  };

  return (
    <>
      {/* Top Search Bar Row */}
      <div className="h-12 border-b border-slate-900 px-6 flex items-center justify-between bg-slate-950/60 backdrop-blur-md select-none shrink-0">
        <div className="flex items-center gap-2 flex-1 max-w-xl">
          <div
            onClick={() => setCommandPaletteOpen(true)}
            className="w-full bg-slate-900 border border-slate-805 hover:bg-slate-850 rounded-lg px-3 py-1.5 flex items-center justify-between text-slate-500 text-xs cursor-pointer select-none"
          >
            <div className="flex items-center gap-2">
              <Search className="w-3.5 h-3.5 text-slate-400" />
              <span>{inputVal || 'Search emails with Natural Language...'}</span>
            </div>
            <div className="flex items-center gap-1 bg-slate-950 px-1.5 py-0.5 rounded text-[10px] border border-slate-800">
              <Command className="w-3 h-3" />
              <span>K</span>
            </div>
          </div>
          {inputVal && (
            <button
              onClick={handleClear}
              className="p-1.5 text-slate-500 hover:text-slate-300 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Dynamic Parsed query tags */}
        {parsedQuery && (
          <div className="flex items-center gap-1.5 overflow-x-auto max-w-[40%] pl-4">
            {parsedQuery.category_filter && (
              <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-indigo-950 text-indigo-400 border border-indigo-900 uppercase">
                Cat:{parsedQuery.category_filter}
              </span>
            )}
            {parsedQuery.sender_filter && (
              <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-900 truncate max-w-[120px]">
                From:{parsedQuery.sender_filter}
              </span>
            )}
            {parsedQuery.date_from && (
              <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-amber-950 text-amber-400 border border-amber-900">
                After:{parsedQuery.date_from.split('T')[0]}
              </span>
            )}
            {parsedQuery.has_attachments && (
              <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-cyan-950 text-cyan-400 border border-cyan-900">
                Attachments
              </span>
            )}
            {parsedQuery.is_unread && (
              <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-rose-950 text-rose-400 border border-rose-900">
                Unread
              </span>
            )}
          </div>
        )}
      </div>

      {/* Command Palette Overlay Dialog modal */}
      {isCommandPaletteOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] px-4">
          {/* Backdrop blur */}
          <div
            className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
            onClick={() => setCommandPaletteOpen(false)}
          />

          {/* Palette container */}
          <div className="relative w-full max-w-lg bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[450px]">
            {/* Input Row */}
            <div className="flex items-center px-4 border-b border-slate-800">
              <Search className="w-4 h-4 text-indigo-400 shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                onKeyDown={handleKeyDownList}
                placeholder="Search emails (e.g. 'emails from Professors about projects last week')"
                className="w-full bg-transparent border-0 outline-none text-slate-100 text-xs px-3 py-3.5 placeholder:text-slate-500 focus:ring-0"
              />
              {searchMutation.isPending && (
                <Sparkles className="w-4 h-4 text-indigo-500 animate-spin mr-2 shrink-0" />
              )}
              <div className="text-[10px] text-slate-500 bg-slate-950 px-2 py-0.5 rounded border border-slate-800 whitespace-nowrap select-none">
                ESC
              </div>
            </div>

            {/* Suggestions & History List */}
            <div className="flex-1 overflow-y-auto py-2 divide-y divide-slate-850/40 select-none scrollbar-thin">
              {listItems.length === 0 ? (
                <div className="px-4 py-8 text-center text-xs text-slate-500 flex flex-col items-center gap-1">
                  <SearchCode className="w-6 h-6 text-slate-700 mb-1" />
                  <span>No recent searches or query recommendations.</span>
                  <span className="text-[10px] text-slate-600 mt-1 max-w-[320px]">
                    Try natural filters: "from:Apple", "is:unread", "emails yesterday"
                  </span>
                </div>
              ) : (
                <div className="py-1">
                  <span className="px-4 py-1 text-[8px] font-black text-slate-500 uppercase tracking-widest block mb-1">
                    {suggestions ? 'AI Recommendations' : 'Recent Searches'}
                  </span>
                  {listItems.map((item, idx) => {
                    const isSelectedIdx = activeIndex === idx;
                    return (
                      <div
                        key={idx}
                        onClick={() => handleRunSearch(item)}
                        className={`px-4 py-2 flex items-center justify-between cursor-pointer text-xs font-semibold ${
                          isSelectedIdx ? 'bg-indigo-600/10 text-indigo-400' : 'text-slate-300 hover:bg-slate-850/60'
                        }`}
                      >
                        <div className="flex items-center gap-2 truncate">
                          {suggestions ? (
                            <Sparkles className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                          ) : (
                            <Clock className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                          )}
                          <span className="truncate">{item}</span>
                        </div>
                        {isSelectedIdx && <ArrowRight className="w-3 h-3 text-indigo-400" />}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Footer */}
            {searchHistory.length > 0 && !suggestions && (
              <div className="p-2 border-t border-slate-800 bg-slate-950/40 flex justify-end shrink-0">
                <button
                  onClick={clearSearchHistory}
                  className="text-[9px] font-bold text-red-400 hover:text-red-300 px-2 py-1 hover:bg-red-950/10 rounded"
                >
                  Clear History
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
