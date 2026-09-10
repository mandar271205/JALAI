import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { 
  View, 
  ScrollView, 
  Pressable, 
  Alert, 
  RefreshControl, 
  Image, 
  Modal, 
  TextInput, 
  ActivityIndicator 
} from 'react-native';
import { useRouter } from 'expo-router';
import { 
  AlertTriangle, 
  Radio, 
  ShieldAlert, 
  MapPin, 
  CloudRain, 
  ChevronRight, 
  LifeBuoy, 
  Camera, 
  Layers, 
  Clock, 
  Compass, 
  Building2, 
  Navigation, 
  Volume2, 
  CheckCircle2, 
  WifiOff, 
  Plus, 
  Trash2, 
  Home as HomeIcon, 
  Building, 
  GraduationCap, 
  ShieldCheck, 
  Check,
  X
} from 'lucide-react-native';

import { AppHeader } from '@/components/shared/app-header';
import { Text } from '@/components/ui/text';
import { emergencyStore, useEmergencyStore } from '@/lib/emergency-store';
import { 
  fetchCurrentWeather, 
  fetchActiveIncidents, 
  fetchActiveAlerts,
  fetchCriticalAssets,
  fetchWatchLocations,
  addWatchLocation,
  deleteWatchLocation,
  type CurrentWeatherResponse,
  type IncidentItem,
  type AlertItem,
  type CriticalAssetItem,
  type WatchLocationItem,
  FALLBACK_WEATHER,
  FALLBACK_INCIDENTS,
  FALLBACK_ALERTS,
  FALLBACK_ASSETS,
  FALLBACK_WATCH_LOCATIONS
} from '@/lib/api';

export default function HomeScreen() {
  const router = useRouter();

  const [refreshing, setRefreshing] = useState(false);
  const [isLiveBackend, setIsLiveBackend] = useState(false);

  // Live state directly from backend
  const [weather, setWeather] = useState<CurrentWeatherResponse>(FALLBACK_WEATHER);
  const [incidents, setIncidents] = useState<IncidentItem[]>(FALLBACK_INCIDENTS);
  const [alerts, setAlerts] = useState<AlertItem[]>(FALLBACK_ALERTS);
  const [assets, setAssets] = useState<CriticalAssetItem[]>(FALLBACK_ASSETS);
  const [watchLocations, setWatchLocations] = useState<WatchLocationItem[]>(FALLBACK_WATCH_LOCATIONS);

  // Watch Location Modal state
  const [isAddingLocation, setIsAddingLocation] = useState(false);
  const [newLocationLabel, setNewLocationLabel] = useState('');
  const [newLocationWard, setNewLocationWard] = useState('Kurla West (Ward L)');
  const [newLocationThreshold, setNewLocationThreshold] = useState<'HIGH' | 'SEVERE'>('HIGH');
  const [isSavingLocation, setIsSavingLocation] = useState(false);

  // Active Ward Incidents Sheet state (Live from /incidents)
  const [showIncidentsModal, setShowIncidentsModal] = useState(false);
  const [selectedWardFilter, setSelectedWardFilter] = useState('ALL');

  const displayedIncidents = useMemo(() => {
    if (selectedWardFilter === 'ALL') return incidents;
    return incidents.filter((i) => i.ward_id?.toLowerCase().includes(selectedWardFilter.toLowerCase()));
  }, [incidents, selectedWardFilter]);

  // Fetch real data from FastAPI backend
  const loadDashboardData = useCallback(async () => {
    try {
      const [weatherRes, incidentsRes, alertsRes, assetsRes, watchRes] = await Promise.all([
        fetchCurrentWeather(),
        fetchActiveIncidents(),
        fetchActiveAlerts(),
        fetchCriticalAssets(),
        fetchWatchLocations(),
      ]);

      setWeather(weatherRes.data);
      setIncidents(Array.isArray(incidentsRes.data) ? incidentsRes.data : FALLBACK_INCIDENTS);
      setAlerts(Array.isArray(alertsRes.data) ? alertsRes.data : FALLBACK_ALERTS);
      setAssets(Array.isArray(assetsRes.data) ? assetsRes.data : FALLBACK_ASSETS);
      setWatchLocations(Array.isArray(watchRes.data) ? watchRes.data : FALLBACK_WATCH_LOCATIONS);
      setIsLiveBackend(weatherRes.isLive || incidentsRes.isLive || alertsRes.isLive || watchRes.isLive);
    } catch (err) {
      setIsLiveBackend(false);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const onRefresh = () => {
    setRefreshing(true);
    loadDashboardData();
  };

  const handleCreateWatchLocation = async () => {
    if (!newLocationLabel.trim()) {
      Alert.alert('Required', "Please enter a name for this monitored location (e.g. Parents' Home).");
      return;
    }
    setIsSavingLocation(true);
    try {
      const coords = newLocationWard.includes('Kurla')
        ? { latitude: 19.0685, longitude: 72.8720, ward_id: 'WARD-08-KURLA' }
        : newLocationWard.includes('Dharavi')
        ? { latitude: 19.0432, longitude: 72.8534, ward_id: 'WARD-12-DHARAVI' }
        : { latitude: 19.0178, longitude: 72.8478, ward_id: 'WARD-04-DADAR' };

      const res = await addWatchLocation({
        label: newLocationLabel.trim(),
        latitude: coords.latitude,
        longitude: coords.longitude,
        ward_id: coords.ward_id,
        risk_threshold: newLocationThreshold,
        notify_push: true,
      });

      if (res.success) {
        setIsAddingLocation(false);
        setNewLocationLabel('');
        const updated = await fetchWatchLocations();
        setWatchLocations(updated.data);
      } else {
        Alert.alert('Saved Offline', 'Location saved to local storage.');
      }
    } catch {
      Alert.alert('Error', 'Failed to save location.');
    } finally {
      setIsSavingLocation(false);
    }
  };

  const handleRemoveWatchLocation = (locationId: string) => {
    Alert.alert(
      'Remove Monitored Place',
      'Stop receiving geofenced flood warnings for this location?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: async () => {
            await deleteWatchLocation(locationId);
            const updated = await fetchWatchLocations();
            setWatchLocations(updated.data);
          },
        },
      ]
    );
  };

  const primaryAlert = alerts[0];
  const criticalIncident = incidents[0];

  // User location title from active regional alert or ward
  const locationLabel = primaryAlert?.area_description 
    ? primaryAlert.area_description 
    : criticalIncident?.ward_id 
    ? `${criticalIncident.ward_id} • Monitored Basin` 
    : 'Kurla & Dharavi Basin, Mumbai';

  const { activeSos } = useEmergencyStore();
  const isSevere = weather.average_rainfall_rate_mm_h >= 40 || primaryAlert?.severity === 'Extreme';

  const handleSosTrigger = () => {
    emergencyStore.openSos({ ward: locationLabel });
  };

  return (
    <View className="flex-1 bg-[#050A14]">
      {/* 1. Tactical Header with Safe Area insets and overflow protection */}
      <AppHeader
        location={locationLabel}
        onDistressPress={handleSosTrigger}
        onProfilePress={() => emergencyStore.openTerminal()}
      />

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingBottom: 90 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor="#38BDF8"
            colors={['#38BDF8']}
          />
        }
      >
        {/* Subtle Offline Banner: Only displayed if backend/network is completely unreachable */}
        {!isLiveBackend && (
          <View className="bg-amber-950/80 border-b border-amber-800/60 px-5 py-2 flex-row items-center justify-between">
            <View className="flex-row items-center gap-2">
              <WifiOff size={13} color="#FBBF24" />
              <Text className="text-xs font-semibold text-amber-200">
                Offline Mode • Showing cached emergency guidance
              </Text>
            </View>
            <Pressable onPress={loadDashboardData}>
              <Text className="text-xs font-bold text-cyan-400">Retry</Text>
            </Pressable>
          </View>
        )}

        {/* 2. Top Urgent Broadcast Ticker */}
        {criticalIncident && (
          <Pressable 
            onPress={() => setShowIncidentsModal(true)}
            className="bg-rose-950/90 border-b border-rose-800/60 px-5 py-3 flex-row items-center justify-between active:bg-rose-900"
          >
            <View className="flex-row items-center gap-2.5 flex-1 pr-3 min-w-0">
              <Radio size={16} color="#FB7185" className="flex-shrink-0" />
              <Text numberOfLines={1} className="text-xs font-bold text-rose-100 flex-1">
                {criticalIncident.title} • {criticalIncident.status}
              </Text>
            </View>
            <View className="bg-rose-600 px-2 py-0.5 rounded flex-shrink-0 flex-row items-center gap-1">
              <Text className="text-[10px] font-black text-white uppercase tracking-wider">
                {incidents.length} ACTIVE
              </Text>
            </View>
          </Pressable>
        )}

        <View className="px-5 pt-4 flex-col gap-5">
          {/* 3. Official IMD / Civil Defense Red Alert Card */}
          {primaryAlert && (
            <View className="bg-[#0B1322] border-2 border-rose-500/70 rounded-2xl p-5 shadow-xl">
              {/* Alert Header Row with Clean Spacing & Badges */}
              <View className="flex-row items-center justify-between mb-3">
                <View className="flex-row items-center gap-2 flex-1 mr-2 min-w-0">
                  <View className="bg-rose-600 px-2 py-0.5 rounded flex-shrink-0">
                    <Text className="text-[10px] font-black text-white uppercase tracking-wider">
                      ● RED ALERT
                    </Text>
                  </View>
                  <Text numberOfLines={1} className="text-xs font-bold text-slate-300 flex-1">
                    Evacuation Advisory
                  </Text>
                </View>
                <View className="bg-rose-950/80 border border-rose-600/50 px-2 py-0.5 rounded flex-shrink-0">
                  <Text className="text-[10px] font-black text-rose-300">
                    NEXT 3 HOURS
                  </Text>
                </View>
              </View>

              <Text className="text-base font-black text-white leading-snug">
                {primaryAlert.headline}
              </Text>

              <Text className="text-xs text-slate-300 mt-2 leading-relaxed">
                {primaryAlert.instruction}
              </Text>

              {/* Action Buttons */}
              <View className="mt-4 pt-3 border-t border-slate-800/80 flex-row gap-3">
                <Pressable
                  onPress={() => router.push('/(tabs)/alerts')}
                  className="flex-1 bg-cyan-500/20 border border-cyan-500/50 py-2.5 rounded-xl flex-row items-center justify-center gap-2 active:bg-cyan-500/30"
                >
                  <Volume2 size={15} color="#38BDF8" />
                  <Text className="text-xs font-bold text-cyan-300">
                    Audio Warning
                  </Text>
                </Pressable>

                <Pressable
                  onPress={() => router.push('/(tabs)/safety')}
                  className="flex-1 bg-slate-800 border border-slate-700 py-2.5 rounded-xl flex-row items-center justify-center gap-2 active:bg-slate-700"
                >
                  <Navigation size={15} color="#FFFFFF" />
                  <Text className="text-xs font-bold text-white">
                    Safe Shelters
                  </Text>
                </Pressable>
              </View>
            </View>
          )}

          {/* 4. Live Weather & Catchment Condition Hero Card */}
          <View className="bg-[#0A1220] border border-slate-800 rounded-2xl p-5 shadow-lg">
            <View className="flex-row items-center justify-between mb-3">
              <View className="flex-row items-center gap-2.5 flex-1 mr-2 min-w-0">
                <View className="w-8 h-8 rounded-lg bg-cyan-950/80 border border-cyan-500/40 items-center justify-center flex-shrink-0">
                  <CloudRain size={18} color="#38BDF8" />
                </View>
                <View className="flex-1 min-w-0">
                  <Text className="text-xs font-bold text-slate-400 uppercase tracking-wider" numberOfLines={1}>
                    Catchment Inundation Risk
                  </Text>
                  <Text numberOfLines={1} className={`text-xs font-black ${isSevere ? 'text-rose-400' : 'text-amber-400'}`}>
                    {isSevere ? 'Severe Downpour in Progress' : 'Heavy Rainfall Active'}
                  </Text>
                </View>
              </View>

              <View className="bg-slate-800/90 px-2.5 py-1 rounded-full flex-shrink-0">
                <Text className="text-xs font-bold text-cyan-300">
                  Catchment
                </Text>
              </View>
            </View>

            {/* Precipitation Rate Display */}
            <View className="my-2.5">
              <View className="flex-row items-baseline gap-2">
                <Text className="text-4xl font-black text-white tracking-tight">
                  {weather.average_rainfall_rate_mm_h}
                </Text>
                <Text className="text-lg font-bold text-cyan-400">
                  mm/h
                </Text>
              </View>
              <Text className="text-xs text-slate-300 mt-1 leading-relaxed">
                {weather.summary}
              </Text>
            </View>

            {/* Visual Intensity Equalizer Meter */}
            <View className="my-3">
              <View className="flex-row justify-between mb-1.5">
                <Text className="text-[11px] font-semibold text-slate-400">
                  Intensity Gauge
                </Text>
                <Text className="text-[11px] font-bold text-rose-400">
                  Torrential Level
                </Text>
              </View>
              <View className="h-2 w-full bg-slate-800 rounded-full overflow-hidden flex-row">
                <View className="h-full bg-cyan-500 w-1/4" />
                <View className="h-full bg-cyan-400 w-1/4" />
                <View className="h-full bg-amber-400 w-1/4" />
                <View className="h-full bg-rose-500 w-1/4" />
              </View>
            </View>

            {/* 3 Perfectly Balanced Citizen Metric Badges */}
            <View className="flex-row gap-2.5 pt-3 border-t border-slate-800/80">
              <View className="flex-1 bg-slate-900/80 p-2.5 rounded-xl border border-slate-800 items-center">
                <Text className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">
                  PEAK RAIN
                </Text>
                <Text className="text-base font-extrabold text-white mt-0.5">
                  {weather.max_recorded_rainfall_mm} mm
                </Text>
                <Text className="text-[9px] text-slate-400 mt-0.5">
                  24h Max
                </Text>
              </View>

              <View className="flex-1 bg-slate-900/80 p-2.5 rounded-xl border border-slate-800 items-center">
                <Text className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">
                  WATER INFLOW
                </Text>
                <Text className="text-base font-extrabold text-rose-400 mt-0.5">
                  +8 cm/h
                </Text>
                <Text className="text-[9px] text-rose-300/80 mt-0.5">
                  Rising Fast
                </Text>
              </View>

              <View className="flex-1 bg-slate-900/80 p-2.5 rounded-xl border border-slate-800 items-center">
                <Text className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">
                  SAFE GROUND
                </Text>
                <Text className="text-base font-extrabold text-emerald-400 mt-0.5">
                  +4.2m
                </Text>
                <Text className="text-[9px] text-emerald-300/80 mt-0.5">
                  450m Away
                </Text>
              </View>
            </View>
          </View>

          {/* 5. Emergency SOS Distress Trigger */}
          <Pressable
            onPress={handleSosTrigger}
            className={`py-4 px-5 rounded-2xl flex-row items-center justify-between border active:scale-[0.98] shadow-xl ${
              activeSos
                ? 'bg-rose-700 border-rose-400'
                : 'bg-rose-950/90 border-rose-600/80'
            }`}
          >
            <View className="flex-row items-center gap-3.5 flex-1 pr-2 min-w-0">
              <View className={`w-12 h-12 rounded-full items-center justify-center shadow flex-shrink-0 ${activeSos ? 'bg-rose-500' : 'bg-rose-600'}`}>
                <LifeBuoy size={24} color="#FFFFFF" />
              </View>
              <View className="flex-1 min-w-0">
                <Text className="text-base font-black text-white tracking-wide uppercase">
                  {activeSos ? 'SOS DISPATCH ACTIVE • TRACK' : 'Broadcast SOS Distress'}
                </Text>
                <Text numberOfLines={1} className="text-xs text-rose-200 mt-0.5">
                  {activeSos ? 'Rescue Unit Dispatched • Tap to view status' : '1-tap GPS transmission to Rescue Command'}
                </Text>
              </View>
            </View>
            <ChevronRight size={22} color="#FECDD3" className="flex-shrink-0" />
          </Pressable>

          {/* 6. Quick Action Station (3 Clean Balanced Tiles) */}
          <View className="flex-row gap-2.5">
            <Pressable
              onPress={() => router.push('/(tabs)/radar')}
              className="flex-1 bg-[#0B1324] border border-slate-800 p-3 rounded-2xl active:bg-slate-800 items-center"
            >
              <View className="w-10 h-10 rounded-xl bg-cyan-950/80 border border-cyan-500/40 items-center justify-center mb-2">
                <Layers size={18} color="#38BDF8" />
              </View>
              <Text className="text-xs font-black text-white text-center">Live Radar</Text>
              <Text numberOfLines={1} className="text-[10px] text-slate-400 mt-0.5 text-center">
                Flood Map
              </Text>
            </Pressable>

            <Pressable
              onPress={() => router.push('/(tabs)/safety')}
              className="flex-1 bg-[#0B1324] border border-slate-800 p-3 rounded-2xl active:bg-slate-800 items-center"
            >
              <View className="w-10 h-10 rounded-xl bg-emerald-950/80 border border-emerald-500/40 items-center justify-center mb-2">
                <Navigation size={18} color="#34D399" />
              </View>
              <Text className="text-xs font-black text-white text-center">Safe Route</Text>
              <Text numberOfLines={1} className="text-[10px] text-slate-400 mt-0.5 text-center">
                High Ground
              </Text>
            </Pressable>

            <Pressable
              onPress={() => router.push('/(tabs)/report')}
              className="flex-1 bg-[#0B1324] border border-slate-800 p-3 rounded-2xl active:bg-slate-800 items-center"
            >
              <View className="w-10 h-10 rounded-xl bg-amber-950/80 border border-amber-500/40 items-center justify-center mb-2">
                <Camera size={18} color="#FBBF24" />
              </View>
              <Text className="text-xs font-black text-white text-center">Report</Text>
              <Text numberOfLines={1} className="text-[10px] text-slate-400 mt-0.5 text-center">
                Water Depth
              </Text>
            </Pressable>
          </View>

          {/* Active Ward Hazards Banner (Direct from /incidents) */}
          <Pressable
            onPress={() => setShowIncidentsModal(true)}
            className="bg-[#0B1324] border border-slate-800 rounded-2xl p-4 flex-row items-center justify-between active:bg-slate-800/80 shadow-md"
          >
            <View className="flex-row items-center gap-3 flex-1 mr-2 min-w-0">
              <View className="w-10 h-10 rounded-xl bg-rose-500/20 border border-rose-500/40 items-center justify-center flex-shrink-0">
                <AlertTriangle size={20} color="#FB7185" />
              </View>
              <View className="flex-1 min-w-0">
                <View className="flex-row items-center gap-2 mb-0.5">
                  <Text className="text-xs font-black text-white" numberOfLines={1}>
                    Active Ward Flood Incidents
                  </Text>
                  <View className="bg-rose-600 px-1.5 py-0.5 rounded">
                    <Text className="text-[9px] font-black text-white">
                      {incidents.length} REPORTED
                    </Text>
                  </View>
                </View>
                <Text className="text-[11px] text-slate-400" numberOfLines={1}>
                  Tap to view verified road breaches & waterlogged spots
                </Text>
              </View>
            </View>
            <ChevronRight size={18} color="#64748B" className="flex-shrink-0" />
          </Pressable>

          {/* Monitored Family Locations Section (Live from /watch-locations) */}
          <View className="mt-1">
            <View className="flex-row items-center justify-between mb-3">
              <View className="flex-row items-center gap-2">
                <HomeIcon size={15} color="#00F0FF" />
                <Text className="text-xs font-black tracking-wider text-slate-400 uppercase">
                  Monitored Family Places ({watchLocations.length})
                </Text>
              </View>

              <Pressable
                onPress={() => setIsAddingLocation(true)}
                className="bg-cyan-500/20 border border-cyan-400/40 px-2.5 py-1 rounded-lg flex-row items-center gap-1 active:scale-95"
              >
                <Plus size={12} color="#00F0FF" />
                <Text className="text-[10px] font-black text-cyan-300 uppercase">
                  Add Place
                </Text>
              </Pressable>
            </View>

            <View className="flex-col gap-2.5">
              {watchLocations.map((loc) => {
                const isAlert = loc.is_alert_active || loc.risk_status === 'SEVERE';
                return (
                  <View
                    key={loc.location_id}
                    className={`p-3.5 rounded-2xl border flex-row items-center justify-between ${
                      isAlert
                        ? 'bg-[#140C18] border-rose-500/70'
                        : 'bg-[#0B1324] border-slate-800'
                    }`}
                  >
                    <View className="flex-1 pr-2">
                      <View className="flex-row items-center gap-1.5 mb-1">
                        <View
                          className={`w-2 h-2 rounded-full ${
                            isAlert ? 'bg-rose-500 animate-pulse' : 'bg-emerald-400'
                          }`}
                        />
                        <Text className="text-xs font-black text-white" numberOfLines={1}>
                          {loc.label}
                        </Text>
                      </View>
                      <Text className="text-[11px] text-slate-400">
                        {loc.ward_id ? loc.ward_id.replace('WARD-', 'Ward ') : 'Catchment Basin'} • Threshold: {loc.risk_threshold}
                      </Text>
                    </View>

                    <View className="flex-row items-center gap-2 flex-shrink-0">
                      <View
                        className={`px-2 py-0.5 rounded ${
                          isAlert
                            ? 'bg-rose-500/20 border border-rose-500/40'
                            : 'bg-emerald-500/20 border border-emerald-500/40'
                        }`}
                      >
                        <Text
                          className={`text-[9px] font-black uppercase ${
                            isAlert ? 'text-rose-300' : 'text-emerald-300'
                          }`}
                        >
                          {isAlert ? '⚠️ Flood Surge' : '🟢 Normal'}
                        </Text>
                      </View>

                      <Pressable
                        onPress={() => handleRemoveWatchLocation(loc.location_id)}
                        className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 active:bg-slate-800"
                      >
                        <Trash2 size={13} color="#94A3B8" />
                      </Pressable>
                    </View>
                  </View>
                );
              })}
            </View>
          </View>

          {/* 7. Live Inundation & Blocked Roads Feed */}
          <View className="mt-1">
            <View className="flex-row items-center justify-between mb-3">
              <Text className="text-xs font-black tracking-wider text-slate-400 uppercase flex-1 mr-2">
                Road Inundations
              </Text>
              <View className="bg-slate-800 px-2.5 py-0.5 rounded-full flex-shrink-0">
                <Text className="text-[11px] font-bold text-slate-300">
                  {incidents.length} Reported
                </Text>
              </View>
            </View>

            <View className="flex-col gap-3">
              {(Array.isArray(incidents) ? incidents : []).map((incident) => {
                const landmark = incident.ward_id === 'WARD-08-KURLA' 
                  ? 'CST Road Bridge, Kurla • 420m away' 
                  : incident.ward_id === 'WARD-04-DADAR' 
                  ? "King's Circle, Dadar • 1.4km away" 
                  : `${incident.ward_id} • Monitored Basin`;

                return (
                  <View
                    key={incident.incident_id}
                    className="bg-[#0A1222] border border-slate-800 rounded-2xl p-4"
                  >
                    <View className="flex-row items-center justify-between mb-2">
                      <View className="flex-row items-center gap-2 flex-1 mr-2 min-w-0">
                        <View
                          className={`px-2 py-0.5 rounded flex-shrink-0 ${
                            incident.severity === 'CRITICAL'
                              ? 'bg-rose-600'
                              : 'bg-amber-600'
                          }`}
                        >
                          <Text className="text-[10px] font-black text-white uppercase">
                            {incident.severity}
                          </Text>
                        </View>
                        <Text numberOfLines={1} className="text-xs font-bold text-cyan-400 flex-1">
                          {incident.ward_id}
                        </Text>
                      </View>

                      <View className="flex-row items-center gap-1.5 flex-shrink-0">
                        <View className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                        <Text className="text-[11px] font-bold text-emerald-400">
                          {incident.status}
                        </Text>
                      </View>
                    </View>

                    <Text className="text-sm font-black text-white leading-snug">
                      {incident.title}
                    </Text>

                    <View className="flex-row items-center gap-1.5 mt-2">
                      <MapPin size={12} color="#94A3B8" />
                      <Text className="text-xs text-slate-400 font-medium">
                        {landmark}
                      </Text>
                    </View>
                  </View>
                );
              })}
            </View>
          </View>

          {/* 8. Critical Facilities & Safe Shelters (From /api/v1/assets) */}
          <View className="mt-1">
            <View className="flex-row items-center justify-between mb-3">
              <Text className="text-xs font-black tracking-wider text-slate-400 uppercase flex-1 mr-2">
                Critical Facilities Nearby
              </Text>
              <Text className="text-xs font-semibold text-slate-400 flex-shrink-0">
                Safe Havens & Medical
              </Text>
            </View>

            <View className="flex-col gap-2.5">
              {(Array.isArray(assets) ? assets : []).map((asset) => (
                <View
                  key={asset.asset_id}
                  className="bg-[#0B1324] border border-slate-800 p-3.5 rounded-2xl flex-row items-center justify-between"
                >
                  <View className="flex-row items-center gap-3 flex-1 pr-3 min-w-0">
                    <View className="w-9 h-9 rounded-xl bg-slate-800 border border-slate-700 items-center justify-center flex-shrink-0">
                      <Building2 size={17} color="#38BDF8" />
                    </View>
                    <View className="flex-1 min-w-0">
                      <Text className="text-xs font-bold text-white" numberOfLines={1}>
                        {asset.name}
                      </Text>
                      <Text className="text-[11px] text-slate-400 mt-0.5" numberOfLines={1}>
                        {asset.asset_type === 'HOSPITAL' ? 'Emergency Trauma Base' : 'Power Infrastructure'} • Threshold {asset.flood_threshold_m}m
                      </Text>
                    </View>
                  </View>

                  <View className={`px-2 py-0.5 rounded flex-shrink-0 ${
                    asset.status === 'AT_RISK' ? 'bg-amber-500/20 border border-amber-500/40' : 'bg-emerald-500/20 border border-emerald-500/40'
                  }`}>
                    <Text className={`text-[10px] font-black uppercase ${
                      asset.status === 'AT_RISK' ? 'text-amber-300' : 'text-emerald-300'
                    }`}>
                      {asset.status === 'AT_RISK' ? 'At Risk' : 'Operational'}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        </View>
      </ScrollView>

      {/* Modal: Add Monitored Family Place */}
      <Modal
        visible={isAddingLocation}
        transparent
        animationType="fade"
        onRequestClose={() => setIsAddingLocation(false)}
      >
        <View className="flex-1 bg-black/80 items-center justify-center px-6">
          <View className="bg-[#0B1322] border border-slate-700 rounded-3xl p-5 w-full shadow-2xl">
            <View className="flex-row items-center justify-between mb-3 border-b border-slate-800 pb-2.5">
              <View className="flex-row items-center gap-2">
                <HomeIcon size={16} color="#00F0FF" />
                <Text className="text-sm font-black text-white uppercase tracking-wider">
                  Add Monitored Place
                </Text>
              </View>
              <Pressable onPress={() => setIsAddingLocation(false)} className="p-1">
                <Text className="text-sm font-bold text-slate-400">✕</Text>
              </Pressable>
            </View>

            <Text className="text-xs text-slate-300 mb-3 leading-relaxed">
              Receive geofenced flood warnings when water rises near your family's residence, workplace, or children's school.
            </Text>

            {/* Label Input */}
            <Text className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
              PLACE LABEL
            </Text>
            <TextInput
              value={newLocationLabel}
              onChangeText={setNewLocationLabel}
              placeholder="e.g. Grandmother's House, Kids' School..."
              placeholderTextColor="#64748B"
              className="bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-white mb-2"
            />

            {/* Quick Presets */}
            <View className="flex-row gap-2 mb-3">
              {["Parents' Home", 'Workplace', "Kids' School"].map((preset) => (
                <Pressable
                  key={preset}
                  onPress={() => setNewLocationLabel(preset)}
                  className="bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-lg"
                >
                  <Text className="text-[10px] text-slate-300 font-bold">{preset}</Text>
                </Pressable>
              ))}
            </View>

            {/* Ward Selector */}
            <Text className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
              SELECT CATCHMENT BASIN / WARD
            </Text>
            <View className="flex-col gap-1.5 mb-3">
              {['Kurla West (Ward L)', 'Dharavi Basin (Ward 12)', "Dadar & King's Circle (Ward 4)"].map((w) => (
                <Pressable
                  key={w}
                  onPress={() => setNewLocationWard(w)}
                  className={`p-2.5 rounded-xl border flex-row items-center justify-between ${
                    newLocationWard === w ? 'bg-cyan-500/20 border-cyan-400' : 'bg-slate-950 border-slate-800'
                  }`}
                >
                  <Text className={`text-xs font-bold ${newLocationWard === w ? 'text-cyan-300' : 'text-slate-400'}`}>
                    {w}
                  </Text>
                  {newLocationWard === w && <Check size={14} color="#00F0FF" />}
                </Pressable>
              ))}
            </View>

            {/* Action Buttons */}
            <View className="flex-row gap-2 mt-1">
              <Pressable
                onPress={() => setIsAddingLocation(false)}
                className="flex-1 py-3 rounded-xl bg-slate-900 border border-slate-800 items-center justify-center"
              >
                <Text className="text-xs font-bold text-slate-400 uppercase">Cancel</Text>
              </Pressable>

              <Pressable
                onPress={handleCreateWatchLocation}
                disabled={isSavingLocation}
                className="flex-1 py-3 rounded-xl bg-cyan-500 items-center justify-center active:bg-cyan-600"
              >
                {isSavingLocation ? (
                  <ActivityIndicator size="small" color="#050A14" />
                ) : (
                  <Text className="text-xs font-black text-slate-950 uppercase">Save Place</Text>
                )}
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>

      {/* 8. Active Ward Incidents Bottom Sheet Modal */}
      <Modal
        visible={showIncidentsModal}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setShowIncidentsModal(false)}
      >
        <View className="flex-1 justify-end bg-black/80">
          <View className="bg-[#0A1120] border-t border-slate-700 rounded-t-3xl p-5 max-h-[82%]">
            {/* Modal Header */}
            <View className="flex-row items-center justify-between pb-3 border-b border-slate-800">
              <View className="flex-row items-center gap-2">
                <AlertTriangle size={18} color="#FB7185" />
                <View>
                  <Text className="text-sm font-black text-white">
                    Active Ward Inundation Incidents
                  </Text>
                  <Text className="text-[10px] text-slate-400">
                    Verified ground hazards from municipal disaster control
                  </Text>
                </View>
              </View>
              <Pressable
                onPress={() => setShowIncidentsModal(false)}
                className="w-8 h-8 rounded-full bg-slate-800 items-center justify-center"
              >
                <X size={16} color="#94A3B8" />
              </Pressable>
            </View>

            {/* Ward Filter Chips */}
            <View className="flex-row gap-2 my-3">
              {['ALL', 'KURLA', 'DADAR', 'DHARAVI'].map((ward) => {
                const isSelected = selectedWardFilter === ward;
                return (
                  <Pressable
                    key={ward}
                    onPress={() => setSelectedWardFilter(ward)}
                    className={`px-3 py-1.5 rounded-xl border ${
                      isSelected
                        ? 'bg-cyan-500/20 border-cyan-400'
                        : 'bg-slate-900 border-slate-800'
                    }`}
                  >
                    <Text className={`text-[11px] font-bold ${isSelected ? 'text-cyan-300' : 'text-slate-400'}`}>
                      {ward === 'ALL' ? 'All Wards' : `Ward ${ward}`}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            {/* Incidents List */}
            <ScrollView className="my-1" showsVerticalScrollIndicator={false}>
              {displayedIncidents.length === 0 ? (
                <View className="py-8 items-center">
                  <Text className="text-xs text-slate-400">No active incidents reported in this sector.</Text>
                </View>
              ) : (
                displayedIncidents.map((inc) => (
                  <View
                    key={inc.incident_id}
                    className="bg-[#050A14] border border-slate-800 rounded-2xl p-4 mb-3"
                  >
                    <View className="flex-row items-center justify-between mb-2">
                      <View className={`px-2 py-0.5 rounded ${
                        inc.severity === 'CRITICAL'
                          ? 'bg-rose-500/20 border border-rose-500/50'
                          : inc.severity === 'HIGH'
                          ? 'bg-amber-500/20 border border-amber-500/50'
                          : 'bg-blue-500/20 border border-blue-500/50'
                      }`}>
                        <Text className={`text-[10px] font-black uppercase ${
                          inc.severity === 'CRITICAL'
                            ? 'text-rose-400'
                            : inc.severity === 'HIGH'
                            ? 'text-amber-400'
                            : 'text-blue-400'
                        }`}>
                          {inc.severity} SEVERITY
                        </Text>
                      </View>

                      <View className="bg-slate-800 px-2 py-0.5 rounded">
                        <Text className="text-[10px] font-bold text-slate-300">
                          {inc.status}
                        </Text>
                      </View>
                    </View>

                    <Text className="text-sm font-black text-white">
                      {inc.title}
                    </Text>

                    <View className="flex-row items-center gap-3 mt-2">
                      <Text className="text-[10px] text-slate-400">
                        📍 {inc.ward_id}
                      </Text>
                      <Text className="text-[10px] text-slate-400">
                        🏷️ {inc.category.replace('_', ' ')}
                      </Text>
                    </View>

                    <View className="mt-3 pt-3 border-t border-slate-800/80 flex-row justify-end">
                      <Pressable
                        onPress={() => {
                          setShowIncidentsModal(false);
                          router.push('/(tabs)/radar');
                        }}
                        className="bg-cyan-500/20 border border-cyan-400/40 px-3 py-1.5 rounded-xl flex-row items-center gap-1.5 active:bg-cyan-500/30"
                      >
                        <MapPin size={12} color="#38BDF8" />
                        <Text className="text-xs font-black text-cyan-300">
                          Track on Radar Map
                        </Text>
                      </Pressable>
                    </View>
                  </View>
                ))
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
}
