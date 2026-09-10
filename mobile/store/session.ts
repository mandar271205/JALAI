import * as SecureStore from "expo-secure-store";
import { create } from "zustand";
import type { AppSession, UserRole } from "@/types";

const KEY = "jalrakshak.session.v1";
type SessionState = {
  hydrated: boolean;
  session: AppSession | null;
  hydrate: () => Promise<void>;
  signIn: (input: {
    identifier: string;
    password: string;
    role: UserRole;
  }) => Promise<void>;
  acceptToken: (token: string, userId: string, role: UserRole) => Promise<void>;
  signOut: () => Promise<void>;
};

export const useSession = create<SessionState>((set) => ({
  hydrated: false,
  session: null,
  hydrate: async () => {
    try {
      const raw = await SecureStore.getItemAsync(KEY);
      set({ session: raw ? JSON.parse(raw) : null, hydrated: true });
    } catch {
      set({ session: null, hydrated: true });
    }
  },
  signIn: async ({ identifier, password, role }) => {
    if (process.env.EXPO_PUBLIC_AUTH_MODE !== "mock")
      throw new Error(
        "Token issuance is not exposed by this backend. Configure the production identity flow.",
      );
    if (!identifier.trim() || !password)
      throw new Error("Identifier and password are required.");
    const session: AppSession = {
      userId: identifier.trim(),
      email: identifier.includes("@") ? identifier : undefined,
      role,
      mock: true,
    };
    await SecureStore.setItemAsync(KEY, JSON.stringify(session));
    set({ session });
  },
  acceptToken: async (token, userId, role) => {
    const session = { token, userId, role, mock: false };
    await SecureStore.setItemAsync(KEY, JSON.stringify(session));
    set({ session });
  },
  signOut: async () => {
    await SecureStore.deleteItemAsync(KEY);
    set({ session: null });
  },
}));
