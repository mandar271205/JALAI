import { useSyncExternalStore } from 'react';
import {
  broadcastSosDistress,
  cancelSosDistress,
  SosDistressResponse,
} from './api';

export interface IceContact {
  id: string;
  name: string;
  relation: string;
  phone: string;
}

export interface AssistanceProfile {
  wheelchair: boolean;
  elderly: boolean;
  infant: boolean;
  medicalOxygen: boolean;
  waistDeep: boolean;
}

export interface EmergencyStoreState {
  isSosModalOpen: boolean;
  isTerminalModalOpen: boolean;
  isBroadcasting: boolean;
  activeSos: SosDistressResponse | null;
  selectedWard: string;
  assistance: AssistanceProfile;
  citizenName: string;
  citizenId: string;
  citizenPhone: string;
  citizenBloodGroup: string;
  iceContacts: IceContact[];
}

const INITIAL_STATE: EmergencyStoreState = {
  isSosModalOpen: false,
  isTerminalModalOpen: false,
  isBroadcasting: false,
  activeSos: null,
  selectedWard: 'Ward L (Kurla West)',
  assistance: {
    wheelchair: false,
    elderly: false,
    infant: false,
    medicalOxygen: false,
    waistDeep: false,
  },
  citizenName: 'Ananya Sharma',
  citizenId: 'IND-MH-MUM-2026-CIT-98214',
  citizenPhone: '+91 98201 12345',
  citizenBloodGroup: 'O+ Positive',
  iceContacts: [
    {
      id: 'ice-1',
      name: 'Rajesh Sharma',
      relation: 'Father',
      phone: '+91 98201 12345',
    },
    {
      id: 'ice-2',
      name: 'Sunita Sharma',
      relation: 'Mother',
      phone: '+91 98201 67890',
    },
    {
      id: 'ice-3',
      name: 'Ward L Disaster Control',
      relation: 'BMC Quick Response',
      phone: '022 2650 4000',
    },
  ],
};

let state: EmergencyStoreState = { ...INITIAL_STATE };
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((listener) => listener());
}

export const emergencyStore = {
  getState() {
    return state;
  },

  openSos(options?: { ward?: string }) {
    state = {
      ...state,
      isSosModalOpen: true,
      selectedWard: options?.ward || state.selectedWard,
    };
    notify();
  },

  closeSos() {
    state = {
      ...state,
      isSosModalOpen: false,
    };
    notify();
  },

  openTerminal() {
    state = {
      ...state,
      isTerminalModalOpen: true,
    };
    notify();
  },

  closeTerminal() {
    state = {
      ...state,
      isTerminalModalOpen: false,
    };
    notify();
  },

  toggleAssistance(key: keyof AssistanceProfile) {
    state = {
      ...state,
      assistance: {
        ...state.assistance,
        [key]: !state.assistance[key],
      },
    };
    notify();
  },

  setWard(ward: string) {
    state = {
      ...state,
      selectedWard: ward,
    };
    notify();
  },

  addIceContact(contact: Omit<IceContact, 'id'>) {
    const newContact: IceContact = {
      ...contact,
      id: `ice-${Date.now()}`,
    };
    state = {
      ...state,
      iceContacts: [newContact, ...state.iceContacts],
    };
    notify();
  },

  removeIceContact(id: string) {
    state = {
      ...state,
      iceContacts: state.iceContacts.filter((c) => c.id !== id),
    };
    notify();
  },

  async transmitDistress(options?: {
    latitude?: number;
    longitude?: number;
    notes?: string;
  }) {
    if (state.isBroadcasting) return;

    state = { ...state, isBroadcasting: true };
    notify();

    const assistanceNeeds: string[] = [];
    if (state.assistance.wheelchair) assistanceNeeds.push('WHEELCHAIR');
    if (state.assistance.elderly) assistanceNeeds.push('ELDERLY_CITIZEN');
    if (state.assistance.infant) assistanceNeeds.push('INFANT_CHILD');
    if (state.assistance.medicalOxygen) assistanceNeeds.push('MEDICAL_OXYGEN');
    if (state.assistance.waistDeep) assistanceNeeds.push('WAIST_DEEP_WATER');

    try {
      const response = await broadcastSosDistress({
        citizen_name: state.citizenName,
        contact_number: state.citizenPhone,
        ward_id: state.selectedWard,
        latitude: options?.latitude ?? 19.0728,
        longitude: options?.longitude ?? 72.8792,
        battery_level: 84,
        assistance_needs: assistanceNeeds,
        notes: options?.notes || 'Critical Citizen Flood Distress Beacon Broadcast',
      });

      state = {
        ...state,
        activeSos: response,
        isBroadcasting: false,
      };
      notify();
    } catch {
      state = { ...state, isBroadcasting: false };
      notify();
    }
  },

  async cancelDistress(reason: string = 'Citizen reported safe') {
    if (!state.activeSos) return;

    const sosId = state.activeSos.sos_id;
    try {
      await cancelSosDistress(sosId, reason);
    } catch {
      // ignore
    }

    state = {
      ...state,
      activeSos: null,
      isBroadcasting: false,
    };
    notify();
  },
};

export function useEmergencyStore(): EmergencyStoreState {
  return useSyncExternalStore(
    (onStoreChange) => {
      listeners.add(onStoreChange);
      return () => listeners.delete(onStoreChange);
    },
    () => state,
    () => INITIAL_STATE
  );
}
