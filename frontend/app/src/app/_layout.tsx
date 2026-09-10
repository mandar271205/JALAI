import React, { useEffect } from 'react';
import '../global.css';

import { Stack } from 'expo-router';
import { PortalHost } from '@rn-primitives/portal';
import * as SplashScreen from 'expo-splash-screen';
import { registerPushDeviceToken } from '@/lib/api';
import { SosModal } from '@/components/shared/sos-modal';
import { SafetyTerminalModal } from '@/components/shared/safety-terminal-modal';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  useEffect(() => {
    SplashScreen.hideAsync().catch(() => {
      /* ignore if already dismissed */
    });

    // Automatically register citizen's emergency broadcast push token with backend
    registerPushDeviceToken('ExponentPushToken[mumbai-citizen-emergency-broadcast-device-token]').catch(() => {
      // Ignore background registration errors
    });
  }, []);

  return (
    <>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen
          name="(tabs)"
          options={{ headerShown: false }}
        />
      </Stack>

      {/* Global Emergency Modals accessible from any screen */}
      <SosModal />
      <SafetyTerminalModal />

      <PortalHost />
    </>
  );
}