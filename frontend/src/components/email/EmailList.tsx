import React, { useEffect, useRef } from 'react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useEmailStore } from '../../stores/useEmailStore';
import { api } from '../../services/api';
import { Email } from '../../types';
import { Paperclip, Star, AlertCircle } from 'lucide-react';
import { formatDistanceToNow, parseISO } from 'date-fns';

export function EmailList() {
  const {
    selectedAccountId,
    selectedFolder,
    selectedCategory,
    selectedPriority,
    selectedEmailId,
    selectedEmailIds,
    searchQuery,
    searchResults,
    setSelectedEmailId,
    setSelectedEmailIds,
  } = useEmailStore();

  const queryClient = useQueryClient();
  const parentRef = useRef<HTMLDivElement>(null);

  // Infinite Query for listing emails when NOT searching
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    status,
  } = useInfiniteQuery({
    queryKey: [
      'emails',
      selectedAccountId,
      selectedFolder,
      selectedCategory,
      selectedPriority,
    ],
    queryFn: async ({ pageParam = undefined }) => {
      // Map focus priorities
      let priorityMin: number | undefined = undefined;
      if (selectedPriority === 'urgent') priorityMin = 7.0;
      if (selectedPriority === 'today') priorityMin = 5.0;
      if (selectedPriority === 'week') priorityMin = 3.0;

      const res = await api.getEmails({
        account_id: selectedAccountId === 'all' ? undefined : selectedAccountId,
        folder: selectedFolder,
        category: selectedCategory === 'all' ? undefined : selectedCategory,
        priority_min: priorityMin,
        after: pageParam,
        limit: 50,
      });
      return res;
    },
    initialPageParam: undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !searchQuery, // Disable if search is active
  });

  // Flatten infinite query results
  const fetchedEmails = data ? data.pages.flatMap((page) => page.emails) : [];

  // Determine which list of emails to display
  const emails: Email[] = searchQuery ? (searchResults || []) : fetchedEmails;

  // Virtualizer setup
  const rowVirtualizer = useVirtualizer({
    count: emails.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 92, // estimate cards height
    overscan: 10,
  });

  // Infinite Scroll Trigger: fetch when getting close to bottom
  const virtualItems = rowVirtualizer.getVirtualItems();
  useEffect(() => {
    if (searchQuery) return;
    const lastItem = virtualItems[virtualItems.length - 1];
    if (!lastItem) return;

    if (
      lastItem.index >= emails.length - 15 &&
      hasNextPage &&
      !isFetchingNextPage
    ) {
      fetchNextPage();
    }
  }, [virtualItems, emails.length, hasNextPage, isFetchingNextPage, fetchNextPage, searchQuery]);

  // Bulk Actions mutations
  const updateFlagsMutation = useMutation({
    mutationFn: ({ ids, updates }: { ids: string[]; updates: any }) =>
      Promise.all(ids.map((id) => api.updateEmail(id, updates))),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['emails'] });
    },
  });

  const triggerActionMutation = useMutation({
    mutationFn: ({ ids, action }: { ids: string[]; action: 'archive' | 'delete' | 'mark_important' }) =>
      Promise.all(ids.map((id) => api.triggerEmailAction(id, action))),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      setSelectedEmailIds([]);
      setSelectedEmailId(null);
    },
  });

  // Keyboard navigation & Multi-select click handler
  const handleEmailClick = (e: React.MouseEvent, email: Email, index: number) => {
    if (e.ctrlKey || e.metaKey) {
      // Toggle selection
      setSelectedEmailIds((prev) =>
        prev.includes(email.id) ? prev.filter((id) => id !== email.id) : [...prev, email.id]
      );
    } else if (e.shiftKey && selectedEmailId) {
      // Shift multi-select
      const lastIndex = emails.findIndex((em) => em.id === selectedEmailId);
      if (lastIndex !== -1) {
        const start = Math.min(lastIndex, index);
        const end = Math.max(lastIndex, index);
        const slicedIds = emails.slice(start, end + 1).map((em) => em.id);
        setSelectedEmailIds(slicedIds);
      }
    } else {
      // Standard selection
      setSelectedEmailId(email.id);
      setSelectedEmailIds([email.id]);
    }
  };

  // Bind Keyboard Navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore keybindings if the user is typing in inputs or textareas
      if (
        document.activeElement?.tagName === 'INPUT' ||
        document.activeElement?.tagName === 'TEXTAREA'
      ) {
        return;
      }

      if (emails.length === 0) return;

      const currentIndex = selectedEmailId
        ? emails.findIndex((em) => em.id === selectedEmailId)
        : -1;

      if (e.key === 'j') {
        // Move selection down
        const nextIndex = Math.min(currentIndex + 1, emails.length - 1);
        const nextEmail = emails[nextIndex];
        if (nextEmail) {
          setSelectedEmailId(nextEmail.id);
          setSelectedEmailIds([nextEmail.id]);
          rowVirtualizer.scrollToIndex(nextIndex, { align: 'auto' });
        }
      } else if (e.key === 'k') {
        // Move selection up
        const nextIndex = Math.max(currentIndex - 1, 0);
        const nextEmail = emails[nextIndex];
        if (nextEmail) {
          setSelectedEmailId(nextEmail.id);
          setSelectedEmailIds([nextEmail.id]);
          rowVirtualizer.scrollToIndex(nextIndex, { align: 'auto' });
        }
      } else if (e.key === 'e') {
        // Archive selected emails
        if (selectedEmailIds.length > 0) {
          triggerActionMutation.mutate({ ids: selectedEmailIds, action: 'archive' });
        }
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        // Trash/Delete selected emails
        if (selectedEmailIds.length > 0) {
          triggerActionMutation.mutate({ ids: selectedEmailIds, action: 'delete' });
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [emails, selectedEmailId, selectedEmailIds, rowVirtualizer]);

  // Format Helper
  const getFormattedDate = (dateString: string | null) => {
    if (!dateString) return '';
    try {
      return formatDistanceToNow(parseISO(dateString), { addSuffix: false });
    } catch {
      return '';
    }
  };

  // Get Category Badge Style
  const getCategoryStyles = (category?: string | null) => {
    switch (category) {
      case 'work':
        return 'bg-indigo-950 text-indigo-400 border border-indigo-900';
      case 'personal':
        return 'bg-emerald-950 text-emerald-400 border border-emerald-900';
      case 'finance':
        return 'bg-amber-950 text-amber-400 border border-amber-900';
      case 'security':
        return 'bg-rose-950 text-rose-400 border border-rose-900';
      case 'spam':
        return 'bg-yellow-950 text-yellow-400 border border-yellow-900';
      default:
        return 'bg-slate-900 text-slate-400 border border-slate-800';
    }
  };

  return (
    <div className="w-90 bg-slate-900 border-r border-slate-900 flex flex-col h-full overflow-hidden select-none">
      {/* List Header */}
      <div className="p-4 border-b border-slate-950 flex items-center justify-between bg-slate-900/60 backdrop-blur-md z-10">
        <div>
          <h2 className="font-semibold text-xs text-white capitalize">
            {searchQuery ? 'Search Results' : selectedFolder}
          </h2>
          <p className="text-[10px] text-slate-500 font-medium mt-0.5">
            {emails.length} conversations
          </p>
        </div>

        {/* Selected actions */}
        {selectedEmailIds.length > 1 && (
          <div className="flex gap-2 animate-scaleUp">
            <button
              onClick={() => triggerActionMutation.mutate({ ids: selectedEmailIds, action: 'archive' })}
              className="px-2 py-1 bg-slate-800 border border-slate-705 text-slate-300 font-bold rounded hover:bg-slate-750 text-[10px]"
            >
              Archive ({selectedEmailIds.length})
            </button>
            <button
              onClick={() => triggerActionMutation.mutate({ ids: selectedEmailIds, action: 'delete' })}
              className="px-2 py-1 bg-red-950/20 border border-red-900 text-red-400 font-bold rounded hover:bg-red-950/45 text-[10px]"
            >
              Trash
            </button>
          </div>
        )}
      </div>

      {/* Virtual Scroll Area */}
      <div
        ref={parentRef}
        className="flex-1 overflow-y-auto divide-y divide-slate-950 scrollbar-thin"
      >
        {status === 'pending' && !searchQuery ? (
          <div className="p-8 text-center text-xs text-slate-500 font-medium">
            Loading conversations...
          </div>
        ) : emails.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500 font-medium">
            No emails found here.
          </div>
        ) : (
          <div
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const email = emails[virtualRow.index];
              if (!email) return null;

              const isSelected = selectedEmailId === email.id;
              const isMultiSelected = selectedEmailIds.includes(email.id);

              return (
                <div
                  key={virtualRow.key}
                  data-index={virtualRow.index}
                  ref={rowVirtualizer.measureElement}
                  onClick={(e) => handleEmailClick(e, email, virtualRow.index)}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                  className={`p-3.5 flex flex-col gap-1.5 cursor-pointer border-l-3 transition-colors ${
                    isSelected
                      ? 'bg-indigo-950/20 border-l-indigo-500'
                      : isMultiSelected
                      ? 'bg-slate-800/40 border-l-slate-600'
                      : 'border-l-transparent bg-slate-900 hover:bg-slate-850/40'
                  }`}
                >
                  {/* Top card metadata row */}
                  <div className="flex items-center justify-between">
                    <span
                      className={`text-[11px] truncate max-w-[160px] ${
                        !email.is_read ? 'font-bold text-slate-100' : 'text-slate-400 font-medium'
                      }`}
                    >
                      {email.sender_name || email.sender_email}
                    </span>
                    <span className="text-[9px] text-slate-500 font-semibold whitespace-nowrap">
                      {getFormattedDate(email.date)}
                    </span>
                  </div>

                  {/* Subject and Snip */}
                  <div className="flex flex-col gap-0.5">
                    <h4
                      className={`text-xs truncate text-slate-200 ${
                        !email.is_read ? 'font-bold text-white' : 'font-medium'
                      }`}
                    >
                      {email.subject || '(No Subject)'}
                    </h4>
                    <p className="text-[10px] text-slate-500 line-clamp-2 leading-relaxed">
                      {email.body_text || ''}
                    </p>
                  </div>

                  {/* Badges/Tags Row */}
                  <div className="flex items-center justify-between pt-1">
                    <div className="flex gap-1.5 items-center">
                      {/* Priority Score badge */}
                      {email.priority_score !== undefined && email.priority_score !== null && (
                        <div
                          className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[8px] font-bold ${
                            email.priority_score >= 7.0
                              ? 'bg-rose-950/40 text-rose-400 border border-rose-900'
                              : email.priority_score >= 5.0
                              ? 'bg-orange-950/40 text-orange-400 border border-orange-900'
                              : 'bg-amber-950/45 text-amber-400 border border-amber-900'
                          }`}
                        >
                          <AlertCircle className="w-2 h-2" />
                          <span>P:{email.priority_score.toFixed(1)}</span>
                        </div>
                      )}

                      {/* Category Badge */}
                      {email.category && (
                        <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-wider ${getCategoryStyles(email.category)}`}>
                          {email.category}
                        </span>
                      )}
                    </div>

                    {/* Icons */}
                    <div className="flex items-center gap-1.5 text-slate-600">
                      {email.has_attachments && <Paperclip className="w-3 h-3 text-slate-500" />}
                      {email.is_starred && <Star className="w-3 h-3 text-amber-500 fill-amber-500" />}
                      {!email.is_read && (
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {isFetchingNextPage && (
          <div className="p-4 text-center text-[10px] text-slate-500 font-semibold bg-slate-900">
            Fetching older messages...
          </div>
        )}
      </div>
    </div>
  );
}
