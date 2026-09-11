"use client";

import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, ZoomControl } from "react-leaflet";
import type { MapMarker } from "@/components/real-estate-map";

const propertyIcon = L.divIcon({
  className: "",
  html: '<span aria-hidden="true" style="display:block;width:30px;height:30px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:#3155a6;border:3px solid white;box-shadow:0 2px 8px #16254d66"></span>',
  iconSize: [30, 30], iconAnchor: [15, 30], popupAnchor: [0, -28],
});

const placeIcon = L.divIcon({
  className: "",
  html: '<span aria-hidden="true" style="display:block;width:16px;height:16px;border-radius:50%;background:#0f766e;border:2px solid white;box-shadow:0 1px 5px #134e4a66"></span>',
  iconSize: [16, 16], iconAnchor: [8, 8], popupAnchor: [0, -8],
});

export default function OpenStreetMapCanvas({ markers }: { markers: MapMarker[] }) {
  const validMarkers = markers.filter(
    (marker): marker is MapMarker & { latitude: number; longitude: number } =>
      marker.latitude != null && marker.longitude != null,
  );
  const center: [number, number] = validMarkers[0]
    ? [validMarkers[0].latitude, validMarkers[0].longitude]
    : [20.5937, 78.9629];

  return (
    <div className="h-64 overflow-hidden rounded-xl border border-border/70">
      <MapContainer center={center} zoom={validMarkers.length ? 13 : 5} zoomControl={false} className="h-full w-full" scrollWheelZoom>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ZoomControl position="bottomright" />
        {validMarkers.map((marker) => (
          <Marker key={`${marker.kind ?? "property"}-${marker.id}`} position={[marker.latitude, marker.longitude]} icon={marker.kind === "place" ? placeIcon : propertyIcon}>
            <Popup>
              <strong>{marker.title}</strong>{marker.subtitle ? <><br />{marker.subtitle}</> : null}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
