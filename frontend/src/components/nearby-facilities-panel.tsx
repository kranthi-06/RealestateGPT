"use client";

import { useEffect, useState } from "react";
import {
  School,
  Hospital,
  Hotel,
  UtensilsCrossed,
  ShoppingCart,
  Landmark,
  Trees,
  Bus,
  Star,
  MapPin,
  Navigation,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { LiveNearbyResponse, LivePlace } from "@/lib/types";
import { locationsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

const CATEGORIES = [
  { key: "school", label: "Schools", Icon: School },
  { key: "hospital", label: "Hospitals", Icon: Hospital },
  { key: "hotel", label: "Hotels", Icon: Hotel },
  { key: "restaurant", label: "Restaurants", Icon: UtensilsCrossed },
  { key: "supermarket", label: "Supermarkets", Icon: ShoppingCart },
  { key: "bank", label: "Banks", Icon: Landmark },
  { key: "park", label: "Parks", Icon: Trees },
  { key: "public_transport", label: "Transport", Icon: Bus },
] as const;

type CategoryKey = (typeof CATEGORIES)[number]["key"];

interface NearbyFacilitiesPanelProps {
  propertyId?: number;
  latitude?: number;
  longitude?: number;
  radiusKm?: number;
  preloaded?: Partial<Record<CategoryKey, LiveNearbyResponse>>;
  className?: string;
  compact?: boolean;
}

function PlaceRow({ place, distanceKm }: { place: LivePlace; distanceKm?: number }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-border bg-background p-3 transition-colors hover:bg-accent/30">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <h4 className="truncate text-sm font-medium text-foreground">{place.name}</h4>
          {place.rating != null && (
            <Badge variant="outline" className="gap-1 px-1.5 py-0 text-[10px]">
              <Star className="h-2.5 w-2.5 fill-amber-400 text-amber-400" />
              <span className="tabular-nums">{place.rating.toFixed(1)}</span>
            </Badge>
          )}
        </div>
        {place.address && (
          <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-muted-foreground">
            <MapPin className="h-3 w-3 shrink-0" />
            <span className="truncate">{place.address}</span>
          </p>
        )}
      </div>
      {distanceKm != null && (
        <Badge variant="secondary" className="shrink-0 gap-1">
          <Navigation className="h-3 w-3" />
          {distanceKm < 1
            ? `${Math.round(distanceKm * 1000)} m`
            : `${distanceKm.toFixed(1)} km`}
        </Badge>
      )}
    </div>
  );
}

function CategoryContent({
  data,
  loading,
  error,
  radiusKm,
}: {
  data?: LiveNearbyResponse;
  loading: boolean;
  error?: string;
  radiusKm: number;
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-border p-3">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="mt-2 h-3 w-1/2" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <p className="rounded-lg border border-dashed border-border bg-background px-3 py-6 text-center text-xs text-muted-foreground">
        Could not load nearby places. {error}
      </p>
    );
  }

  const places = data?.places ?? [];
  if (places.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border bg-background px-3 py-6 text-center text-xs text-muted-foreground">
        No places found within {radiusKm} km.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {places.slice(0, 8).map((p, i) => (
        <PlaceRow
          key={`${p.place_id ?? p.name}-${i}`}
          place={p}
          distanceKm={(p as LivePlace & { distance_km?: number }).distance_km}
        />
      ))}
      <p className="pt-1 text-right text-[11px] text-muted-foreground">
        Source: {data?.source ?? "locations API"} · sample {places.length}
      </p>
    </div>
  );
}

export function NearbyFacilitiesPanel({
  propertyId,
  radiusKm = 3,
  preloaded,
  className,
  compact = false,
}: NearbyFacilitiesPanelProps) {
  const [active, setActive] = useState<CategoryKey>("school");
  const [results, setResults] = useState<Partial<Record<CategoryKey, LiveNearbyResponse>>>(
    preloaded ?? {}
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | undefined>();

  useEffect(() => {
    if (!propertyId) return;
    if (results[active]) return;
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      setLoading(true);
      setError(undefined);
    });
    locationsApi
      .nearby(propertyId, active, radiusKm)
      .then((res) => {
        if (cancelled) return;
        setResults((prev) => ({ ...prev, [active]: res }));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message ?? "Request failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active, propertyId, radiusKm, results]);

  return (
    <Card className={cn(className)}>
      <CardHeader className={cn("flex flex-row items-center justify-between gap-2", compact && "p-4 pb-2")}>
        <CardTitle className={cn("text-sm font-semibold", compact && "text-base")}>
          Nearby Facilities
        </CardTitle>
        <Badge variant="outline" className="text-[10px]">
          within {radiusKm} km
        </Badge>
      </CardHeader>
      <CardContent className={compact ? "p-4 pt-0" : "p-6 pt-0"}>
        <Tabs
          value={active}
          onValueChange={(v) => setActive(v as CategoryKey)}
          className="w-full"
        >
          <TabsList variant="line" className="mb-3 h-auto w-full flex-wrap gap-0 rounded-none border-b border-border p-0">
            {CATEGORIES.map(({ key, label, Icon }) => (
              <TabsTrigger
                key={key}
                value={key}
                className="h-8 flex-none flex-1 basis-auto gap-1 px-3 text-xs"
              >
                <Icon className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{label}</span>
              </TabsTrigger>
            ))}
          </TabsList>
          {CATEGORIES.map(({ key }) => (
            <TabsContent key={key} value={key}>
              <CategoryContent
                data={results[key]}
                loading={loading && !results[key]}
                error={error}
                radiusKm={radiusKm}
              />
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  );
}

export { CATEGORIES as FACILITY_CATEGORIES };
export type { CategoryKey as FacilityCategoryKey };
export default NearbyFacilitiesPanel;
