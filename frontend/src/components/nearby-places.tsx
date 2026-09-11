"use client";

import { useEffect, useState } from "react";
import {
  Bike, Car, HeartPulse, Loader2, MapPinned, ShoppingBasket, TrainFront,
  School, Trees, BriefcaseBusiness, Footprints,
} from "lucide-react";
import { locationsApi } from "@/lib/api";
import type { LiveNearbyResponse, LivePlace, MapProviderStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";

const categories = [
  { key: "metro", label: "Metro", Icon: TrainFront },
  { key: "hospital", label: "Hospitals", Icon: HeartPulse },
  { key: "school", label: "Schools", Icon: School },
  { key: "supermarket", label: "Groceries", Icon: ShoppingBasket },
  { key: "it_park", label: "IT parks", Icon: BriefcaseBusiness },
  { key: "park", label: "Parks", Icon: Trees },
];
const travelModes = [
  { key: "DRIVE", label: "Drive", Icon: Car },
  { key: "WALK", label: "Walk", Icon: Footprints },
  { key: "BICYCLE", label: "Cycle", Icon: Bike },
];

export function NearbyPlaces({ propertyId, onPlacesChange }: { propertyId: number; onPlacesChange?: (places: LivePlace[]) => void }) {
  const [status, setStatus] = useState<MapProviderStatus>();
  const [selected, setSelected] = useState<LiveNearbyResponse>();
  const [category, setCategory] = useState("metro");
  const [travelMode, setTravelMode] = useState("WALK");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    let active = true;
    locationsApi.status().then((value) => {
      if (active) setStatus(value);
    }).catch(() => {
      if (active) setError("Location intelligence is temporarily unavailable.");
    });
    return () => { active = false; };
  }, []);

  const load = async (nextCategory = category, nextTravelMode = travelMode) => {
    setCategory(nextCategory);
    setTravelMode(nextTravelMode);
    setError(undefined);
    setLoading(true);
    try {
      const response = await locationsApi.nearby(propertyId, nextCategory, 3, nextTravelMode);
      setSelected(response);
      onPlacesChange?.(response.places);
    } catch (caught) {
      onPlacesChange?.([]);
      setSelected(undefined);
      setError(caught instanceof Error ? caught.message : "Location intelligence is temporarily unavailable.");
    } finally {
      setLoading(false);
    }
  };

  if (status && !status.configured) {
    return <p className="text-sm text-muted-foreground">Live OpenStreetMap location services are not configured.</p>;
  }

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {categories.map(({ key, label, Icon }) => (
          <Button key={key} variant={category === key ? "default" : "outline"} size="sm" disabled={loading} onClick={() => void load(key)}>
            <Icon className="mr-1.5 size-3.5" />{label}
          </Button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>Route mode:</span>
        {travelModes.map(({ key, label, Icon }) => (
          <Button key={key} variant={travelMode === key ? "secondary" : "ghost"} size="sm" disabled={loading} onClick={() => void load(category, key)}>
            <Icon className="mr-1 size-3.5" />{label}
          </Button>
        ))}
      </div>
      {!selected && !loading && !error && <p className="mt-4 text-sm text-muted-foreground">Choose a category to find current nearby places and calculated routes.</p>}
      {loading && <div className="mt-5 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />Finding nearby places and routes…</div>}
      {error && <p className="mt-4 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}
      {selected && !loading && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {selected.places.map((place) => (
            <article key={place.place_id || place.name} className="rounded-xl border border-border/70 bg-card p-3.5">
              <div className="flex gap-3">
                <MapPinned className="mt-0.5 size-4 shrink-0 text-primary" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2"><h3 className="text-sm font-semibold leading-5">{place.name}</h3>{place.maps_url && <a href={place.maps_url} target="_blank" rel="noreferrer" className="shrink-0 text-xs font-semibold text-primary hover:underline">Map</a>}</div>
                  {place.address && <p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{place.address}</p>}
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                    {place.distance_km != null && <span>{place.distance_km.toFixed(1)} km</span>}
                    {place.travel_minutes != null && <span>{Math.round(place.travel_minutes)} min {place.travel_mode?.toLowerCase()}</span>}
                  </div>
                </div>
              </div>
            </article>
          ))}
          {selected.places.length === 0 && <p className="text-sm text-muted-foreground">No matching places were returned within this radius.</p>}
        </div>
      )}
      {selected && <p className="mt-4 text-xs text-muted-foreground">Places from OpenStreetMap via Overpass. Distance and travel time are calculated by OSRM; no live traffic data is included.</p>}
    </div>
  );
}
