import React from 'react';
import { View, ScrollView } from 'react-native';
import { 
  Construction, 
  Database, 
  Layers, 
  ArrowRight,
  CheckCircle2,
  Sparkles
} from 'lucide-react-native';

import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Text } from '@/components/ui/text';
import { Button } from '@/components/ui/button';

interface PendingScreenProps {
  title: string;
  badgeText: string;
  badgeVariant?: 'default' | 'destructive' | 'secondary' | 'outline';
  description: string;
  plannedFeatures: string[];
  backendEndpoints: string[];
  onExplorePreview?: () => void;
}

export function PendingScreen({
  title,
  badgeText,
  badgeVariant = 'outline',
  description,
  plannedFeatures,
  backendEndpoints,
  onExplorePreview,
}: PendingScreenProps) {
  return (
    <ScrollView className="flex-1 bg-[#070D18] px-4 py-4" contentContainerStyle={{ paddingBottom: 40 }}>
      {/* Top Banner */}
      <View className="mb-4">
        <View className="flex-row items-center gap-2 mb-1.5">
          <Badge variant={badgeVariant} className="border-cyan-500/40 text-cyan-400">
            {badgeText}
          </Badge>
          <Badge variant="secondary" className="bg-slate-800 text-slate-300">
            Phase 2 Pipeline
          </Badge>
        </View>
        <Text className="text-2xl font-black text-white tracking-tight">
          {title}
        </Text>
        <Text className="text-xs text-slate-400 mt-1 leading-relaxed">
          {description}
        </Text>
      </View>

      {/* Pending Implementation Notice Card */}
      <Card className="border-amber-500/40 bg-amber-950/10 mb-4">
        <CardHeader className="pb-2">
          <View className="flex-row items-center gap-2">
            <Construction size={18} color="#F59E0B" />
            <Text className="text-amber-400 font-bold text-sm">
              Layout Planned • Implementation In Progress
            </Text>
          </View>
          <CardDescription className="text-slate-300 text-xs mt-1">
            This module interface is scheduled in the phased execution plan. Tab navigation, state wiring, and backend contracts are pre-mapped below.
          </CardDescription>
        </CardHeader>
      </Card>

      {/* Planned Features List */}
      <Card className="bg-[#0B1324] border-slate-800 mb-4">
        <CardHeader className="pb-2">
          <View className="flex-row items-center gap-2">
            <Layers size={18} color="#38BDF8" />
            <CardTitle className="text-base text-white">Planned UI/UX Modules</CardTitle>
          </View>
        </CardHeader>
        <CardContent className="pt-1 flex flex-col gap-2.5">
          {plannedFeatures.map((feature, idx) => (
            <View key={idx} className="flex-row items-start gap-2.5">
              <CheckCircle2 size={16} color="#0EA5E9" className="mt-0.5" />
              <Text className="text-xs text-slate-200 flex-1 leading-relaxed font-medium">
                {feature}
              </Text>
            </View>
          ))}
        </CardContent>
      </Card>

      {/* Connected Backend Endpoints */}
      <Card className="bg-[#0B1324] border-slate-800 mb-4">
        <CardHeader className="pb-2">
          <View className="flex-row items-center gap-2">
            <Database size={18} color="#10B981" />
            <CardTitle className="text-base text-white">Mapped Backend API Endpoints</CardTitle>
          </View>
        </CardHeader>
        <CardContent className="pt-1 flex flex-col gap-2">
          {backendEndpoints.map((endpoint, idx) => (
            <View key={idx} className="bg-slate-900/90 border border-slate-800 p-2.5 rounded-lg flex-row items-center justify-between">
              <Text className="text-xs font-mono font-bold text-emerald-400">
                {endpoint}
              </Text>
              <Badge variant="outline" className="border-emerald-500/40 text-[10px] text-emerald-300">
                Contract Mapped
              </Badge>
            </View>
          ))}
        </CardContent>
      </Card>

      {/* Quick Action */}
      {onExplorePreview && (
        <Button 
          onPress={onExplorePreview} 
          className="bg-cyan-600 active:bg-cyan-700 w-full"
        >
          <View className="flex-row items-center justify-center gap-2">
            <Sparkles size={16} color="#FFFFFF" />
            <Text className="text-white font-bold text-xs">Preview Design Mock</Text>
          </View>
        </Button>
      )}
    </ScrollView>
  );
}
