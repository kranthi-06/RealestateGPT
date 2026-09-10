"use client";

import { useEffect, useRef, useState } from "react";
import { MapPin } from "lucide-react";

type Marker = {
  id: number;
  latitude?: number | null;
  longitude?: number | null;
  title: string;
};

type MapCenter = { lat: number; lng: number };
type GoogleMap = object;
type GoogleMapConstructor = new (
  element: HTMLElement,
  options: { center: MapCenter; zoom: number; mapId: string }
) => GoogleMap;
type AdvancedMarkerConstructor = new (options: {
  map: GoogleMap;
  position: MapCenter;
  title: string;
}) => object;

interface GoogleMapsApi {
  importLibrary(library: "maps"): Promise<{ Map: GoogleMapConstructor }>;
  importLibrary(library: "marker"): Promise<{
    AdvancedMarkerElement: AdvancedMarkerConstructor;
  }>;
}

declare global {
  interface Window {
    google?: { maps: GoogleMapsApi };
  }
}

type MapState = "loading" | "ready" | "unavailable" | "error";

const mapsApiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY;
let mapsLoadPromise: Promise<void> | undefined;

function loadGoogleMaps(): Promise<void> {
  if (window.google?.maps) return Promise.resolve();
  if (mapsLoadPromise) return mapsLoadPromise;

  mapsLoadPromise = new Promise((resolve, reject) => {
    const existingScript = document.querySelector<HTMLScriptElement>(
      'script[data-realestate-gpt-maps="true"]'
    );
    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(), { once: true });
      existingScript.addEventListener("error", () => reject(new Error("Map script failed")), {
        once: true,
      });
      return;
    }

    const script = document.createElement("script");
    script.dataset.realestateGptMaps = "true";
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(mapsApiKey ?? "")}&v=weekly`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Map script failed"));
    document.head.appendChild(script);
  });

  return mapsLoadPromise;
}

export function RealEstateMap({ markers }: { markers: Marker[] }) {
  const element = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<MapState>(() =>
    mapsApiKey ? "loading" : "unavailable"
  );

  useEffect(() => {
    if (!mapsApiKey) return;

    let active = true;
    const validMarkers = markers.filter(
      (marker): marker is Marker & { latitude: number; longitude: number } =>
        marker.latitude != null && marker.longitude != null
    );

    const initialise = async () => {
      try {
        await loadGoogleMaps();
        const host = element.current;
        const googleMaps = window.google?.maps;
        if (!active || !host || !googleMaps) return;

        const { Map } = await googleMaps.importLibrary("maps");
        const { AdvancedMarkerElement } = await googleMaps.importLibrary("marker");
        if (!active) return;

        const center = validMarkers[0]
          ? { lat: validMarkers[0].latitude, lng: validMarkers[0].longitude }
          : { lat: 20.5937, lng: 78.9629 };
        const map = new Map(host, {
          center,
          zoom: validMarkers.length ? 13 : 5,
          mapId: "REAL_ESTATE_GPT",
        });

        validMarkers.forEach((marker) => {
          new AdvancedMarkerElement({
            map,
            position: { lat: marker.latitude, lng: marker.longitude },
            title: marker.title,
          });
        });
        if (active) setState("ready");
      } catch {
        if (active) setState("error");
      }
    };

    void initialise();
    return () => {
      active = false;
    };
  }, [markers]);

  const statusMessage =
    state === "loading"
      ? "Loading Google Maps…"
      : state === "unavailable"
        ? "Google Maps integration is not configured."
        : "Location map is temporarily unavailable.";

  return (
    <div className="relative h-64 overflow-hidden rounded-xl">
      <div ref={element} className="h-full w-full" />
      {state !== "ready" && (
        <div className="absolute inset-0 flex items-center justify-center border border-dashed bg-muted/30 text-center text-sm text-muted-foreground">
          <div>
            <MapPin className="mx-auto mb-2 size-6" />
            {statusMessage}
          </div>
        </div>
      )}
    </div>
  );
}
