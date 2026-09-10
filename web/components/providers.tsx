"use client";
// ============================================================================
// Global Providers — wraps entire application
// ============================================================================
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { useState } from "react";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000, // 30s default cache
            gcTime: 5 * 60_000, // 5m garbage collect
            retry: (failureCount, error: unknown) => {
              // Don't retry 401/403 errors
              const status = (error as { statusCode?: number })?.statusCode;
              if (status === 401 || status === 403 || status === 404) return false;
              return failureCount < 2;
            },
            refetchOnWindowFocus: false, // Avoid excessive refetching in operational context
          },
          mutations: {
            retry: 0,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster
        position="top-right"
        richColors
        closeButton
        duration={5000}
        toastOptions={{
          style: {
            fontFamily: "Inter, system-ui, sans-serif",
            fontSize: "13px",
          },
        }}
      />
    </QueryClientProvider>
  );
}
