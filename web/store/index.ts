// ============================================================================
// JalRakshak AI — Auth + Notification Zustand Store
// ============================================================================
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AuthUser, UserRole, Notification } from "@/types";
import { clearSession, setMockRole } from "@/lib/api/client";

// ---- Auth Store ------------------------------------------------------------
interface AuthState {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isRealAuth: boolean;
  login: (role: UserRole, userId?: string) => void;
  loginWithSupabaseAuth: (email: string, pass: string) => Promise<void>;
  restoreSession: () => void;
  logout: () => void;
  setLoading: (loading: boolean) => void;
  hasRole: (...roles: UserRole[]) => boolean;
  canDoAction: (action: AuthAction) => boolean;
}

export type AuthAction =
  | "draft_alert"
  | "approve_alert"
  | "publish_alert"
  | "review_report"
  | "create_incident"
  | "transition_incident"
  | "create_responder_task"
  | "view_audit"
  | "view_system"
  | "manage_users";

const ACTION_ROLES: Record<AuthAction, UserRole[]> = {
  draft_alert: ["ANALYST", "ALERT_APPROVER", "MUNICIPAL_OFFICER", "DISASTER_MANAGER", "ADMIN", "SUPER_ADMIN"],
  approve_alert: ["ALERT_APPROVER", "DISASTER_MANAGER", "ADMIN", "SUPER_ADMIN"],
  publish_alert: ["ALERT_APPROVER", "MUNICIPAL_OFFICER", "DISASTER_MANAGER", "ADMIN", "SUPER_ADMIN"],
  review_report: ["ANALYST", "MUNICIPAL_OFFICER", "DISASTER_MANAGER", "ADMIN", "SUPER_ADMIN"],
  create_incident: ["ANALYST", "MUNICIPAL_OFFICER", "DISASTER_MANAGER", "ADMIN", "SUPER_ADMIN"],
  transition_incident: ["MUNICIPAL_OFFICER", "DISASTER_MANAGER", "ADMIN", "SUPER_ADMIN"],
  create_responder_task: ["MUNICIPAL_OFFICER", "DISASTER_MANAGER", "ADMIN", "SUPER_ADMIN"],
  view_audit: ["DISASTER_MANAGER", "ADMIN", "SUPER_ADMIN"],
  view_system: ["ANALYST", "DISASTER_MANAGER", "ADMIN", "SUPER_ADMIN", "ML_ADMIN"],
  manage_users: ["ADMIN", "SUPER_ADMIN"],
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      isRealAuth: false,

      login: (role: UserRole, userId?: string) => {
        const id = userId || `usr-dev-${role.toLowerCase()}-001`;
        const user: AuthUser = {
          user_id: id,
          email: `${id}@jalrakshak.local`,
          role,
          metadata: { auth_provider: "mock" },
        };
        setMockRole(role);
        set({ user, isAuthenticated: true, isRealAuth: false, isLoading: false });
      },

      loginWithSupabaseAuth: async (email: string, pass: string) => {
        set({ isLoading: true });
        try {
          const { loginWithSupabase } = await import("@/lib/auth/supabase");
          const { user } = await loginWithSupabase(email, pass);
          set({ user, isAuthenticated: true, isRealAuth: true, isLoading: false });
        } catch (err) {
          set({ isLoading: false });
          throw err;
        }
      },

      restoreSession: async () => {
        try {
          const { restoreSupabaseSession } = await import("@/lib/auth/supabase");
          const session = restoreSupabaseSession();
          if (session) {
            set({ user: session.user, isAuthenticated: true, isRealAuth: true });
            return;
          }
        } catch {
          // ignore error
        }
      },

      logout: () => {
        import("@/lib/auth/supabase").then(({ logoutSupabase }) => logoutSupabase()).catch(() => {});
        clearSession();
        set({ user: null, isAuthenticated: false, isRealAuth: false, isLoading: false });
      },

      setLoading: (loading: boolean) => set({ isLoading: loading }),

      hasRole: (...roles: UserRole[]) => {
        const { user } = get();
        if (!user) return false;
        return roles.includes(user.role);
      },

      canDoAction: (action: AuthAction) => {
        const { user } = get();
        if (!user) return false;
        const allowedRoles = ACTION_ROLES[action] || [];
        return allowedRoles.includes(user.role);
      },
    }),
    {
      name: "jr-auth",
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        isRealAuth: state.isRealAuth,
      }),
    },
  ),
);

// ---- Notification Store ----------------------------------------------------
interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  addNotification: (notification: Omit<Notification, "id" | "read">) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  clearAll: () => void;
}

let notifIdCounter = 0;

export const useNotificationStore = create<NotificationState>()((set) => ({
  notifications: [],
  unreadCount: 0,

  addNotification: (notif) => {
    const id = `notif-${Date.now()}-${++notifIdCounter}`;
    const notification: Notification = { ...notif, id, read: false };
    set((state) => ({
      notifications: [notification, ...state.notifications].slice(0, 100), // cap at 100
      unreadCount: state.unreadCount + 1,
    }));
  },

  markRead: (id) =>
    set((state) => ({
      notifications: state.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n,
      ),
      unreadCount: Math.max(0, state.unreadCount - 1),
    })),

  markAllRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    })),

  clearAll: () => set({ notifications: [], unreadCount: 0 }),
}));
