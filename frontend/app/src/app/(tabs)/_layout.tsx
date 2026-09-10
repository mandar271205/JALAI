import React from 'react';
import { Tabs } from 'expo-router';
import { BottomNav, type TabKey } from '@/components/shared/bottom-nav';

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
      }}
      tabBar={(props) => {
        const routeName = props.state.routes[props.state.index].name as TabKey;
        return (
          <BottomNav
            currentTab={routeName}
            unreadAlertsCount={3}
            onTabSelect={(tabKey) => {
              props.navigation.navigate(tabKey);
            }}
          />
        );
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Home' }} />
      <Tabs.Screen name="radar" options={{ title: 'Radar' }} />
      <Tabs.Screen name="alerts" options={{ title: 'Alerts' }} />
      <Tabs.Screen name="report" options={{ title: 'Report' }} />
      <Tabs.Screen name="safety" options={{ title: 'Safety' }} />
    </Tabs>
  );
}
