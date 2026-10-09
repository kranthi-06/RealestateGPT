"use client";

import dynamic from "next/dynamic";

export type MapMarker = {
  id: string | number;
  latitude?: number | null;
  longitude?: number | null;
  title: string;
  subtitle?: string;
  kind?: "property" | "place" | "search";
  /** Category label shown in the marker popup. */
  category?: string;
};

const OpenStreetMapCanvas = dynamic(
  () => import("@/components/openstreetmap-canvas"),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-[300px] items-center justify-center rounded-xl border border-dashed bg-muted/30 text-sm text-muted-foreground">
        Loading OpenStreetMap…
      </div>
    ),
  },
);

export function RealEstateMap({
  markers,
  center,
  zoom,
  fitBoundsKey,
}: {
  markers: MapMarker[];
  center?: [number, number];
  zoom?: number;
  fitBoundsKey?: string;
}) {
  return (
    <OpenStreetMapCanvas
      markers={markers}
      center={center ?? [20.5937, 78.9629]}
      zoom={zoom ?? 5}
      fitBoundsKey={fitBoundsKey}
    />
  );
}
