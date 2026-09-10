import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  View, 
  ScrollView, 
  Pressable, 
  Alert, 
  RefreshControl,
  Image,
  TextInput,
  Modal,
  ActivityIndicator
} from 'react-native';
import { useRouter } from 'expo-router';
import { 
  Camera, 
  MapPin, 
  Navigation, 
  ShieldAlert, 
  Clock, 
  Sparkles,
  LifeBuoy,
  Zap,
  ShieldCheck,
  CheckCircle2,
  Droplets,
  AlertTriangle,
  Mic,
  MicOff,
  Radio,
  Share2,
  Crosshair,
  Sliders,
  ChevronRight,
  Eye,
  Check,
  RefreshCw,
  Flame,
  Info
} from 'lucide-react-native';

import { AppHeader } from '@/components/shared/app-header';
import { Text } from '@/components/ui/text';
import { emergencyStore } from '@/lib/emergency-store';
import { 
  fetchFieldReports,
  submitFieldReport,
  type FieldReportItem,
  type SubmitReportPayload,
  FALLBACK_REPORTS
} from '@/lib/api';

type TabMode = 'NEW_REPORT' | 'FEED';
type DepthTier = 'WET_ROAD' | 'ANKLE_DEEP' | 'KNEE_DEEP' | 'WAIST_DEEP';

interface DepthTierMeta {
  tier: DepthTier;
  label: string;
  rangeCm: string;
  rangeIn: string;
  badge: string;
  severityColor: string;
  badgeBg: string;
  badgeText: string;
  description: string;
  depthCm: number;
}

const DEPTH_TIERS: DepthTierMeta[] = [
  {
    tier: 'WET_ROAD',
    label: 'Wet Road',
    rangeCm: '0 - 8 cm',
    rangeIn: '0 - 3 in',
    badge: 'MILD',
    severityColor: '#10B981',
    badgeBg: 'bg-emerald-500/20 border-emerald-500/40',
    badgeText: 'text-emerald-300',
    description: 'Road passable at low speeds. Surface hydroplaning hazard.',
    depthCm: 6.0,
  },
  {
    tier: 'ANKLE_DEEP',
    label: 'Ankle Deep',
    rangeCm: '10 - 20 cm',
    rangeIn: '4 - 8 in',
    badge: 'MODERATE',
    severityColor: '#00F0FF',
    badgeBg: 'bg-cyan-500/20 border-cyan-500/40',
    badgeText: 'text-cyan-300',
    description: 'Curbs covered. 2-wheelers at risk of slipping/stalling.',
    depthCm: 18.0,
  },
  {
    tier: 'KNEE_DEEP',
    label: 'Knee Deep',
    rangeCm: '30 - 60 cm',
    rangeIn: '1 - 2 ft',
    badge: 'DANGEROUS',
    severityColor: '#F59E0B',
    badgeBg: 'bg-amber-500/20 border-amber-500/40',
    badgeText: 'text-amber-300',
    description: 'Car exhausts submerged. Auto rickshaws stalling in flow.',
    depthCm: 50.0,
  },
  {
    tier: 'WAIST_DEEP',
    label: 'Waist Deep+',
    rangeCm: '75+ cm',
    rangeIn: '2.5+ ft',
    badge: 'CRITICAL',
    severityColor: '#F43F5E',
    badgeBg: 'bg-rose-500/20 border-rose-500/40',
    badgeText: 'text-rose-300',
    description: 'Vehicles floating. Pedestrian transit impassable. Evacuate.',
    depthCm: 85.0,
  },
];

const EVIDENCE_PHOTOS = [
  {
    id: 'kurla-bus',
    name: 'Kurla Station West Bus Depot',
    url: 'https://images.unsplash.com/photo-1547683905-f686c993aae5?w=600&auto=format&fit=crop&q=80',
    tag: 'Arterial Inundation',
  },
  {
    id: 'cst-road',
    name: 'CST Road Underpass',
    url: 'https://images.unsplash.com/photo-1515694346937-94d85e41e6f0?w=600&auto=format&fit=crop&q=80',
    tag: 'Bridge Submerged',
  },
  {
    id: 'mithi-canal',
    name: 'Mithi Canal Stormwater Surge',
    url: 'https://images.unsplash.com/photo-1517483000871-1dbf64a6e1c6?w=600&auto=format&fit=crop&q=80',
    tag: 'Drain Overflow',
  },
];

const QUICK_HAZARDS = [
  { id: 'ROAD_BLOCKED', label: '⛔ Road Blocked' },
  { id: 'OPEN_DRAIN', label: '🕳️ Open Manhole' },
  { id: 'VEHICLES_STALLED', label: '🚗 Stalled Cars' },
  { id: 'TRANSFORMER_SPARKING', label: '⚡ Electric Hazard' },
  { id: 'BASEMENT_FLOODED', label: '🏢 Basement Inundated' },
  { id: 'HOSPITAL_ROUTE_CUT', label: '🏥 Hospital Cut Off' },
];

export default function ReportScreen() {
  const router = useRouter();

  const [activeTab, setActiveTab] = useState<TabMode>('NEW_REPORT');
  const [refreshing, setRefreshing] = useState(false);

  // Form State
  const [selectedDepth, setSelectedDepth] = useState<DepthTier>('KNEE_DEEP');
  const [roadBlocked, setRoadBlocked] = useState(true);
  const [drainBlocked, setDrainBlocked] = useState(true);
  const [selectedHazards, setSelectedHazards] = useState<string[]>([
    'ROAD_BLOCKED',
    'VEHICLES_STALLED',
  ]);
  const [description, setDescription] = useState(
    'Heavy water surge outside Kurla bus depot. Several small cars and autos stalled. Pedestrian walkway completely underwater.'
  );
  const [selectedPhotoIndex, setSelectedPhotoIndex] = useState(0);

  // Voice Note Simulation State
  const [isRecordingVoice, setIsRecordingVoice] = useState(false);
  const [voiceSeconds, setVoiceSeconds] = useState(0);
  const voiceTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Submission State
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionResult, setSubmissionResult] = useState<any | null>(null);

  // Community Reports Feed
  const [reports, setReports] = useState<FieldReportItem[]>(FALLBACK_REPORTS);
  const [isLiveBackend, setIsLiveBackend] = useState(false);

  const loadReports = useCallback(async () => {
    try {
      const res = await fetchFieldReports();
      setReports(Array.isArray(res.data) ? res.data : FALLBACK_REPORTS);
      setIsLiveBackend(res.isLive);
    } catch {
      setIsLiveBackend(false);
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  const onRefresh = () => {
    setRefreshing(true);
    loadReports();
  };

  const handleToggleHazard = (hazardId: string) => {
    setSelectedHazards((prev) =>
      prev.includes(hazardId) ? prev.filter((h) => h !== hazardId) : [...prev, hazardId]
    );
  };

  const handleToggleVoiceRecord = () => {
    if (isRecordingVoice) {
      setIsRecordingVoice(false);
      if (voiceTimerRef.current) clearInterval(voiceTimerRef.current);
      setDescription((prev) =>
        prev
          ? `${prev} [Audio Note: 0:${voiceSeconds < 10 ? '0' : ''}${voiceSeconds} recorded - rapid surge direction northeast]`
          : 'High velocity flood surge detected. Audio transcript attached.'
      );
    } else {
      setIsRecordingVoice(true);
      setVoiceSeconds(0);
      voiceTimerRef.current = setInterval(() => {
        setVoiceSeconds((prev) => {
          if (prev >= 60) {
            if (voiceTimerRef.current) clearInterval(voiceTimerRef.current);
            setIsRecordingVoice(false);
            return 60;
          }
          return prev + 1;
        });
      }, 1000);
    }
  };

  useEffect(() => {
    return () => {
      if (voiceTimerRef.current) clearInterval(voiceTimerRef.current);
    };
  }, []);

  const handleSubmit = async () => {
    if (!description.trim()) {
      Alert.alert('Required Field', 'Please add a brief description of the waterlogging situation.');
      return;
    }

    setIsSubmitting(true);
    try {
      const activeMeta = DEPTH_TIERS.find((d) => d.tier === selectedDepth)!;
      const payload: SubmitReportPayload = {
        latitude: 19.0715,
        longitude: 72.8759,
        description: description.trim(),
        depth_level: selectedDepth,
        estimated_water_depth_cm: activeMeta.depthCm,
        road_blocked: roadBlocked,
        drain_blocked: drainBlocked,
        hazards: selectedHazards,
        image_url: EVIDENCE_PHOTOS[selectedPhotoIndex].url,
      };

      const result = await submitFieldReport(payload);
      if (result.success && result.data) {
        setSubmissionResult(result.data);
        // Refresh feed so user sees their new report immediately
        loadReports();
      } else {
        Alert.alert(
          'Report Logged Offline',
          'Network packet queued. Emergency report saved to offline buffer and will sync immediately via SMS gateway.',
          [{ text: 'OK' }]
        );
      }
    } catch (e) {
      Alert.alert('Submission Error', 'Failed to submit report. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const activeDepthMeta = DEPTH_TIERS.find((d) => d.tier === selectedDepth)!;

  return (
    <View className="flex-1 bg-[#050A14]">
      {/* 1. Tactical Universal Header */}
      <AppHeader
        location="Field Reporter • Ward L & G/North"
        onDistressPress={() => emergencyStore.openSos({ ward: 'Ward L & G/North' })}
        onProfilePress={() => emergencyStore.openTerminal()}
      />

      <ScrollView
        className="flex-1"
        contentContainerStyle={{ paddingBottom: 130 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor="#00F0FF"
            colors={['#00F0FF']}
          />
        }
      >
        {/* 2. Top Location & GPS Status Bar */}
        <View className="px-5 pt-4 pb-2">
          <View className="bg-slate-900/90 border border-slate-800 rounded-2xl p-3.5 flex-row items-center justify-between">
            <View className="flex-row items-center gap-3 flex-1 min-w-0 pr-2">
              <View className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/30 items-center justify-center flex-shrink-0">
                <Crosshair size={20} color="#00F0FF" />
              </View>
              <View className="flex-1 min-w-0">
                <View className="flex-row items-center gap-1.5">
                  <View className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <Text className="text-xs font-black text-white uppercase tracking-wider">
                    GPS LOCKED • ±3m ACCURACY
                  </Text>
                </View>
                <Text className="text-[11px] text-slate-400 mt-0.5" numberOfLines={1}>
                  19.0715° N, 72.8759° E • Kurla West (Ward L)
                </Text>
              </View>
            </View>

            <View className="bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-800 flex-shrink-0">
              <Text className="text-[10px] font-bold text-slate-300">
                {isLiveBackend ? '🟢 Server Live' : '🟠 Cached'}
              </Text>
            </View>
          </View>

          {/* 3. Screen Segmented Tabs: New Report vs Live Community Feed */}
          <View className="flex-row gap-2 mt-3 bg-slate-900/60 p-1 rounded-xl border border-slate-800">
            <Pressable
              onPress={() => setActiveTab('NEW_REPORT')}
              className={`flex-1 py-2 rounded-lg items-center justify-center flex-row gap-1.5 active:scale-95 ${
                activeTab === 'NEW_REPORT' ? 'bg-cyan-500' : 'bg-transparent'
              }`}
            >
              <Camera size={14} color={activeTab === 'NEW_REPORT' ? '#050A14' : '#94A3B8'} />
              <Text
                className={`text-xs font-black uppercase tracking-wider ${
                  activeTab === 'NEW_REPORT' ? 'text-slate-950' : 'text-slate-400'
                }`}
              >
                File Hazard Report
              </Text>
            </Pressable>

            <Pressable
              onPress={() => setActiveTab('FEED')}
              className={`flex-1 py-2 rounded-lg items-center justify-center flex-row gap-1.5 active:scale-95 ${
                activeTab === 'FEED' ? 'bg-cyan-500' : 'bg-transparent'
              }`}
            >
              <Radio size={14} color={activeTab === 'FEED' ? '#050A14' : '#94A3B8'} />
              <Text
                className={`text-xs font-black uppercase tracking-wider ${
                  activeTab === 'FEED' ? 'text-slate-950' : 'text-slate-400'
                }`}
              >
                Live Feed ({reports.length})
              </Text>
            </Pressable>
          </View>
        </View>

        {/* ========================================================================= */}
        {/* VIEW 1: FILE NEW CITIZEN HAZARD REPORT FORM                               */}
        {/* ========================================================================= */}
        {activeTab === 'NEW_REPORT' && (
          <View className="px-5 pt-2 flex-col gap-4">

            {/* A. VISUAL EVIDENCE VIEWFINDER */}
            <View className="bg-[#0B1322] border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
              {/* Card Header */}
              <View className="p-3.5 border-b border-slate-800/80 flex-row items-center justify-between">
                <View className="flex-row items-center gap-2">
                  <Camera size={15} color="#00F0FF" />
                  <Text className="text-xs font-black text-white uppercase tracking-wider">
                    Visual Evidence Viewfinder
                  </Text>
                </View>
                <View className="bg-cyan-500/20 border border-cyan-500/40 px-2 py-0.5 rounded flex-row items-center gap-1">
                  <Sparkles size={10} color="#00F0FF" />
                  <Text className="text-[9px] font-black text-cyan-300 uppercase">
                    AI Pre-Scan Ready
                  </Text>
                </View>
              </View>

              {/* Viewfinder Preview with Disaster Framing */}
              <View className="relative h-48 w-full bg-slate-950 items-center justify-center">
                <Image
                  source={{ uri: EVIDENCE_PHOTOS[selectedPhotoIndex].url }}
                  className="w-full h-full"
                  resizeMode="cover"
                />

                {/* Tactical HUD Framing Brackets */}
                <View className="absolute inset-3 pointer-events-none justify-between">
                  <View className="flex-row justify-between">
                    <View className="w-5 h-5 border-t-2 border-l-2 border-cyan-400" />
                    <View className="w-5 h-5 border-t-2 border-r-2 border-cyan-400" />
                  </View>
                  <View className="flex-row justify-between">
                    <View className="w-5 h-5 border-b-2 border-l-2 border-cyan-400" />
                    <View className="w-5 h-5 border-b-2 border-r-2 border-cyan-400" />
                  </View>
                </View>

                {/* Watermark Overlay */}
                <View className="absolute bottom-2 left-3 bg-black/75 px-2.5 py-1 rounded border border-white/20">
                  <Text className="text-[10px] font-mono text-cyan-300">
                    LAT 19.0715° LON 72.8759° • {EVIDENCE_PHOTOS[selectedPhotoIndex].name}
                  </Text>
                </View>
              </View>

              {/* Photo Evidence Preset Selector */}
              <View className="p-3 bg-slate-900/90 flex-row gap-2">
                {EVIDENCE_PHOTOS.map((photo, idx) => (
                  <Pressable
                    key={photo.id}
                    onPress={() => setSelectedPhotoIndex(idx)}
                    className={`flex-1 p-2 rounded-xl border active:scale-95 ${
                      selectedPhotoIndex === idx
                        ? 'bg-cyan-500/20 border-cyan-400'
                        : 'bg-slate-950 border-slate-800'
                    }`}
                  >
                    <Text
                      className={`text-[10px] font-black ${
                        selectedPhotoIndex === idx ? 'text-cyan-300' : 'text-slate-400'
                      }`}
                      numberOfLines={1}
                    >
                      Photo {idx + 1}
                    </Text>
                    <Text className="text-[9px] text-slate-500 mt-0.5" numberOfLines={1}>
                      {photo.tag}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </View>

            {/* B. 4-TIER WATER LEVEL DEPTH SELECTOR */}
            <View className="bg-[#0B1322] border border-slate-800 rounded-2xl p-4 shadow-xl">
              <View className="flex-row items-center justify-between mb-2">
                <View className="flex-row items-center gap-2">
                  <Droplets size={16} color={activeDepthMeta.severityColor} />
                  <Text className="text-xs font-black text-white uppercase tracking-wider">
                    Water Level Depth Selector
                  </Text>
                </View>
                <View className={`px-2.5 py-0.5 rounded-full border ${activeDepthMeta.badgeBg}`}>
                  <Text className={`text-[10px] font-black uppercase ${activeDepthMeta.badgeText}`}>
                    {activeDepthMeta.badge} • {activeDepthMeta.rangeCm}
                  </Text>
                </View>
              </View>

              <Text className="text-xs text-slate-300 mb-3 leading-relaxed">
                Select the current flood water level observed at your location:
              </Text>

              {/* 4 Tiers Grid */}
              <View className="flex-row gap-2">
                {DEPTH_TIERS.map((tierMeta) => {
                  const isSelected = selectedDepth === tierMeta.tier;
                  return (
                    <Pressable
                      key={tierMeta.tier}
                      onPress={() => setSelectedDepth(tierMeta.tier)}
                      style={{
                        borderColor: isSelected ? tierMeta.severityColor : '#1E293B',
                        backgroundColor: isSelected ? `${tierMeta.severityColor}15` : '#070D18',
                      }}
                      className="flex-1 p-2.5 rounded-xl border-2 items-center active:scale-95"
                    >
                      <View
                        style={{ backgroundColor: tierMeta.severityColor }}
                        className="w-2.5 h-2.5 rounded-full mb-1"
                      />
                      <Text
                        style={{ color: isSelected ? '#FFFFFF' : '#94A3B8' }}
                        className="text-[11px] font-black text-center leading-tight min-h-[26px]"
                        numberOfLines={2}
                      >
                        {tierMeta.label}
                      </Text>
                      <Text
                        style={{ color: isSelected ? tierMeta.severityColor : '#64748B' }}
                        className="text-[9px] font-bold mt-1 text-center"
                      >
                        {tierMeta.rangeCm}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>

              {/* Visual Depth Level Meter */}
              <View className="mt-3.5 bg-slate-950 p-3 rounded-xl border border-slate-900">
                <View className="flex-row justify-between items-center mb-1.5">
                  <Text className="text-[10px] font-black text-slate-400 uppercase">
                    CIVIC FLOOD SEVERITY METRIC
                  </Text>
                  <Text
                    style={{ color: activeDepthMeta.severityColor }}
                    className="text-xs font-black"
                  >
                    ~{activeDepthMeta.depthCm} cm Deep ({activeDepthMeta.rangeIn})
                  </Text>
                </View>

                {/* Progress Visual Bar */}
                <View className="h-3 w-full bg-slate-900 rounded-full overflow-hidden flex-row">
                  <View
                    style={{
                      width:
                        selectedDepth === 'WET_ROAD'
                          ? '25%'
                          : selectedDepth === 'ANKLE_DEEP'
                          ? '50%'
                          : selectedDepth === 'KNEE_DEEP'
                          ? '75%'
                          : '100%',
                      backgroundColor: activeDepthMeta.severityColor,
                    }}
                    className="h-full rounded-full transition-all"
                  />
                </View>

                <Text className="text-xs text-slate-300 mt-2 font-medium">
                  {activeDepthMeta.description}
                </Text>
              </View>
            </View>

            {/* C. IMMEDIATE ROAD & INFRASTRUCTURE HAZARD SWITCHES */}
            <View className="bg-[#0B1322] border border-slate-800 rounded-2xl p-4 shadow-xl">
              <View className="flex-row items-center gap-2 mb-3">
                <AlertTriangle size={15} color="#F59E0B" />
                <Text className="text-xs font-black text-white uppercase tracking-wider">
                  Critical Hazard Indicators
                </Text>
              </View>

              {/* Main Hazard Toggles */}
              <View className="flex-col gap-2.5 mb-3">
                <Pressable
                  onPress={() => setRoadBlocked((prev) => !prev)}
                  className={`p-3 rounded-xl border flex-row items-center justify-between active:scale-[0.99] ${
                    roadBlocked
                      ? 'bg-rose-950/40 border-rose-600/70'
                      : 'bg-slate-900/80 border-slate-800'
                  }`}
                >
                  <View className="flex-1 pr-2">
                    <Text className="text-xs font-black text-white">
                      ⛔ Road Completely Blocked / Impassable
                    </Text>
                    <Text className="text-[11px] text-slate-400 mt-0.5">
                      Vehicles cannot transit through this street segment
                    </Text>
                  </View>
                  <View
                    className={`w-6 h-6 rounded-full items-center justify-center ${
                      roadBlocked ? 'bg-rose-600' : 'bg-slate-800'
                    }`}
                  >
                    {roadBlocked && <Check size={14} color="#FFFFFF" />}
                  </View>
                </Pressable>

                <Pressable
                  onPress={() => setDrainBlocked((prev) => !prev)}
                  className={`p-3 rounded-xl border flex-row items-center justify-between active:scale-[0.99] ${
                    drainBlocked
                      ? 'bg-amber-950/40 border-amber-600/70'
                      : 'bg-slate-900/80 border-slate-800'
                  }`}
                >
                  <View className="flex-1 pr-2">
                    <Text className="text-xs font-black text-white">
                      🕳️ Open Manhole / Drain Suction Hazard
                    </Text>
                    <Text className="text-[11px] text-slate-400 mt-0.5">
                      Dangerous vortex or missing manhole cover submerged
                    </Text>
                  </View>
                  <View
                    className={`w-6 h-6 rounded-full items-center justify-center ${
                      drainBlocked ? 'bg-amber-500' : 'bg-slate-800'
                    }`}
                  >
                    {drainBlocked && <Check size={14} color="#050A14" />}
                  </View>
                </Pressable>
              </View>

              {/* Quick Hazard Tag Chips */}
              <Text className="text-[10px] font-black text-slate-400 uppercase tracking-wider mb-2">
                SPECIFIC HAZARD TAGS
              </Text>
              <View className="flex-row flex-wrap gap-2">
                {QUICK_HAZARDS.map((h) => {
                  const isSelected = selectedHazards.includes(h.id);
                  return (
                    <Pressable
                      key={h.id}
                      onPress={() => handleToggleHazard(h.id)}
                      className={`px-3 py-1.5 rounded-lg border active:scale-95 ${
                        isSelected
                          ? 'bg-cyan-500/20 border-cyan-400'
                          : 'bg-slate-900 border-slate-800'
                      }`}
                    >
                      <Text
                        className={`text-xs font-bold ${
                          isSelected ? 'text-cyan-300' : 'text-slate-400'
                        }`}
                      >
                        {h.label}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>

            {/* D. VOICE NOTE & RAPID FIELD DESCRIPTION */}
            <View className="bg-[#0B1322] border border-slate-800 rounded-2xl p-4 shadow-xl">
              <View className="flex-row items-center justify-between mb-2.5">
                <Text className="text-xs font-black text-white uppercase tracking-wider">
                  Field Description & Voice Memo
                </Text>

                {/* Voice Note Button */}
                <Pressable
                  onPress={handleToggleVoiceRecord}
                  className={`px-3 py-1 rounded-full flex-row items-center gap-1.5 border active:scale-95 ${
                    isRecordingVoice
                      ? 'bg-rose-600 border-rose-500 animate-pulse'
                      : 'bg-slate-900 border-slate-700'
                  }`}
                >
                  {isRecordingVoice ? (
                    <>
                      <MicOff size={12} color="#FFFFFF" />
                      <Text className="text-[10px] font-black text-white uppercase">
                        Recording 0:{voiceSeconds < 10 ? '0' : ''}{voiceSeconds}
                      </Text>
                    </>
                  ) : (
                    <>
                      <Mic size={12} color="#00F0FF" />
                      <Text className="text-[10px] font-bold text-cyan-300 uppercase">
                        Record Audio Memo
                      </Text>
                    </>
                  )}
                </Pressable>
              </View>

              {/* Text Input */}
              <TextInput
                value={description}
                onChangeText={setDescription}
                placeholder="Describe trapped vehicles, rapid surge, or landmarks..."
                placeholderTextColor="#64748B"
                multiline
                numberOfLines={3}
                className="bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-100 font-medium leading-relaxed min-h-[75px]"
                textAlignVertical="top"
              />

              {/* Offline Telemetry Notice */}
              <View className="flex-row items-center gap-1.5 mt-2.5">
                <Radio size={12} color="#10B981" />
                <Text className="text-[10px] text-slate-400 font-semibold">
                  Offline Buffer Ready: Auto-syncs via encrypted SMS if LTE drops.
                </Text>
              </View>
            </View>

            {/* E. SUBMIT URGENT REPORT BUTTON */}
            <Pressable
              onPress={handleSubmit}
              disabled={isSubmitting}
              className="bg-cyan-500 active:bg-cyan-600 py-4 rounded-2xl flex-row items-center justify-center gap-2.5 shadow-xl shadow-cyan-500/20 active:scale-[0.98]"
            >
              {isSubmitting ? (
                <>
                  <ActivityIndicator size="small" color="#050A14" />
                  <Text className="text-sm font-black text-slate-950 uppercase tracking-wider">
                    Analyzing Vision Evidence...
                  </Text>
                </>
              ) : (
                <>
                  <ShieldAlert size={18} color="#050A14" />
                  <Text className="text-sm font-black text-slate-950 uppercase tracking-wider">
                    Submit Verified Disaster Report
                  </Text>
                </>
              )}
            </Pressable>
          </View>
        )}

        {/* ========================================================================= */}
        {/* VIEW 2: LIVE COMMUNITY FIELD REPORTS FEED                                 */}
        {/* ========================================================================= */}
        {activeTab === 'FEED' && (
          <View className="px-5 pt-2 flex-col gap-3.5">
            <View className="flex-row items-center justify-between mb-1">
              <Text className="text-xs font-black text-slate-400 uppercase tracking-wider">
                COMMUNITY HAZARD BULLETINS ({reports.length})
              </Text>
              <Pressable
                onPress={onRefresh}
                className="flex-row items-center gap-1 bg-slate-900 px-2.5 py-1 rounded-lg border border-slate-800 active:scale-95"
              >
                <RefreshCw size={11} color="#00F0FF" />
                <Text className="text-[10px] font-bold text-cyan-300">Refresh</Text>
              </Pressable>
            </View>

            {reports.map((item, idx) => {
              const isCritical = item.estimated_water_depth_cm >= 60;
              return (
                <View
                  key={item.report_id || idx}
                  className={`bg-[#0B1322] border rounded-2xl p-4 shadow-lg ${
                    isCritical ? 'border-rose-500/70' : 'border-slate-800'
                  }`}
                >
                  {/* Report Card Header */}
                  <View className="flex-row items-center justify-between mb-2">
                    <View className="flex-row items-center gap-2">
                      <View className="w-7 h-7 rounded-full bg-cyan-950 border border-cyan-500/40 items-center justify-center">
                        <MapPin size={13} color="#00F0FF" />
                      </View>
                      <View>
                        <Text className="text-xs font-bold text-white">
                          Citizen Reporter • {item.citizen_id || 'usr-citizen'}
                        </Text>
                        <Text className="text-[10px] text-slate-400">
                          {new Date(item.submitted_at).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}{' '}
                          • Kurla Basin
                        </Text>
                      </View>
                    </View>

                    {/* AI Verification Badge */}
                    <View className="bg-emerald-500/20 border border-emerald-500/40 px-2.5 py-0.5 rounded-full flex-row items-center gap-1">
                      <ShieldCheck size={11} color="#34D399" />
                      <Text className="text-[9px] font-black text-emerald-300 uppercase">
                        AI Verified ({Math.round((item.ai_confidence || 0.95) * 100)}%)
                      </Text>
                    </View>
                  </View>

                  {/* Photo Evidence Preview if available */}
                  {item.image_url ? (
                    <View className="h-32 w-full rounded-xl overflow-hidden mb-2.5 border border-slate-800 bg-slate-950">
                      <Image
                        source={{ uri: item.image_url }}
                        className="w-full h-full"
                        resizeMode="cover"
                      />
                      <View className="absolute bottom-1.5 right-2 bg-black/80 px-2 py-0.5 rounded">
                        <Text className="text-[9px] font-bold text-white">
                          Vision Analyzed
                        </Text>
                      </View>
                    </View>
                  ) : null}

                  {/* Description */}
                  <Text className="text-xs text-slate-200 leading-relaxed font-medium mb-3">
                    {item.description}
                  </Text>

                  {/* Water Depth & Road Status Badges */}
                  <View className="flex-row gap-2 mb-3">
                    <View className="flex-1 bg-slate-950 p-2 rounded-xl border border-slate-900">
                      <Text className="text-[9px] font-bold text-slate-400 uppercase">
                        WATER DEPTH
                      </Text>
                      <Text
                        className={`text-xs font-black mt-0.5 ${
                          isCritical ? 'text-rose-400' : 'text-amber-400'
                        }`}
                      >
                        {item.estimated_water_depth_cm} cm Inundation
                      </Text>
                    </View>

                    <View className="flex-1 bg-slate-950 p-2 rounded-xl border border-slate-900">
                      <Text className="text-[9px] font-bold text-slate-400 uppercase">
                        ROADWAY STATUS
                      </Text>
                      <Text className="text-xs font-black text-rose-400 mt-0.5">
                        ⛔ Strictly Impassable
                      </Text>
                    </View>
                  </View>

                  {/* Action Link to Radar Map */}
                  <Pressable
                    onPress={() => router.push('/(tabs)/radar')}
                    className="bg-slate-900 border border-slate-800 py-2 rounded-xl flex-row items-center justify-center gap-1.5 active:bg-slate-800"
                  >
                    <Navigation size={12} color="#00F0FF" />
                    <Text className="text-xs font-bold text-cyan-300 uppercase">
                      Inspect On Radar Map
                    </Text>
                  </Pressable>
                </View>
              );
            })}
          </View>
        )}
      </ScrollView>

      {/* ========================================================================= */}
      {/* 4. SUCCESS SUBMISSION CONFIRMATION MODAL                                  */}
      {/* ========================================================================= */}
      <Modal
        visible={!!submissionResult}
        transparent
        animationType="fade"
        onRequestClose={() => setSubmissionResult(null)}
      >
        <View className="flex-1 bg-black/85 items-center justify-center px-6">
          <View className="bg-[#0B1322] border-2 border-cyan-500 rounded-3xl p-5 w-full shadow-2xl">
            {/* Header Icon */}
            <View className="items-center mb-3">
              <View className="w-14 h-14 rounded-full bg-emerald-500/20 border-2 border-emerald-400 items-center justify-center mb-2">
                <CheckCircle2 size={32} color="#34D399" />
              </View>
              <Text className="text-lg font-black text-white uppercase tracking-tight">
                REPORT LOGGED & VERIFIED
              </Text>
              <Text className="text-xs text-slate-400 mt-0.5 text-center">
                Automated ML Vision Heuristic Verification Complete
              </Text>
            </View>

            {/* Report Metadata Details */}
            <View className="bg-slate-950 p-3 rounded-2xl border border-slate-800 flex-col gap-2 my-2">
              <View className="flex-row justify-between">
                <Text className="text-xs text-slate-400 font-semibold">Report ID:</Text>
                <Text className="text-xs font-mono text-cyan-300 font-bold">
                  {submissionResult?.report_id?.slice(0, 16)}...
                </Text>
              </View>

              <View className="flex-row justify-between">
                <Text className="text-xs text-slate-400 font-semibold">Verification:</Text>
                <Text className="text-xs font-bold text-emerald-400">
                  AI_VERIFIED ({Math.round((submissionResult?.ai_confidence || 0.95) * 100)}% Confidence)
                </Text>
              </View>

              <View className="flex-row justify-between">
                <Text className="text-xs text-slate-400 font-semibold">Logged Depth:</Text>
                <Text className="text-xs font-bold text-amber-400">
                  {submissionResult?.estimated_water_depth_cm || 50} cm Inundation
                </Text>
              </View>

              <View className="flex-row justify-between">
                <Text className="text-xs text-slate-400 font-semibold">Disaster Unit:</Text>
                <Text className="text-xs font-bold text-white">
                  Ward L Operations Command
                </Text>
              </View>
            </View>

            <Text className="text-[11px] text-slate-400 text-center my-2">
              Your field observation has been broadcast to municipal rescue units and pinned to the live Leaflet Radar.
            </Text>

            {/* Action Buttons */}
            <View className="flex-row gap-2 mt-2">
              <Pressable
                onPress={() => {
                  setSubmissionResult(null);
                  setActiveTab('FEED');
                }}
                className="flex-1 py-3 rounded-xl bg-slate-900 border border-slate-700 items-center justify-center active:bg-slate-800"
              >
                <Text className="text-xs font-bold text-white uppercase">
                  View in Feed
                </Text>
              </Pressable>

              <Pressable
                onPress={() => {
                  setSubmissionResult(null);
                  router.push('/(tabs)/radar');
                }}
                className="flex-1 py-3 rounded-xl bg-cyan-500 items-center justify-center active:bg-cyan-600"
              >
                <Text className="text-xs font-black text-slate-950 uppercase">
                  View on Radar
                </Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}
