import React from 'react';
import { View, Pressable, Image } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ShieldAlert, Radio } from 'lucide-react-native';

import { Text } from '@/components/ui/text';
import { emergencyStore } from '@/lib/emergency-store';

interface AppHeaderProps {
  location?: string;
  onDistressPress?: () => void;
  onProfilePress?: () => void;
}

export function AppHeader({
  location = 'Koramangala, BLR • GPS Active',
  onDistressPress = () => emergencyStore.openSos(),
  onProfilePress = () => emergencyStore.openTerminal(),
}: AppHeaderProps) {
  const insets = useSafeAreaInsets();

  return (
    <View
      style={{ paddingTop: Math.max(insets.top + 8, 20) }}
      className="bg-[#080E1A] px-5 pb-3.5 border-b border-slate-800/80 flex-row items-center justify-between"
    >
      {/* Brand & Operational GPS Status (Constrained so it never overflows) */}
      <View className="flex-row items-center gap-3 flex-1 mr-3 min-w-0">
        {/* Shield Icon Box */}
        <View className="w-10 h-10 rounded-xl bg-cyan-950/70 border border-cyan-500/40 items-center justify-center flex-shrink-0">
          <ShieldAlert size={20} color="#38BDF8" />
        </View>

        <View className="flex-1 min-w-0">
          <View className="flex-row items-center gap-2">
            <Text className="text-lg font-black tracking-tight text-white">
              JALAI
            </Text>
            <View className="bg-emerald-500/20 border border-emerald-500/40 px-2 py-0.5 rounded-full flex-shrink-0">
              <Text className="text-[10px] font-black tracking-wider text-emerald-300 uppercase">
                ONLINE
              </Text>
            </View>
          </View>

          {/* Location Beacon with Text Ellipsis */}
          <View className="flex-row items-center gap-1.5 mt-0.5">
            <View className="w-2 h-2 rounded-full bg-cyan-400 flex-shrink-0" />
            <Text 
              numberOfLines={1} 
              ellipsizeMode="tail" 
              className="text-xs font-semibold text-slate-400 flex-1"
            >
              {location}
            </Text>
          </View>
        </View>
      </View>

      {/* Right Controls: Fixed width, never squished or pushed off screen */}
      <View className="flex-row items-center gap-2.5 flex-shrink-0">
        {/* Distress Ping Beacon */}
        <Pressable
          onPress={onDistressPress}
          accessibilityLabel="Broadcast SOS Distress Ping"
          className="w-10 h-10 rounded-full bg-rose-950/60 border border-rose-500/50 items-center justify-center active:scale-95"
        >
          <Radio size={19} color="#FB7185" />
        </Pressable>

        {/* User Profile Avatar with Operational Indicator */}
        <Pressable
          onPress={onProfilePress}
          className="relative active:scale-95"
        >
          <View className="w-10 h-10 rounded-full bg-slate-800 border border-slate-700 items-center justify-center overflow-hidden">
            <Image
              source={{ uri: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80' }}
              className="w-full h-full"
              resizeMode="cover"
            />
          </View>
          <View className="absolute bottom-0 right-0 w-3 h-3 rounded-full bg-emerald-500 border-2 border-[#080E1A]" />
        </Pressable>
      </View>
    </View>
  );
}

