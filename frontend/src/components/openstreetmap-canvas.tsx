"use client";

import { useEffect, useMemo } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, ZoomControl, useMap } from "react-leaflet";
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

const searchIcon = L.divIcon({
  className: "",
  html: '<span aria-hidden="true" style="display:block;width:22px;height:22px;border-radius:50%;background:#16a34a;border:3px solid white;box-shadow:0 0 0 6px rgba(22,163,74,.25),0 2px 8px #14532d66"></span>',
  iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -11],
});

/**
 * Imperative map control.
 *
 * react-leaflet only reads ``center``/``zoom`` when the MapContainer mounts, so
 * changing them as props does nothing. This component applies them explicitly
 * and fits the bounds to the markers when asked.
 */
function MapController({
  center,
  zoom,
  markers,
  fitBoundsKey,
}: {
  center: [number, number];
  zoom: number;
  markers: (MapMarker & { latitude: number; longitude: number })[];
  fitBoundsKey: string;
}) {
  const map = useMap();

  // Centre/zoom the map on the searched place.
  useEffect(() => {
    map.setView(center, zoom, { animate: true });
    // Invalidate size because the container can be resized by layout changes.
    map.invalidateSize();
  }, [map, center, zoom]);

  // Fit all visible markers (searched place + facilities + properties).
  useEffect(() => {
    if (!fitBoundsKey || markers.length < 2) return;
    const bounds = L.latLngBounds(markers.map((m) => [m.latitude, m.longitude]));
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
    }
  }, [map, markers, fitBoundsKey]);

  return null;
}

export default function OpenStreetMapCanvas({
  markers,
  center,
  zoom,
  fitBoundsKey,
}: {
  markers: MapMarker[];
  center: [number, number];
  zoom: number;
  /** Changes whenever the result set changes and the map should refit. */
  fitBoundsKey?: string;
}) {
  const validMarkers = useMemo(
    () =>
      markers.filter(
        (marker): marker is MapMarker & { latitude: number; longitude: number } =>
          marker.latitude != null && marker.longitude != null,
      ),
    [markers],
  );

  // Keep the container height stable so Leaflet never renders a 0px map.
  return (
    <div className="h-full w-full overflow-hidden rounded-xl border border-border/70">
      <MapContainer
        center={center}
        zoom={zoom}
        zoomControl={false}
        className="h-full w-full"
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ZoomControl position="bottomright" />
        <MapController
          center={center}
          zoom={zoom}
          markers={validMarkers}
          fitBoundsKey={fitBoundsKey ?? ""}
        />
        {validMarkers.map((marker) => (
          <Marker
            key={`${marker.kind ?? "property"}-${marker.id}`}
            position={[marker.latitude, marker.longitude]}
            icon={
              marker.kind === "place"
                ? placeIcon
                : marker.kind === "search"
                  ? searchIcon
                  : propertyIcon
            }
          >
            <Popup>
              <div className="min-w-[160px]">
                <strong className="block text-sm">{marker.title}</strong>
                {marker.category && (
                  <span className="mt-0.5 inline-block rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                    {marker.category}
                  </span>
                )}
                {marker.subtitle && (
                  <span className="mt-1 block text-xs text-muted-foreground">{marker.subtitle}</span>
                )}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
