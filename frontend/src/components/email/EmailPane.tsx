import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEmailStore } from '../../stores/useEmailStore';
import { api } from '../../services/api';
import { 
  Archive, 
  Trash2, 
  Star, 
  Sparkles, 
  ThumbsUp, 
  ThumbsDown, 
  Square,
  ChevronDown,
  ChevronUp,
  MailOpen,
  Mail,
  Paperclip,
  RefreshCw
} from 'lucide-react';
import { format, parseISO } from 'date-fns';

export function EmailPane() {
  const { selectedEmailId, setSelectedEmailId } = useEmailStore();
  const queryClient = useQueryClient();
  const [feedbackSubmitted, setFeedbackSubmitted] = useState<boolean | null>(null);
  const [correctedCategory, setCorrectedCategory] = useState<string>('');
  
  // Track collapsed threads: thread email id -> boolean
  const [collapsedThreadIds, setCollapsedThreadIds] = useState<Record<string, boolean>>({});

  // Fetch full email details (triggers background AI analysis if not complete)
  const { data: email, isLoading, error } = useQuery({
    queryKey: ['email', selectedEmailId],
    queryFn: () => (selectedEmailId ? api.getEmailDetail(selectedEmailId) : null),
    enabled: !!selectedEmailId,
  });

  // Fetch conversation thread
  const { data: threadEmails = [] } = useQuery({
    queryKey: ['email-thread', selectedEmailId],
    queryFn: () => (selectedEmailId ? api.getEmailThread(selectedEmailId) : null),
    enabled: !!selectedEmailId,
  });

  // Automatically mark email as read if it is loaded and unread
  useEffect(() => {
    if (email && !email.is_read) {
      api.updateEmail(email.id, { is_read: true }).then(() => {
        queryClient.invalidateQueries({ queryKey: ['emails'] });
        queryClient.invalidateQueries({ queryKey: ['email', email.id] });
      });
    }
  }, [email?.id, email?.is_read, queryClient]);

  // Set corrected category state when email analysis category is available
  useEffect(() => {
    if (email?.category) {
      setCorrectedCategory(email.category);
    }
    setFeedbackSubmitted(null);
  }, [email]);

  // Mutations
  const updateFlagsMutation = useMutation({
    mutationFn: ({ id, updates }: { id: string; updates: any }) => api.updateEmail(id, updates),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      queryClient.invalidateQueries({ queryKey: ['email', data.id] });
    },
  });

  const triggerActionMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'archive' | 'delete' | 'mark_important' }) =>
      api.triggerEmailAction(id, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      setSelectedEmailId(null);
    },
  });

  const feedbackMutation = useMutation({
    mutationFn: (payload: {
      email_id: string;
      category_correction?: string;
      priority_correction?: number;
      spam_correction?: boolean;
      feedback_notes?: string;
    }) => api.submitFeedback(payload),
    onSuccess: () => {
      setFeedbackSubmitted(true);
      queryClient.invalidateQueries({ queryKey: ['email', selectedEmailId] });
    },
  });

  if (!selectedEmailId) {
    return (
      <div className="flex-1 bg-slate-950 flex flex-col items-center justify-center text-slate-500 font-sans select-none">
        <Mail className="w-12 h-12 text-slate-700 mb-3" />
        <span className="text-xs font-semibold">Select a conversation to read</span>
        <span className="text-[10px] text-slate-600 mt-1">Press J or K to navigate</span>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex-1 bg-slate-950 flex items-center justify-center text-slate-500 font-sans">
        <div className="text-xs font-semibold flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-indigo-400 animate-pulse" />
          Loading conversation details...
        </div>
      </div>
    );
  }

  if (error || !email) {
    return (
      <div className="flex-1 bg-slate-950 flex items-center justify-center text-slate-500 font-sans">
        <span className="text-xs font-semibold text-rose-400">Failed to fetch email details.</span>
      </div>
    );
  }

  const handleAction = (action: 'archive' | 'delete' | 'mark_important') => {
    triggerActionMutation.mutate({ id: email.id, action });
  };

  const handleToggleStar = () => {
    updateFlagsMutation.mutate({
      id: email.id,
      updates: { is_starred: !email.is_starred },
    });
  };

  const handleToggleRead = () => {
    updateFlagsMutation.mutate({
      id: email.id,
      updates: { is_read: !email.is_read },
    });
  };

  const handleFeedback = (isPositive: boolean) => {
    feedbackMutation.mutate({
      email_id: email.id,
      feedback_notes: isPositive ? 'User liked AI analysis' : 'User disliked AI analysis',
    });
  };

  const handleCategoryCorrection = (category: string) => {
    setCorrectedCategory(category);
    feedbackMutation.mutate({
      email_id: email.id,
      category_correction: category,
    });
  };

  // Safe HTML Iframe Ref Handler
  const renderIframeBody = (html: string | undefined, text: string | undefined) => {
    // If html exists, load it, otherwise convert newlines of text to divs
    const rawContent = html || `<div>${(text || '').replace(/\n/g, '<br/>')}</div>`;
    // Clean up content slightly to prevent bad scripts inside srcDoc
    const cleanedContent = rawContent.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
    
    return (
      <iframe
        title="Email Body Sandbox"
        srcDoc={`
          <html>
            <head>
              <style>
                body {
                  font-family: sans-serif;
                  font-size: 13px;
                  line-height: 1.6;
                  color: #cbd5e1;
                  background-color: transparent;
                  margin: 0;
                  padding: 8px 0;
                  word-break: break-word;
                }
                a { color: #6366f1; text-decoration: none; }
                a:hover { text-decoration: underline; }
                blockquote {
                  border-left: 2px solid #334155;
                  padding-left: 12px;
                  margin-left: 0;
                  color: #64748b;
                }
              </style>
            </head>
            <body>
              ${cleanedContent}
            </body>
          </html>
        `}
        sandbox="allow-popups allow-popups-to-escape-sandbox"
        className="w-full min-h-[300px] bg-transparent border-0"
        onLoad={(e) => {
          // Auto-resize iframe height
          const iframe = e.target as HTMLIFrameElement;
          if (iframe.contentWindow?.document.body) {
            iframe.style.height = `${iframe.contentWindow.document.body.scrollHeight + 30}px`;
          }
        }}
      />
    );
  };

  return (
    <div className="flex-1 bg-slate-950 flex flex-col h-full overflow-hidden font-sans">
      {/* Top Toolbar Action buttons */}
      <div className="h-12 border-b border-slate-900 px-6 flex items-center justify-between bg-slate-950/60 backdrop-blur-md select-none shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => handleAction('archive')}
            disabled={email.folder === 'Archive'}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-905 rounded transition-all disabled:opacity-30 disabled:hover:bg-transparent"
            title="Archive Email"
          >
            <Archive className="w-4 h-4" />
          </button>
          <button
            onClick={() => handleAction('delete')}
            disabled={email.folder === 'Trash'}
            className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-950/10 rounded transition-all disabled:opacity-30"
            title="Move to Trash"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            onClick={handleToggleRead}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-905 rounded transition-all"
            title={email.is_read ? 'Mark as Unread' : 'Mark as Read'}
          >
            {email.is_read ? <Mail className="w-4 h-4" /> : <MailOpen className="w-4 h-4" />}
          </button>
          <button
            onClick={handleToggleStar}
            className={`p-1.5 rounded transition-all ${
              email.is_starred ? 'text-amber-500 hover:text-amber-400' : 'text-slate-400 hover:text-amber-500'
            }`}
            title={email.is_starred ? 'Remove Star' : 'Star conversation'}
          >
            <Star className={`w-4 h-4 ${email.is_starred ? 'fill-amber-500' : ''}`} />
          </button>
        </div>
      </div>

      {/* Main Content Area split into Email Body Thread + AI Panel */}
      <div className="flex-1 flex overflow-hidden">
        {/* Scrollable conversation messages section */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6 scrollbar-thin">
          {/* Thread Header */}
          <div className="pb-4 border-b border-slate-900">
            <h2 className="text-base font-bold text-white tracking-tight leading-snug">
              {email.subject || '(No Subject)'}
            </h2>
            <div className="flex items-center gap-1.5 mt-2">
              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-900 border border-slate-800 text-slate-400 uppercase tracking-wider">
                {email.folder}
              </span>
            </div>
          </div>

          {/* Conversation list */}
          <div className="space-y-4">
            {(threadEmails || []).map((te, index) => {
              const isLatest = te.id === email.id;
              const isCollapsed = collapsedThreadIds[te.id] ?? (!isLatest && index < (threadEmails?.length || 0) - 1);

              const toggleCollapse = () => {
                setCollapsedThreadIds((prev) => ({
                  ...prev,
                  [te.id]: !isCollapsed,
                }));
              };

              return (
                <div
                  key={te.id}
                  className={`border border-slate-900 rounded-xl overflow-hidden bg-slate-900/10 ${
                    isLatest ? 'ring-1 ring-indigo-500/25 bg-slate-900/20' : ''
                  }`}
                >
                  {/* Message Item Header */}
                  <div
                    onClick={toggleCollapse}
                    className="p-4 flex items-center justify-between cursor-pointer hover:bg-slate-900/40 select-none"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-semibold text-slate-300">
                        {te.sender_name ? te.sender_name.charAt(0).toUpperCase() : te.sender_email.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-bold text-slate-200">
                            {te.sender_name || te.sender_email}
                          </span>
                          {te.sender_name && (
                            <span className="text-[9px] text-slate-500 font-semibold">
                              &lt;{te.sender_email}&gt;
                            </span>
                          )}
                        </div>
                        <p className="text-[9px] text-slate-500 font-semibold mt-0.5">
                          {te.date ? format(parseISO(te.date), 'PP p') : ''}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      {te.has_attachments && <Paperclip className="w-3.5 h-3.5 text-slate-500" />}
                      <button className="text-slate-500 hover:text-slate-300">
                        {isCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Message Body Content (if expanded) */}
                  {!isCollapsed && (
                    <div className="p-4 border-t border-slate-900/60 bg-slate-900/5">
                      {renderIframeBody(te.body_html, te.body_text)}

                      {/* Attachments List */}
                      {te.attachment_names && te.attachment_names.length > 0 && (
                        <div className="mt-4 pt-3 border-t border-slate-900/40">
                          <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                            <Paperclip className="w-3 h-3 text-indigo-400" />
                            Attachments ({te.attachment_names.length})
                          </h5>
                          <div className="flex flex-wrap gap-2">
                            {te.attachment_names.map((name, i) => (
                              <div
                                key={i}
                                className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-950 border border-slate-850 text-[10px] text-slate-300"
                              >
                                <span className="truncate max-w-[150px] font-semibold">{name}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* AI Analysis Sidebar Pane */}
        <div className="w-72 border-l border-slate-900 bg-slate-950/60 backdrop-blur-md p-5 flex flex-col h-full overflow-y-auto select-none scrollbar-thin gap-5">
          <div className="flex items-center gap-2 pb-3 border-b border-slate-900 shrink-0">
            <Sparkles className="w-4 h-4 text-indigo-400 animate-pulse" />
            <h3 className="font-bold text-xs text-white uppercase tracking-wider">
              AI Copilot Insights
            </h3>
          </div>

          {email.analysis?.is_pending ? (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-500 text-center p-4">
              <RefreshCw className="w-6 h-6 animate-spin text-indigo-500 mb-2" />
              <p className="text-[10px] font-bold text-slate-400">Processing Insights...</p>
              <p className="text-[9px] text-slate-600 mt-1 max-w-[180px]">
                Ollama model is running classification and summarization tasks.
              </p>
            </div>
          ) : (
            <>
              {/* Category selector */}
              <div className="space-y-1.5">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  Category Classification
                </span>
                <div className="relative">
                  <select
                    value={correctedCategory}
                    onChange={(e) => handleCategoryCorrection(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 font-semibold appearance-none focus:outline-none focus:border-indigo-600 cursor-pointer pr-8 capitalize"
                  >
                    {['work', 'personal', 'finance', 'newsletter', 'shopping', 'travel', 'security', 'spam', 'other'].map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="w-4 h-4 text-slate-500 absolute right-3 top-2.5 pointer-events-none" />
                </div>
              </div>

              {/* Priority Scorer */}
              <div className="space-y-1.5">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  Priority Rating
                </span>
                <div className="bg-slate-900 border border-slate-850 p-3 rounded-lg flex items-center justify-between">
                  <div>
                    <span className="text-xl font-black text-white">
                      {email.priority_score !== undefined && email.priority_score !== null
                        ? email.priority_score.toFixed(1)
                        : '0.0'}
                    </span>
                    <span className="text-[9px] text-slate-500 ml-1 font-bold">/ 10</span>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded text-[8px] font-bold uppercase tracking-wider ${
                      email.priority_score !== undefined && email.priority_score !== null && email.priority_score >= 7.0
                        ? 'bg-rose-950 text-rose-400 border border-rose-900'
                        : email.priority_score !== undefined && email.priority_score !== null && email.priority_score >= 5.0
                        ? 'bg-orange-950 text-orange-400 border border-orange-900'
                        : 'bg-indigo-950 text-indigo-400 border border-indigo-900'
                    }`}
                  >
                    {email.priority_score !== undefined && email.priority_score !== null && email.priority_score >= 7.0
                      ? 'Urgent Focus'
                      : email.priority_score !== undefined && email.priority_score !== null && email.priority_score >= 5.0
                      ? 'Due Today'
                      : 'Standard'}
                  </span>
                </div>
              </div>

              {/* Summary Block */}
              <div className="space-y-1.5">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  Summary Synthesis
                </span>
                <div className="bg-slate-900/40 border border-slate-900/60 p-3 rounded-lg text-slate-300 text-[11px] leading-relaxed font-medium">
                  {email.analysis?.summary || 'No summary generated yet.'}
                </div>
              </div>

              {/* Action items Checklist */}
              <div className="space-y-1.5">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  Extracted Action Items
                </span>
                {email.analysis?.action_items && email.analysis.action_items.length > 0 ? (
                  <div className="space-y-2">
                    {email.analysis.action_items.map((item, i) => (
                      <div key={i} className="flex gap-2 text-[10px] text-slate-300 font-semibold items-start leading-snug">
                        <Square className="w-3.5 h-3.5 text-slate-600 shrink-0 mt-0.5" />
                        <span>{item}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-[10px] text-slate-650 italic pl-1">
                    No immediate action items found.
                  </div>
                )}
              </div>

              {/* Feedback controls */}
              <div className="pt-4 border-t border-slate-900 flex flex-col gap-2 shrink-0">
                <span className="text-[9px] font-bold text-slate-600 uppercase tracking-widest text-center">
                  Was this Analysis Useful?
                </span>
                {feedbackSubmitted ? (
                  <span className="text-[9px] font-bold text-emerald-400 text-center animate-fadeIn py-1">
                    Thanks for your feedback!
                  </span>
                ) : (
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleFeedback(true)}
                      className="flex-1 bg-slate-900 border border-slate-850 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded py-1.5 flex items-center justify-center gap-1.5 text-[10px] font-bold transition-colors"
                    >
                      <ThumbsUp className="w-3.5 h-3.5" />
                      Yes
                    </button>
                    <button
                      onClick={() => handleFeedback(false)}
                      className="flex-1 bg-slate-900 border border-slate-850 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded py-1.5 flex items-center justify-center gap-1.5 text-[10px] font-bold transition-colors"
                    >
                      <ThumbsDown className="w-3.5 h-3.5" />
                      No
                    </button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
