import { useState } from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { AppLayout } from './components/layout/AppLayout';
import { OnboardingFlow } from './components/shared/OnboardingFlow';
import { api } from './services/api';


function AppContent() {
  const [isOnboardedOverride, setIsOnboardedOverride] = useState(false);

  // Check if any accounts exist
  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => api.getAccounts(),
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-500 font-sans">
        <div className="text-xs font-semibold animate-pulse">
          Starting LeafMail AI Client...
        </div>
      </div>
    );
  }

  // Show onboarding wizard if no accounts are registered
  if (accounts.length === 0 && !isOnboardedOverride) {
    return <OnboardingFlow onComplete={() => setIsOnboardedOverride(true)} />;
  }

  return <AppLayout />;
}

export default function App() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  );
}
