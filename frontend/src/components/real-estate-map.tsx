"use client";

import dynamic from "next/dynamic";

export type MapMarker = {
  id: string | number;
  latitude?: number | null;
  longitude?: number | null;
  title: string;
  subtitle?: string;
  kind?: "property" | "place";
};

const OpenStreetMapCanvas = dynamic(
  () => import("@/components/openstreetmap-canvas"),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-64 items-center justify-center rounded-xl border border-dashed bg-muted/30 text-sm text-muted-foreground">
        Loading OpenStreetMap…
      </div>
    ),
  },
);

export function RealEstateMap({
  markers,
  center,
  zoom,
}: {
  markers: MapMarker[];
  center?: [number, number];
  zoom?: number;
}) {
  return <OpenStreetMapCanvas markers={markers} center={center ?? [20.5937, 78.9629]} zoom={zoom ?? 5} />;
}
