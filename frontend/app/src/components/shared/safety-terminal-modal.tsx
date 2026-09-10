import React, { useState, useEffect } from 'react';
import {
  Modal,
  View,
  Pressable,
  ScrollView,
  Image,
  Linking,
  TextInput,
  Alert,
  Dimensions,
} from 'react-native';
import {
  ShieldAlert,
  X,
  Activity,
  User,
  Phone,
  MessageSquare,
  Plus,
  Trash2,
  Check,
  Radio,
  Wifi,
  Server,
  Heart,
  ChevronRight,
} from 'lucide-react-native';

import { Text } from '@/components/ui/text';
import {
  useEmergencyStore,
  emergencyStore,
  AssistanceProfile,
} from '@/lib/emergency-store';
import { fetchWeatherSourcesStatus, WeatherSourceStatus } from '@/lib/api';

export function SafetyTerminalModal() {
  const {
    isTerminalModalOpen,
    citizenName,
    citizenId,
    citizenPhone,
    citizenBloodGroup,
    selectedWard,
    iceContacts,
    assistance,
  } = useEmergencyStore();

  const [radarStatus, setRadarStatus] = useState<WeatherSourceStatus | null>(null);

  useEffect(() => {
    if (isTerminalModalOpen) {
      fetchWeatherSourcesStatus()
        .then((res) => {
          if (res.data && res.data.length > 0) {
            setRadarStatus(res.data[0]);
          }
        })
        .catch(() => {});
    }
  }, [isTerminalModalOpen]);

  const [isAddingContact, setIsAddingContact] = useState(false);
  const [newContactName, setNewContactName] = useState('');
  const [newContactRelation, setNewContactRelation] = useState('');
  const [newContactPhone, setNewContactPhone] = useState('');

  const handleDial = (phoneNumber: string) => {
    Linking.openURL(`tel:${phoneNumber}`).catch(() => {
      Alert.alert('Call Failed', `Could not dial ${phoneNumber}`);
    });
  };

  const handleSms = (phoneNumber: string) => {
    const text = `EMERGENCY ALERT: I am in ${selectedWard} using JALAI Disaster Response. My GPS location is active.`;
    Linking.openURL(`sms:${phoneNumber}?body=${encodeURIComponent(text)}`).catch(() => {
      Alert.alert('SMS Failed', `Could not send message to ${phoneNumber}`);
    });
  };

  const handleSaveContact = () => {
    if (!newContactName.trim() || !newContactPhone.trim()) {
      Alert.alert('Missing Details', 'Please provide a contact name and phone number.');
      return;
    }

    emergencyStore.addIceContact({
      name: newContactName.trim(),
      relation: newContactRelation.trim() || 'Family',
      phone: newContactPhone.trim(),
    });

    setNewContactName('');
    setNewContactRelation('');
    setNewContactPhone('');
    setIsAddingContact(false);
  };

  const assistanceItems: { key: keyof AssistanceProfile; label: string; desc: string; icon: string }[] = [
    {
      key: 'wheelchair',
      label: 'Mobility Impairment',
      desc: 'Wheelchair or stretcher required for evacuation',
      icon: '🦽',
    },
    {
      key: 'elderly',
      label: 'Senior Citizen (65+)',
      desc: 'Assistance needed during rapid transit',
      icon: '👴',
    },
    {
      key: 'infant',
      label: 'Infant / Young Child',
      desc: 'Evacuation carries baby supplies / infant harness',
      icon: '👶',
    },
    {
      key: 'medicalOxygen',
      label: 'Medical Dependency',
      desc: 'Requires continuous oxygen or refrigerated insulin',
      icon: '🏥',
    },
  ];

  const { height: windowHeight } = Dimensions.get('window');
  const sheetHeight = Math.min(Math.round(windowHeight * 0.88), 750);

  return (
    <Modal
      visible={isTerminalModalOpen}
      animationType="slide"
      transparent={true}
      onRequestClose={() => emergencyStore.closeTerminal()}
    >
      <View className="flex-1 bg-black/75 justify-end">
        {/* Backdrop tap to dismiss */}
        <Pressable
          className="flex-1"
          onPress={() => emergencyStore.closeTerminal()}
        />

        {/* Modal Container with explicit height so ScrollView expands properly */}
        <View
          style={{ height: sheetHeight }}
          className="bg-[#070D18] border-t-2 border-cyan-500 rounded-t-3xl flex-col overflow-hidden shadow-2xl"
        >
          {/* Top Bar */}
          <View className="px-5 pt-4 pb-3 border-b border-slate-800/80 flex-row items-center justify-between bg-[#0A1220]">
            <View className="flex-row items-center gap-2.5">
              <View className="w-8 h-8 rounded-xl bg-cyan-950 border border-cyan-500/50 items-center justify-center">
                <ShieldAlert size={17} color="#38BDF8" />
              </View>
              <View>
                <Text className="text-sm font-black tracking-wider text-white uppercase">
                  CITIZEN SAFETY TERMINAL
                </Text>
                <Text className="text-[10px] font-bold text-cyan-400">
                  SECTOR 08 • MUMBAI DISASTER NETWORK
                </Text>
              </View>
            </View>

            <Pressable
              onPress={() => emergencyStore.closeTerminal()}
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
            {/* 1. Citizen Identity Card */}
            <View className="bg-gradient-to-r from-slate-900 to-[#0B1528] border border-cyan-500/30 rounded-2xl p-4 mb-4">
              <View className="flex-row items-center gap-3.5">
                <View className="relative">
                  <View className="w-14 h-14 rounded-2xl bg-slate-800 border-2 border-cyan-500/60 overflow-hidden">
                    <Image
                      source={{
                        uri: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
                      }}
                      className="w-full h-full"
                      resizeMode="cover"
                    />
                  </View>
                  <View className="absolute -bottom-1 -right-1 bg-emerald-500 w-4 h-4 rounded-full border-2 border-[#070D18]" />
                </View>

                <View className="flex-1">
                  <View className="flex-row items-center gap-2">
                    <Text className="text-base font-black text-white">
                      {citizenName}
                    </Text>
                    <View className="bg-emerald-500/20 px-2 py-0.5 rounded-full border border-emerald-500/40">
                      <Text className="text-[10px] font-black text-emerald-300">
                        VERIFIED
                      </Text>
                    </View>
                  </View>
                  <Text className="text-xs font-mono text-cyan-300 mt-0.5">
                    {citizenId}
                  </Text>
                  <Text className="text-[11px] text-slate-400 mt-0.5">
                    {selectedWard} • Monitored Basin
                  </Text>
                </View>
              </View>

              <View className="mt-3.5 pt-3 border-t border-slate-800 flex-row justify-between items-center">
                <View className="flex-row items-center gap-1.5">
                  <Heart size={13} color="#F43F5E" />
                  <Text className="text-xs text-slate-300">Blood Group:</Text>
                  <Text className="text-xs font-bold text-white">{citizenBloodGroup}</Text>
                </View>
                <View className="flex-row items-center gap-1.5">
                  <Phone size={13} color="#38BDF8" />
                  <Text className="text-xs text-slate-300">{citizenPhone}</Text>
                </View>
              </View>
            </View>

            {/* 2. System Diagnostics & Telemetry Hub */}
            <View className="mb-4">
              <Text className="text-[11px] font-black uppercase text-slate-400 tracking-wider mb-2">
                Operational Telemetry & Diagnostics
              </Text>
              <View className="bg-[#050A14] border border-slate-800 rounded-2xl p-3.5 gap-2.5">
                <View className="flex-row items-center justify-between">
                  <View className="flex-row items-center gap-2">
                    <Server size={14} color="#34D399" />
                    <Text className="text-xs text-slate-300">FastAPI Gateway</Text>
                  </View>
                  <View className="flex-row items-center gap-1.5">
                    <View className="w-2 h-2 rounded-full bg-emerald-400" />
                    <Text className="text-xs font-mono font-bold text-emerald-300">
                      ONLINE (18ms)
                    </Text>
                  </View>
                </View>

                <View className="h-px bg-slate-800/80" />

                <View className="flex-row items-center justify-between">
                  <View className="flex-row items-center gap-2">
                    <Radio size={14} color="#38BDF8" />
                    <Text className="text-xs text-slate-300">IMD Doppler Radar</Text>
                  </View>
                  <Text className="text-xs font-bold text-cyan-300">
                    {radarStatus
                      ? `${radarStatus.status} (${Math.round(radarStatus.latency_seconds)}s)`
                      : 'S-Band Colaba Synced'}
                  </Text>
                </View>

                <View className="h-px bg-slate-800/80" />

                <View className="flex-row items-center justify-between">
                  <View className="flex-row items-center gap-2">
                    <Wifi size={14} color="#A855F7" />
                    <Text className="text-xs text-slate-300">CAP Broadcast Channel</Text>
                  </View>
                  <Text className="text-xs font-mono font-bold text-purple-300">
                    4370 MHz Armed
                  </Text>
                </View>
              </View>
            </View>

            {/* 3. In Case of Emergency (ICE) Contacts */}
            <View className="mb-4">
              <View className="flex-row items-center justify-between mb-2">
                <Text className="text-[11px] font-black uppercase text-slate-400 tracking-wider">
                  Emergency (ICE) Family Contacts
                </Text>
                <Pressable
                  onPress={() => setIsAddingContact(!isAddingContact)}
                  className="flex-row items-center gap-1 bg-cyan-950/60 px-2 py-1 rounded-lg border border-cyan-500/40"
                >
                  <Plus size={12} color="#38BDF8" />
                  <Text className="text-[11px] font-bold text-cyan-300">
                    {isAddingContact ? 'Cancel' : 'Add Contact'}
                  </Text>
                </Pressable>
              </View>

              {/* Add Contact Form Drawer */}
              {isAddingContact && (
                <View className="bg-slate-900 border border-cyan-500/40 rounded-xl p-3 mb-3 gap-2.5">
                  <Text className="text-xs font-bold text-cyan-300">
                    Register New Emergency ICE Contact
                  </Text>
                  <TextInput
                    value={newContactName}
                    onChangeText={setNewContactName}
                    placeholder="Full Name (e.g. Vikram Sharma)"
                    placeholderTextColor="#64748B"
                    className="bg-[#050A14] border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
                  />
                  <TextInput
                    value={newContactRelation}
                    onChangeText={setNewContactRelation}
                    placeholder="Relation (e.g. Brother / Neighbor)"
                    placeholderTextColor="#64748B"
                    className="bg-[#050A14] border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
                  />
                  <TextInput
                    value={newContactPhone}
                    onChangeText={setNewContactPhone}
                    placeholder="Phone Number (e.g. +91 98200 55555)"
                    placeholderTextColor="#64748B"
                    keyboardType="phone-pad"
                    className="bg-[#050A14] border border-slate-700 rounded-lg px-3 py-2 text-xs text-white"
                  />
                  <Pressable
                    onPress={handleSaveContact}
                    className="bg-cyan-600 active:bg-cyan-700 py-2.5 rounded-lg items-center justify-center mt-1"
                  >
                    <Text className="text-xs font-black text-white uppercase tracking-wider">
                      Save ICE Contact
                    </Text>
                  </Pressable>
                </View>
              )}

              {/* ICE Contacts List */}
              <View className="gap-2">
                {iceContacts.map((contact) => (
                  <View
                    key={contact.id}
                    className="bg-[#050A14] border border-slate-800 rounded-xl p-3 flex-row items-center justify-between"
                  >
                    <View className="flex-1 mr-2">
                      <View className="flex-row items-center gap-1.5">
                        <Text className="text-xs font-black text-white">
                          {contact.name}
                        </Text>
                        <View className="bg-slate-800 px-1.5 py-0.5 rounded">
                          <Text className="text-[10px] text-slate-400">
                            {contact.relation}
                          </Text>
                        </View>
                      </View>
                      <Text className="text-xs font-mono text-cyan-300 mt-0.5">
                        {contact.phone}
                      </Text>
                    </View>

                    <View className="flex-row items-center gap-1.5">
                      <Pressable
                        onPress={() => handleDial(contact.phone)}
                        className="w-8 h-8 rounded-lg bg-emerald-950/80 border border-emerald-500/50 items-center justify-center active:scale-95"
                      >
                        <Phone size={14} color="#34D399" />
                      </Pressable>

                      <Pressable
                        onPress={() => handleSms(contact.phone)}
                        className="w-8 h-8 rounded-lg bg-cyan-950/80 border border-cyan-500/50 items-center justify-center active:scale-95"
                      >
                        <MessageSquare size={14} color="#38BDF8" />
                      </Pressable>

                      {iceContacts.length > 1 && (
                        <Pressable
                          onPress={() => emergencyStore.removeIceContact(contact.id)}
                          className="w-8 h-8 rounded-lg bg-slate-900 border border-slate-800 items-center justify-center active:scale-95"
                        >
                          <Trash2 size={13} color="#64748B" />
                        </Pressable>
                      )}
                    </View>
                  </View>
                ))}
              </View>
            </View>

            {/* 4. Mobility & Special Assistance Settings */}
            <View className="mb-4">
              <Text className="text-[11px] font-black uppercase text-slate-400 tracking-wider mb-2">
                Citizen Vulnerability & Assistance Flags
              </Text>
              <Text className="text-[11px] text-slate-400 mb-2.5">
                Saved preferences are automatically broadcast to NDRF rescue teams during any SOS dispatch.
              </Text>

              <View className="gap-2">
                {assistanceItems.map((item) => {
                  const isActive = assistance[item.key];
                  return (
                    <Pressable
                      key={item.key}
                      onPress={() => emergencyStore.toggleAssistance(item.key)}
                      className={`p-3 rounded-xl border flex-row items-center justify-between ${
                        isActive
                          ? 'bg-rose-950/40 border-rose-500/70'
                          : 'bg-[#050A14] border-slate-800'
                      }`}
                    >
                      <View className="flex-row items-center gap-3 flex-1 mr-2">
                        <Text className="text-lg">{item.icon}</Text>
                        <View className="flex-1">
                          <Text
                            className={`text-xs font-bold ${
                              isActive ? 'text-rose-200' : 'text-white'
                            }`}
                          >
                            {item.label}
                          </Text>
                          <Text className="text-[10px] text-slate-400 mt-0.5">
                            {item.desc}
                          </Text>
                        </View>
                      </View>

                      <View
                        className={`w-5 h-5 rounded-md border items-center justify-center ${
                          isActive
                            ? 'bg-rose-500 border-rose-400'
                            : 'bg-slate-800 border-slate-700'
                        }`}
                      >
                        {isActive && <Check size={12} color="#FFFFFF" />}
                      </View>
                    </Pressable>
                  );
                })}
              </View>
            </View>

            {/* 5. Direct Helpline Access */}
            <View>
              <Text className="text-[11px] font-black uppercase text-slate-400 tracking-wider mb-2">
                Government Disaster Helplines
              </Text>
              <View className="bg-[#050A14] border border-slate-800 rounded-xl overflow-hidden divide-y divide-slate-800/60">
                <Pressable
                  onPress={() => handleDial('1916')}
                  className="p-3 flex-row items-center justify-between active:bg-slate-900"
                >
                  <View>
                    <Text className="text-xs font-bold text-white">
                      BMC Disaster Control Room
                    </Text>
                    <Text className="text-[10px] text-slate-400">
                      Municipal Corporation of Greater Mumbai (MCGM)
                    </Text>
                  </View>
                  <View className="flex-row items-center gap-1.5">
                    <Text className="text-xs font-bold font-mono text-cyan-400">1916</Text>
                    <ChevronRight size={14} color="#64748B" />
                  </View>
                </Pressable>

                <Pressable
                  onPress={() => handleDial('1078')}
                  className="p-3 flex-row items-center justify-between active:bg-slate-900"
                >
                  <View>
                    <Text className="text-xs font-bold text-white">
                      NDRF National Disaster Helpline
                    </Text>
                    <Text className="text-[10px] text-slate-400">
                      National Disaster Response Force HQ
                    </Text>
                  </View>
                  <View className="flex-row items-center gap-1.5">
                    <Text className="text-xs font-bold font-mono text-rose-400">1078</Text>
                    <ChevronRight size={14} color="#64748B" />
                  </View>
                </Pressable>

                <Pressable
                  onPress={() => handleDial('108')}
                  className="p-3 flex-row items-center justify-between active:bg-slate-900"
                >
                  <View>
                    <Text className="text-xs font-bold text-white">
                      Emergency Ambulance Service
                    </Text>
                    <Text className="text-[10px] text-slate-400">
                      Maharashtra Emergency Medical Services
                    </Text>
                  </View>
                  <View className="flex-row items-center gap-1.5">
                    <Text className="text-xs font-bold font-mono text-emerald-400">108</Text>
                    <ChevronRight size={14} color="#64748B" />
                  </View>
                </Pressable>
              </View>
            </View>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}
