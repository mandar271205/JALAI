import React from 'react';
import { View, Pressable } from 'react-native';
import { 
  LayoutGrid, 
  Radar as RadarIcon, 
  AlertTriangle, 
  Camera, 
  ShieldCheck 
} from 'lucide-react-native';

import { Text } from '@/components/ui/text';

export type TabKey = 'index' | 'radar' | 'alerts' | 'report' | 'safety';

interface BottomNavProps {
  currentTab: TabKey;
  onTabSelect: (tab: TabKey) => void;
  unreadAlertsCount?: number;
}

interface TabItemConfig {
  key: TabKey;
  label: string;
  Icon: React.ComponentType<{ size: number; color: string }>;
  hasBadge?: boolean;
}

const TABS: TabItemConfig[] = [
  { key: 'index', label: 'Home', Icon: LayoutGrid },
  { key: 'radar', label: 'Radar', Icon: RadarIcon },
  { key: 'alerts', label: 'Alerts', Icon: AlertTriangle, hasBadge: true },
  { key: 'report', label: 'Report', Icon: Camera },
  { key: 'safety', label: 'Safety', Icon: ShieldCheck },
];

export function BottomNav({
  currentTab,
  onTabSelect,
  unreadAlertsCount = 3,
}: BottomNavProps) {
  return (
    <View className="bg-[#0B111E] border-t border-[#1E293B] px-3 pt-2 pb-5 flex-row items-center justify-around shadow-lg shadow-black/80">
      {TABS.map((tab) => {
        const isActive = currentTab === tab.key;
        const IconComponent = tab.Icon;
        const color = isActive ? '#38BDF8' : '#64748B';

        return (
          <Pressable
            key={tab.key}
            onPress={() => onTabSelect(tab.key)}
            className="items-center justify-center flex-1 py-1 active:opacity-75"
          >
            <View className="relative items-center justify-center">
              <IconComponent size={22} color={color} />

              {/* Notification Badge on Alerts */}
              {tab.hasBadge && unreadAlertsCount > 0 && (
                <View className="absolute -top-1.5 -right-2 bg-red-500 rounded-full px-1 min-w-[15px] h-[15px] items-center justify-center border border-[#0B111E]">
                  <Text className="text-[9px] font-black text-white text-center leading-none">
                    {unreadAlertsCount}
                  </Text>
                </View>
              )}
            </View>

            <Text
              className={`text-[10px] font-bold mt-1 tracking-tight ${
                isActive ? 'text-cyan-400 font-extrabold' : 'text-slate-400'
              }`}
            >
              {tab.label}
            </Text>

            {/* Subtle Active Indicator Bar */}
            {isActive && (
              <View className="w-4 h-0.5 bg-cyan-400 rounded-full mt-0.5" />
            )}
          </Pressable>
        );
      })}
    </View>
  );
}
