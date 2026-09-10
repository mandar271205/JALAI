import React, { useState } from 'react';
import {
  Modal,
  View,
  Pressable,
  ScrollView,
  Linking,
  ActivityIndicator,
  Alert,
  Dimensions,
} from 'react-native';
import {
  Radio,
  AlertTriangle,
  X,
  PhoneCall,
  ShieldCheck,
  BatteryCharging,
  Navigation,
  Check,
  LifeBuoy,
  Clock,
  HeartPulse,
} from 'lucide-react-native';

import { Text } from '@/components/ui/text';
import {
  useEmergencyStore,
  emergencyStore,
  AssistanceProfile,
} from '@/lib/emergency-store';

const HOTLINES = [
  { number: '1078', label: 'NDRF Disaster Helpline', color: '#EF4444' },
  { number: '1916', label: 'BMC Disaster Control', color: '#38BDF8' },
  { number: '101', label: 'Fire & Flood Rescue', color: '#F97316' },
  { number: '100', label: 'Mumbai Police HQ', color: '#A855F7' },
];

export function SosModal() {
  const {
    isSosModalOpen,
    isBroadcasting,
    activeSos,
    selectedWard,
    assistance,
    citizenName,
    citizenPhone,
  } = useEmergencyStore();

  const [cancelLoading, setCancelLoading] = useState(false);

  const handleDial = (phoneNumber: string) => {
    Linking.openURL(`tel:${phoneNumber}`).catch(() => {
      Alert.alert('Phone Call Failed', `Unable to dial ${phoneNumber} automatically.`);
    });
  };

  const handleBroadcast = async () => {
    await emergencyStore.transmitDistress({
      latitude: 19.0728,
      longitude: 72.8792,
      notes: 'Citizen broadcast distress via JALAI Mobile App',
    });
  };

  const handleCancel = () => {
    Alert.alert(
      'Cancel Distress Signal?',
      'Only cancel if you have reached safe high ground or rescue units have already assisted you.',
      [
        { text: 'Keep Beacon Active', style: 'cancel' },
        {
          text: 'Confirm Safe & Cancel',
          style: 'destructive',
          onPress: async () => {
            setCancelLoading(true);
            await emergencyStore.cancelDistress('Citizen confirmed reach to safety');
            setCancelLoading(false);
          },
        },
      ]
    );
  };

  const assistanceItems: { key: keyof AssistanceProfile; label: string; icon: string }[] = [
    { key: 'wheelchair', label: 'Wheelchair / Mobility Bound', icon: '🦽' },
    { key: 'elderly', label: 'Senior Citizen (65+)', icon: '👴' },
    { key: 'infant', label: 'Infant / Young Children', icon: '👶' },
    { key: 'medicalOxygen', label: 'Medical Supplies / Oxygen', icon: '🏥' },
    { key: 'waistDeep', label: 'Water Level Above Waist', icon: '🌊' },
  ];

  const { height: windowHeight } = Dimensions.get('window');
  const sheetHeight = Math.min(Math.round(windowHeight * 0.88), 750);

  return (
    <Modal
      visible={isSosModalOpen}
      animationType="slide"
      transparent={true}
      onRequestClose={() => {
        if (!activeSos) emergencyStore.closeSos();
      }}
    >
      <View className="flex-1 bg-black/75 justify-end">
        {/* Backdrop tap to dismiss */}
        <Pressable
          className="flex-1"
          onPress={() => {
            if (!activeSos) emergencyStore.closeSos();
          }}
        />

        {/* Modal Container with explicit height so ScrollView expands properly */}
        <View
          style={{ height: sheetHeight }}
          className="bg-[#070D18] border-t-2 border-rose-500 rounded-t-3xl flex-col overflow-hidden shadow-2xl"
        >
          {/* Header Bar */}
          <View className="px-5 pt-4 pb-3 border-b border-slate-800/80 flex-row items-center justify-between bg-[#0A1220]">
            <View className="flex-row items-center gap-2.5">
              <View className="w-8 h-8 rounded-full bg-rose-950/80 border border-rose-500/60 items-center justify-center">
                <Radio size={16} color="#FB7185" />
              </View>
              <View>
                <Text className="text-sm font-black tracking-wider text-rose-400 uppercase">
                  {activeSos ? 'SOS DISPATCH ACTIVE' : 'EMERGENCY SOS DISTRESS'}
                </Text>
                <Text className="text-[10px] font-bold text-slate-400">
                  DISASTER CELL FREQ: CAP 4370 MHz
                </Text>
              </View>
            </View>

            <Pressable
              onPress={() => emergencyStore.closeSos()}
              className="w-8 h-8 rounded-full bg-slate-800 items-center justify-center active:scale-95"
            >
              <X size={18} color="#94A3B8" />
            </Pressable>
          </View>

          <ScrollView
            className="flex-1 px-5 py-4"
            showsVerticalScrollIndicator={true}
            contentContainerStyle={{ paddingBottom: 60 }}
          >
            {/* Active Dispatch Mode */}
            {activeSos ? (
              <View className="gap-4">
                {/* Status Hero Card */}
                <View className="bg-rose-950/40 border-2 border-rose-500/80 rounded-2xl p-4">
                  <View className="flex-row items-center justify-between mb-2">
                    <View className="bg-rose-500/30 border border-rose-400 px-2.5 py-1 rounded-full flex-row items-center gap-1.5">
                      <View className="w-2 h-2 rounded-full bg-rose-400 animate-pulse" />
                      <Text className="text-[11px] font-black tracking-wider text-rose-200 uppercase">
                        {activeSos.status}
                      </Text>
                    </View>
                    <Text className="text-xs font-mono font-bold text-rose-300">
                      {activeSos.sos_id}
                    </Text>
                  </View>

                  <Text className="text-xl font-black text-white tracking-tight mt-1">
                    Rescue Unit En Route
                  </Text>
                  <Text className="text-xs text-slate-300 mt-1">
                    Your distress beacon is locked on GPS. Emergency responders have been dispatched to your sector.
                  </Text>

                  {/* Dispatch Details Grid */}
                  <View className="bg-[#050A14] border border-slate-800 rounded-xl p-3.5 mt-3 gap-2.5">
                    <View className="flex-row justify-between items-center">
                      <Text className="text-xs text-slate-400">Assigned Battalion</Text>
                      <Text className="text-xs font-bold text-white text-right max-w-[65%]">
                        {activeSos.assigned_unit}
                      </Text>
                    </View>
                    <View className="h-px bg-slate-800/80" />
                    <View className="flex-row justify-between items-center">
                      <Text className="text-xs text-slate-400">Vehicle Callsign</Text>
                      <Text className="text-xs font-bold text-cyan-400">
                        {activeSos.vehicle_callsign}
                      </Text>
                    </View>
                    <View className="h-px bg-slate-800/80" />
                    <View className="flex-row justify-between items-center">
                      <Text className="text-xs text-slate-400">Estimated Arrival (ETA)</Text>
                      <View className="flex-row items-center gap-1 bg-amber-500/20 px-2 py-0.5 rounded-full border border-amber-500/40">
                        <Clock size={12} color="#FBBF24" />
                        <Text className="text-xs font-black text-amber-300">
                          ~{activeSos.eta_minutes} Mins
                        </Text>
                      </View>
                    </View>
                  </View>
                </View>

                {/* Direct Action for Active SOS */}
                <View className="gap-2.5">
                  <Pressable
                    onPress={() => handleDial(activeSos.responder_phone || '1078')}
                    className="bg-emerald-600 active:bg-emerald-500 py-3.5 px-4 rounded-xl flex-row items-center justify-center gap-2 border border-emerald-400 shadow-lg"
                  >
                    <PhoneCall size={18} color="#FFFFFF" />
                    <Text className="text-sm font-black text-white uppercase tracking-wider">
                      Call NDRF Incident Commander ({activeSos.responder_phone || '1078'})
                    </Text>
                  </Pressable>

                  <Pressable
                    onPress={() => handleDial(activeSos.disaster_control_phone || '1916')}
                    className="bg-cyan-950/60 active:bg-cyan-900/60 py-3 px-4 rounded-xl flex-row items-center justify-center gap-2 border border-cyan-500/40"
                  >
                    <LifeBuoy size={16} color="#38BDF8" />
                    <Text className="text-xs font-bold text-cyan-200">
                      Call BMC Disaster Control Room ({activeSos.disaster_control_phone || '1916'})
                    </Text>
                  </Pressable>

                  <Pressable
                    disabled={cancelLoading}
                    onPress={handleCancel}
                    className="bg-slate-900 active:bg-slate-800 py-3 px-4 rounded-xl flex-row items-center justify-center gap-2 border border-slate-700 mt-1"
                  >
                    {cancelLoading ? (
                      <ActivityIndicator size="small" color="#94A3B8" />
                    ) : (
                      <>
                        <ShieldCheck size={16} color="#94A3B8" />
                        <Text className="text-xs font-bold text-slate-300">
                          I Am Now Safe • De-escalate Beacon
                        </Text>
                      </>
                    )}
                  </Pressable>
                </View>
              </View>
            ) : (
              /* Standby / Broadcast Mode */
              <View className="gap-4">
                {/* Warning Alert Banner */}
                <View className="bg-rose-950/30 border border-rose-500/40 rounded-2xl p-4 flex-row items-start gap-3">
                  <View className="w-9 h-9 rounded-xl bg-rose-900/60 border border-rose-500/60 items-center justify-center flex-shrink-0 mt-0.5">
                    <AlertTriangle size={20} color="#FB7185" />
                  </View>
                  <View className="flex-1">
                    <Text className="text-sm font-black text-white">
                      Instant Search & Rescue Broadcast
                    </Text>
                    <Text className="text-xs text-slate-300 mt-0.5 leading-relaxed">
                      Pressing the beacon below alerts the National Disaster Response Force (NDRF), Mumbai Fire Brigade, and Ward {selectedWard} emergency response boats.
                    </Text>
                  </View>
                </View>

                {/* Telemetry Strip */}
                <View className="bg-[#050A14] border border-slate-800 rounded-xl p-3.5">
                  <Text className="text-[11px] font-black uppercase text-slate-400 tracking-wider mb-2.5">
                    Live Telemetry Ready for Transmission
                  </Text>
                  <View className="gap-2">
                    <View className="flex-row items-center justify-between">
                      <View className="flex-row items-center gap-1.5">
                        <Navigation size={13} color="#38BDF8" />
                        <Text className="text-xs text-slate-300">GPS Coordinates</Text>
                      </View>
                      <Text className="text-xs font-mono font-bold text-cyan-300">
                        19.0728° N, 72.8792° E (±3.8m)
                      </Text>
                    </View>

                    <View className="flex-row items-center justify-between">
                      <View className="flex-row items-center gap-1.5">
                        <BatteryCharging size={13} color="#34D399" />
                        <Text className="text-xs text-slate-300">Device Battery Level</Text>
                      </View>
                      <Text className="text-xs font-bold text-emerald-400">84% Optimal</Text>
                    </View>

                    <View className="flex-row items-center justify-between">
                      <View className="flex-row items-center gap-1.5">
                        <HeartPulse size={13} color="#F472B6" />
                        <Text className="text-xs text-slate-300">Citizen Identity</Text>
                      </View>
                      <Text className="text-xs font-bold text-white">
                        {citizenName} ({citizenPhone})
                      </Text>
                    </View>
                  </View>
                </View>

                {/* Assistance Needs Toggles */}
                <View>
                  <Text className="text-[11px] font-black uppercase text-slate-400 tracking-wider mb-2">
                    Special Assistance Needed (Select all that apply)
                  </Text>
                  <View className="flex-row flex-wrap gap-2">
                    {assistanceItems.map((item) => {
                      const isSelected = assistance[item.key];
                      return (
                        <Pressable
                          key={item.key}
                          onPress={() => emergencyStore.toggleAssistance(item.key)}
                          className={`flex-row items-center gap-1.5 px-3 py-2 rounded-xl border ${
                            isSelected
                              ? 'bg-rose-950/70 border-rose-500'
                              : 'bg-slate-900 border-slate-800'
                          } active:scale-98`}
                        >
                          <Text className="text-sm">{item.icon}</Text>
                          <Text
                            className={`text-xs font-bold ${
                              isSelected ? 'text-rose-200' : 'text-slate-300'
                            }`}
                          >
                            {item.label}
                          </Text>
                          {isSelected && <Check size={13} color="#FB7185" />}
                        </Pressable>
                      );
                    })}
                  </View>
                </View>

                {/* Master SOS Broadcast Button */}
                <Pressable
                  disabled={isBroadcasting}
                  onPress={handleBroadcast}
                  className="bg-rose-600 active:bg-rose-700 py-4 px-5 rounded-2xl flex-row items-center justify-center gap-3 border-2 border-rose-400 shadow-xl mt-1 active:scale-98"
                >
                  {isBroadcasting ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <>
                      <Radio size={22} color="#FFFFFF" />
                      <Text className="text-base font-black text-white uppercase tracking-wider">
                        BROADCAST SOS DISTRESS BEACON
                      </Text>
                    </>
                  )}
                </Pressable>

                {/* Direct Dial Emergency Speed Dials */}
                <View className="mt-2">
                  <Text className="text-[11px] font-black uppercase text-slate-400 tracking-wider mb-2">
                    Or Call Disaster Hotlines Immediately
                  </Text>
                  <View className="grid grid-cols-2 gap-2 flex-row flex-wrap">
                    {HOTLINES.map((h) => (
                      <Pressable
                        key={h.number}
                        onPress={() => handleDial(h.number)}
                        className="flex-1 min-w-[45%] bg-[#0A1220] border border-slate-800 p-3 rounded-xl flex-row items-center gap-2.5 active:bg-slate-800"
                      >
                        <View
                          style={{ borderColor: h.color }}
                          className="w-8 h-8 rounded-lg bg-slate-900 border items-center justify-center"
                        >
                          <PhoneCall size={14} color={h.color} />
                        </View>
                        <View className="flex-1 min-w-0">
                          <Text className="text-xs font-black text-white">
                            Dial {h.number}
                          </Text>
                          <Text
                            numberOfLines={1}
                            className="text-[10px] text-slate-400"
                          >
                            {h.label}
                          </Text>
                        </View>
                      </Pressable>
                    ))}
                  </View>
                </View>
              </View>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}
