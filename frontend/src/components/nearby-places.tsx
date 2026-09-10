"use client";
import { useEffect, useState } from "react";
import { HeartPulse, School, TrainFront } from "lucide-react";
import { locationsApi } from "@/lib/api";
import type { LiveNearbyResponse, MapProviderStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";

const categories = [{ key: "metro", label: "Metro", Icon: TrainFront }, { key: "hospital", label: "Healthcare", Icon: HeartPulse }, { key: "school", label: "Education", Icon: School }];
export function NearbyPlaces({ propertyId }: { propertyId: number }) {
  const [status, setStatus] = useState<MapProviderStatus>(); const [selected, setSelected] = useState<LiveNearbyResponse>(); const [error, setError] = useState<string>();
  useEffect(() => { void locationsApi.status().then(setStatus).catch(() => setError("Location intelligence temporarily unavailable.")); }, []);
  const load = async (category: string) => { setError(undefined); try { setSelected(await locationsApi.nearby(propertyId, category)); } catch { setError("Location intelligence temporarily unavailable. Try again later."); } };
  if (status && !status.configured) return <p className="text-sm text-muted-foreground">Google Maps integration is not configured. Nearby live places are unavailable.</p>;
  return <div><div className="flex flex-wrap gap-2">{categories.map(({ key, label, Icon }) => <Button key={key} variant="outline" size="sm" onClick={() => load(key)}><Icon className="mr-1 size-3.5" />{label}</Button>)}</div>{error && <p className="mt-3 text-sm text-destructive">{error}</p>}{selected && <div className="mt-4 space-y-2">{selected.places.map((place) => <a key={place.place_id || place.name} href={place.maps_url} target="_blank" rel="noreferrer" className="flex items-center justify-between rounded-lg border p-3 text-sm hover:border-primary"><span><b>{place.name}</b>{place.address ? ` · ${place.address}` : ""}</span><span>{place.rating ? `★ ${place.rating}` : "Google Maps"}</span></a>)}{selected.places.length === 0 && <p className="text-sm text-muted-foreground">No matching places found.</p>}</div>}</div>;
}
