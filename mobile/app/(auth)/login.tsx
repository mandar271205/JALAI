import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { Eye, EyeOff, ShieldCheck } from "lucide-react-native";
import { Button, FieldLabel, Screen, Unavailable } from "@/components/ui";
import { colors } from "@/lib/theme";
import { loginSchema } from "@/lib/validation/forms";
import { useSession } from "@/store/session";
import type { UserRole } from "@/types";
import { z } from "zod";
type Form = z.infer<typeof loginSchema>;
export default function Login() {
  const router = useRouter();
  const signIn = useSession((s) => s.signIn);
  const [hidden, setHidden] = useState(true);
  const [error, setError] = useState("");
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
    setValue,
    watch,
  } = useForm<Form>({
    resolver: zodResolver(loginSchema),
    defaultValues: { identifier: "", password: "", role: "CITIZEN" },
  });
  const role = watch("role");
  const submit = handleSubmit(async (v) => {
    try {
      setError("");
      await signIn(v);
      router.replace(
        v.role === "FIELD_RESPONDER"
          ? "/(responder)/dashboard"
          : "/(citizen)/(tabs)/home",
      );
    } catch (e) {
      setError((e as Error).message);
    }
  });
  const mock = process.env.EXPO_PUBLIC_AUTH_MODE === "mock";
  return (
    <Screen
      title="JalRakshak AI"
      subtitle="Trusted flood intelligence for citizens and response teams."
    >
      <View style={s.brand}>
        <View style={s.logo}>
          <ShieldCheck color="#fff" size={30} />
        </View>
        <Text style={s.brandText}>Sign in securely</Text>
      </View>
      {!mock ? (
        <Unavailable
          title="Identity provider setup required"
          detail="The backend validates bearer tokens but does not issue them. Configure the production identity flow before sign-in can be enabled."
        />
      ) : (
        <>
          <View style={s.notice}>
            <Text style={s.noticeText}>
              LOCAL DEVELOPMENT MODE · identity is simulated by
              backend-supported mock headers.
            </Text>
          </View>
          <FieldLabel>Email or identifier</FieldLabel>
          <Controller
            control={control}
            name="identifier"
            render={({ field }) => (
              <TextInput
                accessibilityLabel="Email or identifier"
                autoCapitalize="none"
                value={field.value}
                onBlur={field.onBlur}
                onChangeText={field.onChange}
                style={s.input}
                placeholder="citizen@example.org"
              />
            )}
          />
          {errors.identifier ? (
            <Text style={s.error}>{errors.identifier.message}</Text>
          ) : null}
          <FieldLabel>Password</FieldLabel>
          <View style={s.password}>
            <Controller
              control={control}
              name="password"
              render={({ field }) => (
                <TextInput
                  accessibilityLabel="Password"
                  secureTextEntry={hidden}
                  value={field.value}
                  onBlur={field.onBlur}
                  onChangeText={field.onChange}
                  style={[s.input, { flex: 1, borderWidth: 0 }]}
                  placeholder="••••••••"
                />
              )}
            />
            <Pressable
              accessibilityLabel={hidden ? "Show password" : "Hide password"}
              onPress={() => setHidden((v) => !v)}
            >
              {hidden ? (
                <Eye size={20} color={colors.muted} />
              ) : (
                <EyeOff size={20} color={colors.muted} />
              )}
            </Pressable>
          </View>
          {errors.password ? (
            <Text style={s.error}>{errors.password.message}</Text>
          ) : null}
          <FieldLabel>Experience</FieldLabel>
          <View style={s.roles}>
            {(["CITIZEN", "FIELD_RESPONDER"] as UserRole[]).map((r) => (
              <Pressable
                key={r}
                onPress={() => setValue("role", r)}
                style={[s.role, role === r && s.roleActive]}
              >
                <Text style={[s.roleText, role === r && s.roleTextActive]}>
                  {r === "CITIZEN" ? "Citizen" : "Field responder"}
                </Text>
              </Pressable>
            ))}
          </View>
          {error ? (
            <Text accessibilityRole="alert" style={s.error}>
              {error}
            </Text>
          ) : null}
          <Button
            disabled={isSubmitting}
            label={isSubmitting ? "Signing in…" : "Continue"}
            onPress={() => void submit()}
          />
        </>
      )}
    </Screen>
  );
}
const s = StyleSheet.create({
  brand: { alignItems: "center", gap: 10, marginVertical: 12 },
  logo: {
    width: 62,
    height: 62,
    borderRadius: 20,
    backgroundColor: colors.teal,
    alignItems: "center",
    justifyContent: "center",
  },
  brandText: { color: colors.ink, fontSize: 18, fontWeight: "800" },
  notice: { backgroundColor: "#FFF8E7", borderRadius: 12, padding: 11 },
  noticeText: { color: colors.moderate, fontSize: 11, fontWeight: "700" },
  input: {
    minHeight: 50,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    paddingHorizontal: 14,
    color: colors.ink,
  },
  password: {
    minHeight: 50,
    flexDirection: "row",
    alignItems: "center",
    borderRadius: 13,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.surface,
    paddingRight: 14,
  },
  roles: { flexDirection: "row", gap: 10 },
  role: {
    flex: 1,
    minHeight: 46,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 13,
    alignItems: "center",
    justifyContent: "center",
  },
  roleActive: { backgroundColor: colors.aqua, borderColor: colors.teal },
  roleText: { color: colors.muted, fontWeight: "700" },
  roleTextActive: { color: colors.teal },
  error: { color: colors.severe, fontSize: 12 },
});
