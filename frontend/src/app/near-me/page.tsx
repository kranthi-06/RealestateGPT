"use client";

import { useMemo, useState, useCallback } from "react";
import {
  LocateFixed,
  LocateOff,
  Navigation,
  Loader2,
  Clock3,
  Sparkles,
  MapPin,
  Globe,
  XCircle,
} from "lucide-react";
import { searchApi, ApiError } from "@/lib/api";
import type { Property, WebDiscoveryCard as WebDiscoveryCardData } from "@/lib/types";
import WebDiscoveryCard from "@/components/web-discovery-card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import PropertyListRow from "@/components/property-list-row";
import { NearbyFacilitiesPanel } from "@/components/nearby-facilities-panel";
import { EmptyState } from "@/components/empty-state";
import { useAuth } from "@/lib/auth-context";
import Link from "next/link";

type LocState = "idle" | "pending" | "granted" | "denied" | "timeout" | "unsupported";

type LoadState = "idle" | "loading" | "ready" | "error";

function haversineKm(
  a: { lat: number; lng: number },
  b: { lat: number; lng: number }
): number {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

function stripDuplicates<T extends { url: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    if (seen.has(item.url)) continue;
    seen.add(item.url);
    out.push(item);
  }
  return out;
}

function NearMeCard({
  locState,
  userCoords,
  onRequest,
  onClear,
  onRefresh,
  radiusKm,
}: {
  locState: LocState;
  userCoords: { lat: number; lng: number } | null;
  onRequest: () => void;
  onClear: () => void;
  onRefresh?: () => void;
  radiusKm: number;
}) {
  if (locState === "granted" && userCoords) {
    return (
      <div className="flex flex-col gap-2 rounded-2xl border border-emerald-200/70 bg-emerald-50/60 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5 text-sm text-emerald-900">
          <LocateFixed className="h-4 w-4 shrink-0" />
          <span className="truncate">
            Searching near{" "}
            <span className="font-medium tabular-nums">
              {userCoords.lat.toFixed(4)}, {userCoords.lng.toFixed(4)}
            </span>
            <span className="text-emerald-700/70"> · within {radiusKm} km</span>
          </span>
        </div>
        <div className="flex gap-2">
          {onRefresh && (
            <Button
              variant="ghost"
              size="sm"
              className="h-8 rounded-lg text-xs"
              onClick={onRefresh}
            >
              Refresh
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-8 rounded-lg text-xs"
            onClick={onClear}
          >
            Reset location
          </Button>
        </div>
      </div>
    );
  }

  const messages: Partial<
    Record<
      LocState,
      { icon: typeof LocateOff; title: string; note: string; retry?: boolean }
    >
  > = {
    denied: {
      icon: LocateOff,
      title: "Location access was denied",
      note: "You can still search by city, locality, or address.",
    },
    timeout: {
      icon: Clock3,
      title: "Location request timed out",
      note: "Your browser did not respond in time. Retry, or continue with a manual search.",
      retry: true,
    },
    unsupported: {
      icon: LocateOff,
      title: "Location is not supported by this browser",
      note: "Use a city or locality to find properties near a place you know.",
    },
  };

  if (locState in messages) {
    const msg = messages[locState];
    const Icon = msg!.icon;
    return (
      <div className="rounded-2xl border border-amber-200/70 bg-amber-50/50 p-4">
        <div className="flex items-start gap-3">
          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-amber-900">{msg!.title}</p>
            <p className="mt-0.5 text-xs text-amber-800/80">{msg!.note}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {msg!.retry && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 rounded-lg text-xs"
                  onClick={onRequest}
                >
                  Retry location
                </Button>
              )}
              <Button
                asChild
                variant="outline"
                size="sm"
                className="h-8 rounded-lg text-xs"
              >
                <Link href="/search">Open search</Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Navigation className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground">Find properties near you</p>
          <p className="text-xs text-muted-foreground truncate">
            Allow location access to search within a {radiusKm} km radius. Results route
            through FastAPI — no keys live in the browser.
          </p>
        </div>
      </div>
      <Button
        size="sm"
        onClick={onRequest}
        disabled={locState === "pending"}
        className="shrink-0 rounded-lg"
      >
        {locState === "pending" ? (
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
        ) : (
          <LocateFixed className="mr-2 h-3.5 w-3.5" />
        )}
        {locState === "pending" ? "Requesting…" : "Use My Location"}
      </Button>
    </div>
  );
}

export default function NearMePage() {
  const { user } = useAuth();
  const RADIUS_KM = 5;
  const [locState, setLocState] = useState<LocState>("idle");
  const [userCoords, setUserCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | undefined>();
  const [properties, setProperties] = useState<Property[] | null>(null);
  const [compareIds, setCompareIds] = useState<Set<number>>(new Set());
  const [radiusKm, setRadiusKm] = useState<number>(RADIUS_KM);

  const [webResults, setWebResults] = useState<WebDiscoveryCardData[] | null>(null);
  const [webLoadState, setWebLoadState] = useState<LoadState>("idle");
  const [webError, setWebError] = useState<string | null>(null);

  const toggleCompare = (id: number) => {
    setCompareIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const propertiesWithDistance = useMemo(() => {
    if (!properties || !userCoords) return [];
    return properties
      .map((p) => {
        const hasCoords =
          typeof p.latitude === "number" && typeof p.longitude === "number";
        const distanceKm = hasCoords
          ? haversineKm(userCoords, { lat: p.latitude!, lng: p.longitude! })
          : undefined;
        return { property: p, distanceKm };
      })
      .sort((a, b) => {
        if (a.distanceKm == null && b.distanceKm == null) return 0;
        if (a.distanceKm == null) return 1;
        if (b.distanceKm == null) return -1;
        return a.distanceKm - b.distanceKm;
      });
  }, [properties, userCoords]);

  const nearestPropertyId =
    propertiesWithDistance[0]?.property?.id ??
    (properties && properties.length ? properties[0].id : undefined);

  const requestLocation = () => {
    if (!navigator.geolocation) {
      setLocState("unsupported");
      return;
    }
    setLocState("pending");
    setErrorMsg(undefined);
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const c = { lat: coords.latitude, lng: coords.longitude };
        setUserCoords(c);
        setLocState("granted");
        await Promise.all([runSearch(c.lat, c.lng), runWebSearch(c.lat, c.lng)]);
      },
      (err) => {
        if (err.code === 1) setLocState("denied");
        else if (err.code === 3) setLocState("timeout");
        else setLocState("denied");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
    );
  };

  const runSearch = async (lat: number, lng: number) => {
    setLoadState("loading");
    setErrorMsg(undefined);
    try {
      const res = await searchApi.nearMe({
        latitude: lat,
        longitude: lng,
        radius_km: radiusKm,
      });
      setProperties(res.properties ?? []);
      setLoadState("ready");
    } catch (caught) {
      setErrorMsg(
        caught instanceof ApiError
          ? caught.message
          : "We couldn't load nearby properties. Please try again."
      );
      setLoadState("error");
    }
  };

  const runWebSearch = async (lat: number, lng: number) => {
    setWebLoadState("loading");
    setWebError(null);
    try {
      const res = await searchApi.unified({
        query: "real estate properties and websites",
        location: { latitude: lat, longitude: lng, radius_km: radiusKm },
        include_web: true,
      });
      const cards: WebDiscoveryCardData[] = res.web_discoveries ?? [];
      setWebResults(stripDuplicates(cards));
      setWebLoadState("ready");
    } catch (caught) {
      setWebError(
        caught instanceof ApiError ? caught.message : "We couldn't load web results. Please try again."
      );
      setWebLoadState("error");
    }
  };

  const refresh = () => {
    if (userCoords) {
      runSearch(userCoords.lat, userCoords.lng);
      runWebSearch(userCoords.lat, userCoords.lng);
    } else {
      requestLocation();
    }
  };

  const clearLocation = () => {
    setLocState("idle");
    setUserCoords(null);
    setProperties(null);
    setLoadState("idle");
    setErrorMsg(undefined);
    setCompareIds(new Set());
    setWebResults(null);
    setWebLoadState("idle");
    setWebError(null);
  };



  return (
    <main className="page-shell animate-fade-in">
      <section className="mb-5 pt-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <Badge
              variant="outline"
              className="mb-2 gap-1.5 border-emerald-200 bg-emerald-50 text-emerald-700"
            >
              <Sparkles className="h-3 w-3" />
              Proximity intelligence
            </Badge>
            <h1 className="section-title text-3xl sm:text-4xl">Properties & facilities near you</h1>
            <p className="section-subtitle mt-2 max-w-2xl">
              Browser location → FastAPI geospatial search → real MongoDB inventory.
              Distance is calculated locally from returned coordinates.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <MapPin className="h-3.5 w-3.5" />
            <span>Search radius</span>
            <select
              className="ml-1 rounded-md border border-border bg-background px-2 py-1 text-xs"
              value={radiusKm}
              onChange={(e) => {
                const v = Number(e.target.value);
                setRadiusKm(v);
                if (userCoords) runSearch(userCoords.lat, userCoords.lng);
              }}
              disabled={!userCoords || loadState === "loading"}
            >
              <option value={2}>2 km</option>
              <option value={5}>5 km</option>
              <option value={10}>10 km</option>
              <option value={20}>20 km</option>
            </select>
          </div>
        </div>

        <div className="mt-5">
          <NearMeCard
            locState={locState}
            userCoords={userCoords}
            onRequest={requestLocation}
            onClear={clearLocation}
            onRefresh={userCoords ? refresh : undefined}
            radiusKm={radiusKm}
          />
        </div>

        {errorMsg && loadState === "error" && (
          <p
            role="alert"
            className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {errorMsg}
          </p>
        )}
      </section>

      {loadState === "loading" && (
        <section className="grid gap-4 lg:grid-cols-[1.25fr_0.95fr]">
          <div className="space-y-3">
            <Skeleton className="h-6 w-48" />
            {Array.from({ length: 5 }).map((_, i) => (
              <Card key={i}>
                <CardContent className="p-4">
                  <div className="flex gap-4">
                    <Skeleton className="h-24 w-24 shrink-0 rounded-lg" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-4 w-2/3" />
                      <Skeleton className="h-3 w-1/2" />
                      <Skeleton className="h-3 w-1/3" />
                      <div className="flex gap-2 pt-1">
                        <Skeleton className="h-5 w-16 rounded-full" />
                        <Skeleton className="h-5 w-14 rounded-full" />
                        <Skeleton className="h-5 w-20 rounded-full" />
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card className="h-fit">
            <CardHeader>
              <Skeleton className="h-5 w-40" />
            </CardHeader>
            <CardContent className="space-y-2">
              <Skeleton className="h-8 w-full" />
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-lg" />
              ))}
            </CardContent>
          </Card>
        </section>
      )}

      {loadState === "ready" && (
        <>
          {compareIds.size > 0 && (
            <div className="sticky bottom-4 z-30 mx-auto mb-4 flex w-full max-w-3xl items-center justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50/80 px-4 py-3 shadow-lg backdrop-blur animate-slide-up">
              <div className="text-sm">
                <span className="font-semibold text-emerald-900">
                  {compareIds.size} propert{compareIds.size === 1 ? "y" : "ies"}
                </span>
                <span className="text-emerald-800/70"> selected for comparison</span>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 rounded-lg text-xs"
                  onClick={() => setCompareIds(new Set())}
                >
                  Clear
                </Button>
                <Button
                  asChild
                  size="sm"
                  className="h-8 rounded-lg"
                  disabled={compareIds.size < 2}
                >
                  <Link
                    href={`/compare?ids=${Array.from(compareIds)
                      .slice(0, 4)
                      .join(",")}`}
                  >
                    Compare
                  </Link>
                </Button>
              </div>
            </div>
          )}

          <section className="grid gap-6 lg:grid-cols-[1.25fr_0.95fr]">
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-lg font-semibold tracking-tight">
                  Properties Near You
                  <span className="ml-2 text-sm font-normal text-muted-foreground">
                    {propertiesWithDistance.length} result
                    {propertiesWithDistance.length === 1 ? "" : "s"}
                  </span>
                </h2>
                <div className="flex items-center gap-1 text-xs text-muted-foreground tabular-nums">
                  <Navigation className="h-3 w-3" />
                  nearest first
                </div>
              </div>

              {propertiesWithDistance.length === 0 ? (
                <EmptyState
                  title="No verified properties within this radius"
                  description="Try a wider radius or switch to manual city-based search."
                  actionLabel="Open search"
                  actionHref="/search"
                />
              ) : (
                <div className="space-y-3">
                  {propertiesWithDistance.map(({ property, distanceKm }) => (
                    <PropertyListRow
                      key={property.id}
                      property={property}
                      showDistance
                      distanceKm={distanceKm}
                      showCompare
                      showSave={!!user}
                      isCompareSelected={compareIds.has(property.id)}
                      onCompareToggle={toggleCompare}
                    />
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-6">
              <Card className="overflow-hidden">
                <CardHeader className="flex flex-row items-center justify-between gap-2 p-4 pb-2">
                  <div>
                    <CardTitle className="text-sm font-semibold">
                      Search summary
                    </CardTitle>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Grounded in FastAPI + MongoDB geospatial
                    </p>
                  </div>
                  <Badge variant="outline" className="text-[10px]">
                    radius {radiusKm} km
                  </Badge>
                </CardHeader>
                <CardContent className="grid grid-cols-3 gap-3 p-4 pt-2 text-center">
                  <div className="rounded-xl border border-border bg-background p-3">
                    <div className="text-2xl font-semibold tracking-tight tabular-nums">
                      {propertiesWithDistance.length}
                    </div>
                    <div className="mt-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                      Properties
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-background p-3">
                    <div className="text-2xl font-semibold tracking-tight tabular-nums">
                      {propertiesWithDistance[0]?.distanceKm != null
                        ? propertiesWithDistance[0].distanceKm < 1
                          ? `${Math.round(propertiesWithDistance[0].distanceKm * 1000)}m`
                          : propertiesWithDistance[0].distanceKm.toFixed(1)
                        : "—"}
                    </div>
                    <div className="mt-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                      Nearest
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-background p-3">
                    <div className="text-2xl font-semibold tracking-tight tabular-nums">
                      8
                    </div>
                    <div className="mt-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                      Facility types
                    </div>
                  </div>
                </CardContent>
              </Card>

              {nearestPropertyId != null ? (
                <NearbyFacilitiesPanel
                  propertyId={nearestPropertyId}
                  radiusKm={radiusKm}
                  compact
                />
              ) : (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm font-semibold">
                      Nearby Facilities
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="rounded-lg border border-dashed border-border bg-background px-3 py-6 text-center text-xs text-muted-foreground">
                      Allow location and return at least one property to view nearby
                      Schools, Hospitals, Restaurants, Transport, and more.
                    </p>
                  </CardContent>
                </Card>
              )}

              {nearestPropertyId != null && (
                <Card className="border-emerald-200/60 bg-emerald-50/30">
                  <CardHeader className="p-4 pb-2">
                    <CardTitle className="flex items-center gap-1.5 text-sm font-semibold text-emerald-900">
                      <Sparkles className="h-3.5 w-3.5" />
                      AI area note
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-4 pt-2 text-xs leading-relaxed text-emerald-900/80">
                    This panel is anchored to the nearest returned property for an
                    honest, server-side-only facilities lookup. Switch to a specific
                    property details page for a tailored AI analysis including price
                    intelligence, value score, and personalised recommendation.
                    <div className="mt-3 flex gap-2">
                      <Button asChild size="sm" variant="outline" className="h-8 rounded-lg text-xs">
                        <Link href={`/properties/${nearestPropertyId}`}>
                          View nearest property
                        </Link>
                      </Button>
                      <Button asChild size="sm" variant="ghost" className="h-8 rounded-lg text-xs">
                        <Link href="/assistant">Ask AI assistant</Link>
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </section>
        </>
      )}
          {/* Web discovery results (Near Me only — never duplicated on Explore) */}
      {loadState === "ready" && properties && (
        <section className="mt-6 border-t border-border/60">
          <div className="flex items-center gap-2 px-1 py-3">
            <Sparkles className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">Web results near you</h2>
            <span className="ml-auto text-xs text-muted-foreground">
              {webLoadState === "ready" ? "Powered by Tavily (server-side)" : "Click to search the web"}
            </span>
          </div>
          <div className="bg-card rounded-xl border border-border/60 p-4">
            {webResults && webResults.length > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {webResults.map((card) => (
                  <WebDiscoveryCard
                    key={card.id || card.url}
                    discovery={card}
                  />
                ))}
              </div>
            ) : webLoadState === "ready" ? (
              <EmptyState
                title="No web results found"
                description="No independent web sources matched your location yet. Try a city-based search or refine your query."
                actionLabel="Browse search"
                actionHref="/search"
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                Allow location access, then search to see web results near you.
              </p>
            )}
          </div>
        </section>
      )}
</main>
  );
}
