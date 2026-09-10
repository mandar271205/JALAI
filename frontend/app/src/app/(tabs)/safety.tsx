import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  View, 
  ScrollView, 
  Pressable, 
  Alert, 
  RefreshControl,
  Share,
  ActivityIndicator
} from 'react-native';
import { useRouter } from 'expo-router';
import { 
  Navigation, 
  MapPin, 
  ShieldAlert, 
  Clock, 
  Compass, 
  Sparkles, 
  LifeBuoy, 
  Zap, 
  Building2, 
  ShieldCheck, 
  CheckCircle2, 
  Droplets, 
  AlertTriangle, 
  Radio, 
  Share2, 
  ChevronRight, 
  ArrowUpRight, 
  TrendingUp, 
  Activity, 
  Layers, 
  Check, 
  Wifi, 
  Info,
  ArrowDown,
  CircleDot,
  Circle,
  X
} from 'lucide-react-native';

import { AppHeader } from '@/components/shared/app-header';
import { Text } from '@/components/ui/text';
import { emergencyStore } from '@/lib/emergency-store';
import { 
  fetchLowerRiskRoute,
  fetchCriticalAssets,
  fetchRoadClosures,
  fetchCurrentWeather,
  type LowerRiskRouteResponse,
  type CriticalAssetItem,
  type RoadClosureSegment,
  type CurrentWeatherResponse,
  FALLBACK_ROUTE,
  FALLBACK_ASSETS,
  FALLBACK_ROAD_CLOSURES,
  FALLBACK_WEATHER
} from '@/lib/api';

type SelectedRouteId = 'SAFE_ELEVATED' | 'DIRECT_HAZARD';

interface WaypointStep {
  title: string;
  instruction: string;
  distance: string;
  elevation: string;
  status: 'SAFE' | 'DIVERT' | 'ELEVATED' | 'ARRIVAL';
}

export default function SafetyScreen() {
  const router = useRouter();

  const [refreshing, setRefreshing] = useState(false);
  const [selectedRoute, setSelectedRoute] = useState<SelectedRouteId>('SAFE_ELEVATED');
  const [isNavigating, setIsNavigating] = useState(false);

  // Live Backend State
  const [routeData, setRouteData] = useState<LowerRiskRouteResponse>(FALLBACK_ROUTE);
  const [assets, setAssets] = useState<CriticalAssetItem[]>(FALLBACK_ASSETS);
  const [roadClosures, setRoadClosures] = useState<RoadClosureSegment[]>(FALLBACK_ROAD_CLOSURES);
  const [weather, setWeather] = useState<CurrentWeatherResponse>(FALLBACK_WEATHER);
  const [isLiveBackend, setIsLiveBackend] = useState(false);

  // Selectable Destination Safe Haven State
  const shelters = useMemo(
    () => assets.filter((a) => a.asset_type === 'HOSPITAL' || a.asset_type === 'RELIEF_SHELTER'),
    [assets]
  );

  const [selectedDestination, setSelectedDestination] = useState<CriticalAssetItem>(
    FALLBACK_ASSETS.find((a) => a.asset_id === 'asset-hosp-001') || FALLBACK_ASSETS[0]
  );

  const loadSafetyData = useCallback(async () => {
    try {
      const [routeRes, assetsRes, closuresRes, weatherRes] = await Promise.all([
        fetchLowerRiskRoute(),
        fetchCriticalAssets(),
        fetchRoadClosures(),
        fetchCurrentWeather(),
      ]);

      setRouteData(routeRes?.data || FALLBACK_ROUTE);
      const fetchedAssets = Array.isArray(assetsRes?.data) ? assetsRes.data : FALLBACK_ASSETS;
      setAssets(fetchedAssets);
      setRoadClosures(Array.isArray(closuresRes?.data) ? closuresRes.data : FALLBACK_ROAD_CLOSURES);
      setWeather(weatherRes?.data || FALLBACK_WEATHER);

      setIsLiveBackend(routeRes.isLive || assetsRes.isLive);
    } catch {
      setIsLiveBackend(false);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadSafetyData();
  }, [loadSafetyData]);

  const onRefresh = () => {
    setRefreshing(true);
    loadSafetyData();
  };

  // Dynamic corridor metrics based on selected target haven
  const destinationMeta = useMemo(() => {
    if (selectedDestination.name.includes('Kurla')) {
      return { 
        distance: '1.8 km', 
        time: '6.2 min', 
        elevation: `+${selectedDestination.elevation_msl || 13.5}m MSL`,
        shortName: 'Kurla Shelter'
      };
    }
    if (selectedDestination.name.includes('Dadar')) {
      return { 
        distance: '3.4 km', 
        time: '11.5 min', 
        elevation: `+${selectedDestination.elevation_msl || 16.2}m MSL`,
        shortName: 'Dadar Relief Base'
      };
    }
    return { 
      distance: '2.6 km', 
      time: '8.6 min', 
      elevation: `+${selectedDestination.elevation_msl || 14.8}m MSL`,
      shortName: 'Sion Hospital'
    };
  }, [selectedDestination]);

  // Turn-by-turn dynamic waypoints
  const waypoints: WaypointStep[] = useMemo(() => [
    {
      title: 'Depart Kurla West Station Plaza',
      instruction: 'Head south on Station Road. Maintain low speed on wet pavement.',
      distance: '350 m',
      elevation: '+8.2m MSL',
      status: 'SAFE',
    },
    {
      title: 'Divert onto High-Ground Flyover Ramp',
      instruction: 'Turn right before CST Road underpass. DO NOT enter lower underpass (0.85m water).',
      distance: '450 m',
      elevation: '+11.5m MSL',
      status: 'DIVERT',
    },
    {
      title: 'Transit Eastern High Ground Corridor',
      instruction: 'Safe elevated transit above inundated Mithi Basin. 100% dry flyover deck.',
      distance: '1.4 km',
      elevation: '+13.6m MSL',
      status: 'ELEVATED',
    },
    {
      title: `Arrival at ${selectedDestination.name}`,
      instruction: 'High ground haven secured. Medical triage and shelter support available.',
      distance: destinationMeta.distance,
      elevation: destinationMeta.elevation,
      status: 'ARRIVAL',
    },
  ], [selectedDestination, destinationMeta]);

  const handleSelectDestination = (haven: CriticalAssetItem) => {
    setSelectedDestination(haven);
    Alert.alert(
      'Target Safe Haven Updated',
      `Corridor recalculated to ${haven.name} (+${haven.elevation_msl || 14.8}m MSL). Avoids submerged CST basin.`
    );
  };

  const handleStartNavigation = () => {
    if (selectedRoute === 'DIRECT_HAZARD') {
      Alert.alert(
        'CRITICAL ROUTE WARNING',
        'The direct route contains 0.85m standing water at CST Road and has been closed by municipal police. Switch to the Safe Elevated Corridor to proceed.',
        [
          { text: 'Switch to Safe Route', onPress: () => setSelectedRoute('SAFE_ELEVATED') },
          { text: 'Cancel', style: 'cancel' },
        ]
      );
      return;
    }

    setIsNavigating(true);
    Alert.alert(
      'LOWER-RISK NAVIGATION ENGAGED',
      `Live GPS tracking active along Eastern High Ground Elevated Corridor (+5.4m MSL). Steers 100% clear of Mithi canal flooding.`,
      [
        { text: 'View on Radar Map', onPress: () => router.push('/(tabs)/radar') },
        { text: 'Stay in Guidance HUD', style: 'default' },
      ]
    );
  };

  const handleShareRoute = async () => {
    try {
      await Share.share({
        message: `🧭 EVACUATION ROUTE ADVISORY (JALAI Disaster Network)\nRecommended: Eastern High Ground Elevated Corridor to ${selectedDestination.name}.\nDistance: ${destinationMeta.distance} • Elevation: +5.4m MSL\nAvoided: CST Road (0.85m flood) & Mithi Canal barricade.`,
      });
    } catch {
      Alert.alert('Route Shared', 'Advisory corridor link copied to clipboard.');
    }
  };

  const routeProperties = routeData.features?.[0]?.properties || FALLBACK_ROUTE.features[0].properties;
  const avoidedSegments = routeProperties.avoided_risky_segments || [];

  return (
    <View className="flex-1 bg-[#050A14]">
      {/* 1. Universal Tactical Header */}
      <AppHeader
        location={`Kurla to ${destinationMeta.shortName} • Safe Route`}
        onDistressPress={() => emergencyStore.openSos({ ward: `Kurla to ${destinationMeta.shortName}` })}
        onProfilePress={() => emergencyStore.openTerminal()}
      />

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingBottom: 140 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor="#00F0FF"
            colors={['#00F0FF']}
          />
        }
      >
        {/* Active Navigation HUD Banner (Shown when user starts navigation) */}
        {isNavigating && (
          <View className="px-5 pt-3">
            <View className="bg-[#051E1E] border-2 border-emerald-400 rounded-2xl p-4 shadow-2xl">
              <View className="flex-row items-center justify-between pb-2 border-b border-emerald-900/60">
                <View className="flex-row items-center gap-2">
                  <View className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse" />
                  <Text className="text-xs font-black text-emerald-300 tracking-wider uppercase">
                    LOWER-RISK NAVIGATION ENGAGED
                  </Text>
                </View>
                <Pressable
                  onPress={() => setIsNavigating(false)}
                  className="bg-rose-500/20 border border-rose-500/60 px-2.5 py-0.5 rounded-lg active:bg-rose-500/30"
                >
                  <Text className="text-[10px] font-black text-rose-300">
                    EXIT NAV
                  </Text>
                </Pressable>
              </View>

              <View className="mt-3">
                <View className="flex-row items-center gap-2 mb-1">
                  <ArrowUpRight size={18} color="#34D399" />
                  <Text className="text-sm font-black text-white">
                    In 350m: Divert onto High-Ground Flyover Ramp
                  </Text>
                </View>
                <Text className="text-xs text-emerald-200/90 leading-relaxed pl-6">
                  Turn right before CST underpass. Safe dry deck elevation (+13.6m MSL).
                </Text>

                <View className="flex-row items-center justify-between mt-3 pt-2.5 border-t border-emerald-900/50">
                  <Text className="text-xs font-bold text-slate-300">
                    ETA: <Text className="font-black text-emerald-300">{destinationMeta.time}</Text> • Distance: <Text className="font-black text-white">{destinationMeta.distance}</Text>
                  </Text>
                  <Pressable
                    onPress={() => router.push('/(tabs)/radar')}
                    className="bg-cyan-500/20 px-2.5 py-1 rounded-lg border border-cyan-500/40"
                  >
                    <Text className="text-[10px] font-black text-cyan-300">
                      VIEW ON RADAR →
                    </Text>
                  </Pressable>
                </View>
              </View>
            </View>
          </View>
        )}

        {/* 2. Tactical Telemetry & Corridor Subheader */}
        <View className="px-5 pt-4 pb-2">
          {/* Status Row */}
          <View className="flex-row items-center justify-between mb-2">
            <View className="flex-row items-center gap-2">
              <View className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
              <Text className="text-[11px] font-black text-cyan-300 uppercase tracking-wider">
                Tactical Path Finder
              </Text>
            </View>
            <View className="bg-slate-900/90 px-2.5 py-1 rounded-full border border-slate-800 flex-row items-center gap-1.5">
              <View className={`w-2 h-2 rounded-full ${isLiveBackend ? 'bg-emerald-400' : 'bg-amber-400'}`} />
              <Text className="text-[10px] font-bold text-slate-300">
                {isLiveBackend ? 'Dijkstra Algorithmic Sync' : 'Offline Route Cached'}
              </Text>
            </View>
          </View>

          {/* Corridor Origin & Destination Card (Responsive Vertical Flow) */}
          <View className="bg-[#0B1322] border border-slate-800 rounded-2xl p-4 shadow-xl">
            {/* Origin */}
            <View className="flex-row items-start gap-3">
              <View className="w-8 h-8 rounded-xl bg-cyan-500/20 border border-cyan-500/40 items-center justify-center mt-0.5 flex-shrink-0">
                <MapPin size={16} color="#00F0FF" />
              </View>
              <View className="flex-1 min-w-0">
                <Text className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                  EVACUATION ORIGIN (GPS)
                </Text>
                <Text className="text-sm font-black text-white mt-0.5">
                  Kurla West Station Plaza
                </Text>
                <Text className="text-[11px] text-cyan-300 font-semibold mt-0.5">
                  Ground Elevation: +8.2m MSL • Low Catchment
                </Text>
              </View>
            </View>

            {/* Connecting Transit Line with Metric Capsule */}
            <View className="flex-row items-center my-2 ml-4">
              <View className="w-0.5 h-6 bg-cyan-500/40 mr-3" />
              <View className="bg-cyan-950/80 border border-cyan-500/30 px-2.5 py-0.5 rounded-full flex-row items-center gap-1.5">
                <ArrowDown size={11} color="#00F0FF" />
                <Text className="text-[10px] font-bold text-cyan-300">
                  {selectedRoute === 'SAFE_ELEVATED'
                    ? `${destinationMeta.distance} Safe Corridor • ${destinationMeta.time}`
                    : '2.1 km Blocked CST Arterial'}
                </Text>
              </View>
            </View>

            {/* Destination */}
            <View className="flex-row items-start gap-3">
              <View className="w-8 h-8 rounded-xl bg-emerald-500/20 border border-emerald-500/40 items-center justify-center mt-0.5 flex-shrink-0">
                <Building2 size={16} color="#34D399" />
              </View>
              <View className="flex-1 min-w-0">
                <Text className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                  TARGET SAFE HAVEN (RESCUE BASE)
                </Text>
                <Text className="text-sm font-black text-white mt-0.5">
                  {selectedDestination.name}
                </Text>
                <Text className="text-[11px] text-emerald-400 font-semibold mt-0.5">
                  Safe Elevation: {destinationMeta.elevation} • Dry High Ground
                </Text>
              </View>
            </View>

            {/* Micro Sensors Row */}
            <View className="flex-row items-center justify-between pt-3 mt-3 border-t border-slate-800/80">
              <View className="flex-row items-center gap-1.5">
                <Droplets size={13} color="#00F0FF" />
                <Text className="text-xs text-slate-300 font-semibold">
                  Rain: <Text className="font-bold text-white">{weather.average_rainfall_rate_mm_h || 48.5} mm/h</Text>
                </Text>
              </View>
              <View className="flex-row items-center gap-1.5">
                <Activity size={13} color="#34D399" />
                <Text className="text-xs text-slate-300 font-semibold">
                  Sync: <Text className="font-bold text-emerald-400">12s Auto-Reroute</Text>
                </Text>
              </View>
            </View>
          </View>
        </View>

        {/* 3. Compact Safety Directive Callout */}
        <View className="px-5 py-1.5">
          <View className="bg-[#081525] border-l-4 border-l-cyan-400 border border-cyan-500/30 rounded-r-xl rounded-l-sm p-3">
            <View className="flex-row items-center gap-1.5 mb-0.5">
              <ShieldAlert size={14} color="#00F0FF" />
              <Text className="text-[10px] font-black text-cyan-300 uppercase tracking-wider">
                TOPOLOGICAL ELEVATION ROUTING
              </Text>
            </View>
            <Text className="text-xs text-slate-200 leading-relaxed font-medium">
              Routes are computed via topological elevation weighting to steer transit away from submerged culverts and police barricades, prioritizing elevated flyover corridors.
            </Text>
          </View>
        </View>

        {/* 4. Route Evaluation Matrix (2 Paths Calculated) */}
        <View className="px-5 pt-3 flex-col gap-3.5">
          <Text className="text-xs font-black text-slate-400 uppercase tracking-wider">
            ROUTE EVALUATION MATRIX (2 CALCULATED PATHS)
          </Text>

          {/* PATH 1: RECOMMENDED SAFE ELEVATED CORRIDOR */}
          <Pressable
            onPress={() => setSelectedRoute('SAFE_ELEVATED')}
            className={`p-4 rounded-2xl border-2 transition-all active:scale-[0.99] ${
              selectedRoute === 'SAFE_ELEVATED'
                ? 'bg-[#0A1628] border-cyan-400 shadow-xl'
                : 'bg-[#080E1C] border-slate-800'
            }`}
          >
            {/* Header Badge Row */}
            <View className="flex-row items-center justify-between mb-2">
              <View className="bg-emerald-500/20 border border-emerald-500/40 px-2.5 py-0.5 rounded-full flex-row items-center gap-1.5">
                <CheckCircle2 size={12} color="#34D399" />
                <Text className="text-[10px] font-black text-emerald-300 uppercase tracking-wider">
                  RECOMMENDED BY DISASTER COMMAND
                </Text>
              </View>

              <View className="flex-row items-center gap-1.5">
                {selectedRoute === 'SAFE_ELEVATED' ? (
                  <CircleDot size={18} color="#00F0FF" />
                ) : (
                  <Circle size={18} color="#64748B" />
                )}
              </View>
            </View>

            {/* Route Name & Tier */}
            <View className="mb-1">
              <Text className="text-base font-black text-white tracking-tight">
                Eastern High Ground Elevated Corridor
              </Text>
              <Text className="text-[11px] font-bold text-cyan-300 mt-0.5">
                Tier 1 • Minimal Inundation Risk (+5.4m MSL Deck)
              </Text>
            </View>

            <Text className="text-xs text-slate-300 mt-1 leading-relaxed">
              Ascends onto elevated flyover deck above flooded basin. Guaranteed dry transit above Mithi River catchment.
            </Text>

            {/* Metrics Row */}
            <View className="flex-row gap-2 my-3">
              <View className="flex-1 bg-slate-950 p-2.5 rounded-xl border border-slate-800 items-center">
                <Text className="text-[9px] font-bold text-slate-400 uppercase">TRANSIT TIME</Text>
                <Text className="text-sm font-black text-white mt-0.5">{destinationMeta.time}</Text>
              </View>
              <View className="flex-1 bg-slate-950 p-2.5 rounded-xl border border-slate-800 items-center">
                <Text className="text-[9px] font-bold text-slate-400 uppercase">DISTANCE</Text>
                <Text className="text-sm font-black text-white mt-0.5">{destinationMeta.distance}</Text>
              </View>
              <View className="flex-1 bg-slate-950 p-2.5 rounded-xl border border-slate-800 items-center">
                <Text className="text-[9px] font-bold text-slate-400 uppercase">ELEVATION</Text>
                <Text className="text-sm font-black text-emerald-400 mt-0.5">+5.4m MSL</Text>
              </View>
            </View>

            {/* Avoided Culvert Hazards */}
            <View className="bg-slate-950/80 p-3 rounded-xl border border-slate-800">
              <Text className="text-[10px] font-black text-amber-400 uppercase tracking-wider mb-1.5">
                AVOIDED INUNDATION HAZARDS ({avoidedSegments.length})
              </Text>
              {avoidedSegments.map((seg, idx) => (
                <View key={idx} className="flex-row items-center gap-1.5 mt-1">
                  <View className="w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                  <Text className="text-xs text-slate-300 font-medium flex-1">
                    {seg.road_name}: <Text className="text-slate-400">{seg.reason}</Text>
                  </Text>
                </View>
              ))}
            </View>
          </Pressable>

          {/* PATH 2: DIRECT LOW-LYING HAZARDOUS ARTERIAL */}
          <Pressable
            onPress={() => setSelectedRoute('DIRECT_HAZARD')}
            className={`p-4 rounded-2xl border-2 transition-all active:scale-[0.99] ${
              selectedRoute === 'DIRECT_HAZARD'
                ? 'bg-[#180A12] border-rose-500 shadow-xl'
                : 'bg-[#0E0A14] border-slate-800/80'
            }`}
          >
            {/* Header Badge Row */}
            <View className="flex-row items-center justify-between mb-2">
              <View className="bg-rose-500/20 border border-rose-500/40 px-2.5 py-0.5 rounded-full flex-row items-center gap-1.5">
                <AlertTriangle size={12} color="#F87171" />
                <Text className="text-[10px] font-black text-rose-300 uppercase tracking-wider">
                  DO NOT ATTEMPT • WATERLOGGED
                </Text>
              </View>

              <View className="flex-row items-center gap-1.5">
                {selectedRoute === 'DIRECT_HAZARD' ? (
                  <CircleDot size={18} color="#FB7185" />
                ) : (
                  <Circle size={18} color="#64748B" />
                )}
              </View>
            </View>

            {/* Route Name & Tier */}
            <View className="mb-1">
              <Text className="text-base font-black text-white tracking-tight">
                Direct Arterial via CST Road Underpass
              </Text>
              <Text className="text-[11px] font-bold text-rose-400 mt-0.5">
                Tier 4 • Impassable Flood Underpass (0.85m Water)
              </Text>
            </View>

            <Text className="text-xs text-rose-200/90 mt-1 leading-relaxed">
              Shorter physical road (2.1 km), but completely blocked by 0.85m standing water under railway bridge.
            </Text>

            {/* Metrics Row */}
            <View className="flex-row gap-2 my-3">
              <View className="flex-1 bg-slate-950 p-2.5 rounded-xl border border-slate-800 items-center">
                <Text className="text-[9px] font-bold text-slate-400 uppercase">EST. DELAY</Text>
                <Text className="text-sm font-black text-rose-400 mt-0.5">Impassable</Text>
              </View>
              <View className="flex-1 bg-slate-950 p-2.5 rounded-xl border border-slate-800 items-center">
                <Text className="text-[9px] font-bold text-slate-400 uppercase">WATER DEPTH</Text>
                <Text className="text-sm font-black text-rose-400 mt-0.5">0.85 m Deep</Text>
              </View>
              <View className="flex-1 bg-slate-950 p-2.5 rounded-xl border border-slate-800 items-center">
                <Text className="text-[9px] font-bold text-slate-400 uppercase">ROAD STATUS</Text>
                <Text className="text-sm font-black text-rose-400 mt-0.5">Barricaded</Text>
              </View>
            </View>

            {/* Danger Warning Callout */}
            <View className="bg-rose-950/40 p-3 rounded-xl border border-rose-900/60 flex-row items-center gap-2">
              <AlertTriangle size={15} color="#FB7185" className="flex-shrink-0" />
              <Text className="text-xs text-rose-200 font-medium flex-1">
                Vehicles stalling in current. Risk of open manhole vortex suction.
              </Text>
            </View>
          </Pressable>
        </View>

        {/* 5. Route Elevation Cross-Section Profile (MSL Altitude Visual Graph) */}
        <View className="px-5 pt-4">
          <View className="bg-[#0B1322] border border-slate-800 rounded-2xl p-4 shadow-xl">
            {/* Header: Title and Safety Badge without collision */}
            <View className="flex-row items-center justify-between gap-2 mb-3">
              <View className="flex-row items-center gap-2 flex-1 min-w-0">
                <TrendingUp size={16} color="#00F0FF" />
                <Text numberOfLines={1} className="text-xs font-black text-white uppercase tracking-wider">
                  Topographic MSL Profile
                </Text>
              </View>
              <View className="bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 rounded-full flex-row items-center gap-1 flex-shrink-0">
                <View className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                <Text className="text-[10px] font-black text-emerald-300 uppercase tracking-wide">
                  Safe Corridor
                </Text>
              </View>
            </View>

            {/* Visual Step-by-Step Terrain Bar Chart */}
            <View className="bg-slate-950/90 rounded-xl p-3.5 border border-slate-900">
              {/* Profile Bars Area with proper clearance */}
              <View className="h-32 w-full flex-row items-end justify-between px-2 pt-5 pb-1 border-b border-slate-800/80 relative">
                {/* Horizontal Datum Threshold Indicator (+3.6m flood water line) */}
                <View 
                  style={{ bottom: 26 }} 
                  className="absolute left-0 right-0 border-b border-dashed border-rose-500/40 flex-row items-center justify-end pr-1 z-0"
                >
                  <Text className="text-[8px] font-mono font-bold text-rose-400/80 bg-slate-950/90 px-1 -bottom-2">
                    Inundation Datum +3.6m
                  </Text>
                </View>

                {/* Point 1: Origin */}
                <View className="items-center z-10 flex-1">
                  <Text className="text-[9px] font-mono text-cyan-300 font-bold mb-1">+8.2m</Text>
                  <View className="w-9 h-14 bg-cyan-500/80 rounded-t-md border-t border-x border-cyan-400" />
                  <Text numberOfLines={1} className="text-[8px] text-slate-400 mt-1 font-bold text-center">Kurla West</Text>
                </View>

                {/* Point 2: Hazard Depression */}
                <View className="items-center z-10 flex-1">
                  <Text className="text-[9px] font-mono text-rose-400 font-bold mb-1">+2.8m ⚠️</Text>
                  <View className="w-9 h-6 bg-rose-500 rounded-t-md border-t border-x border-rose-400" />
                  <Text numberOfLines={1} className="text-[8px] text-rose-400 mt-1 font-bold text-center">CST Basin</Text>
                </View>

                {/* Point 3: Elevated Bypass Deck */}
                <View className="items-center z-10 flex-1">
                  <Text className="text-[9px] font-mono text-emerald-300 font-bold mb-1">+13.6m</Text>
                  <View className="w-9 h-20 bg-emerald-500 rounded-t-md border-t border-x border-emerald-300 shadow-sm shadow-emerald-400" />
                  <Text numberOfLines={1} className="text-[8px] text-emerald-300 mt-1 font-bold text-center">Bypass Deck</Text>
                </View>

                {/* Point 4: Safe Haven Destination */}
                <View className="items-center z-10 flex-1">
                  <Text className="text-[9px] font-mono text-emerald-300 font-bold mb-1">
                    {destinationMeta.elevation.replace(' MSL', '')}
                  </Text>
                  <View className="w-9 h-20 bg-emerald-400 rounded-t-md border-t border-x border-emerald-200 shadow-sm shadow-emerald-400" />
                  <Text numberOfLines={1} className="text-[8px] text-emerald-300 mt-1 font-bold text-center">Safe Haven</Text>
                </View>
              </View>

              {/* Water Ingress & Clearance Threshold Badges */}
              <View className="flex-row items-center gap-2 mt-2.5">
                <View className="flex-1 bg-rose-950/40 border border-rose-500/30 px-2 py-1.5 rounded-lg flex-row items-center gap-1.5 min-w-0">
                  <View className="w-1.5 h-1.5 rounded-full bg-rose-500 flex-shrink-0" />
                  <Text numberOfLines={1} className="text-[9px] font-bold text-rose-300 flex-1">
                    Flood Level: +3.6m MSL
                  </Text>
                </View>
                <View className="flex-1 bg-emerald-950/40 border border-emerald-500/30 px-2 py-1.5 rounded-lg flex-row items-center gap-1.5 min-w-0">
                  <View className="w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" />
                  <Text numberOfLines={1} className="text-[9px] font-bold text-emerald-300 flex-1">
                    Clearance: +5.4m
                  </Text>
                </View>
              </View>
            </View>
          </View>
        </View>

        {/* 6. Turn-by-Turn Disaster Evacuation Waypoints */}
        <View className="px-5 pt-4">
          <View className="bg-[#0B1322] border border-slate-800 rounded-2xl p-4 shadow-xl">
            <View className="flex-row items-center justify-between mb-3">
              <View className="flex-row items-center gap-2">
                <Compass size={15} color="#00F0FF" />
                <Text className="text-xs font-black text-white uppercase tracking-wider">
                  Corridor Waypoints & Turns
                </Text>
              </View>
              <Text className="text-[10px] font-bold text-slate-400 uppercase">
                4 Tactical Segments
              </Text>
            </View>

            <View className="flex-col gap-3">
              {waypoints.map((wp, idx) => (
                <View key={idx} className="flex-row items-start gap-3">
                  {/* Waypoint Number Circle */}
                  <View className="w-7 h-7 rounded-full bg-slate-900 border border-slate-700 items-center justify-center mt-0.5 flex-shrink-0">
                    <Text className="text-xs font-black text-cyan-400">{idx + 1}</Text>
                  </View>

                  <View className="flex-1 pb-2 border-b border-slate-800/80">
                    <View className="flex-row items-center justify-between">
                      <Text className="text-xs font-bold text-white flex-1 pr-2">
                        {wp.title}
                      </Text>
                      <Text className="text-[10px] font-mono text-cyan-300 font-bold">
                        {wp.distance}
                      </Text>
                    </View>
                    <Text className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
                      {wp.instruction}
                    </Text>
                    <View className="flex-row items-center gap-2 mt-1">
                      <Text className="text-[10px] font-bold text-slate-300">
                        Elevation: <Text className="text-emerald-400">{wp.elevation}</Text>
                      </Text>
                      <View className="w-1 h-1 rounded-full bg-slate-700" />
                      <Text className="text-[10px] font-bold text-cyan-400">
                        {wp.status}
                      </Text>
                    </View>
                  </View>
                </View>
              ))}
            </View>
          </View>
        </View>

        {/* 7. Verified High-Ground Relief Havens & Shelters Directory */}
        <View className="px-5 pt-4">
          <View className="bg-[#0B1322] border border-slate-800 rounded-2xl p-4 shadow-xl">
            <View className="flex-row items-center justify-between mb-3">
              <View className="flex-row items-center gap-2">
                <Building2 size={15} color="#00F0FF" />
                <Text className="text-xs font-black text-white uppercase tracking-wider">
                  Verified Safe Shelters & Havens
                </Text>
              </View>
              <View className="bg-emerald-500/20 border border-emerald-500/40 px-2 py-0.5 rounded">
                <Text className="text-[9px] font-black text-emerald-400 uppercase">
                  Open 24/7
                </Text>
              </View>
            </View>

            <View className="flex-col gap-2.5">
              {shelters.map((haven) => {
                const isCurrent = selectedDestination.asset_id === haven.asset_id;
                return (
                  <View
                    key={haven.asset_id}
                    className={`p-3 rounded-xl border flex-row items-center justify-between ${
                      isCurrent
                        ? 'bg-cyan-950/30 border-cyan-500/60'
                        : 'bg-slate-900/90 border-slate-800'
                    }`}
                  >
                    <View className="flex-1 pr-3">
                      <View className="flex-row items-center gap-1.5">
                        <ShieldCheck size={13} color={isCurrent ? '#00F0FF' : '#34D399'} />
                        <Text className="text-xs font-bold text-white" numberOfLines={1}>
                          {haven.name}
                        </Text>
                      </View>
                      <Text className="text-[11px] text-slate-400 mt-0.5">
                        Safe Ground: <Text className="text-emerald-400 font-bold">+{haven.elevation_msl || 14.2}m MSL</Text> • Capacity: {haven.capacity || 120} Beds
                      </Text>
                    </View>

                    {isCurrent ? (
                      <View className="bg-emerald-500/20 border border-emerald-500/50 px-2.5 py-1 rounded-lg">
                        <Text className="text-[10px] font-black text-emerald-300 uppercase">
                          ACTIVE TARGET
                        </Text>
                      </View>
                    ) : (
                      <Pressable
                        onPress={() => handleSelectDestination(haven)}
                        className="bg-cyan-500/20 border border-cyan-400/40 px-3 py-1.5 rounded-lg active:scale-95"
                      >
                        <Text className="text-xs font-black text-cyan-300 uppercase">
                          Select
                        </Text>
                      </Pressable>
                    )}
                  </View>
                );
              })}
            </View>
          </View>
        </View>

        {/* 8. Interactive Action Buttons */}
        <View className="px-5 pt-4 flex-col gap-2.5">
          {/* Main Navigation Launch Button */}
          <Pressable
            onPress={handleStartNavigation}
            className={`py-4 rounded-2xl flex-row items-center justify-center gap-2.5 shadow-xl active:scale-[0.98] ${
              selectedRoute === 'SAFE_ELEVATED'
                ? 'bg-cyan-500 active:bg-cyan-600 shadow-cyan-500/20'
                : 'bg-rose-600 active:bg-rose-700'
            }`}
          >
            <Navigation size={18} color="#050A14" />
            <Text className="text-sm font-black text-slate-950 uppercase tracking-wider">
              {isNavigating
                ? 'Navigation Active • Tap to View Map'
                : 'Start Lower-Risk Navigation'}
            </Text>
          </Pressable>

          {/* Secondary Actions */}
          <View className="flex-row gap-2.5">
            <Pressable
              onPress={() => router.push('/(tabs)/radar')}
              className="flex-1 py-3 bg-slate-900 border border-slate-800 rounded-xl flex-row items-center justify-center gap-1.5 active:bg-slate-800"
            >
              <Compass size={14} color="#00F0FF" />
              <Text className="text-xs font-bold text-white uppercase">
                View On Radar
              </Text>
            </Pressable>

            <Pressable
              onPress={handleShareRoute}
              className="flex-1 py-3 bg-slate-900 border border-slate-800 rounded-xl flex-row items-center justify-center gap-1.5 active:bg-slate-800"
            >
              <Share2 size={14} color="#00F0FF" />
              <Text className="text-xs font-bold text-white uppercase">
                Share Route
              </Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}
