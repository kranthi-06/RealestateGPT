"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import {
  MapPin,
  Building2,
  Search,
  Globe,
  Loader2,
  AlertCircle,
  Hospital,
  GraduationCap,
  UtensilsCrossed,
  ShoppingBag,
  TreePine,
  Landmark,
  Bus,
  BedDouble,
  Navigation,
  RefreshCw,
  LocateFixed,
} from "lucide-react";
import { propertiesApi, locationsApi } from "@/lib/api";
import type { LivePlace, Property } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { PropertyListRow } from "@/components/property-list-row";
import { RealEstateMap } from "@/components/real-estate-map";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** Facility categories, in display order. Keys map to backend valid values. */
const FACILITY_CATEGORIES = [
  { key: "hospital", label: "Hospitals & Clinics", icon: Hospital, color: "text-red-600", bg: "bg-red-50" },
  { key: "school", label: "Schools & Colleges", icon: GraduationCap, color: "text-blue-600", bg: "bg-blue-50" },
  { key: "restaurant", label: "Restaurants & Cafes", icon: UtensilsCrossed, color: "text-orange-600", bg: "bg-orange-50" },
  { key: "shopping", label: "Shopping & Supermarkets", icon: ShoppingBag, color: "text-pink-600", bg: "bg-pink-50" },
  { key: "bank", label: "Banks & ATMs", icon: Landmark, color: "text-indigo-600", bg: "bg-indigo-50" },
  { key: "public_transport", label: "Bus Stops & Transport", icon: Bus, color: "text-purple-600", bg: "bg-purple-50" },
  { key: "hotel", label: "Hotels & Accommodation", icon: BedDouble, color: "text-teal-600", bg: "bg-teal-50" },
  { key: "park", label: "Parks & Recreation", icon: TreePine, color: "text-green-600", bg: "bg-green-50" },
] as const;

type FacilityKey = (typeof FACILITY_CATEGORIES)[number]["key"];

/** A place plus the category it was fetched under. */
type CategorizedPlace = LivePlace & { categoryKey: FacilityKey; categoryLabel: string };

type GeocodeState = "idle" | "loading" | "ready" | "error";

function haversineKm(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(bLat - aLat);
  const dLng = toRad(bLng - aLng);
  const lat1 = toRad(aLat);
  const lat2 = toRad(bLat);
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

function formatDistance(km: number | null): string {
  if (km == null || !Number.isFinite(km)) return "—";
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(km < 10 ? 1 : 0)} km`;
}

type FacilityCategory = (typeof FACILITY_CATEGORIES)[number];

/** One nearby place as a card: name, category, address, distance, map button. */
function PlaceCard({
  place,
  category,
  origin,
}: {
  place: CategorizedPlace;
  category: FacilityCategory;
  origin: [number, number];
}) {
  const Icon = category.icon;
  const distanceKm =
    place.latitude != null && place.longitude != null
      ? haversineKm(origin[0], origin[1], place.latitude, place.longitude)
      : null;
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border/60 bg-card p-3 transition-colors hover:border-primary/40">
      <span
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
          category.bg,
          category.color
        )}
      >
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">{place.name}</p>
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {category.label}
        </p>
        {place.address && (
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{place.address}</p>
        )}
        <p className="mt-1 flex items-center gap-1 text-[11px] tabular-nums text-muted-foreground">
          <Navigation className="h-3 w-3" />
          {formatDistance(distanceKm)} from searched location
        </p>
      </div>
      {place.latitude != null && place.longitude != null && (
        <a
          href={`https://www.openstreetmap.org/directions?from=${origin[0]},${origin[1]}&to=${place.latitude},${place.longitude}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border border-border bg-background px-2.5 text-[11px] font-medium text-foreground transition-colors hover:bg-primary/5 hover:text-primary"
        >
          <MapPin className="h-3 w-3" />
          Map
        </a>
      )}
    </div>
  );
}

export default function ExploreClient() {
  const [query, setQuery] = useState("");
  const [geoState, setGeoState] = useState<GeocodeState>("idle");
  const [geoError, setGeoError] = useState<string | null>(null);
  const [resolvedLabel, setResolvedLabel] = useState<string | null>(null);
  const [center, setCenter] = useState<[number, number]>([22.5, 79.0]);
  const [zoom, setZoom] = useState(5);

  const [placesByCategory, setPlacesByCategory] = useState<Record<string, CategorizedPlace[]>>({});
  const [placesLoading, setPlacesLoading] = useState(false);
  const [placesError, setPlacesError] = useState<string | null>(null);

  const [properties, setProperties] = useState<Property[] | null>(null);
  const [propertiesLoading, setPropertiesLoading] = useState(false);

  const [selected, setSelected] = useState<FacilityKey | "all" | "verified">("all");
  const inputRef = useRef<HTMLInputElement>(null);

  /**
   * Places grouped by the category that found them, deduplicated once: a place
   * mapped in two categories (e.g. a mall that is also a supermarket) belongs
   * to the first category in display order. Every count in the UI — chips,
   * section headers and the "All" total — is derived from this, so they always
   * agree with the cards actually rendered.
   */
  const placesByCategoryDeduped = useMemo<Record<string, CategorizedPlace[]>>(() => {
    const grouped: Record<string, CategorizedPlace[]> = {};
    const seen = new Set<string>();
    for (const category of FACILITY_CATEGORIES) {
      for (const place of placesByCategory[category.key] ?? []) {
        const key = `${place.place_id ?? ""}|${place.name ?? ""}`.toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        (grouped[category.key] ??= []).push(place);
      }
    }
    return grouped;
  }, [placesByCategory]);

  const allPlaces = useMemo<CategorizedPlace[]>(
    () => FACILITY_CATEGORIES.flatMap((category) => placesByCategoryDeduped[category.key] ?? []),
    [placesByCategoryDeduped]
  );

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const category of FACILITY_CATEGORIES) {
      counts[category.key] = (placesByCategoryDeduped[category.key] ?? []).length;
    }
    return counts;
  }, [placesByCategoryDeduped]);

  const verifiedCount = properties?.length ?? 0;

  /** Categories that actually have results, in display order. */
  const activeCategories = useMemo(
    () => FACILITY_CATEGORIES.filter((category) => (categoryCounts[category.key] ?? 0) > 0),
    [categoryCounts]
  );

  /** Places visible for the current category selection. */
  const visiblePlaces = useMemo(() => {
    if (selected === "all") return allPlaces;
    if (selected === "verified") return [];
    return allPlaces.filter((place) => place.categoryKey === selected);
  }, [allPlaces, selected]);

  const mapMarkers = useMemo(() => {
    const markers: Array<{
      id: string | number;
      latitude: number;
      longitude: number;
      title: string;
      subtitle?: string;
      kind: "property" | "place" | "search";
      category?: string;
    }> = [];

    if (geoState === "ready") {
      markers.push({
        id: "search-location",
        latitude: center[0],
        longitude: center[1],
        title: resolvedLabel || "Searched location",
        subtitle: "Searched location",
        kind: "search",
        category: "Searched location",
      });
    }

    visiblePlaces.forEach((place, index) => {
      if (place.latitude == null || place.longitude == null) return;
      markers.push({
        id: `${place.categoryKey}-${place.place_id ?? place.name ?? index}`,
        latitude: place.latitude,
        longitude: place.longitude,
        title: place.name,
        subtitle: place.address ?? undefined,
        kind: "place",
        category: place.categoryLabel,
      });
    });

    if (selected === "all" || selected === "verified") {
      (properties ?? []).forEach((property) => {
        if (property.latitude == null || property.longitude == null) return;
        markers.push({
          id: `property-${property.id}`,
          latitude: property.latitude,
          longitude: property.longitude,
          title: property.title,
          subtitle: property.locality ?? property.city,
          kind: "property",
          category: "Verified property",
        });
      });
    }

    return markers;
  }, [geoState, center, resolvedLabel, visiblePlaces, properties, selected]);

  /**
   * Changes when the searched location or the category selection changes, so
   * the map refits to the relevant markers. It deliberately does NOT change
   * when individual results stream in: the map must stay centered on the
   * searched place instead of re-zooming on every arriving category.
   */
  const fitBoundsKey = useMemo(
    () => `${selected}:${center[0].toFixed(4)},${center[1].toFixed(4)}`,
    [selected, center]
  );

  const loadNearbyForLocation = useCallback(async (latitude: number, longitude: number) => {
    setPlacesLoading(true);
    setPlacesError(null);
    setPlacesByCategory({});

    try {
      // One combined Overpass query for every facility category: a single
      // request keeps the public instance from rate limiting the search, and
      // all category counts then come from the same successful fetch, so a
      // count can never read 0 because one category silently failed.
      const res = await locationsApi.nearbyMulti(
        latitude,
        longitude,
        FACILITY_CATEGORIES.map((category) => category.key),
        5
      );
      const next: Record<string, CategorizedPlace[]> = {};
      for (const category of FACILITY_CATEGORIES) {
        next[category.key] = (res.results?.[category.key] ?? []).map((place) => ({
          ...place,
          categoryKey: category.key,
          categoryLabel: category.label,
        }));
      }
      setPlacesByCategory(next);
    } catch {
      setPlacesByCategory({});
      setPlacesError(
        "OpenStreetMap could not return nearby facilities for this location right now. " +
          "The public Overpass service may be busy — try again in a moment."
      );
    }
    setPlacesLoading(false);
  }, []);

  const loadProperties = useCallback(async (latitude: number, longitude: number) => {
    setPropertiesLoading(true);
    try {
      // radius_km is required by the API whenever coordinates are supplied.
      const res = await propertiesApi.list({
        latitude,
        longitude,
        radius_km: 25,
        page_size: 30,
      });
      setProperties(res.properties);
    } catch {
      setProperties(null);
    } finally {
      setPropertiesLoading(false);
    }
  }, []);

  const runSearch = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text) {
        setGeoError("Type a city, locality, landmark, or address.");
        return;
      }
      setGeoState("loading");
      setGeoError(null);
      setPlacesByCategory({});
      setPlacesError(null);
      setProperties(null);

      try {
        const geo = await locationsApi.geocode(text);
        const nextCenter: [number, number] = [geo.latitude, geo.longitude];
        setCenter(nextCenter);
        setZoom(13);
        setResolvedLabel(geo.formatted_address || text);
        setGeoState("ready");

        // Facilities and listings load in parallel; neither blocks the map.
        void loadNearbyForLocation(geo.latitude, geo.longitude);
        void loadProperties(geo.latitude, geo.longitude);
      } catch (error) {
        setGeoState("error");
        setResolvedLabel(null);
        setGeoError(
          error instanceof Error
            ? `Could not find "${text}" on OpenStreetMap. Try a different city, locality, or address.`
            : `Could not geocode "${text}".`
        );
      }
    },
    [loadNearbyForLocation, loadProperties]
  );

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void runSearch(query);
  };

  const useMyLocation = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setGeoError("This browser does not support location access.");
      return;
    }
    setGeoState("loading");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        setCenter([lat, lng]);
        setZoom(14);
        setResolvedLabel(`${lat.toFixed(4)}, ${lng.toFixed(4)}`);
        setGeoState("ready");
        void loadNearbyForLocation(lat, lng);
        void loadProperties(lat, lng);
      },
      () => {
        setGeoState("error");
        setGeoError("Location access was denied. Search by city, locality, or address instead.");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
    );
  };

  const clear = () => {
    setQuery("");
    setGeoState("idle");
    setGeoError(null);
    setResolvedLabel(null);
    setPlacesByCategory({});
    setPlacesError(null);
    setProperties(null);
    setSelected("all");
    setCenter([22.5, 79.0]);
    setZoom(5);
    inputRef.current?.focus();
  };

  const filterTabs = [
    { key: "all" as const, label: "All", count: allPlaces.length + verifiedCount, icon: Globe },
    ...FACILITY_CATEGORIES.map((category) => ({
      key: category.key,
      label: category.label,
      count: categoryCounts[category.key] ?? 0,
      icon: category.icon,
    })),
    {
      key: "verified" as const,
      label: "Verified Properties",
      count: verifiedCount,
      icon: Building2,
    },
  ];

  return (
    <div className="page-shell py-6">
      <div className="mb-5">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Explore Map</h1>
        <p className="mt-1.5 text-muted-foreground">
          Search any city, locality, landmark, or address. Geocoded with OpenStreetMap Nominatim;
          nearby facilities come from Overpass and verified listings from our catalogue.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_1.05fr] xl:grid-cols-[1fr_1.15fr]">
        {/* ── Left: search, categories, listings ── */}
        <div className="space-y-5">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Globe className="h-4 w-4 text-primary" />
                Search Location
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <form onSubmit={onSubmit} className="flex flex-wrap gap-2">
                <Input
                  ref={inputRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="City, locality, landmark or address…"
                  className="h-11 flex-1"
                  disabled={geoState === "loading"}
                  autoFocus
                />
                <Button
                  type="submit"
                  disabled={geoState === "loading" || !query.trim()}
                  className="h-11 gap-1.5 px-4"
                >
                  {geoState === "loading" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Search className="h-4 w-4" />
                  )}
                  Search
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={useMyLocation}
                  disabled={geoState === "loading"}
                  className="h-11 gap-1.5"
                  title="Use my current location"
                >
                  <LocateFixed className="h-4 w-4" />
                  <span className="hidden sm:inline">Near me</span>
                </Button>
                {geoState !== "idle" && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={clear}
                    disabled={geoState === "loading"}
                    className="h-11"
                  >
                    Clear
                  </Button>
                )}
              </form>

              {geoError && (
                <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm text-destructive">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span className="text-xs">{geoError}</span>
                </div>
              )}

              {geoState === "ready" && (
                <div className="flex items-start gap-2 rounded-xl border border-emerald-200/70 bg-emerald-50/50 px-3 py-2.5">
                  <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-emerald-900">{resolvedLabel}</p>
                    <p className="text-[11px] tabular-nums text-emerald-800/80">
                      {center[0].toFixed(4)}, {center[1].toFixed(4)}
                      {placesLoading ? " · loading facilities…" : ` · ${allPlaces.length} nearby places`}
                    </p>
                  </div>
                </div>
              )}

              {placesError && (
                <div className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-200/70 bg-amber-50/50 px-3 py-2.5">
                  <AlertCircle className="h-4 w-4 shrink-0 text-amber-700" />
                  <span className="flex-1 text-xs text-amber-900">{placesError}</span>
                  <button
                    type="button"
                    onClick={() => void loadNearbyForLocation(center[0], center[1])}
                    disabled={placesLoading}
                    className="inline-flex h-7 shrink-0 items-center gap-1 rounded-lg border border-amber-300 bg-white px-2.5 text-[11px] font-medium text-amber-900 transition-colors hover:bg-amber-50 disabled:opacity-50"
                  >
                    {placesLoading ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3 w-3" />
                    )}
                    Retry
                  </button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Category filter chips */}
          {geoState === "ready" && (
            <div className="flex flex-wrap gap-2">
              {filterTabs.map((tab) => {
                const Icon = tab.icon;
                const active = selected === tab.key;
                return (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setSelected(tab.key)}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                      active
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground",
                      tab.count === 0 && !active && "opacity-50"
                    )}
                    aria-pressed={active}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {tab.label}
                    <span className="tabular-nums">({tab.count})</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Listings header */}
          {geoState === "ready" && (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-semibold text-foreground">
                {selected === "verified"
                  ? "Verified Properties"
                  : selected === "all"
                    ? "All nearby places"
                    : FACILITY_CATEGORIES.find((c) => c.key === selected)?.label}
                <span className="ml-1.5 text-sm font-normal tabular-nums text-muted-foreground">
                  {selected === "verified"
                    ? verifiedCount
                    : selected === "all"
                      ? allPlaces.length
                      : visiblePlaces.length}{" "}
                  result{visiblePlaces.length === 1 && selected !== "verified" ? "" : "s"}
                </span>
              </h2>
              {(placesLoading || propertiesLoading) && (
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Loading…
                </span>
              )}
            </div>
          )}

          {/* Place cards — grouped into category sections when viewing "All" */}
          {geoState === "ready" && selected !== "verified" && (
            <div className="space-y-4">
              {placesLoading && allPlaces.length === 0 ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-20 rounded-xl" />
                ))
              ) : selected === "all" ? (
                placesError && activeCategories.length === 0 ? (
                  <EmptyState
                    title="Nearby places could not be loaded"
                    description="OpenStreetMap did not answer this time. Use the Retry button above — the public Overpass service is often busy for a few seconds."
                  />
                ) : activeCategories.length === 0 ? (
                  <EmptyState
                    title="No nearby places found"
                    description="OpenStreetMap has no mapped facilities within 5 km of the searched location. Try a more specific locality or another city."
                  />
                ) : (
                  activeCategories.map((category) => {
                    const CategoryIcon = category.icon;
                    return (
                    <section key={category.key} className="space-y-2">
                      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                        <CategoryIcon className={cn("h-4 w-4", category.color)} />
                        {category.label}
                        <span className="text-xs font-normal tabular-nums text-muted-foreground">
                          ({categoryCounts[category.key] ?? 0})
                        </span>
                      </h3>
                      {(placesByCategoryDeduped[category.key] ?? []).map((place, index) => (
                        <PlaceCard
                          key={`${place.categoryKey}-${place.place_id ?? place.name ?? index}`}
                          place={place}
                          category={category}
                          origin={center}
                        />
                      ))}
                    </section>
                    );
                  })
                )
              ) : visiblePlaces.length === 0 ? (
                placesError ? (
                  <EmptyState
                    title="Nearby places could not be loaded"
                    description="OpenStreetMap did not answer this time. Use the Retry button above to try the facilities again."
                  />
                ) : (
                  <EmptyState
                    title="No places in this category"
                    description="OpenStreetMap has no mapped entries of this type within 5 km of the searched location. Try a wider search or another category."
                  />
                )
              ) : (
                <div className="space-y-2">
                  {visiblePlaces.map((place, index) => {
                    const category =
                      FACILITY_CATEGORIES.find((c) => c.key === place.categoryKey) ??
                      FACILITY_CATEGORIES[0];
                    return (
                      <PlaceCard
                        key={`${place.categoryKey}-${place.place_id ?? place.name ?? index}`}
                        place={place}
                        category={category}
                        origin={center}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Verified properties */}
          {geoState === "ready" && (selected === "verified" || selected === "all") && (
            <div className="space-y-2">
              {selected === "all" && (
                <h3 className="flex items-center gap-1.5 pt-1 text-sm font-semibold text-foreground">
                  <Building2 className="h-4 w-4 text-primary" />
                  Verified Properties
                  <span className="text-xs font-normal tabular-nums text-muted-foreground">
                    ({verifiedCount})
                  </span>
                </h3>
              )}
              {propertiesLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-24 rounded-xl" />
                ))
              ) : verifiedCount === 0 ? (
                <p className="rounded-xl border border-dashed border-border bg-muted/20 px-3 py-5 text-center text-xs text-muted-foreground">
                  No verified catalogue listings within 25 km of this location.
                </p>
              ) : (
                (properties ?? []).map((property) => (
                  <PropertyListRow key={property.id} property={property} showDistance={false} />
                ))
              )}
            </div>
          )}

          {geoState === "idle" && (
            <EmptyState
              title="Explore a city or landmark"
              description="Search a city, locality, landmark or address — or use your current location — to see nearby facilities and verified listings on the map."
            />
          )}
        </div>

        {/* ── Right: map ── */}
        <div className="lg:sticky lg:top-20 lg:self-start">
          <Card className="overflow-hidden">
            <CardHeader className="flex flex-row items-center justify-between gap-2 pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Building2 className="h-4 w-4 text-primary" />
                Map View
              </CardTitle>
              {geoState === "ready" && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 text-[11px] text-muted-foreground"
                  onClick={() => {
                    setZoom(13);
                  }}
                  title="Re-centre on the searched location"
                >
                  <RefreshCw className="h-3 w-3" />
                  Recentre
                </Button>
              )}
            </CardHeader>
            <CardContent className="p-0">
              <div className="h-[420px] lg:h-[520px]">
                <RealEstateMap
                  markers={mapMarkers}
                  center={center}
                  zoom={zoom}
                  fitBoundsKey={fitBoundsKey}
                />
              </div>
            </CardContent>
            <div className="flex flex-wrap items-center gap-3 border-t border-border/60 px-4 py-2.5 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-600" />
                Searched place
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-teal-700" />
                Facility ({visiblePlaces.length})
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rotate-45 rounded-bl-full rounded-br-full bg-[#3155a6]" />
                Verified property
              </span>
              <span className="ml-auto flex items-center gap-1">
                <MapPin className="h-3 w-3" />
                {center[0].toFixed(3)}, {center[1].toFixed(3)}
              </span>
            </div>
          </Card>

          {/* Legend / counts */}
          {geoState === "ready" && (
            <Card className="mt-3">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Nearby places by category</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-2 pt-0 sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4">
                {FACILITY_CATEGORIES.map((category) => {
                  const Icon = category.icon;
                  const count = categoryCounts[category.key] ?? 0;
                  const active = selected === category.key;
                  return (
                    <button
                      key={category.key}
                      type="button"
                      onClick={() => setSelected(active ? "all" : category.key)}
                      className={cn(
                        "flex flex-col items-start gap-1 rounded-xl border p-2.5 text-left transition-colors",
                        active
                          ? "border-primary bg-primary/5"
                          : "border-border/60 bg-background hover:border-primary/40"
                      )}
                    >
                      <Icon className={cn("h-4 w-4", category.color)} />
                      <span className="text-[11px] font-medium leading-tight text-foreground">
                        {category.label}
                      </span>
                      <span className="text-sm font-bold tabular-nums text-foreground">{count}</span>
                    </button>
                  );
                })}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
