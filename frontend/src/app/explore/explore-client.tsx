"use client";

import { useState, useCallback, useMemo } from "react";
import { MapPin, Building2, Search, Globe, Loader2, AlertCircle } from "lucide-react";
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

export default function ExploreClient() {
  const [query, setQuery] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [geocoding, setGeocoding] = useState(false);
  const [geocodeError, setGeocodeError] = useState<string | null>(null);
  const [places, setPlaces] = useState<LivePlace[]>([]);
  const [placesLoading, setPlacesLoading] = useState(false);
  const [properties, setProperties] = useState<Property[] | null>(null);
  const [loading, setLoading] = useState(false);

  const mapMarkers = useMemo(() => {
    const all: Array<{ id: number; latitude: number; longitude: number; title: string; subtitle: string; kind: "property" | "place" }> = [];
    (properties ?? []).forEach((p) => {
      if (typeof p.latitude === "number" && typeof p.longitude === "number") {
        all.push({ id: p.id, latitude: p.latitude, longitude: p.longitude, title: p.title, subtitle: p.locality ?? p.city, kind: "property" });
      }
    });
    places.forEach((pl, idx) => {
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
  }, [properties, places]);

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
      const res = await locationsApi.nearbyCoordinates(latitude, longitude, "hospital", 5);
      setPlaces(res.places ?? []);
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

  const handleSubmit = (e: React.FormEvent) => { e.preventDefault(); geocodePlace(query); };

  const clear = () => {
    setQuery("");
    setCoords(null);
    setPlaces([]);
    setProperties(null);
    setGeocodeError(null);
    setLoading(false);
  };



  return (
    <div className="grid gap-6 lg:grid-cols-[1.25fr_0.95fr]">
      <div className="space-y-4">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Globe className="h-4 w-4 text-primary" /> Explore any place</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <form onSubmit={handleSubmit} className="flex gap-2">
              <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Type any city, neighbourhood, or address... e.g. Nandyal, Hyderabad, Banjara Hills" className="flex-1" disabled={geocoding} autoFocus />
              <Button type="submit" disabled={geocoding || !query.trim()} aria-label="Search location">{geocoding ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPin className="h-4 w-4" />}</Button>
              {coords && <Button variant="outline" size="sm" onClick={clear} disabled={loading}>Clear</Button>}
            </form>
            {geocodeError && <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" /><span className="text-xs">{geocodeError}</span></div>}
            {coords && !geocoding && <div className="flex items-start gap-2 rounded-xl border border-emerald-200/70 bg-emerald-50/50 px-3 py-3"><MapPin className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" /><div className="min-w-0"><p className="text-xs font-medium text-emerald-900">{coords.lat.toFixed(4)}, {coords.lng.toFixed(4)}</p><p className="text-xs text-emerald-800/80">{places.length > 0 ? "Nearby places loaded" : "No nearby places found"}</p></div></div>}
            {placesLoading && <div className="space-y-2"><Skeleton className="h-4 w-40" /><Skeleton className="h-16 w-full rounded-lg" /></div>}
          </CardContent>
        </Card>
        <div className="space-y-3">
          <div className="flex items-center justify-between"><h2>Listings<span className="ml-2 text-sm font-normal text-muted-foreground">{properties?.length ?? 0} result{(properties?.length ?? 0) === 1 ? "" : "s"}</span></h2></div>
          {loading ? <div className="space-y-3">{[...Array(4)].map((_, i) => <Card key={i}><CardContent className="p-4"><div className="flex gap-4"><Skeleton className="h-24 w-24 shrink-0 rounded-lg" /><div className="flex-1 space-y-2"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-3 w-1/2" /><Skeleton className="h-3 w-1/3" /></div></div></CardContent></Card>)}</div> : properties && properties.length > 0 ? <div className="space-y-3">{properties.map((property) => <PropertyListRow key={property.id} property={property} />)}</div> : <EmptyState title="Explore a city or landmark" description={coords ? "No verified properties found nearby. Try a different location or drop back to a named city." : "Type any city or landmark and press Enter to see verified listings, maps, and nearby intelligence plotted on OpenStreetMap."} actionLabel="Browse search" actionHref="/search" />}
        </div>
      </div>
      <div className="space-y-6">
        <Card className="overflow-hidden"><CardHeader><CardTitle className="flex items-center gap-2 text-base"><Building2 className="h-4 w-4 text-primary" /> Map view</CardTitle></CardHeader><CardContent className="p-0"><div className="h-[420px]"><RealEstateMap markers={mapMarkers} /></div></CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2 text-base"><Search className="h-4 w-4 text-primary" /> Near you</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground space-y-2">
          {places.length === 0 ? <p>No nearby places found.</p> : <ul className="space-y-1.5">{places.map((pl) => <li key={pl.place_id ?? pl.name}><Link href={`/search?city=${encodeURIComponent(pl.name)}`} className="flex items-center gap-2 rounded-lg border border-border/60 bg-background px-3 py-2 hover:bg-primary/5 transition-colors"><MapPin className="h-3.5 w-3.5 shrink-0 text-primary" /><div className="min-w-0"><p className="text-xs font-medium text-foreground truncate">{pl.name}</p><p className="text-[11px] text-muted-foreground truncate">{pl.address || "Location"}</p></div></Link></li>)}</ul>}
        </CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2 text-base"><Search className="h-4 w-4 text-primary" /> How it works</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground space-y-2"><p>Type any city, neighbourhood, or address - no dropdown required.</p><p>Free-text geocoding routes through OpenStreetMap (Nominatim) + backend.</p><p>Verified listings, maps, and nearby intelligence all render on an OpenStreetMap canvas.</p><p>Jump to any property detail page for price intelligence, AI analysis, and nearby facilities.</p></CardContent></Card>
      </div>
    </div>
  );
}
