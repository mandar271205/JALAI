"use client";
// ============================================================================
// Dashboard Layout — wraps all authenticated pages with AppShell
// ============================================================================
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { useAuthStore } from "@/store";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { isAuthenticated, logout, restoreSession } = useAuthStore();

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  useEffect(() => {
    const handleExpired = () => {
      logout();
      router.replace("/login");
    };
    window.addEventListener("jr:session-expired", handleExpired);
    return () => window.removeEventListener("jr:session-expired", handleExpired);
  }, [logout, router]);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, router]);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-pulse text-sm text-gray-400">Checking session…</div>
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
