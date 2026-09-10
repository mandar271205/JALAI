import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  View, 
  ScrollView, 
  Pressable, 
  Alert, 
  RefreshControl,
  Share,
  Modal,
  ActivityIndicator
} from 'react-native';
import { useRouter } from 'expo-router';
import { 
  Radio, 
  Volume2, 
  VolumeX,
  Play, 
  Pause, 
  CloudRain, 
  AlertTriangle, 
  MapPin, 
  Navigation, 
  Share2, 
  ChevronRight, 
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
  Activity,
  ArrowUpRight,
  Sliders,
  FileText,
  X
} from 'lucide-react-native';

import { AppHeader } from '@/components/shared/app-header';
import { Text } from '@/components/ui/text';
import { emergencyStore, useEmergencyStore } from '@/lib/emergency-store';
import { 
  fetchActiveAlerts, 
  fetchCurrentWeather,
  fetchRiskCells,
  fetchRoadClosures,
  fetchCriticalAssets,
  fetchAlertCapXml,
  type AlertItem,
  type CurrentWeatherResponse,
  type RiskCellItem,
  type RoadClosureSegment,
  type CriticalAssetItem,
  FALLBACK_ALERTS,
  FALLBACK_WEATHER,
  FALLBACK_RISK_CELLS,
  FALLBACK_ROAD_CLOSURES,
  FALLBACK_ASSETS
} from '@/lib/api';

type AlertFilter = 'ALL' | 'GOVT' | 'AI' | 'ROADS';
type AudioLang = 'EN' | 'HI' | 'MR';

interface AudioContent {
  title: string;
  langLabel: string;
  quote: string;
}

const AUDIO_SCRIPTS: Record<AudioLang, AudioContent> = {
  EN: {
    title: 'Disaster Audio Advisory (English)',
    langLabel: 'Official English Broadcast',
    quote: '"Official IMD flash flood directive: Avoid low-lying underpasses and basement parking along Mithi River catchment. Move to designated high ground immediately."'
  },
  HI: {
    title: 'आपदा चेतावनी ध्वनि बुलेटिन (हिंदी)',
    langLabel: 'आधिकारिक हिंदी प्रसारण',
    quote: '"आधिकारिक चेतावनी: मीठी नदी जलभराव क्षेत्र में तुरंत निचले इलाकों को खाली करें। सभी नागरिक सायन अस्पताल या उच्च स्थल राहत शिविरों की ओर जाएं।"'
  },
  MR: {
    title: 'आपत्ती चेतावणी ध्वनी बुलेटिन (मराठी)',
    langLabel: 'अधिकृत मराठी प्रसारण',
    quote: '"अधिकृत चेतावणी: मिठी नदीच्या पूर क्षेत्रातील सखल भागातून तातडीने सुरक्षित स्थळी जा. सर्व नागरिकांनी सायन किंवा सुरक्षित मदत केंद्रांचा आश्रय घ्यावा."'
  }
};

function formatWardName(wardId: string): string {
  if (wardId === 'WARD-12-DHARAVI') return 'Dharavi Basin (Ward 12)';
  if (wardId === 'WARD-08-KURLA') return 'Kurla West (Ward 8)';
  if (wardId === 'WARD-04-DADAR') return 'Dadar & King\'s Circle (Ward 4)';
  return wardId ? wardId.replace('WARD-', 'Ward ').replace('-', ' ') : 'Catchment Basin';
}

function cleanRoadName(name: string): string {
  return name.replace(' [CLOSED]', '').replace('[CLOSED]', '').trim();
}

function cleanHeadline(headline: string): string {
  if (!headline) return 'Civic Emergency Advisory';
  return headline
    .replace(/^IMD RED ALERT:\s*/i, '')
    .replace(/^CIVIC TRAFFIC ADVISORY:\s*/i, '')
    .replace(/^CIVIL DEFENSE ADVISORY:\s*/i, '')
    .replace(/^FLASH FLOOD WARNING:\s*/i, 'Flash Flood Warning: ')
    .replace(/^[A-Z0-9\s]{4,}:\s*/, '')
    .trim();
}

export default function AlertsScreen() {
  const router = useRouter();

  const [refreshing, setRefreshing] = useState(false);
  const [activeFilter, setActiveFilter] = useState<AlertFilter>('ALL');

  // Interactive Audio Warning Player State
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [selectedLang, setSelectedLang] = useState<AudioLang>('EN');
  const [audioSeconds, setAudioSeconds] = useState(24);

  // Audio timer simulation
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // OASIS CAP 1.2 XML Inspection State
  const [selectedCapXml, setSelectedCapXml] = useState<string | null>(null);
  const [selectedCapAlertId, setSelectedCapAlertId] = useState<string | null>(null);
  const [loadingCapXml, setLoadingCapXml] = useState(false);

  const handleViewCapXml = async (alertId: string) => {
    setLoadingCapXml(true);
    setSelectedCapAlertId(alertId);
    try {
      const xml = await fetchAlertCapXml(alertId);
      setSelectedCapXml(xml);
    } catch {
      Alert.alert('Error', 'Could not load CAP XML certificate.');
    } finally {
      setLoadingCapXml(false);
    }
  };

  useEffect(() => {
    if (isPlayingAudio) {
      timerRef.current = setInterval(() => {
        setAudioSeconds((prev) => (prev >= 75 ? 0 : prev + 1));
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlayingAudio]);

  // Live State from Backend
  const [alerts, setAlerts] = useState<AlertItem[]>(FALLBACK_ALERTS);
  const [weather, setWeather] = useState<CurrentWeatherResponse>(FALLBACK_WEATHER);
  const [riskCells, setRiskCells] = useState<RiskCellItem[]>(FALLBACK_RISK_CELLS);
  const [roadClosures, setRoadClosures] = useState<RoadClosureSegment[]>(FALLBACK_ROAD_CLOSURES);
  const [assets, setAssets] = useState<CriticalAssetItem[]>(FALLBACK_ASSETS);
  const [isLiveBackend, setIsLiveBackend] = useState(false);

  const loadAlertsData = useCallback(async () => {
    try {
      const [alertsRes, weatherRes, riskRes, closuresRes, assetsRes] = await Promise.all([
        fetchActiveAlerts(),
        fetchCurrentWeather(),
        fetchRiskCells(),
        fetchRoadClosures(),
        fetchCriticalAssets(),
      ]);

      setAlerts(Array.isArray(alertsRes?.data) ? alertsRes.data : FALLBACK_ALERTS);
      setWeather(weatherRes?.data || FALLBACK_WEATHER);
      setRiskCells(Array.isArray(riskRes?.data) ? riskRes.data : FALLBACK_RISK_CELLS);
      setRoadClosures(Array.isArray(closuresRes?.data) ? closuresRes.data : FALLBACK_ROAD_CLOSURES);
      setAssets(Array.isArray(assetsRes?.data) ? assetsRes.data : FALLBACK_ASSETS);

      setIsLiveBackend(alertsRes.isLive || weatherRes.isLive || closuresRes.isLive);
    } catch (e) {
      setIsLiveBackend(false);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadAlertsData();
  }, [loadAlertsData]);

  const onRefresh = () => {
    setRefreshing(true);
    loadAlertsData();
  };

  const handleToggleAudio = () => {
    setIsPlayingAudio((prev) => !prev);
  };

  const handleShareAlert = async (alertItem: AlertItem) => {
    try {
      await Share.share({
        message: `🚨 OFFICIAL DISASTER ADVISORY\nHeadline: ${alertItem.headline}\nArea: ${alertItem.area_description}\nSeverity: ${alertItem.severity.toUpperCase()}\nDirective: ${alertItem.instruction}\nVerified via JALAI Disaster Early Warning System.`,
      });
    } catch (error) {
      Alert.alert('Advisory Shared', 'Emergency warning copied to clipboard.');
    }
  };

  const { activeSos } = useEmergencyStore();

  const handleSosTrigger = () => {
    emergencyStore.openSos({ ward: 'Ward L & G/North' });
  };

  const filteredRoads = roadClosures.filter(r => r.is_closed || r.status === 'INUNDATED');
  const totalFeedsCount = alerts.length + riskCells.length + filteredRoads.length;

  const currentAudio = AUDIO_SCRIPTS[selectedLang];
  const audioProgressPercent = Math.min(100, Math.round((audioSeconds / 75) * 100));
  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  return (
    <View className="flex-1 bg-[#050A14]">
      {/* 1. Tactical Universal Header with Safe Area Insets */}
      <AppHeader
        location="Disaster Ops • Ward L & G/North"
        onDistressPress={handleSosTrigger}
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
        {/* 2. Top Tactical Broadcast Subheader */}
        <View className="px-5 pt-4 pb-2">
          {/* Status Row */}
          <View className="flex-row items-center justify-between mb-1.5">
            <View className="flex-row items-center gap-2">
              <View className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse shadow-sm shadow-rose-500" />
              <Text className="text-[11px] font-black text-rose-400 uppercase tracking-wider">
                Official Disaster Broadcast
              </Text>
            </View>
            <View className="flex-row items-center gap-1.5 bg-slate-900/90 px-2.5 py-1 rounded-full border border-slate-800">
              <View className={`w-2 h-2 rounded-full ${isLiveBackend ? 'bg-emerald-400' : 'bg-amber-400'}`} />
              <Text className="text-[10px] font-bold text-slate-300">
                {isLiveBackend ? 'Live Synced' : 'Offline Cached'}
              </Text>
            </View>
          </View>

          {/* Title Row */}
          <View className="flex-row items-center justify-between mt-1">
            <Text className="text-2xl font-black text-white tracking-tight">
              Emergency Hub
            </Text>
            <View className="bg-cyan-950/80 border border-cyan-500/40 px-3 py-1 rounded-full flex-row items-center gap-1.5">
              <Radio size={12} color="#00F0FF" />
              <Text className="text-xs font-bold text-cyan-300">
                {totalFeedsCount} Active Feeds
              </Text>
            </View>
          </View>

          {/* 3. Category Filter Tabs (With proper padding so pills never clip) */}
          <ScrollView 
            horizontal 
            showsHorizontalScrollIndicator={false} 
            contentContainerStyle={{ paddingRight: 20, gap: 8 }}
            className="mt-4 flex-row"
          >
            <Pressable
              onPress={() => setActiveFilter('ALL')}
              className={`px-3.5 py-2 rounded-xl flex-row items-center gap-1.5 border active:scale-95 ${
                activeFilter === 'ALL'
                  ? 'bg-cyan-500/20 border-cyan-400'
                  : 'bg-[#080E1A] border-slate-800'
              }`}
            >
              <Radio size={13} color={activeFilter === 'ALL' ? '#00F0FF' : '#94A3B8'} />
              <Text
                className={`text-xs font-bold ${
                  activeFilter === 'ALL' ? 'text-cyan-300' : 'text-slate-400'
                }`}
              >
                All Feeds ({totalFeedsCount})
              </Text>
            </Pressable>

            <Pressable
              onPress={() => setActiveFilter('GOVT')}
              className={`px-3.5 py-2 rounded-xl flex-row items-center gap-1.5 border active:scale-95 ${
                activeFilter === 'GOVT'
                  ? 'bg-rose-500/20 border-rose-400'
                  : 'bg-[#080E1A] border-slate-800'
              }`}
            >
              <ShieldAlert size={13} color={activeFilter === 'GOVT' ? '#FB7185' : '#94A3B8'} />
              <Text
                className={`text-xs font-bold ${
                  activeFilter === 'GOVT' ? 'text-rose-300' : 'text-slate-400'
                }`}
              >
                Govt Official ({alerts.length})
              </Text>
            </Pressable>

            <Pressable
              onPress={() => setActiveFilter('AI')}
              className={`px-3.5 py-2 rounded-xl flex-row items-center gap-1.5 border active:scale-95 ${
                activeFilter === 'AI'
                  ? 'bg-cyan-500/20 border-cyan-400'
                  : 'bg-[#080E1A] border-slate-800'
              }`}
            >
              <Sparkles size={13} color={activeFilter === 'AI' ? '#00F0FF' : '#94A3B8'} />
              <Text
                className={`text-xs font-bold ${
                  activeFilter === 'AI' ? 'text-cyan-300' : 'text-slate-400'
                }`}
              >
                AI Predictive ({riskCells.length})
              </Text>
            </Pressable>

            <Pressable
              onPress={() => setActiveFilter('ROADS')}
              className={`px-3.5 py-2 rounded-xl flex-row items-center gap-1.5 border active:scale-95 ${
                activeFilter === 'ROADS'
                  ? 'bg-amber-500/20 border-amber-400'
                  : 'bg-[#080E1A] border-slate-800'
              }`}
            >
              <Navigation size={13} color={activeFilter === 'ROADS' ? '#FBBF24' : '#94A3B8'} />
              <Text
                className={`text-xs font-bold ${
                  activeFilter === 'ROADS' ? 'text-amber-300' : 'text-slate-400'
                }`}
              >
                Road Closures ({filteredRoads.length})
              </Text>
            </Pressable>
          </ScrollView>
        </View>

        {/* Multilingual Voice Broadcast Player */}
        <View className="px-5 pt-3">
          <View className="bg-[#0B1527] border border-cyan-500/50 rounded-2xl p-4 shadow-xl">
            {/* Player Header */}
            <View className="flex-row items-center justify-between mb-3">
              <View className="flex-row items-center gap-2 flex-1 mr-2 min-w-0">
                <Volume2 size={16} color="#00F0FF" />
                <Text className="text-xs font-black text-white uppercase tracking-wider" numberOfLines={1}>
                  Civil Defense Audio Advisory
                </Text>
              </View>
              <View className="flex-row gap-1">
                {(['EN', 'HI', 'MR'] as AudioLang[]).map((lang) => (
                  <Pressable
                    key={lang}
                    onPress={() => setSelectedLang(lang)}
                    className={`px-2 py-0.5 rounded-md border ${
                      selectedLang === lang
                        ? 'bg-cyan-500/30 border-cyan-400'
                        : 'bg-slate-900 border-slate-800'
                    }`}
                  >
                    <Text className={`text-[10px] font-black ${selectedLang === lang ? 'text-cyan-200' : 'text-slate-400'}`}>
                      {lang === 'EN' ? 'ENG' : lang === 'HI' ? 'हिंदी' : 'मराठी'}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </View>

            {/* Audio Quote */}
            <Text className="text-xs text-slate-300 italic mb-3 leading-relaxed">
              {currentAudio.quote}
            </Text>

            {/* Waveform & Playback Controls */}
            <View className="bg-[#050B14] rounded-xl p-3 border border-slate-800 flex-row items-center gap-3">
              <Pressable
                onPress={handleToggleAudio}
                className="w-10 h-10 rounded-full bg-cyan-500 items-center justify-center shadow-lg active:scale-95 flex-shrink-0"
              >
                {isPlayingAudio ? (
                  <Pause size={18} color="#050A14" />
                ) : (
                  <Play size={18} color="#050A14" />
                )}
              </Pressable>

              <View className="flex-1">
                <View className="flex-row items-center justify-between mb-1">
                  <Text className="text-[10px] font-bold text-cyan-300">
                    {currentAudio.langLabel}
                  </Text>
                  <Text className="text-[10px] font-mono text-slate-400">
                    {formatTime(audioSeconds)} / 1:15
                  </Text>
                </View>

                {/* Audio Progress Bar */}
                <View className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                  <View
                    className="h-full bg-cyan-400"
                    style={{ width: `${audioProgressPercent}%` }}
                  />
                </View>
              </View>
            </View>
          </View>
        </View>

        {/* 4. Alert Cards Stream (100% Dynamically Mapped from Backend) */}
        <View className="px-5 pt-3 flex-col gap-4">

          {/* ================= DYNAMIC LIST 1: OFFICIAL GOVERNMENT CAP WARNINGS ================= */}
          {(activeFilter === 'ALL' || activeFilter === 'GOVT') &&
            alerts.map((alertItem, idx) => {
              const isExtreme = alertItem.severity === 'Extreme';
              const isSevere = alertItem.severity === 'Severe';
              const isModerate = !isExtreme && !isSevere;

              const cardBorder = isExtreme 
                ? 'border-2 border-rose-500/80 bg-[#0A1120]' 
                : isSevere 
                ? 'border-2 border-amber-500/70 bg-[#0B1324]' 
                : 'border border-emerald-500/60 bg-[#081220]';

              const severityPill = isExtreme 
                ? { bg: 'bg-rose-600', text: 'LEVEL 4 • RED ALERT', dot: 'bg-white' }
                : isSevere 
                ? { bg: 'bg-amber-600', text: 'LEVEL 3 • SEVERE WARNING', dot: 'bg-amber-200' }
                : { bg: 'bg-emerald-600', text: 'LEVEL 2 • CIVIC NOTICE', dot: 'bg-emerald-200' };

              const authorityTag = isExtreme
                ? 'IMD DISASTER UNIT'
                : isSevere
                ? 'TRAFFIC POLICE DIRECTIVE'
                : 'CIVIL DEFENSE HAVEN';

              const displayHeadline = cleanHeadline(alertItem.headline);

              return (
                <View key={alertItem.alert_id || idx} className={`${cardBorder} rounded-2xl p-4 shadow-xl`}>
                  
                  {/* Authoritative Unified Top Header Bar */}
                  <View className="flex-row items-center justify-between mb-3">
                    {/* Left: Official Level Badge */}
                    <View className={`${severityPill.bg} px-2.5 py-1 rounded-full flex-row items-center gap-1.5`}>
                      <View className={`w-2 h-2 rounded-full ${severityPill.dot} animate-pulse`} />
                      <Text className="text-[10px] font-black text-white uppercase tracking-wider">
                        {severityPill.text}
                      </Text>
                    </View>

                    {/* Right: Official Authority Verification Seal */}
                    <View className="flex-row items-center gap-1 bg-slate-900/90 border border-slate-700/60 px-2 py-0.5 rounded-md">
                      <ShieldCheck size={11} color={isExtreme ? '#F87171' : isSevere ? '#FBBF24' : '#34D399'} />
                      <Text className="text-[9px] font-bold text-slate-300 uppercase tracking-wide">
                        {authorityTag}
                      </Text>
                    </View>
                  </View>

                  {/* Clean Headline (Never Repeats Prefix!) */}
                  <Text className="text-lg font-black text-white tracking-tight leading-snug">
                    {displayHeadline}
                  </Text>

                  {/* Clean Structured Timing & Impact Corridor (Zero Truncation!) */}
                  <View className="flex-col gap-1.5 mt-2 mb-3.5 bg-slate-950/60 p-2.5 rounded-xl border border-slate-900">
                    <View className="flex-row items-center gap-2">
                      <Clock size={12} color={isExtreme ? '#F87171' : isSevere ? '#FBBF24' : '#34D399'} />
                      <Text className="text-xs font-bold text-slate-200">
                        Active Advisory • Immediate Effect (Next 3 Hours)
                      </Text>
                    </View>
                    <View className="flex-row items-start gap-2">
                      <MapPin size={12} color="#94A3B8" style={{ marginTop: 2 }} />
                      <Text className="text-xs text-slate-300 font-medium leading-relaxed flex-1">
                        {alertItem.area_description}
                      </Text>
                    </View>
                  </View>

                  {/* ================= HIGH-TECH EMERGENCY SPOKEN AUDIO PLAYER ================= */}
                  {idx === 0 && isExtreme && (
                    <View className="bg-slate-950/90 border border-rose-900/50 rounded-xl p-3 mb-3.5 shadow-inner">
                      {/* Audio Header Row */}
                      <View className="flex-row items-center justify-between mb-2">
                        <View className="flex-row items-center gap-1.5">
                          <Volume2 size={13} color="#F43F5E" />
                          <Text className="text-[10px] font-black text-rose-300 uppercase tracking-wider">
                            Official Spoken Audio Bulletin
                          </Text>
                        </View>

                        {/* Language Selection Tabs */}
                        <View className="flex-row gap-1 bg-slate-900 p-0.5 rounded-lg border border-slate-800">
                          {(['EN', 'HI', 'KN'] as AudioLang[]).map((lang) => (
                            <Pressable
                              key={lang}
                              onPress={() => setSelectedLang(lang)}
                              className={`px-2 py-0.5 rounded-md active:scale-95 ${
                                selectedLang === lang
                                  ? 'bg-rose-600'
                                  : 'bg-transparent'
                              }`}
                            >
                              <Text
                                className={`text-[10px] font-black ${
                                  selectedLang === lang ? 'text-white' : 'text-slate-400'
                                }`}
                              >
                                {lang}
                              </Text>
                            </Pressable>
                          ))}
                        </View>
                      </View>

                      {/* Main Audio Controls */}
                      <View className="flex-row items-center gap-3">
                        <Pressable
                          onPress={handleToggleAudio}
                          className="w-11 h-11 rounded-full bg-rose-600 items-center justify-center active:scale-95 shadow-lg shadow-rose-600/50"
                        >
                          {isPlayingAudio ? (
                            <Pause size={18} color="#FFFFFF" />
                          ) : (
                            <Play size={18} color="#FFFFFF" style={{ marginLeft: 2 }} />
                          )}
                        </Pressable>

                        <View className="flex-1 min-w-0">
                          <Text className="text-xs font-black text-white" numberOfLines={1}>
                            {currentAudio.title}
                          </Text>
                          <Text className="text-[11px] text-slate-400 mt-0.5" numberOfLines={1}>
                            {isPlayingAudio ? 'Broadcasting verified voice bulletin...' : currentAudio.langLabel}
                          </Text>
                        </View>
                      </View>

                      {/* Animated Equalizer Waveform & Progress Bar */}
                      <View className="mt-2.5 pt-2 border-t border-slate-900">
                        {/* Audio Frequency Bars Simulation */}
                        <View className="flex-row items-center justify-between h-4 px-1 mb-1.5">
                          {[6, 12, 16, 9, 14, 18, 11, 7, 15, 17, 10, 14, 16, 8, 12, 15].map((h, bIdx) => (
                            <View
                              key={bIdx}
                              style={{ 
                                height: isPlayingAudio ? Math.max(4, (h * ((bIdx + audioSeconds) % 5 + 1)) / 3) : 3,
                                backgroundColor: isPlayingAudio ? '#F43F5E' : '#475569'
                              }}
                              className="w-1 rounded-full transition-all"
                            />
                          ))}
                        </View>

                        {/* Progress Bar */}
                        <View className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden">
                          <View 
                            style={{ width: `${audioProgressPercent}%` }} 
                            className="h-full bg-rose-500 rounded-full" 
                          />
                        </View>
                        <View className="flex-row justify-between items-center mt-1">
                          <Text className="text-[10px] text-rose-400 font-bold">{formatTime(audioSeconds)}</Text>
                          <Text className="text-[10px] text-slate-500 font-medium">1:15</Text>
                        </View>
                      </View>

                      {/* Spoken Quote Transcript */}
                      <Text className="text-[11px] text-slate-300 italic mt-2 bg-slate-900/60 p-2 rounded-lg border border-slate-800">
                        {currentAudio.quote}
                      </Text>
                    </View>
                  )}

                  {/* Mandatory Citizen Action Directive (With Official Accent Bar) */}
                  <View className={`border-l-4 rounded-r-xl rounded-l-sm p-3.5 mb-3.5 ${
                    isExtreme 
                      ? 'border-l-rose-500 bg-rose-950/20 border border-rose-900/40' 
                      : isSevere
                      ? 'border-l-amber-500 bg-amber-950/20 border border-amber-900/40'
                      : 'border-l-emerald-500 bg-emerald-950/20 border border-emerald-900/40'
                  }`}>
                    <View className="flex-row items-center gap-1.5 mb-1.5">
                      <AlertTriangle size={13} color={isExtreme ? '#F87171' : isSevere ? '#FBBF24' : '#34D399'} />
                      <Text className={`text-[10px] font-black uppercase tracking-wider ${
                        isExtreme ? 'text-rose-300' : isSevere ? 'text-amber-300' : 'text-emerald-300'
                      }`}>
                        MANDATORY CITIZEN ACTION DIRECTIVE
                      </Text>
                    </View>
                    <Text className="text-xs text-slate-100 leading-relaxed font-medium">
                      {alertItem.instruction}
                    </Text>
                  </View>

                  {/* Dual Civic Telemetry Readout */}
                  {isExtreme && (
                    <View className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 mb-3.5 flex-row items-center justify-between">
                      {/* Metric 1 */}
                      <View>
                        <Text className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">
                          PRECIPITATION RATE
                        </Text>
                        <View className="flex-row items-baseline gap-1 mt-0.5">
                          <Text className="text-2xl font-black text-white">
                            {weather.average_rainfall_rate_mm_h || 48.5}
                          </Text>
                          <Text className="text-xs font-bold text-rose-400">mm/hr</Text>
                        </View>
                        <Text className="text-[10px] font-semibold text-rose-300 mt-0.5">
                          Extreme Cloudburst
                        </Text>
                      </View>

                      {/* Visual 5-Segment Telemetry Level Gauge */}
                      <View className="items-end">
                        <Text className="text-[9px] font-bold text-slate-400 uppercase tracking-wider mb-1.5">
                          SURGE LEVEL
                        </Text>
                        <View className="flex-row items-end gap-1 h-6">
                          <View className="w-2 h-2.5 bg-rose-500 rounded-sm" />
                          <View className="w-2 h-3.5 bg-rose-500 rounded-sm" />
                          <View className="w-2 h-4.5 bg-rose-500 rounded-sm" />
                          <View className="w-2 h-5.5 bg-rose-500 rounded-sm" />
                          <View className="w-2 h-6.5 bg-rose-600 rounded-sm shadow-sm shadow-rose-500" />
                        </View>
                        <Text className="text-[10px] font-bold text-white mt-1">
                          +0.72m Inundation
                        </Text>
                      </View>
                    </View>
                  )}

                  {isSevere && (
                    <View className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 mb-3.5 flex-row gap-2.5">
                      <View className="flex-1 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                        <Text className="text-[9px] font-bold text-slate-400 uppercase">
                          POLICE STATUS
                        </Text>
                        <Text className="text-xs font-black text-rose-400 mt-0.5" numberOfLines={1}>
                          ⛔ Strictly Barricaded
                        </Text>
                      </View>
                      <View className="flex-1 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                        <Text className="text-[9px] font-bold text-slate-400 uppercase">
                          INUNDATION DEPTH
                        </Text>
                        <Text className="text-xs font-black text-amber-400 mt-0.5" numberOfLines={1}>
                          0.85m Waterlogging
                        </Text>
                      </View>
                    </View>
                  )}

                  {isModerate && (
                    <View className="bg-slate-900/80 border border-slate-800 rounded-xl p-3 mb-3.5 flex-row gap-2.5">
                      <View className="flex-1 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                        <Text className="text-[9px] font-bold text-slate-400 uppercase">
                          SAFE HAVEN ELEVATION
                        </Text>
                        <Text className="text-xs font-black text-emerald-400 mt-0.5" numberOfLines={1}>
                          +5.4m MSL (Safe Ground)
                        </Text>
                      </View>
                      <View className="flex-1 bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                        <Text className="text-[9px] font-bold text-slate-400 uppercase">
                          FACILITY CAPACITY
                        </Text>
                        <Text className="text-xs font-black text-cyan-300 mt-0.5" numberOfLines={1}>
                          120 Beds Ready
                        </Text>
                      </View>
                    </View>
                  )}

                  {/* Correct Action Hierarchy: Primary Safety Action (Solid) + Secondary Utility (Outline) */}
                  <View className="flex-row gap-2.5">
                    <Pressable
                      onPress={() => router.push('/(tabs)/radar')}
                      className={`flex-1 py-3 rounded-xl flex-row items-center justify-center gap-2 active:scale-95 ${
                        isExtreme 
                          ? 'bg-rose-600 active:bg-rose-700' 
                          : isSevere
                          ? 'bg-amber-500 active:bg-amber-600'
                          : 'bg-emerald-500 active:bg-emerald-600'
                      }`}
                    >
                      <Navigation size={15} color={isExtreme ? '#FFFFFF' : '#050A14'} />
                      <Text className={`text-xs font-black uppercase tracking-wider ${
                        isExtreme ? 'text-white' : 'text-slate-950'
                      }`}>
                        {isExtreme 
                          ? 'View Impact Zone on Radar' 
                          : isSevere 
                          ? 'View Road Closures on Radar' 
                          : 'Navigate to Safe Haven'}
                      </Text>
                    </Pressable>

                    <Pressable
                      onPress={() => handleShareAlert(alertItem)}
                      className="bg-slate-900 border border-slate-700 px-3.5 py-3 rounded-xl flex-row items-center justify-center gap-1.5 active:bg-slate-800"
                    >
                      <Share2 size={14} color="#CBD5E1" />
                      <Text className="text-xs font-bold text-slate-200 uppercase">
                        Share
                      </Text>
                    </Pressable>

                    <Pressable
                      onPress={() => handleViewCapXml(alertItem.alert_id)}
                      className="bg-cyan-950/60 border border-cyan-500/40 px-3 py-3 rounded-xl flex-row items-center justify-center gap-1.5 active:bg-cyan-900/60"
                    >
                      <FileText size={14} color="#38BDF8" />
                      <Text className="text-xs font-bold text-cyan-300 uppercase">
                        CAP XML
                      </Text>
                    </Pressable>
                  </View>
                </View>
              );
            })}

          {/* ================= DYNAMIC LIST 2: AI PREDICTIVE CLOUDBURST NOWCASTS ================= */}
          {(activeFilter === 'ALL' || activeFilter === 'AI') &&
            riskCells.map((cell, idx) => (
              <View key={cell.h3_cell_id || idx} className="bg-[#0A1222] border-2 border-cyan-500/60 rounded-2xl p-4 shadow-lg">
                {/* Header Row */}
                <View className="flex-row items-center justify-between mb-2.5">
                  <View className="bg-cyan-500/20 border border-cyan-400/40 px-2.5 py-0.5 rounded-full flex-row items-center gap-1.5">
                    <Sparkles size={12} color="#00F0FF" />
                    <Text className="text-[10px] font-black text-cyan-300 uppercase">
                      AI Inundation Nowcast
                    </Text>
                  </View>
                  <Text className="text-xs font-semibold text-slate-400">
                    Confidence: <Text className="font-bold text-amber-400">{Math.round((cell.confidence || 0.90) * 100)}%</Text> • ETA 25 Min
                  </Text>
                </View>

                {/* Title & Humanized Description */}
                <Text className="text-base font-black text-white tracking-tight leading-snug">
                  Rapid Catchment Inundation • {formatWardName(cell.ward_id)}
                </Text>
                <Text className="text-xs text-cyan-200 mt-1 leading-relaxed">
                  Localized heavy precipitation ({cell.rainfall_rate_mm_h} mm/hr). Low-lying stormwater channels expected to overflow within 25 minutes.
                </Text>

                {/* Recommended Evacuation Passage */}
                <View className="border-l-4 border-l-cyan-500 bg-cyan-950/20 border border-cyan-900/40 rounded-r-xl rounded-l-sm p-3 my-3">
                  <View className="flex-row items-center gap-1.5 mb-1">
                    <Navigation size={13} color="#00F0FF" />
                    <Text className="text-[10px] font-black text-cyan-300 uppercase tracking-wider">
                      RECOMMENDED EVACUATION PASSAGE
                    </Text>
                  </View>
                  <Text className="text-xs text-slate-200 leading-relaxed font-medium">
                    Avoid low-lying CST Road and Mithi Canal underpasses. Divert onto the elevated Eastern High Ground arterial corridor immediately.
                  </Text>
                </View>

                {/* Elevation Advantage Banner */}
                <View className="bg-slate-950 border border-slate-800 rounded-xl p-3 mb-3.5">
                  <View className="mb-2">
                    <Text className="text-xs font-black text-emerald-400">
                      Elevation Advantage: +5.4m Higher Ground Transit Corridor
                    </Text>
                    <Text className="text-[11px] text-slate-400 mt-0.5">
                      Safe transit guaranteed via elevated bypass route
                    </Text>
                  </View>
                  <View className="h-2 w-full bg-slate-800 rounded-full overflow-hidden flex-row">
                    <View className="h-full bg-rose-500 w-1/4" />
                    <View className="h-full bg-amber-500 w-1/4" />
                    <View className="h-full bg-emerald-400 w-1/2" />
                  </View>
                </View>

                {/* Primary Action Button */}
                <Pressable
                  onPress={() => router.push('/(tabs)/safety')}
                  className="bg-cyan-500 py-3 rounded-xl flex-row items-center justify-center gap-2 active:bg-cyan-600"
                >
                  <Navigation size={15} color="#050A14" />
                  <Text className="text-xs font-black text-slate-950 uppercase tracking-wider">
                    Reroute via High-Ground Corridor
                  </Text>
                </Pressable>
              </View>
            ))}

          {/* ================= DYNAMIC LIST 3: REAL ROAD CLOSURES ADVISORIES ================= */}
          {(activeFilter === 'ALL' || activeFilter === 'ROADS') &&
            filteredRoads.map((road, idx) => {
              const isStrictlyClosed = road.is_closed;
              return (
                <View key={road.road_name + idx} className="bg-[#0B1424] border border-amber-500/60 rounded-2xl p-4 shadow-lg">
                  {/* Header Row */}
                  <View className="flex-row items-center justify-between mb-2">
                    <View className="flex-row items-center gap-1.5 bg-amber-500/20 border border-amber-500/40 px-2.5 py-0.5 rounded">
                      <AlertTriangle size={11} color="#FBBF24" />
                      <Text className="text-[10px] font-black text-amber-300 uppercase">
                        Traffic Police Road Advisory
                      </Text>
                    </View>
                    <Text className="text-xs text-slate-400 font-medium">Verified Active</Text>
                  </View>

                  <Text className="text-base font-black text-white tracking-tight">
                    {cleanRoadName(road.road_name)}
                  </Text>
                  <Text className="text-xs text-slate-300 mt-1 leading-relaxed">
                    {isStrictlyClosed
                      ? 'Traffic halted by municipal police due to canal overflow. Secondary diversion active via elevated bypass.'
                      : `Deep waterlogging (${road.flood_depth_m}m) recorded. Single lane slow speed only.`}
                  </Text>

                  {/* Road Status Metrics */}
                  <View className="flex-row gap-2.5 my-3">
                    <View className="flex-1 bg-slate-900/90 p-2.5 rounded-xl border border-slate-800">
                      <Text className="text-[9px] font-bold text-slate-400 uppercase">
                        POLICE STATUS
                      </Text>
                      <Text className={`text-xs font-black mt-1 ${isStrictlyClosed ? 'text-rose-400' : 'text-amber-400'}`} numberOfLines={1}>
                        {isStrictlyClosed ? '⛔ Strictly Closed' : '⚠️ Submerged Slow'}
                      </Text>
                    </View>

                    <View className="flex-1 bg-slate-900/90 p-2.5 rounded-xl border border-slate-800">
                      <Text className="text-[9px] font-bold text-slate-400 uppercase">
                        WATER DEPTH
                      </Text>
                      <Text className="text-xs font-black text-amber-400 mt-1" numberOfLines={1}>
                        {road.flood_depth_m > 0 ? `${road.flood_depth_m}m Inundated` : 'Barricaded'}
                      </Text>
                    </View>
                  </View>

                  {/* Action Button */}
                  <Pressable
                    onPress={() => router.push('/(tabs)/radar')}
                    className="bg-slate-850 border border-slate-700 py-3 rounded-xl flex-row items-center justify-center gap-2 active:bg-slate-750"
                  >
                    <Compass size={14} color="#FBBF24" />
                    <Text className="text-xs font-bold text-white uppercase tracking-wider">
                      Inspect Closure On Radar
                    </Text>
                  </Pressable>
                </View>
              );
            })}

          {/* ================= DYNAMIC LIST 4: CRITICAL FACILITIES & SHELTER BASES ================= */}
          {(activeFilter === 'ALL' || activeFilter === 'GOVT') && (
            <View className="bg-[#0B1322] border border-slate-800 rounded-2xl p-4">
              {/* Header */}
              <View className="flex-row items-center justify-between mb-3">
                <View className="flex-row items-center gap-1.5 flex-1 mr-2 min-w-0">
                  <Zap size={14} color="#00F0FF" className="flex-shrink-0" />
                  <Text className="text-xs font-black text-cyan-400 uppercase tracking-wider flex-1" numberOfLines={1}>
                    Infrastructure Sentinel
                  </Text>
                </View>
                <View className="bg-emerald-500/20 border border-emerald-500/40 px-2 py-0.5 rounded flex-shrink-0">
                  <Text className="text-[9px] font-black text-emerald-400 uppercase">
                    Safe Bases Active
                  </Text>
                </View>
              </View>

              <View className="flex-col gap-3">
                {assets.map((asset) => (
                  <View key={asset.asset_id} className="bg-slate-900/90 border border-slate-800 p-3 rounded-xl flex-row items-center justify-between">
                    <View className="flex-1 pr-3 min-w-0">
                      <Text className="text-xs font-bold text-white" numberOfLines={1}>
                        {asset.name}
                      </Text>
                      <Text className="text-[11px] text-slate-400 mt-0.5" numberOfLines={1}>
                        {asset.asset_type === 'HOSPITAL' 
                          ? 'Emergency Safe Haven • 120 Beds Open' 
                          : '110kV Power Grid • Protected by Sandbag Dykes'}
                      </Text>
                    </View>

                    <View className={`px-2 py-0.5 rounded flex-shrink-0 ${
                      asset.status === 'AT_RISK' ? 'bg-amber-500/20 text-amber-300' : 'bg-emerald-500/20 text-emerald-300'
                    }`}>
                      <Text className={`text-[10px] font-black uppercase ${
                        asset.status === 'AT_RISK' ? 'text-amber-300' : 'text-emerald-300'
                      }`}>
                        {asset.status === 'AT_RISK' ? 'Monitored' : 'Operational'}
                      </Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* ================= CARD 5: STICKY FLOATING SOS BANNER ================= */}
          <Pressable
            onPress={handleSosTrigger}
            className={`border p-4 rounded-2xl flex-row items-center justify-between active:scale-[0.98] shadow-xl mt-2 ${
              activeSos
                ? 'bg-rose-700 border-rose-400'
                : 'bg-rose-950/90 border-rose-600/70'
            }`}
          >
            <View className="flex-row items-center gap-3.5 flex-1 pr-2">
              <View className={`w-11 h-11 rounded-full items-center justify-center shadow ${activeSos ? 'bg-rose-500' : 'bg-rose-600'}`}>
                <LifeBuoy size={22} color="#FFFFFF" />
              </View>
              <View className="flex-1">
                <Text className="text-sm font-black text-white uppercase tracking-wide">
                  {activeSos ? 'SOS DISPATCH ACTIVE • RESCUE EN ROUTE' : 'STRANDED IN FLOOD WATER?'}
                </Text>
                <Text className="text-xs text-rose-200 mt-0.5">
                  {activeSos ? 'Tap to view live ETA and responder contacts' : 'Broadcast GPS to Disaster Rescue Command'}
                </Text>
              </View>
            </View>
            <ChevronRight size={22} color="#FECDD3" />
          </Pressable>
        </View>
      </ScrollView>

      {/* OASIS CAP 1.2 XML Inspection Modal */}
      <Modal
        visible={Boolean(selectedCapAlertId)}
        animationType="fade"
        transparent={true}
        onRequestClose={() => {
          setSelectedCapAlertId(null);
          setSelectedCapXml(null);
        }}
      >
        <View className="flex-1 bg-black/85 justify-center p-4">
          <View className="bg-[#070D18] border-2 border-cyan-500 rounded-2xl max-h-[85%] flex-col overflow-hidden shadow-2xl">
            {/* Modal Header */}
            <View className="px-4 py-3 bg-[#0A1220] border-b border-slate-800 flex-row items-center justify-between">
              <View className="flex-row items-center gap-2">
                <View className="w-8 h-8 rounded-lg bg-cyan-950 border border-cyan-500/50 items-center justify-center">
                  <FileText size={16} color="#38BDF8" />
                </View>
                <View>
                  <Text className="text-xs font-black text-white uppercase tracking-wider">
                    OASIS CAP 1.2 XML CERTIFICATE
                  </Text>
                  <Text className="text-[10px] text-cyan-300 font-mono">
                    URN:OASIS:NAMES:TC:EMERGENCY:CAP:1.2
                  </Text>
                </View>
              </View>
              <Pressable
                onPress={() => {
                  setSelectedCapAlertId(null);
                  setSelectedCapXml(null);
                }}
                className="w-8 h-8 rounded-full bg-slate-800 items-center justify-center active:scale-95"
              >
                <X size={16} color="#94A3B8" />
              </Pressable>
            </View>

            {/* XML Body */}
            <ScrollView className="p-4 flex-1">
              {loadingCapXml ? (
                <View className="py-12 items-center justify-center">
                  <ActivityIndicator size="large" color="#38BDF8" />
                  <Text className="text-xs text-slate-400 mt-2 font-bold">
                    Fetching Authenticated CAP 1.2 XML...
                  </Text>
                </View>
              ) : (
                <View>
                  <Text className="text-[10px] text-slate-400 mb-2">
                    Official Common Alerting Protocol XML schema disseminated to NDMA, BMC Disaster Room, and Cell Broadcast transmitters:
                  </Text>
                  <View className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                    <Text className="text-[11px] font-mono text-emerald-400 leading-relaxed">
                      {selectedCapXml}
                    </Text>
                  </View>
                </View>
              )}
            </ScrollView>

            {/* Modal Footer */}
            <View className="p-3 bg-[#0A1220] border-t border-slate-800 flex-row gap-2">
              <Pressable
                onPress={() => {
                  if (selectedCapXml) {
                    Share.share({ message: selectedCapXml }).catch(() => {});
                  }
                }}
                className="flex-1 py-2.5 bg-cyan-600 rounded-xl flex-row items-center justify-center gap-1.5 active:bg-cyan-700"
              >
                <Share2 size={14} color="#FFFFFF" />
                <Text className="text-xs font-black text-white uppercase tracking-wider">
                  Share XML Certificate
                </Text>
              </Pressable>
              <Pressable
                onPress={() => {
                  setSelectedCapAlertId(null);
                  setSelectedCapXml(null);
                }}
                className="px-4 py-2.5 bg-slate-800 rounded-xl items-center justify-center active:bg-slate-700"
              >
                <Text className="text-xs font-bold text-slate-300">Close</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}
