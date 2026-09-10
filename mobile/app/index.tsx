import { Redirect } from "expo-router";
import { ActivityIndicator, View } from "react-native";
import { colors } from "@/lib/theme";
import { useSession } from "@/store/session";
export default function Index() {
  const { hydrated, session } = useSession();
  if (!hydrated)
    return (
      <View
        style={{
          flex: 1,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: colors.canvas,
        }}
      >
        <ActivityIndicator color={colors.teal} />
      </View>
    );
  if (!session) return <Redirect href="/(auth)/login" />;
  return (
    <Redirect
      href={
        session.role === "FIELD_RESPONDER"
          ? "/(responder)/dashboard"
          : "/(citizen)/(tabs)/home"
      }
    />
  );
}
