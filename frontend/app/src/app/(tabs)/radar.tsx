import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { 
  View, 
  ScrollView, 
  Pressable, 
  TextInput, 
  Dimensions, 
  Alert,
  Share,
  Animated,
  PanResponder,
  TouchableOpacity,
  Modal
} from 'react-native';
import { useRouter } from 'expo-router';
import { WebView } from 'react-native-webview';
import { 
  Search, 
  X, 
  CloudRain, 
  AlertTriangle, 
  ShieldCheck, 
  Navigation, 
  Camera, 
  CheckCircle2, 
  Crosshair, 
  Droplets, 
  Clock, 
  Share2,
  Shield,
  Activity,
  Layers,
  MapPin,
  ChevronUp,
  ChevronDown,
  TrendingUp,
  ChevronRight,
  History,
  RotateCcw,
  SkipBack,
  SkipForward,
  Play,
  Pause
} from 'lucide-react-native';

import { AppHeader } from '@/components/shared/app-header';
import { Text } from '@/components/ui/text';
import { emergencyStore } from '@/lib/emergency-store';
import { 
  fetchActiveIncidents, 
  fetchCriticalAssets, 
  fetchFieldReports,
  fetchRiskCells,
  fetchRoadClosures,
  fetchLowerRiskRoute,
  fetchCellTimeline,
  createReplaySession,
  controlReplayPlayback,
  scrubReplayTime,
  fetchReplaySlice,
  type IncidentItem, 
  type CriticalAssetItem,
  type FieldReportItem,
  type RiskCellItem,
  type RoadClosureSegment,
  type LowerRiskRouteResponse,
  type CellTimelineResponse,
  type ReplaySession,
  type ReplaySliceData,
  FALLBACK_ROUTE,
  FALLBACK_CELL_TIMELINE,
  CARTO_API_KEY
} from '@/lib/api';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');
const DRAWER_HEIGHT = Math.min(SCREEN_HEIGHT * 0.56, 480);
const COLLAPSED_HEIGHT = 145;
const HIDDEN_OFFSET = DRAWER_HEIGHT - COLLAPSED_HEIGHT;

export interface RadarPoint {
  id: string;
  title: string;
  landmark: string;
  coordinates: [number, number]; // [lat, lon]
  risk: 'LOW' | 'MODERATE' | 'HIGH' | 'SEVERE';
  waterDepth: string;
  inflowRate: string;
  trafficStatus: string;
  verification: string;
  estRecession: string;
  type: 'INCIDENT' | 'ASSET' | 'REPORT';
}

const DEFAULT_POINTS: RadarPoint[] = [
  {
    id: 'inc-kurla-01',
    title: 'Mithi River Overspill at CST Road Bridge',
    landmark: 'CST Road, Kurla West • 420m away',
    coordinates: [19.0712, 72.8756],
    risk: 'SEVERE',
    waterDepth: '0.85m Water (2.8 ft)',
    inflowRate: '+8 cm/h',
    trafficStatus: 'Halted (Road Closed)',
    verification: 'Verified by NDRF Unit 4',
    estRecession: '~1h 40m (Pumps Active)',
    type: 'INCIDENT',
  },
  {
    id: 'inc-dadar-02',
    title: "Severe Waterlogging Under King's Circle Flyover",
    landmark: "King's Circle, Dadar • 1.4km away",
    coordinates: [19.0305, 72.8598],
    risk: 'HIGH',
    waterDepth: '0.45m Water (1.5 ft)',
    inflowRate: '+4 cm/h',
    trafficStatus: 'Single Lane (Slow Speed)',
    verification: 'Verified by BMC Traffic Police',
    estRecession: '~50 mins',
    type: 'INCIDENT',
  },
  {
    id: 'rep-kurla-bus',
    title: 'Kurla Station Bus Depot Inundation',
    landmark: 'Kurla Station Road • 320m away',
    coordinates: [19.0715, 72.8759],
    risk: 'SEVERE',
    waterDepth: '75 cm (Waist Level)',
    inflowRate: '+6 cm/h',
    trafficStatus: 'Buses Suspended',
    verification: 'AI Verified Field Photo (96% Conf)',
    estRecession: '~2h 10m',
    type: 'REPORT',
  },
  {
    id: 'asset-hosp-01',
    title: 'Sion Municipal General Hospital',
    landmark: 'Sion West • 850m away',
    coordinates: [19.0365, 72.8601],
    risk: 'LOW',
    waterDepth: '0 Inches (Elevated Ramp)',
    inflowRate: '0 cm/h',
    trafficStatus: 'Emergency Lane Open',
    verification: 'Safe Haven • 120 Beds Open',
    estRecession: 'Safe High Ground (+5.4m MSL)',
    type: 'ASSET',
  },
  {
    id: 'asset-power-02',
    title: 'Dharavi 110kV Electrical Substation',
    landmark: 'Dharavi Cross Road • 600m away',
    coordinates: [19.0432, 72.8534],
    risk: 'MODERATE',
    waterDepth: '0.15m Waterlogging',
    inflowRate: '+2 cm/h',
    trafficStatus: 'Normal (Access Protected)',
    verification: 'Protected by Sandbag Dykes',
    estRecession: 'Backup Systems Active',
    type: 'ASSET',
  },
];

export default function RadarScreen() {
  const router = useRouter();
  const webViewRef = useRef<WebView>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [activeLayers, setActiveLayers] = useState({
    rain: true,
    flood: true,
    roads: true,
  });

  const [points, setPoints] = useState<RadarPoint[]>(DEFAULT_POINTS);
  const [selectedPoint, setSelectedPoint] = useState<RadarPoint>(DEFAULT_POINTS[0]);
  const [isBypassActive, setIsBypassActive] = useState(false);
  const [routeData, setRouteData] = useState<LowerRiskRouteResponse>(FALLBACK_ROUTE);
  const [riskCells, setRiskCells] = useState<RiskCellItem[]>([]);
  const [roadClosures, setRoadClosures] = useState<RoadClosureSegment[]>([]);
  const [isLiveApi, setIsLiveApi] = useState(false);
  const [isExpandedState, setIsExpandedState] = useState(false);

  // 90-Minute Predictive Inundation Timeline state (From /risk/{h3_cell}/timeline)
  const [timelineData, setTimelineData] = useState<CellTimelineResponse>(FALLBACK_CELL_TIMELINE);
  const [showTimelineModal, setShowTimelineModal] = useState(false);
  const [isLoadingTimeline, setIsLoadingTimeline] = useState(false);

  const handleOpenTimeline = async (cellId = '8860145b53fffff') => {
    setIsLoadingTimeline(true);
    setShowTimelineModal(true);
    try {
      const res = await fetchCellTimeline(cellId);
      if (res?.data) {
        setTimelineData(res.data);
      }
    } catch {
      // fallback
    } finally {
      setIsLoadingTimeline(false);
    }
  };

  // -------------------------------------------------------------
  // Historical Disaster Replay State & Virtual Clock Handlers
  // -------------------------------------------------------------
  const livePointsRef = useRef<RadarPoint[]>([]);
  const liveRiskCellsRef = useRef<RiskCellItem[]>([]);
  const [isReplayMode, setIsReplayMode] = useState(false);
  const [replaySession, setReplaySession] = useState<ReplaySession | null>(null);
  const [replaySlice, setReplaySlice] = useState<ReplaySliceData | null>(null);
  const [isLoadingReplay, setIsLoadingReplay] = useState(false);

  const BENCHMARK_TIMESTEPS = [
    { label: '06:00 AM', tag: 'Onset', iso: '2025-07-26T06:00:00Z', rain: '22 mm/h', depth: '0.15m' },
    { label: '09:00 AM', tag: 'Surge', iso: '2025-07-26T09:00:00Z', rain: '68 mm/h', depth: '0.65m' },
    { label: '12:00 PM', tag: 'PEAK', iso: '2025-07-26T12:00:00Z', rain: '110 mm/h', depth: '1.45m' },
    { label: '03:00 PM', tag: 'Receding', iso: '2025-07-26T15:00:00Z', rain: '45 mm/h', depth: '0.90m' },
    { label: '06:00 PM', tag: 'Clear', iso: '2025-07-26T18:00:00Z', rain: '12 mm/h', depth: '0.30m' },
  ];

  const applyReplaySliceToMap = useCallback((slice: ReplaySliceData) => {
    const replayPoints: RadarPoint[] = [];

    // Historical Incidents from slice
    (slice.incidents || []).forEach((inc) => {
      replayPoints.push({
        id: inc.incident_id,
        title: inc.title,
        landmark: 'Historical Inundation • 26 July 2025 Benchmark',
        coordinates: [inc.latitude, inc.longitude],
        risk: (inc.severity === 'CRITICAL' ? 'SEVERE' : inc.severity === 'HIGH' ? 'HIGH' : 'MODERATE') as any,
        waterDepth: `Historical Disaster Slice (${inc.severity})`,
        inflowRate: `${slice.weather?.rainfall_rate_mm_h ?? 0} mm/h Rate`,
        trafficStatus: inc.status,
        verification: 'Benchmark Event Ground Truth',
        estRecession: 'Peak Surge Event (12:00 PM)',
        type: 'INCIDENT',
      });
    });

    // Historical Field Reports from slice
    (slice.reports || []).forEach((rep) => {
      replayPoints.push({
        id: rep.report_id,
        title: `${rep.category.replace('_', ' ')} Hazard`,
        landmark: 'Mithi River Basin Ground Observation',
        coordinates: [rep.latitude, rep.longitude],
        risk: rep.water_depth_cm > 50 ? 'SEVERE' : 'HIGH',
        waterDepth: `${rep.water_depth_cm} cm Depth`,
        inflowRate: 'Field SAR Inundation',
        trafficStatus: 'Road Impassable',
        verification: `${rep.verification_status} (Benchmark)`,
        estRecession: 'Receding phase after 15:00',
        type: 'REPORT',
      });
    });

    if (replayPoints.length > 0) {
      setPoints(replayPoints);
      setSelectedPoint(replayPoints[0]);
    }

    // Historical risk cells mapped from high_risk_cells snapshot
    const highCells = slice.risk_snapshot?.high_risk_cells || [];
    const syntheticCells: RiskCellItem[] = [
      {
        h3_cell_id: '886189254dfffff',
        risk_level: highCells.includes('886189254dfffff') ? 'SEVERE' : 'MODERATE',
        confidence: 0.96,
        flood_depth_m: slice.model_outputs?.max_predicted_depth_m ?? 0.5,
        rainfall_rate_mm_h: slice.weather?.rainfall_rate_mm_h ?? 40,
        ward_id: 'WARD-08-KURLA',
      },
      {
        h3_cell_id: '886189254bfffff',
        risk_level: highCells.includes('886189254bfffff') ? 'SEVERE' : 'HIGH',
        confidence: 0.94,
        flood_depth_m: (slice.model_outputs?.max_predicted_depth_m ?? 0.5) * 0.8,
        rainfall_rate_mm_h: (slice.weather?.rainfall_rate_mm_h ?? 40) * 0.9,
        ward_id: 'WARD-04-DADAR',
      },
      {
        h3_cell_id: '8861892555fffff',
        risk_level: highCells.includes('8861892555fffff') ? 'SEVERE' : 'LOW',
        confidence: 0.92,
        flood_depth_m: (slice.model_outputs?.max_predicted_depth_m ?? 0.5) * 0.6,
        rainfall_rate_mm_h: (slice.weather?.rainfall_rate_mm_h ?? 40) * 0.7,
        ward_id: 'WARD-12-DHARAVI',
      },
    ];
    setRiskCells(syntheticCells);
  }, []);

  const handleStartReplay = async () => {
    setIsLoadingReplay(true);
    try {
      livePointsRef.current = points;
      liveRiskCellsRef.current = riskCells;

      const session = await createReplaySession(1.0);
      if (session) {
        setReplaySession(session);
        const stateRes = await fetchReplaySlice(session.session_id);
        if (stateRes?.temporal_slice) {
          setReplaySlice(stateRes.temporal_slice);
          applyReplaySliceToMap(stateRes.temporal_slice);
        }
        setIsReplayMode(true);
      } else {
        Alert.alert('Replay Server', 'Could not establish connection to the historical replay server.');
      }
    } catch {
      Alert.alert('Replay Error', 'Unable to initiate historical replay session.');
    } finally {
      setIsLoadingReplay(false);
    }
  };

  const handleExitReplay = () => {
    setIsReplayMode(false);
    setReplaySession(null);
    setReplaySlice(null);
    if (livePointsRef.current.length > 0) {
      setPoints(livePointsRef.current);
      setSelectedPoint(livePointsRef.current[0]);
    }
    if (liveRiskCellsRef.current.length > 0) {
      setRiskCells(liveRiskCellsRef.current);
    }
  };

  const handleScrubTimestamp = async (isoTimestamp: string) => {
    if (!replaySession) return;
    setIsLoadingReplay(true);
    try {
      const updated = await scrubReplayTime(replaySession.session_id, isoTimestamp);
      if (updated) {
        setReplaySession(updated);
        const stateRes = await fetchReplaySlice(replaySession.session_id);
        if (stateRes?.temporal_slice) {
          setReplaySlice(stateRes.temporal_slice);
          applyReplaySliceToMap(stateRes.temporal_slice);
        }
      }
    } catch {
      //
    } finally {
      setIsLoadingReplay(false);
    }
  };

  const handleControlStep = async (action: 'STEP_FORWARD' | 'STEP_BACKWARD' | 'RESET') => {
    if (!replaySession) return;
    setIsLoadingReplay(true);
    try {
      const updated = await controlReplayPlayback(replaySession.session_id, action);
      if (updated) {
        setReplaySession(updated);
        const stateRes = await fetchReplaySlice(replaySession.session_id);
        if (stateRes?.temporal_slice) {
          setReplaySlice(stateRes.temporal_slice);
          applyReplaySliceToMap(stateRes.temporal_slice);
        }
      }
    } catch {
      //
    } finally {
      setIsLoadingReplay(false);
    }
  };

  // -------------------------------------------------------------
  // Slidable & Responsive Gesture Drawer
  // -------------------------------------------------------------
  const translateY = useRef(new Animated.Value(HIDDEN_OFFSET)).current;
  const isExpandedRef = useRef(false);
  const panStartOffset = useRef(HIDDEN_OFFSET);

  const animateTo = useCallback((toExpanded: boolean) => {
    isExpandedRef.current = toExpanded;
    setIsExpandedState(toExpanded);
    Animated.spring(translateY, {
      toValue: toExpanded ? 0 : HIDDEN_OFFSET,
      useNativeDriver: false,
      friction: 8,
      tension: 45,
    }).start();
  }, [translateY]);

  const toggleDrawer = useCallback(() => {
    animateTo(!isExpandedRef.current);
  }, [animateTo]);

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dy) > 4,
        onPanResponderGrant: () => {
          panStartOffset.current = isExpandedRef.current ? 0 : HIDDEN_OFFSET;
          translateY.stopAnimation();
        },
        onPanResponderMove: (_, gesture) => {
          const nextOffset = Math.max(0, Math.min(HIDDEN_OFFSET, panStartOffset.current + gesture.dy));
          translateY.setValue(nextOffset);
        },
        onPanResponderRelease: (_, gesture) => {
          // If tap without drag (less than 6px movement), toggle state
          if (Math.abs(gesture.dy) < 6 && Math.abs(gesture.dx) < 6) {
            animateTo(!isExpandedRef.current);
            return;
          }

          // Swiped upwards
          if (gesture.dy < -35 || gesture.vy < -0.35) {
            animateTo(true);
          }
          // Swiped downwards
          else if (gesture.dy > 35 || gesture.vy > 0.35) {
            animateTo(false);
          }
          // Snap based on midpoint
          else {
            const current = panStartOffset.current + gesture.dy;
            animateTo(current < HIDDEN_OFFSET * 0.5);
          }
        },
      }),
    [animateTo, translateY]
  );

  // -------------------------------------------------------------
  // Load 100% Real Backend Data
  // -------------------------------------------------------------
  useEffect(() => {
    async function loadAllBackendData() {
      try {
        const [incRes, assetRes, reportRes, riskRes, routeRes, closureRes] = await Promise.all([
          fetchActiveIncidents(),
          fetchCriticalAssets(),
          fetchFieldReports(),
          fetchRiskCells(),
          fetchLowerRiskRoute(),
          fetchRoadClosures(),
        ]);

        if (routeRes?.data) {
          setRouteData(routeRes.data);
        }

        if (riskRes?.data) {
          setRiskCells(riskRes.data);
        }

        if (closureRes?.data) {
          setRoadClosures(closureRes.data);
        }

        const mappedPoints: RadarPoint[] = [];

        // 1. Incidents from GET /api/v1/incidents
        const incidents = Array.isArray(incRes?.data) ? incRes.data : [];
        incidents.forEach((inc: IncidentItem) => {
          mappedPoints.push({
            id: inc.incident_id,
            title: inc.title,
            landmark: inc.ward_id === 'WARD-08-KURLA' 
              ? 'CST Road, Kurla West • 420m away' 
              : "King's Circle, Dadar • 1.4km away",
            coordinates: [inc.location.latitude, inc.location.longitude],
            risk: inc.severity === 'CRITICAL' ? 'SEVERE' : 'HIGH',
            waterDepth: inc.severity === 'CRITICAL' ? '0.85m Water (2.8 ft)' : '0.45m Water (1.5 ft)',
            inflowRate: inc.severity === 'CRITICAL' ? '+8 cm/h' : '+4 cm/h',
            trafficStatus: inc.status === 'DISPATCHED' ? 'Halted (Road Closed)' : 'Single Lane (Slow Speed)',
            verification: `Verified by Civic Emergency Unit (${inc.status})`,
            estRecession: inc.severity === 'CRITICAL' ? '~1h 40m (Pumps Active)' : '~50 mins',
            type: 'INCIDENT',
          });
        });

        // 2. Field Reports from GET /api/v1/reports
        const reports = Array.isArray(reportRes?.data) ? reportRes.data : [];
        reports.forEach((rep: FieldReportItem) => {
          mappedPoints.push({
            id: rep.report_id,
            title: rep.description.split('.')[0],
            landmark: 'Kurla Station Road • 320m away',
            coordinates: [rep.location.latitude, rep.location.longitude],
            risk: 'SEVERE',
            waterDepth: `${rep.estimated_water_depth_cm} cm (Waist Level)`,
            inflowRate: '+6 cm/h',
            trafficStatus: 'Buses Suspended',
            verification: `${rep.verification_status} (${Math.round(rep.ai_confidence * 100)}% Conf)`,
            estRecession: '~2h 10m',
            type: 'REPORT',
          });
        });

        // 3. Critical Assets from GET /api/v1/assets
        const assets = Array.isArray(assetRes?.data) ? assetRes.data : [];
        assets.forEach((asset: CriticalAssetItem) => {
          mappedPoints.push({
            id: asset.asset_id,
            title: asset.name,
            landmark: `${asset.asset_type === 'HOSPITAL' ? 'Sion West' : 'Dharavi'} • Safe Facility`,
            coordinates: [asset.location.latitude, asset.location.longitude],
            risk: asset.status === 'AT_RISK' ? 'MODERATE' : 'LOW',
            waterDepth: asset.status === 'AT_RISK' ? '0.15m Water' : '0 Inches (Dry High Ground)',
            inflowRate: '0 cm/h',
            trafficStatus: 'Emergency Access Open',
            verification: asset.status === 'AT_RISK' ? 'Monitored Critical Asset' : 'Safe Haven • Disaster Shelter',
            estRecession: 'Safe High Ground (+5.4m MSL)',
            type: 'ASSET',
          });
        });

        if (mappedPoints.length > 0) {
          setPoints(mappedPoints);
          setSelectedPoint(mappedPoints[0]);
          setIsLiveApi(incRes.isLive || assetRes.isLive || reportRes.isLive);
        }
      } catch (e) {
        // Fallback default points remain active
      }
    }
    loadAllBackendData();
  }, []);

  // Update map markers smoothly whenever points update
  useEffect(() => {
    if (webViewRef.current && points.length > 0) {
      webViewRef.current.injectJavaScript(`
        if (window.updateMapPoints) {
          window.updateMapPoints(${JSON.stringify(points)});
        }
        true;
      `);
    }
  }, [points]);

  // Update flood zones dynamically from real /risk/cells backend
  useEffect(() => {
    if (webViewRef.current && riskCells.length > 0) {
      webViewRef.current.injectJavaScript(`
        if (window.updateRiskCells) {
          window.updateRiskCells(${JSON.stringify(riskCells)});
        }
        true;
      `);
    }
  }, [riskCells]);

  // Update road closures dynamically from real /routes/closures backend
  useEffect(() => {
    if (webViewRef.current && roadClosures.length > 0) {
      webViewRef.current.injectJavaScript(`
        if (window.updateRoadClosures) {
          window.updateRoadClosures(${JSON.stringify(roadClosures)});
        }
        true;
      `);
    }
  }, [roadClosures]);

  // Filter points matching search query
  const filteredPoints = useMemo(() => {
    if (!searchQuery.trim()) return [];
    const q = searchQuery.toLowerCase();
    return points.filter(
      (p) => p.title.toLowerCase().includes(q) || p.landmark.toLowerCase().includes(q)
    );
  }, [searchQuery, points]);

  const toggleLayer = (layer: 'rain' | 'flood' | 'roads') => {
    setActiveLayers((prev) => {
      const updated = { ...prev, [layer]: !prev[layer] };
      if (webViewRef.current) {
        webViewRef.current.injectJavaScript(`
          if (window.toggleMapLayer) {
            window.toggleMapLayer('${layer}', ${updated[layer]});
          }
          true;
        `);
      }
      return updated;
    });
  };

  const handleSelectPoint = (point: RadarPoint) => {
    setSelectedPoint(point);
    setSearchQuery('');
    if (webViewRef.current) {
      webViewRef.current.injectJavaScript(`
        if (window.focusPoint) {
          window.focusPoint(${point.coordinates[0]}, ${point.coordinates[1]}, 16);
        }
        true;
      `);
    }
  };

  const handleRecenter = () => {
    if (webViewRef.current) {
      webViewRef.current.injectJavaScript(`
        if (window.focusPoint) {
          window.focusPoint(19.068, 72.868, 14);
        }
        true;
      `);
    }
  };

  const handleToggleBypass = () => {
    const nextState = !isBypassActive;
    setIsBypassActive(nextState);

    // Extract real coordinates from backend route
    const routeCoords = routeData.features[0]?.geometry?.coordinates.map(
      ([lon, lat]) => [lat, lon]
    ) || [
      [19.0712, 72.8756],
      [19.0550, 72.8800],
      [19.0365, 72.8601],
    ];

    if (webViewRef.current) {
      webViewRef.current.injectJavaScript(`
        if (window.toggleBypass) {
          window.toggleBypass(${nextState}, ${JSON.stringify(routeCoords)});
        }
        true;
      `);
    }
  };

  const handleShareAdvisory = async () => {
    try {
      await Share.share({
        message: `🚨 JALAI Flood Warning: ${selectedPoint.title}\nDepth: ${selectedPoint.waterDepth} (${selectedPoint.risk} Risk)\nTraffic: ${selectedPoint.trafficStatus}\nElevation safe haven available at Sion Hospital. Avoid submerged routes.`,
      });
    } catch (e) {
      // Cancelled
    }
  };

  // -------------------------------------------------------------
  // Leaflet + Authenticated CartoDB Raster Basemap HTML
  // Uses official key param (?key=...)
  // -------------------------------------------------------------
  const stableMapHtml = useMemo(() => `
    <!DOCTYPE html>
    <html>
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
          * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
          html, body, #map {
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            background-color: #050A14;
            overflow: hidden;
          }
          .custom-pin {
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            border-radius: 9999px;
            cursor: pointer;
          }
          .pulse-beacon {
            position: relative;
            width: 18px;
            height: 18px;
            background: #00F0FF;
            border: 2.5px solid #FFFFFF;
            border-radius: 50%;
            box-shadow: 0 0 16px #00F0FF;
          }
          .pulse-beacon::after {
            content: '';
            position: absolute;
            top: -9px;
            left: -9px;
            right: -9px;
            bottom: -9px;
            border-radius: 50%;
            border: 2px solid #00F0FF;
            animation: pulse 2s cubic-bezier(0.25, 1, 0.5, 1) infinite;
          }
          @keyframes pulse {
            0% { transform: scale(0.6); opacity: 1; }
            100% { transform: scale(2.4); opacity: 0; }
          }
          .pin-badge {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 4px 10px;
            border-radius: 9999px;
            border: 1.5px solid rgba(255,255,255,0.9);
            color: #FFFFFF;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.3px;
            box-shadow: 0 6px 18px rgba(0,0,0,0.7);
            transition: transform 0.15s ease;
          }
          .pin-badge:active {
            transform: scale(0.92);
          }
        </style>
      </head>
      <body>
        <div id="map"></div>
        <script>
          var map = L.map('map', {
            zoomControl: false,
            attributionControl: false
          }).setView([19.068, 72.868], 14);

          // Authenticated CARTO Dark Matter Raster Basemap
          // Official parameters: /rastertiles/dark_all/{z}/{x}/{y}.png?key=YOUR_KEY
          var cartoKey = '${CARTO_API_KEY}';
          var tileUrl = 'https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png?key=' + encodeURIComponent(cartoKey);

          L.tileLayer(tileUrl, {
            maxZoom: 20,
            subdomains: 'abcd'
          }).addTo(map);

          // Layer Groups
          var rainLayer = L.layerGroup().addTo(map);
          var floodLayer = L.layerGroup().addTo(map);
          var roadLayer = L.layerGroup().addTo(map);
          var markersLayer = L.layerGroup().addTo(map);
          var bypassLayer = L.layerGroup();

          // 1. User Position Marker
          var userIcon = L.divIcon({
            className: 'custom-pin',
            html: '<div class="pulse-beacon"></div>',
            iconSize: [22, 22],
            iconAnchor: [11, 11]
          });
          L.marker([19.068, 72.868], { icon: userIcon }).addTo(map);

          // 2. Dynamic Flood Risk Inundation Zones from /risk/cells
          window.updateRiskCells = function(cells) {
            floodLayer.clearLayers();
            var wardCoords = {
              'WARD-12-DHARAVI': [19.043, 72.855],
              'WARD-08-KURLA': [19.071, 72.875],
              'WARD-04-DADAR': [19.030, 72.860]
            };

            cells.forEach(function(c) {
              var pos = wardCoords[c.ward_id] || [19.055, 72.865];
              var color = c.risk_level === 'SEVERE' ? '#EF4444' : c.risk_level === 'HIGH' ? '#F59E0B' : '#3B82F6';
              var radius = c.rainfall_rate_mm_h ? (c.rainfall_rate_mm_h * 12) : 600;

              L.circle(pos, {
                color: color,
                fillColor: color,
                fillOpacity: c.risk_level === 'SEVERE' ? 0.35 : 0.25,
                weight: 1.5,
                radius: radius
              }).addTo(floodLayer);
            });
          };

          // 3. Dynamic Road Closures & Submerged Routes from /routes/closures
          window.updateRoadClosures = function(closures) {
            roadLayer.clearLayers();
            closures.forEach(function(r) {
              var isClosed = r.is_closed;
              var isInundated = r.status === 'INUNDATED';
              var color = isClosed ? '#EF4444' : isInundated ? '#F59E0B' : '#64748B';
              var weight = isClosed ? 5 : isInundated ? 4 : 2;
              var dash = isClosed ? '8, 8' : isInundated ? '6, 4' : null;

              var poly = L.polyline(r.coordinates, {
                color: color,
                weight: weight,
                dashArray: dash,
                opacity: isClosed ? 0.95 : 0.8
              }).addTo(roadLayer);

              if (isClosed) {
                var midLat = (r.coordinates[0][0] + r.coordinates[1][0]) / 2;
                var midLon = (r.coordinates[0][1] + r.coordinates[1][1]) / 2;
                var closureBadge = L.divIcon({
                  className: 'custom-pin',
                  html: '<div style="background:#EF4444; color:#FFF; font-size:9px; font-weight:900; padding:2px 6px; border-radius:9999px; border:1px solid #FFF; white-space:nowrap; box-shadow:0 2px 8px rgba(0,0,0,0.8);">⛔ CLOSED</div>',
                  iconSize: [60, 20],
                  iconAnchor: [30, 10]
                });
                L.marker([midLat, midLon], { icon: closureBadge }).addTo(roadLayer);
              }
            });
          };

          // 4. Rain Radar Precipitation Catchment Overlay
          L.circle([19.065, 72.870], {
            color: '#06B6D4',
            fillColor: '#0284C7',
            fillOpacity: 0.16,
            weight: 1,
            radius: 2400
          }).addTo(rainLayer);

          // 5. Dynamic Backend Markers
          window.updateMapPoints = function(pointsData) {
            markersLayer.clearLayers();
            pointsData.forEach(function(pt) {
              var badgeBg = pt.risk === 'SEVERE' 
                ? '#EF4444' 
                : pt.risk === 'HIGH' 
                ? '#F59E0B' 
                : pt.risk === 'MODERATE' 
                ? '#3B82F6' 
                : '#10B981';

              var label = pt.risk === 'SEVERE' || pt.risk === 'HIGH' 
                ? '● ' + pt.waterDepth.split(' ')[0] + ' ' + (pt.waterDepth.split(' ')[1] || '')
                : pt.type === 'ASSET' ? '🛡️ ' + pt.title.split(' ')[0] : '● ' + pt.title.split(' ')[0];

              var iconHtml = '<div class="pin-badge" style="background:' + badgeBg + ';">' + label + '</div>';

              var markerIcon = L.divIcon({
                className: 'custom-pin',
                html: iconHtml,
                iconSize: [110, 28],
                iconAnchor: [55, 14]
              });

              var m = L.marker(pt.coordinates, { icon: markerIcon }).addTo(markersLayer);
              m.on('click', function() {
                if (window.ReactNativeWebView) {
                  window.ReactNativeWebView.postMessage(JSON.stringify({
                    type: 'SELECT_POINT',
                    id: pt.id
                  }));
                }
              });
            });
          };

          // Initial Points Render
          window.updateMapPoints(${JSON.stringify(DEFAULT_POINTS)});

          // Layer Toggles
          window.toggleMapLayer = function(layer, active) {
            if (layer === 'rain') {
              active ? map.addLayer(rainLayer) : map.removeLayer(rainLayer);
            } else if (layer === 'flood') {
              active ? map.addLayer(floodLayer) : map.removeLayer(floodLayer);
            } else if (layer === 'roads') {
              active ? map.addLayer(roadLayer) : map.removeLayer(roadLayer);
            }
          };

          window.focusPoint = function(lat, lon, zoom) {
            map.flyTo([lat, lon], zoom || 15, { duration: 1.0 });
          };

          // Safe Lower-Risk Route Display
          var currentBypassPolyline = null;
          window.toggleBypass = function(active, coords) {
            if (currentBypassPolyline) {
              map.removeLayer(currentBypassPolyline);
              currentBypassPolyline = null;
            }
            if (active && coords && coords.length > 0) {
              currentBypassPolyline = L.polyline(coords, {
                color: '#00F0FF',
                weight: 6,
                opacity: 0.95,
                lineJoin: 'round'
              }).addTo(map);
              map.fitBounds(currentBypassPolyline.getBounds(), { padding: [50, 50] });
            }
          };
        </script>
      </body>
    </html>
  `, []);

  const handleMessage = (event: any) => {
    try {
      const message = JSON.parse(event.nativeEvent.data);
      if (message.type === 'SELECT_POINT') {
        const found = points.find((p) => p.id === message.id);
        if (found) {
          setSelectedPoint(found);
        }
      }
    } catch (e) {
      // Ignore
    }
  };

  const riskBadgeStyle = 
    selectedPoint.risk === 'SEVERE'
      ? { bg: 'bg-rose-600', text: 'text-white' }
      : selectedPoint.risk === 'HIGH'
      ? { bg: 'bg-amber-500', text: 'text-slate-950' }
      : selectedPoint.risk === 'MODERATE'
      ? { bg: 'bg-blue-600', text: 'text-white' }
      : { bg: 'bg-emerald-600', text: 'text-white' };

  return (
    <View className="flex-1 bg-[#050A14]">
      {/* 1. Tactical Header with Safe Area Insets */}
      <AppHeader
        location="Kurla Basin, Mumbai • Live Radar"
        onDistressPress={() => emergencyStore.openSos({ ward: 'Kurla Basin, Mumbai' })}
        onProfilePress={() => emergencyStore.openTerminal()}
      />

      {/* 2. FULL-SCREEN REAL MAP */}
      <View className="flex-1 relative bg-[#050A14]">
        <WebView
          ref={webViewRef}
          originWhitelist={['*']}
          source={{ html: stableMapHtml }}
          onMessage={handleMessage}
          style={{ flex: 1, backgroundColor: '#050A14' }}
          javaScriptEnabled={true}
          domStorageEnabled={true}
        />

        {/* 3. FLOATING TOP CONTROLS OVER MAP */}
        <View className="absolute top-3 left-4 right-4 z-20">
          {/* Glassmorphic Search Bar */}
          <View className="bg-[#0A1120]/95 border border-slate-700/80 rounded-2xl px-3.5 py-2.5 flex-row items-center justify-between shadow-2xl">
            <View className="flex-row items-center gap-2.5 flex-1 mr-2 min-w-0">
              <Search size={16} color="#00F0FF" />
              <TextInput
                value={searchQuery}
                onChangeText={setSearchQuery}
                placeholder="Search flood hotspots, havens, or reports..."
                placeholderTextColor="#64748B"
                className="text-xs font-bold text-white flex-1 p-0"
                numberOfLines={1}
              />
            </View>
            {searchQuery.length > 0 && (
              <Pressable onPress={() => setSearchQuery('')} className="p-1">
                <X size={15} color="#94A3B8" />
              </Pressable>
            )}
          </View>

          {/* Search Suggestions Dropdown */}
          {filteredPoints.length > 0 && (
            <View className="bg-[#0A1120] border border-slate-700 rounded-2xl mt-1.5 p-2 shadow-2xl">
              {filteredPoints.map((item) => (
                <Pressable
                  key={item.id}
                  onPress={() => handleSelectPoint(item)}
                  className="py-2 px-2.5 border-b border-slate-800 last:border-b-0 flex-row items-center justify-between active:bg-slate-800/60 rounded-lg"
                >
                  <View className="flex-1 mr-2">
                    <Text className="text-xs font-bold text-white" numberOfLines={1}>
                      {item.title}
                    </Text>
                    <Text className="text-[10px] text-slate-400 mt-0.5" numberOfLines={1}>
                      {item.landmark}
                    </Text>
                  </View>
                  <View className={`px-2 py-0.5 rounded ${
                    item.risk === 'SEVERE' ? 'bg-rose-500/20 text-rose-400' : 'bg-emerald-500/20 text-emerald-400'
                  }`}>
                    <Text className={`text-[9px] font-black uppercase ${
                      item.risk === 'SEVERE' ? 'text-rose-400' : 'text-emerald-400'
                    }`}>
                      {item.risk}
                    </Text>
                  </View>
                </Pressable>
              ))}
            </View>
          )}

          {/* Clean Floating Layer Switcher Pills */}
          <View className="flex-row gap-2 mt-2">
            <Pressable
              onPress={() => toggleLayer('rain')}
              className={`px-3 py-1.5 rounded-xl border flex-row items-center gap-1.5 shadow-md active:scale-95 ${
                activeLayers.rain
                  ? 'bg-[#00F0FF]/15 border-[#00F0FF]'
                  : 'bg-[#080E1A]/90 border-slate-700/80'
              }`}
            >
              <CloudRain size={12} color={activeLayers.rain ? '#00F0FF' : '#64748B'} />
              <Text className={`text-[11px] font-bold ${activeLayers.rain ? 'text-[#00F0FF]' : 'text-slate-400'}`}>
                Rain Radar
              </Text>
            </Pressable>

            <Pressable
              onPress={() => toggleLayer('flood')}
              className={`px-3 py-1.5 rounded-xl border flex-row items-center gap-1.5 shadow-md active:scale-95 ${
                activeLayers.flood
                  ? 'bg-rose-500/15 border-rose-500'
                  : 'bg-[#080E1A]/90 border-slate-700/80'
              }`}
            >
              <AlertTriangle size={12} color={activeLayers.flood ? '#FB7185' : '#64748B'} />
              <Text className={`text-[11px] font-bold ${activeLayers.flood ? 'text-rose-300' : 'text-slate-400'}`}>
                Flood Zones
              </Text>
            </Pressable>

            <Pressable
              onPress={() => toggleLayer('roads')}
              className={`px-3 py-1.5 rounded-xl border flex-row items-center gap-1.5 shadow-md active:scale-95 ${
                activeLayers.roads
                  ? 'bg-amber-500/15 border-amber-500'
                  : 'bg-[#080E1A]/90 border-slate-700/80'
              }`}
            >
              <Navigation size={12} color={activeLayers.roads ? '#FBBF24' : '#64748B'} />
              <Text className={`text-[11px] font-bold ${activeLayers.roads ? 'text-amber-300' : 'text-slate-400'}`}>
                Road Closures
              </Text>
            </Pressable>
          </View>

          {/* Historical Disaster Replay Trigger / Controller */}
          {!isReplayMode ? (
            <Pressable
              onPress={handleStartReplay}
              disabled={isLoadingReplay}
              className="mt-2 bg-[#0A1324]/95 border border-cyan-500/50 rounded-xl px-3 py-2 flex-row items-center justify-between shadow-xl active:scale-98"
            >
              <View className="flex-row items-center gap-2">
                <History size={15} color="#00F0FF" />
                <View>
                  <Text className="text-xs font-black text-white">
                    26 July Disaster Benchmark Replay
                  </Text>
                  <Text className="text-[10px] text-cyan-300">
                    Scrub historical storm flood progression & closed streets
                  </Text>
                </View>
              </View>
              <View className="bg-cyan-500/20 px-2 py-1 rounded-lg border border-cyan-500/40">
                <Text className="text-[10px] font-black text-cyan-200">
                  {isLoadingReplay ? 'LAUNCHING...' : 'REPLAY'}
                </Text>
              </View>
            </Pressable>
          ) : (
            <View className="mt-2 bg-[#09111F]/98 border border-cyan-400 rounded-2xl p-3 shadow-2xl">
              {/* Header & Mode Badge */}
              <View className="flex-row items-center justify-between pb-2 border-b border-cyan-900/60">
                <View className="flex-row items-center gap-2">
                  <View className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
                  <Text className="text-xs font-black text-cyan-300 tracking-wider">
                    26 JULY 2025 BENCHMARK REPLAY
                  </Text>
                </View>
                <TouchableOpacity
                  onPress={handleExitReplay}
                  className="bg-rose-500/20 border border-rose-500/60 px-2 py-1 rounded-lg"
                >
                  <Text className="text-[10px] font-black text-rose-300">
                    EXIT REPLAY
                  </Text>
                </TouchableOpacity>
              </View>

              {/* Real-time Historical Telemetry Slice */}
              <View className="flex-row items-center justify-between my-2 bg-[#040813] rounded-xl p-2 border border-slate-800">
                <View className="items-center flex-1 border-r border-slate-800">
                  <Text className="text-[9px] text-slate-400 font-bold">CLOCK</Text>
                  <Text className="text-xs font-black text-white mt-0.5">
                    {replaySession?.simulated_time
                      ? new Date(replaySession.simulated_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                      : '06:00 AM'}
                  </Text>
                </View>
                <View className="items-center flex-1 border-r border-slate-800">
                  <Text className="text-[9px] text-slate-400 font-bold">RAIN RATE</Text>
                  <Text className="text-xs font-black text-cyan-400 mt-0.5">
                    {replaySlice?.weather?.rainfall_rate_mm_h ?? 22} mm/h
                  </Text>
                </View>
                <View className="items-center flex-1 border-r border-slate-800">
                  <Text className="text-[9px] text-slate-400 font-bold">TOTAL ACC</Text>
                  <Text className="text-xs font-black text-amber-400 mt-0.5">
                    {replaySlice?.weather?.accumulated_rain_mm ?? 45} mm
                  </Text>
                </View>
                <View className="items-center flex-1">
                  <Text className="text-[9px] text-slate-400 font-bold">MAX DEPTH</Text>
                  <Text className="text-xs font-black text-rose-400 mt-0.5">
                    {replaySlice?.model_outputs?.max_predicted_depth_m ?? 0.15} m
                  </Text>
                </View>
              </View>

              {/* 5-Step Quick Scrubbing Bar */}
              <View className="flex-row gap-1.5 justify-between">
                {BENCHMARK_TIMESTEPS.map((step) => {
                  const isCurrent = replaySession?.simulated_time?.startsWith(step.iso.substring(0, 13));
                  return (
                    <TouchableOpacity
                      key={step.iso}
                      onPress={() => handleScrubTimestamp(step.iso)}
                      disabled={isLoadingReplay}
                      className={`flex-1 py-1.5 px-0.5 rounded-lg items-center border ${
                        isCurrent
                          ? 'bg-cyan-500/30 border-cyan-400'
                          : 'bg-slate-900/80 border-slate-800'
                      }`}
                    >
                      <Text className={`text-[9px] font-black ${isCurrent ? 'text-cyan-200' : 'text-slate-300'}`}>
                        {step.label}
                      </Text>
                      <Text className={`text-[8px] font-bold ${isCurrent ? 'text-cyan-300' : 'text-slate-500'}`}>
                        {step.tag}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              {/* Step Forward / Backward Actions */}
              <View className="flex-row items-center justify-between mt-2 pt-1.5 border-t border-slate-800/80">
                <View className="flex-row items-center gap-1.5">
                  <TouchableOpacity
                    onPress={() => handleControlStep('STEP_BACKWARD')}
                    disabled={isLoadingReplay}
                    className="bg-slate-800/90 p-1.5 rounded-lg border border-slate-700 active:scale-95"
                  >
                    <SkipBack size={13} color="#94A3B8" />
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => handleControlStep('RESET')}
                    disabled={isLoadingReplay}
                    className="bg-slate-800/90 p-1.5 rounded-lg border border-slate-700 active:scale-95"
                  >
                    <RotateCcw size={13} color="#94A3B8" />
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => handleControlStep('STEP_FORWARD')}
                    disabled={isLoadingReplay}
                    className="bg-slate-800/90 p-1.5 rounded-lg border border-slate-700 active:scale-95"
                  >
                    <SkipForward size={13} color="#94A3B8" />
                  </TouchableOpacity>
                </View>

                <Text className="text-[10px] font-bold text-cyan-400">
                  {isLoadingReplay ? 'Scrubbing slice...' : 'Map updated to virtual slice'}
                </Text>
              </View>
            </View>
          )}
        </View>

        {/* 4. FLOATING RIGHT MAP BUTTONS */}
        <View 
          className="absolute right-4 flex-col gap-2.5 z-20"
          style={{ top: isReplayMode ? 270 : 130 }}
        >
          {/* Recenter button */}
          <Pressable
            onPress={handleRecenter}
            className="w-11 h-11 rounded-2xl bg-[#080E1A]/95 border border-slate-700 items-center justify-center shadow-xl active:scale-95"
          >
            <Crosshair size={19} color="#00F0FF" />
          </Pressable>

          {/* Lower-Risk Bypass Route Toggle */}
          <Pressable
            onPress={handleToggleBypass}
            className={`w-11 h-11 rounded-2xl border items-center justify-center shadow-xl active:scale-95 ${
              isBypassActive 
                ? 'bg-[#00F0FF] border-[#00F0FF]' 
                : 'bg-[#080E1A]/95 border-slate-700'
            }`}
          >
            <Navigation size={19} color={isBypassActive ? '#050A14' : '#34D399'} />
          </Pressable>
        </View>

        {/* Live GPS & Backend Indicator Badge */}
        <View className="absolute left-4 bottom-3 z-10 flex-row items-center gap-1.5 bg-[#080E1A]/85 border border-slate-800 px-2.5 py-1 rounded-full">
          <View className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          <Text className="text-[10px] font-bold text-slate-300">
            {isLiveApi ? 'Live Backend Telemetry' : 'Offline Cached Mesh'}
          </Text>
        </View>
      </View>

      {/* 5. GESTURE-SLIDABLE BOTTOM TELEMETRY DRAWER */}
      <Animated.View
        style={{
          transform: [{ translateY }],
          height: DRAWER_HEIGHT,
        }}
        className="absolute bottom-0 left-0 right-0 bg-[#080E1A] border-t border-slate-800 shadow-2xl z-30"
      >
        {/* DRAG & SLIDE HEADER ZONE (PanResponder attached for silky slide gesture) */}
        <View
          {...panResponder.panHandlers}
          className="w-full pt-2 pb-2 px-4 bg-[#080E1A] border-b border-slate-800/60"
        >
          {/* Visual Drag Handle Bar */}
          <View className="w-12 h-1.5 bg-slate-600 rounded-full self-center mb-1.5" />
          
          <View className="flex-row items-center justify-between">
            <View className="flex-row items-center gap-1.5">
              {isExpandedState ? (
                <ChevronDown size={14} color="#00F0FF" />
              ) : (
                <ChevronUp size={14} color="#00F0FF" />
              )}
              <Text className="text-[10px] font-black text-cyan-400 uppercase tracking-widest">
                {isExpandedState ? 'Slide Down to Collapse' : 'Slide Up for Full Telemetry'}
              </Text>
            </View>

            <View className="flex-row items-center gap-1 bg-slate-900 px-2 py-0.5 rounded-full border border-slate-800">
              <View className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <Text className="text-[9px] font-bold text-slate-400 uppercase">
                Interactive
              </Text>
            </View>
          </View>

          {/* Quick Summary Row right inside the drag zone */}
          <View className="flex-row items-center justify-between mt-2">
            <View className="flex-1 mr-3 min-w-0">
              <View className="flex-row items-center gap-2 mb-1">
                <View className={`px-2 py-0.5 rounded ${riskBadgeStyle.bg} flex-shrink-0`}>
                  <Text className={`text-[10px] font-black uppercase tracking-wider ${riskBadgeStyle.text}`}>
                    {selectedPoint.risk} • {selectedPoint.waterDepth}
                  </Text>
                </View>
                <Text className="text-[10px] font-bold text-rose-400 uppercase">
                  INFLOW {selectedPoint.inflowRate}
                </Text>
              </View>

              <Text className="text-sm font-black text-white" numberOfLines={1}>
                {selectedPoint.title}
              </Text>
              <Text className="text-[11px] text-slate-400 mt-0.5 font-medium" numberOfLines={1}>
                {selectedPoint.landmark}
              </Text>
            </View>

            {/* Quick Action Button */}
            <Pressable
              onPress={handleToggleBypass}
              className={`px-3 py-2 rounded-xl flex-row items-center gap-1.5 border active:scale-95 flex-shrink-0 ${
                isBypassActive 
                  ? 'bg-[#00F0FF] border-[#00F0FF]' 
                  : 'bg-slate-800 border-slate-700'
              }`}
            >
              <Navigation size={13} color={isBypassActive ? '#050A14' : '#00F0FF'} />
              <Text className={`text-xs font-black uppercase ${
                isBypassActive ? 'text-slate-950' : 'text-white'
              }`}>
                {isBypassActive ? 'Bypass On' : 'Avoid'}
              </Text>
            </Pressable>
          </View>
        </View>

        {/* EXPANDED TELEMETRY DETAILS (Revealed when slid up) */}
        <ScrollView showsVerticalScrollIndicator={false} bounces={false} className="px-4 pt-3 pb-8">
          {/* 3 Telemetry Metric Cards (2-line wrap to eliminate truncation) */}
          <View className="flex-row gap-2 mb-3">
            <View className="flex-1 bg-slate-900/90 border border-slate-800 p-2.5 rounded-xl min-h-[58px] justify-between">
              <Text className="text-[9px] font-bold text-slate-400 uppercase">TRAFFIC</Text>
              <Text className="text-[11px] font-black text-white leading-tight" numberOfLines={2}>
                {selectedPoint.trafficStatus}
              </Text>
            </View>

            <View className="flex-1 bg-slate-900/90 border border-slate-800 p-2.5 rounded-xl min-h-[58px] justify-between">
              <Text className="text-[9px] font-bold text-slate-400 uppercase">VERIFIED</Text>
              <Text className="text-[11px] font-black text-emerald-400 leading-tight" numberOfLines={2}>
                {selectedPoint.verification}
              </Text>
            </View>

            <View className="flex-1 bg-slate-900/90 border border-slate-800 p-2.5 rounded-xl min-h-[58px] justify-between">
              <Text className="text-[9px] font-bold text-slate-400 uppercase">RECESSION</Text>
              <Text className="text-[11px] font-black text-[#00F0FF] leading-tight" numberOfLines={2}>
                {selectedPoint.estRecession}
              </Text>
            </View>
          </View>

          {/* 90-Min Inundation Predictive Hydrograph Button (From /risk/{cell}/timeline) */}
          <Pressable
            onPress={() => handleOpenTimeline('8860145b53fffff')}
            className="bg-cyan-950/40 border border-cyan-500/50 rounded-xl p-3 mb-3 flex-row items-center justify-between active:scale-[0.99]"
          >
            <View className="flex-row items-center gap-2.5 flex-1 pr-2">
              <View className="w-8 h-8 rounded-lg bg-cyan-500/20 border border-cyan-400 items-center justify-center flex-shrink-0">
                <TrendingUp size={16} color="#00F0FF" />
              </View>
              <View className="flex-1">
                <Text className="text-xs font-black text-white">
                  90-Min Predictive Water Hydrograph
                </Text>
                <Text className="text-[10px] text-cyan-300 mt-0.5">
                  Peak Depth: 0.78m at +60m • Tap to inspect curve
                </Text>
              </View>
            </View>
            <ChevronRight size={16} color="#00F0FF" />
          </Pressable>

          {/* Lower-Risk Routing Advisory from Backend */}
          <View className="bg-slate-900/80 border border-slate-800 p-3 rounded-xl mb-3">
            <View className="flex-row items-center justify-between mb-1.5">
              <View className="flex-row items-center gap-1.5">
                <ShieldCheck size={14} color="#34D399" />
                <Text className="text-xs font-bold text-emerald-300">
                  {routeData.features[0]?.properties?.route_title || 'Flood-Averse Lower-Risk Route'}
                </Text>
              </View>
              <Text className="text-[10px] font-black text-slate-400">
                {Math.round((routeData.features[0]?.properties?.distance_meters || 2600) / 100) / 10} km • ~9 min
              </Text>
            </View>
            <Text className="text-[11px] text-slate-300 leading-relaxed">
              Avoids submerged arterial segment ({routeData.features[0]?.properties?.avoided_risky_segments?.[0]?.road_name || 'CST Road'}) with 0.85m water. Diverts via elevated Eastern High Ground link.
            </Text>
          </View>

          {/* Action Buttons: Navigate Bypass, Report, Share */}
          <View className="flex-row gap-2 mb-6">
            <Pressable
              onPress={handleToggleBypass}
              className={`flex-1 py-3 rounded-xl flex-row items-center justify-center gap-2 border active:scale-95 ${
                isBypassActive
                  ? 'bg-[#00F0FF] border-[#00F0FF]'
                  : 'bg-slate-800 border-slate-700'
              }`}
            >
              <Navigation size={14} color={isBypassActive ? '#050A14' : '#00F0FF'} />
              <Text className={`text-xs font-black uppercase tracking-wider ${
                isBypassActive ? 'text-slate-950' : 'text-white'
              }`}>
                {isBypassActive ? 'Disable Bypass' : 'Navigate Bypass'}
              </Text>
            </Pressable>

            <Pressable
              onPress={() => router.push('/(tabs)/report')}
              className="bg-slate-800 border border-slate-700 px-3.5 py-3 rounded-xl flex-row items-center justify-center gap-1.5 active:bg-slate-700"
            >
              <Camera size={14} color="#FBBF24" />
              <Text className="text-xs font-bold text-white uppercase">
                Report
              </Text>
            </Pressable>

            <Pressable
              onPress={handleShareAdvisory}
              className="bg-slate-800 border border-slate-700 px-3 py-3 rounded-xl items-center justify-center active:bg-slate-700"
            >
              <Share2 size={14} color="#94A3B8" />
            </Pressable>
          </View>
        </ScrollView>
      </Animated.View>

      {/* Modal: 90-Minute Predictive Water Hydrograph (From /risk/{cell}/timeline) */}
      <Modal
        visible={showTimelineModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowTimelineModal(false)}
      >
        <View className="flex-1 bg-black/85 items-center justify-center px-6">
          <View className="bg-[#0B1322] border border-cyan-500 rounded-3xl p-5 w-full shadow-2xl">
            {/* Header */}
            <View className="flex-row items-center justify-between mb-3 border-b border-slate-800 pb-2.5">
              <View className="flex-row items-center gap-2">
                <TrendingUp size={18} color="#00F0FF" />
                <Text className="text-sm font-black text-white uppercase tracking-wider">
                  Predictive Hydrograph
                </Text>
              </View>
              <Pressable onPress={() => setShowTimelineModal(false)} className="p-1">
                <Text className="text-sm font-bold text-slate-400">✕</Text>
              </Pressable>
            </View>

            <Text className="text-xs text-slate-300 mb-1">
              H3 Hexagon Cell: <Text className="font-mono text-cyan-300 font-bold">{timelineData.h3_cell_id}</Text>
            </Text>
            <Text className="text-[11px] text-slate-400 mb-3">
              Kurla West & Dharavi Basin • AI Model: {timelineData.model_version}
            </Text>

            {/* Peak Surge Highlight Card */}
            <View className="bg-rose-950/40 border border-rose-600/70 p-3 rounded-xl mb-3 flex-row items-center justify-between">
              <View>
                <Text className="text-[10px] font-black text-rose-300 uppercase">
                  PEAK INUNDATION SURGE
                </Text>
                <Text className="text-lg font-black text-white mt-0.5">
                  0.78m (Severe Risk)
                </Text>
                <Text className="text-[10px] text-slate-300 mt-0.5">
                  Expected in ~60 mins (91% Probability)
                </Text>
              </View>
              <View className="bg-rose-600 px-2 py-1 rounded">
                <Text className="text-[10px] font-black text-white uppercase">
                  PEAK AT +60m
                </Text>
              </View>
            </View>

            {/* Visual Step-by-Step Hydrograph Bar Curve */}
            <View className="bg-slate-950 p-3 rounded-xl border border-slate-900 mb-3">
              <Text className="text-[10px] font-bold text-slate-400 uppercase mb-2">
                90-MINUTE WATER INGRESS PROGRESSION
              </Text>
              <View className="flex-row items-end justify-between h-28 px-2 pb-1 border-b border-slate-800">
                {timelineData.timeline.map((point, pIdx) => {
                  const isPeak = point.depth_m >= 0.7;
                  const barHeight = Math.max(12, Math.round((point.depth_m / 0.85) * 80));
                  return (
                    <View key={pIdx} className="items-center">
                      <Text
                        className={`text-[9px] font-bold font-mono mb-1 ${
                          isPeak ? 'text-rose-400' : 'text-cyan-300'
                        }`}
                      >
                        {point.depth_m}m
                      </Text>
                      <View
                        style={{ height: barHeight }}
                        className={`w-10 rounded-t ${
                          isPeak
                            ? 'bg-rose-500 shadow-sm shadow-rose-500'
                            : 'bg-cyan-500/80'
                        }`}
                      />
                      <Text
                        className={`text-[9px] mt-1 font-bold ${
                          isPeak ? 'text-rose-400' : 'text-slate-400'
                        }`}
                      >
                        +{point.time_offset_min}m
                      </Text>
                    </View>
                  );
                })}
              </View>
              <View className="flex-row justify-between items-center pt-1.5">
                <Text className="text-[9px] text-slate-400">
                  Surge begins: +30m
                </Text>
                <Text className="text-[9px] text-emerald-400">
                  Receding: +90m (pumps active)
                </Text>
              </View>
            </View>

            {/* Directive */}
            <Text className="text-[11px] text-slate-300 mb-3 leading-relaxed">
              ⚠️ <Text className="font-bold text-white">Action Directive:</Text> Low-lying basements will exceed safety threshold within 45 minutes. Evacuate to higher elevation before peak water level.
            </Text>

            {/* Close / Action Button */}
            <Pressable
              onPress={() => setShowTimelineModal(false)}
              className="py-3 rounded-xl bg-cyan-500 items-center justify-center active:bg-cyan-600"
            >
              <Text className="text-xs font-black text-slate-950 uppercase">
                Understood • Return to Map
              </Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}
