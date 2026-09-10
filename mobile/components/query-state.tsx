import type { PropsWithChildren } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { StateView } from "./ui";
import { userMessage } from "@/lib/api/client";
export function QueryState<T>({
  query,
  empty = false,
  children,
}: PropsWithChildren<{ query: UseQueryResult<T, Error>; empty?: boolean }>) {
  if (query.isLoading) return <StateView state="loading" />;
  if (query.isError && !query.data)
    return (
      <StateView
        state="error"
        message={userMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  if (empty) return <StateView state="empty" />;
  return (
    <>
      {query.isError ? (
        <StateView
          state="degraded"
          message={userMessage(query.error)}
          onRetry={() => void query.refetch()}
        />
      ) : null}
      {children}
    </>
  );
}
