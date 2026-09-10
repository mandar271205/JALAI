import "react-native-gesture-handler";
import { useEffect, useState } from "react";
import NetInfo from "@react-native-community/netinfo";
import {
  QueryClient,
  QueryClientProvider,
  focusManager,
  onlineManager,
} from "@tanstack/react-query";
import { Stack, useRouter } from "expo-router";
import * as Notifications from "expo-notifications";
import { AppState, Platform } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import {
  configureForegroundNotifications,
  notificationPath,
} from "@/lib/notifications/push";
import { initOutbox } from "@/lib/offline/outbox";
import { useSession } from "@/store/session";

configureForegroundNotifications();
export default function RootLayout() {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: 1, gcTime: 24 * 60 * 60 * 1000 },
        },
      }),
  );
  const hydrate = useSession((s) => s.hydrate);
  const router = useRouter();
  useEffect(() => {
    void hydrate();
    void initOutbox();
    const net = NetInfo.addEventListener((s) =>
      onlineManager.setOnline(Boolean(s.isConnected)),
    );
    const app = AppState.addEventListener("change", (state) =>
      focusManager.setFocused(
        Platform.OS === "web" ? true : state === "active",
      ),
    );
    const notification = Notifications.addNotificationResponseReceivedListener(
      (r) => router.push(notificationPath(r.notification.request.content.data)),
    );
    return () => {
      net();
      app.remove();
      notification.remove();
    };
  }, [hydrate, router]);
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={client}>
        <Stack
          screenOptions={{ headerShown: false, animation: "slide_from_right" }}
        />
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
