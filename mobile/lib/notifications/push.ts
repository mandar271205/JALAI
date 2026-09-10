import { Platform } from "react-native";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";
import { devicesApi } from "@/lib/api";
export function notificationPath(data: Record<string, unknown>) {
  if (data.alert_id) return `/(citizen)/alerts/${data.alert_id}`;
  if (data.report_id) return `/(citizen)/reports/${data.report_id}`;
  if (data.task_id) return `/(responder)/tasks/${data.task_id}`;
  if (data.incident_id) return `/(citizen)/incidents/${data.incident_id}`;
  return "/";
}
export async function registerPush(userId: string) {
  if (!Device.isDevice)
    return {
      configured: false,
      reason: "A physical development/native build is required.",
    };
  const current = await Notifications.getPermissionsAsync();
  const permission = current.granted
    ? current
    : await Notifications.requestPermissionsAsync();
  if (!permission.granted)
    return {
      configured: false,
      reason: "Notification permission was not granted.",
    };
  if (Platform.OS === "android")
    await Notifications.setNotificationChannelAsync("emergency", {
      name: "Emergency alerts",
      importance: Notifications.AndroidImportance.MAX,
    });
  const projectId =
    process.env.EXPO_PUBLIC_EAS_PROJECT_ID ||
    Constants.expoConfig?.extra?.eas?.projectId;
  if (!projectId)
    return {
      configured: false,
      reason: "EAS project/FCM configuration is missing.",
    };
  const result = await Notifications.getExpoPushTokenAsync({ projectId });
  const deviceId = `${Platform.OS}-${userId}`;
  await devicesApi.register({
    token: result.data,
    device_os: Platform.OS,
    device_id: deviceId,
  });
  return { configured: true, token: result.data, deviceId };
}
export function configureForegroundNotifications() {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: false,
      shouldSetBadge: true,
    }),
  });
}
