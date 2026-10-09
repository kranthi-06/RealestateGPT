"use client";

import { useState, useCallback, useMemo, useRef } from "react";
import { MapPin, Building2, Search, Globe, Loader2, AlertCircle, Hospital, GraduationCap, UtensilsCrossed, TrainFront, ShoppingBag, TreePine } from "lucide-react";
import { propertiesApi, locationsApi } from "@/lib/api";
import type { Property, LivePlace } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { PropertyListRow } from "@/components/property-list-row";
import { RealEstateMap } from "@/components/real-estate-map";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import Link from "next/link";

const FACILITY_CATEGORIES = [
  { key: "hospital", label: "Hospitals", icon: Hospital, color: "text-red-600" },
  { key: "school", label: "Schools", icon: GraduationCap, color: "text-blue-600" },
  { key: "restaurant", label: "Restaurants", icon: UtensilsCrossed, color: "text-orange-600" },
  { key: "metro", label: "Metro/Transport", icon: TrainFront, color: "text-purple-600" },
  { key: "mall", label: "Shopping", icon: ShoppingBag, color: "text-pink-600" },
  { key: "park", label: "Parks", icon: TreePine, color: "text-green-600" },
] as const;

type FacilityCategory = (typeof FACILITY_CATEGORIES)[number]["key"];

export default function ExploreClient() {
  const [query, setQuery] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [geocoding, setGeocoding] = useState(false);
  const [geocodeError, setGeocodeError] = useState<string | null>(null);
  const [places, setPlaces] = useState<LivePlace[]>([]);
  const [placesLoading, setPlacesLoading] = useState(false);
  const [properties, setProperties] = useState<Property[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<FacilityCategory | "all">("all");
  const [mapCenter, setMapCenter] = useState<[number, number]>([20.5937, 78.9629]);
  const [mapZoom, setMapZoom] = useState(5);
  const inputRef = useRef<HTMLInputElement>(null);

  const mapMarkers = useMemo(() => {
    const all: Array<{ id: number; latitude: number; longitude: number; title: string; subtitle: string; kind: "property" | "place" }> = [];
    (properties ?? []).forEach((p) => {
      if (typeof p.latitude === "number" && typeof p.longitude === "number") {
        all.push({ id: p.id, latitude: p.latitude, longitude: p.longitude, title: p.title, subtitle: p.locality ?? p.city, kind: "property" });
      }
    });
    const filteredPlaces = selectedCategory === "all"
      ? places
      : places.filter((p) => p.categories?.includes(selectedCategory));
    filteredPlaces.forEach((pl, idx) => {
      all.push({
        id: pl.place_id ? Number(pl.place_id.slice(-8)) : 900000 + idx,
        latitude: pl.latitude ?? 0,
        longitude: pl.longitude ?? 0,
        title: pl.name,
        subtitle: pl.address ?? pl.name,
        kind: "place",
      });
    });
    return all;
  }, [properties, places, selectedCategory]);

  const loadPropertiesForLocation = useCallback(async (latitude: number, longitude: number) => {
    setLoading(true);
    try {
      const res = await propertiesApi.list({ latitude, longitude, page_size: 30 });
      setProperties(res.properties);
    } catch {
      setProperties(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadNearbyPlaces = useCallback(async (latitude: number, longitude: number) => {
    setPlacesLoading(true);
    try {
      const results = await Promise.allSettled(
        FACILITY_CATEGORIES.map(async (cat) => {
          try {
            const res = await locationsApi.nearbyCoordinates(latitude, longitude, cat.key, 5);
            return { category: cat.key, places: res.places ?? [] };
          } catch {
            return { category: cat.key, places: [] };
          }
        })
      );
      const allPlaces: LivePlace[] = [];
      results.forEach((result) => {
        if (result.status === "fulfilled") {
          allPlaces.push(...result.value.places);
        }
      });
      setPlaces(allPlaces);
    } catch {
      setPlaces([]);
    } finally {
      setPlacesLoading(false);
    }
  }, []);

  const geocodePlace = useCallback(async (text: string) => {
    if (!text.trim()) {
      setCoords(null);
      setPlaces([]);
      setProperties(null);
      setGeocodeError(null);
      return;
    }
    setGeocoding(true);
    setGeocodeError(null);
    setPlaces([]);
    setProperties(null);
    try {
      const geoData = await locationsApi.geocode(text.trim());
      const c = { lat: geoData.latitude, lng: geoData.longitude };
      setCoords(c);
      setMapCenter([c.lat, c.lng]);
      setMapZoom(13);
      setGeocodeError(null);
      await Promise.all([
        loadPropertiesForLocation(c.lat, c.lng),
        loadNearbyPlaces(c.lat, c.lng),
      ]);
    } catch (e) {
      setGeocodeError(e instanceof Error ? e.message : `Could not geocode "${text.trim()}".`);
      setCoords(null);
      setPlaces([]);
      setProperties(null);
    } finally {
      setGeocoding(false);
    }
  }, [loadPropertiesForLocation, loadNearbyPlaces]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    geocodePlace(query);
  };

  const clear = () => {
    setQuery("");
    setCoords(null);
    setPlaces([]);
    setProperties(null);
    setGeocodeError(null);
    setLoading(false);
    setMapCenter([20.5937, 78.9629]);
    setMapZoom(5);
    inputRef.current?.focus();
  };

  const filteredPlaces = useMemo(() => {
    if (selectedCategory === "all") return places;
    return places.filter((p) => p.categories?.includes(selectedCategory));
  }, [places, selectedCategory]);

  return (
    <div className="page-shell py-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-foreground">Explore Map</h1>
        <p className="mt-2 text-muted-foreground">
          Search any city, locality, landmark, or address. Geocoded via OpenStreetMap Nominatim.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.25fr_0.95fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Globe className="h-4 w-4 text-primary" />
                Search Location
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={handleSubmit} className="flex gap-2">
                <Input
                  ref={inputRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Type any city, neighbourhood, or address... e.g. Nandyal, Hyderabad, Banjara Hills"
                  className="flex-1"
                  disabled={geocoding}
                  autoFocus
                />
                <Button type="submit" disabled={geocoding || !query.trim()} aria-label="Search location">
                  {geocoding ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPin className="h-4 w-4" />}
                </Button>
                {coords && <Button variant="outline" size="sm" onClick={clear} disabled={loading}>Clear</Button>}
              </form>
              {geocodeError && (
                <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span className="text-xs">{geocodeError}</span>
                </div>
              )}
              {coords && !geocoding && (
                <div className="flex items-start gap-2 rounded-xl border border-emerald-200/70 bg-emerald-50/50 px-3 py-3">
                  <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-emerald-900">
                      {coords.lat.toFixed(4)}, {coords.lng.toFixed(4)}
                    </p>
                    <p className="text-xs text-emerald-800/80">
                      {places.length > 0 ? `${places.length} nearby places found` : "No nearby places found"}
                      {properties ? ` · ${properties.length} properties` : ""}
                    </p>
                  </div>
                </div>
              )}
              {placesLoading && (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-16 w-full rounded-lg" />
                </div>
              )}
            </CardContent>
          </Card>

          {/* Facility Category Filter */}
          {places.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setSelectedCategory("all")}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                  selectedCategory === "all"
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border bg-card text-muted-foreground hover:border-primary/40"
                }`}
              >
                All ({places.length})
              </button>
              {FACILITY_CATEGORIES.map((cat) => {
                const count = places.filter((p) => p.categories?.includes(cat.key)).length;
                if (count === 0) return null;
                const Icon = cat.icon;
                return (
                  <button
                    key={cat.key}
                    type="button"
                    onClick={() => setSelectedCategory(cat.key)}
                    className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                      selectedCategory === cat.key
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-card text-muted-foreground hover:border-primary/40"
                    }`}
                  >
                    <Icon className={`h-3.5 w-3.5 ${cat.color}`} />
                    {cat.label} ({count})
                  </button>
                );
              })}
            </div>
          )}

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">
                Listings
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  {properties?.length ?? 0} result{(properties?.length ?? 0) === 1 ? "" : "s"}
                </span>
              </h2>
            </div>
            {loading ? (
              <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                  <Card key={i}>
                    <CardContent className="p-4">
                      <div className="flex gap-4">
                        <Skeleton className="h-24 w-24 shrink-0 rounded-lg" />
                        <div className="flex-1 space-y-2">
                          <Skeleton className="h-4 w-2/3" />
                          <Skeleton className="h-3 w-1/2" />
                          <Skeleton className="h-3 w-1/3" />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : properties && properties.length > 0 ? (
              <div className="space-y-3">
                {properties.map((property) => (
                  <PropertyListRow key={property.id} property={property} />
                ))}
              </div>
            ) : (
              <EmptyState
                title="Explore a city or landmark"
                description={coords ? "No verified properties found nearby. Try a different location." : "Type any city or landmark and press Enter to see verified listings, maps, and nearby intelligence plotted on OpenStreetMap."}
                actionLabel="Browse search"
                actionHref="/search"
              />
            )}
          </div>
        </div>

        <div className="space-y-6">
          <Card className="overflow-hidden">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Building2 className="h-4 w-4 text-primary" />
                Map View
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="h-[420px]">
                <RealEstateMap markers={mapMarkers} center={mapCenter} zoom={mapZoom} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Search className="h-4 w-4 text-primary" />
                Nearby Places
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground space-y-2">
              {filteredPlaces.length === 0 ? (
                <p>No nearby places found.</p>
              ) : (
                <ul className="space-y-1.5">
                  {filteredPlaces.slice(0, 15).map((pl) => (
                    <li key={pl.place_id ?? pl.name}>
                      <Link
                        href={`/search?city=${encodeURIComponent(pl.name)}`}
                        className="flex items-center gap-2 rounded-lg border border-border/60 bg-background px-3 py-2 hover:bg-primary/5 transition-colors"
                      >
                        <MapPin className="h-3.5 w-3.5 shrink-0 text-primary" />
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-foreground truncate">{pl.name}</p>
                          <p className="text-[11px] text-muted-foreground truncate">{pl.address || "Location"}</p>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
