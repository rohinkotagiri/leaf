import React, { useState, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Mail, Shield, Server, RefreshCw, CheckCircle, AlertCircle, ArrowRight } from 'lucide-react';
import { api } from '../../services/api';
import type { ProviderType } from '../../types';

interface OnboardingFlowProps {
  onComplete: () => void;
}

export function OnboardingFlow({ onComplete }: OnboardingFlowProps) {
  const [step, setStep] = useState(1);
  const [provider, setProvider] = useState<ProviderType>('generic');
  
  // Credentials form state
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [imapHost, setImapHost] = useState('');
  const [imapPort, setImapPort] = useState(993);
  const [useSsl, setUseSsl] = useState(true);

  // Status feedback
  const [errorMessage, setErrorMessage] = useState('');
  const [testingMessage, setTestingMessage] = useState('');
  const [accountId, setAccountId] = useState('');
  const [testSuccess, setTestSuccess] = useState(false);

  const queryClient = useQueryClient();

  // Reset custom IMAP hosts when provider changes
  useEffect(() => {
    if (provider === 'gmail') {
      setImapHost('imap.gmail.com');
      setImapPort(993);
      setUseSsl(true);
    } else if (provider === 'outlook') {
      setImapHost('outlook.office365.com');
      setImapPort(993);
      setUseSsl(true);
    } else {
      setImapHost('');
      setImapPort(993);
      setUseSsl(true);
    }
  }, [provider]);

  // Mutations
  const createAccountMutation = useMutation({
    mutationFn: (payload: any) => api.addAccount(payload),
    onSuccess: (data) => {
      setAccountId(data.id);
      setStep(3);
      runConnectionTest(data.id);
    },
    onError: (err: any) => {
      setErrorMessage(err.response?.data?.detail || 'Failed to register account.');
    },
  });

  const testConnectionMutation = useMutation({
    mutationFn: (id: string) => api.testAccount(id),
    onSuccess: (data) => {
      if (data.success) {
        setTestSuccess(true);
        setTestingMessage('Connection test passed! Authenticated successfully.');
        setTimeout(() => {
          setStep(4);
          triggerInitialSync();
        }, 1500);
      } else {
        setErrorMessage(data.message || 'Connection failed.');
      }
    },
    onError: (err: any) => {
      setErrorMessage(err.response?.data?.detail || 'Failed to authenticate connection.');
    },
  });

  const triggerSyncMutation = useMutation({
    mutationFn: (id: string) => api.triggerSync(id),
  });

  const triggerBackfillMutation = useMutation({
    mutationFn: () => api.startBackfill(),
  });

  // Query backfill status in Step 4
  const { data: backfillStatus } = useQuery({
    queryKey: ['backfill-status'],
    queryFn: () => api.getBackfillStatus(),
    enabled: step === 4,
    refetchInterval: step === 4 ? 2000 : false,
  });

  const handleNextStep1 = (selected: ProviderType) => {
    setProvider(selected);
    setStep(2);
  };

  const handleRegister = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage('');
    if (!email || !displayName || !password || !imapHost) {
      setErrorMessage('Please fill in all fields.');
      return;
    }

    createAccountMutation.mutate({
      email_address: email,
      display_name: displayName,
      provider,
      imap_host: imapHost,
      imap_port: imapPort,
      use_ssl: useSsl,
      password,
    });
  };

  const runConnectionTest = (id: string) => {
    setTestingMessage('Establishing connection to IMAP server...');
    setErrorMessage('');
    testConnectionMutation.mutate(id);
  };

  const triggerInitialSync = () => {
    if (accountId) {
      triggerSyncMutation.mutate(accountId);
      triggerBackfillMutation.mutate();
    }
  };

  const finishOnboarding = () => {
    queryClient.invalidateQueries({ queryKey: ['accounts'] });
    onComplete();
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-6 text-slate-100 font-sans selection:bg-indigo-500 selection:text-white">
      {/* Background Gradients */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-[40%] -left-[20%] w-[80%] h-[80%] rounded-full bg-indigo-900/10 blur-[120px]" />
        <div className="absolute -bottom-[40%] -right-[20%] w-[80%] h-[80%] rounded-full bg-violet-900/10 blur-[120px]" />
      </div>

      <div className="w-full max-w-xl bg-slate-900/80 backdrop-blur-md border border-slate-800 rounded-2xl shadow-2xl p-8 relative overflow-hidden">
        {/* Step Indicators */}
        <div className="flex items-center justify-between mb-8 pb-6 border-b border-slate-800/60">
          {[1, 2, 3, 4].map((s) => (
            <div key={s} className="flex items-center">
              <div
                className={`w-9 h-9 rounded-full flex items-center justify-center font-semibold text-sm transition-all duration-300 ${
                  step === s
                    ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/25 ring-2 ring-indigo-400'
                    : step > s
                    ? 'bg-indigo-900/50 text-indigo-200 border border-indigo-500/30'
                    : 'bg-slate-800 text-slate-400 border border-slate-700/60'
                }`}
              >
                {step > s ? <CheckCircle className="w-5 h-5 text-indigo-300" /> : s}
              </div>
              {s < 4 && (
                <div
                  className={`h-[2px] w-12 sm:w-16 mx-2 rounded transition-all duration-500 ${
                    step > s ? 'bg-indigo-600' : 'bg-slate-800'
                  }`}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step 1: Provider Selection */}
        {step === 1 && (
          <div className="animate-fadeIn">
            <h2 className="text-2xl font-bold mb-2 tracking-tight text-white">Select Provider</h2>
            <p className="text-slate-400 mb-6 text-sm">Choose where your emails are hosted to start connection setup.</p>
            <div className="grid grid-cols-1 gap-4">
              <button
                onClick={() => handleNextStep1('gmail')}
                className="group flex items-center p-4 rounded-xl border border-slate-800 bg-slate-950 hover:bg-indigo-950/20 hover:border-indigo-500/50 transition-all text-left"
              >
                <div className="w-12 h-12 rounded-lg bg-red-500/10 flex items-center justify-center text-red-400 mr-4 group-hover:scale-110 transition-transform">
                  <Mail className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">Google Gmail</h3>
                  <p className="text-xs text-slate-400">Connect using Google App Password or IMAP</p>
                </div>
                <ArrowRight className="w-5 h-5 ml-auto text-slate-500 group-hover:text-indigo-400 group-hover:translate-x-1 transition-all" />
              </button>

              <button
                onClick={() => handleNextStep1('outlook')}
                className="group flex items-center p-4 rounded-xl border border-slate-800 bg-slate-950 hover:bg-indigo-950/20 hover:border-indigo-500/50 transition-all text-left"
              >
                <div className="w-12 h-12 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-400 mr-4 group-hover:scale-110 transition-transform">
                  <Shield className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">Microsoft Outlook / 365</h3>
                  <p className="text-xs text-slate-400">Connect using Outlook Credentials or App Password</p>
                </div>
                <ArrowRight className="w-5 h-5 ml-auto text-slate-500 group-hover:text-indigo-400 group-hover:translate-x-1 transition-all" />
              </button>

              <button
                onClick={() => handleNextStep1('generic')}
                className="group flex items-center p-4 rounded-xl border border-slate-800 bg-slate-950 hover:bg-indigo-950/20 hover:border-indigo-500/50 transition-all text-left"
              >
                <div className="w-12 h-12 rounded-lg bg-purple-500/10 flex items-center justify-center text-purple-400 mr-4 group-hover:scale-110 transition-transform">
                  <Server className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">Other IMAP Server</h3>
                  <p className="text-xs text-slate-400">Configure manually using custom host, port, and SSL settings</p>
                </div>
                <ArrowRight className="w-5 h-5 ml-auto text-slate-500 group-hover:text-indigo-400 group-hover:translate-x-1 transition-all" />
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Credentials Input */}
        {step === 2 && (
          <form onSubmit={handleRegister} className="animate-fadeIn space-y-4">
            <h2 className="text-2xl font-bold tracking-tight text-white">
              {provider === 'generic' ? 'IMAP Configuration' : `${provider.toUpperCase()} Settings`}
            </h2>
            <p className="text-slate-400 text-sm">Provide credentials to log in. Passwords will be saved securely.</p>

            {errorMessage && (
              <div className="flex items-center gap-2 p-3 bg-red-950/30 border border-red-800/50 text-red-300 rounded-lg text-xs">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{errorMessage}</span>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="block text-xs font-medium text-slate-400 mb-1">Display Name</label>
                <input
                  type="text"
                  placeholder="e.g. John Doe"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 transition-colors"
                />
              </div>

              <div className="col-span-2">
                <label className="block text-xs font-medium text-slate-400 mb-1">Email Address</label>
                <input
                  type="email"
                  placeholder="e.g. john@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 transition-colors"
                />
              </div>

              <div className="col-span-2">
                <label className="block text-xs font-medium text-slate-400 mb-1">Password / App Password</label>
                <input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 transition-colors"
                />
              </div>

              {provider === 'generic' && (
                <>
                  <div className="col-span-2 sm:col-span-1">
                    <label className="block text-xs font-medium text-slate-400 mb-1">IMAP Server</label>
                    <input
                      type="text"
                      placeholder="imap.host.com"
                      value={imapHost}
                      onChange={(e) => setImapHost(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 transition-colors"
                    />
                  </div>

                  <div className="col-span-1 sm:col-span-1">
                    <label className="block text-xs font-medium text-slate-400 mb-1">IMAP Port</label>
                    <input
                      type="number"
                      placeholder="993"
                      value={imapPort}
                      onChange={(e) => setImapPort(parseInt(e.target.value))}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 transition-colors"
                    />
                  </div>

                  <div className="col-span-2 flex items-center gap-2 pt-2">
                    <input
                      type="checkbox"
                      id="sslCheckbox"
                      checked={useSsl}
                      onChange={(e) => setUseSsl(e.target.checked)}
                      className="rounded border-slate-800 bg-slate-950 text-indigo-600 focus:ring-indigo-500"
                    />
                    <label htmlFor="sslCheckbox" className="text-xs text-slate-300 cursor-pointer">
                      Use SSL Connection
                    </label>
                  </div>
                </>
              )}
            </div>

            <div className="flex gap-3 pt-4 border-t border-slate-800/40">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="flex-1 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-slate-300 font-semibold py-2 rounded-lg text-sm transition-colors"
              >
                Back
              </button>
              <button
                type="submit"
                disabled={createAccountMutation.isPending}
                className="flex-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold py-2 rounded-lg text-sm shadow-lg shadow-indigo-600/20 transition-all flex items-center justify-center gap-2"
              >
                {createAccountMutation.isPending && <RefreshCw className="w-4 h-4 animate-spin" />}
                Register Account
              </button>
            </div>
          </form>
        )}

        {/* Step 3: Connection Testing */}
        {step === 3 && (
          <div className="animate-fadeIn text-center py-6 space-y-6">
            <h2 className="text-2xl font-bold tracking-tight text-white">Verifying Connection</h2>
            
            <div className="flex justify-center relative">
              <div className="w-20 h-20 rounded-full border border-indigo-500/25 flex items-center justify-center bg-slate-950 shadow-inner">
                {testSuccess ? (
                  <CheckCircle className="w-10 h-10 text-emerald-400 animate-scaleUp" />
                ) : errorMessage ? (
                  <AlertCircle className="w-10 h-10 text-red-400" />
                ) : (
                  <RefreshCw className="w-8 h-8 text-indigo-500 animate-spin" />
                )}
              </div>
            </div>

            <p className="text-sm text-slate-300 max-w-sm mx-auto">
              {errorMessage ? errorMessage : testingMessage}
            </p>

            {errorMessage && (
              <div className="flex justify-center gap-4 pt-4">
                <button
                  onClick={() => setStep(2)}
                  className="bg-slate-950 hover:bg-slate-900 border border-slate-800 text-slate-300 font-semibold px-4 py-2 rounded-lg text-sm transition-colors"
                >
                  Edit Configuration
                </button>
                <button
                  onClick={() => runConnectionTest(accountId)}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-4 py-2 rounded-lg text-sm shadow-lg shadow-indigo-600/20 transition-all"
                >
                  Retry Connection
                </button>
              </div>
            )}
          </div>
        )}

        {/* Step 4: Initial Sync Progress */}
        {step === 4 && (
          <div className="animate-fadeIn py-4 space-y-6">
            <h2 className="text-2xl font-bold tracking-tight text-white text-center">Synchronizing Email Box</h2>
            <p className="text-slate-400 text-xs text-center max-w-sm mx-auto">
              Downloading email headers and executing initial AI analysis (classification, priorities, action items).
            </p>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-4">
              <div className="flex items-center justify-between text-xs font-semibold">
                <span className="text-indigo-400 flex items-center gap-1">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  {backfillStatus?.is_running ? 'Importing Historical Data' : 'Initial sync complete'}
                </span>
                <span className="text-slate-400">
                  {backfillStatus?.processed_emails || 0} / {backfillStatus?.total_emails || 0} Emails
                </span>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-slate-900 h-2.5 rounded-full overflow-hidden border border-slate-800/80">
                <div
                  className="bg-indigo-500 h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${
                      backfillStatus?.total_emails
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

            <div className="pt-4 flex justify-center border-t border-slate-800/40">
              <button
                onClick={finishOnboarding}
                className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-2.5 rounded-lg text-sm shadow-lg shadow-indigo-600/25 transition-all flex items-center justify-center gap-2"
              >
                Go to Inbox
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
