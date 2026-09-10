import * as Location from "expo-location";
export async function requestCurrentLocation() {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (!permission.granted) return null;
  const point = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.Balanced,
  });
  return {
    latitude: point.coords.latitude,
    longitude: point.coords.longitude,
    accuracy: point.coords.accuracy,
    timestamp: point.timestamp,
  };
}
