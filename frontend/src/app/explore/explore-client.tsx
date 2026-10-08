"use client";

import { useEffect, useState } from "react";
import { MapPin, Building2, Search } from "lucide-react";
import { propertiesApi } from "@/lib/api";
import type { Property } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { PropertyListRow } from "@/components/property-list-row";
import { RealEstateMap } from "@/components/real-estate-map";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";

export default function ExploreClient() {
  const [cities, setCities] = useState<string[]>([]);
  const [selectedCity, setSelectedCity] = useState("");
  const [properties, setProperties] = useState<Property[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    propertiesApi
      .getCities()
      .then((c) => { if (!cancelled) setCities(c); })
      .catch(() => { if (!cancelled) setError("Failed to load cities"); });
    return () => { cancelled = true; };
  }, []);

  const loadCity = async (city: string) => {
    setSelectedCity(city);
    if (!city) {
      setProperties(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await propertiesApi.list({ city, page_size: 30 });
      setProperties(res.properties);
    } catch {
      setError("Failed to load properties for this city");
      setProperties(null);
    } finally {
      setLoading(false);
    }
  };

  const mapMarkers = (properties ?? []).map((p) => ({
    id: p.id,
    latitude: p.latitude ?? null,
    longitude: p.longitude ?? null,
    title: p.title,
    subtitle: p.locality ?? p.city,
    kind: "property" as const,
  }));

  return (
    <div className="grid gap-6 lg:grid-cols-[1.25fr_0.95fr]">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <MapPin className="h-4 w-4 text-primary" />
              Explore by city
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Select
              value={selectedCity}
              onChange={(e) => loadCity(e.target.value)}
              placeholder="Select a city"
              options={cities.map((c) => ({ value: c, label: c }))}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            {loading && (
              <div className="space-y-2">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-16 w-full rounded-lg" />
                <Skeleton className="h-16 w-full rounded-lg" />
              </div>
            )}
            {!loading && properties && properties.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No verified properties found in {selectedCity}.
              </p>
            )}
          </CardContent>
        </Card>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold tracking-tight">
              Listings
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {properties?.length ?? 0} result{(properties?.length ?? 0) === 1 ? "" : "s"}
              </span>
            </h2>
          </div>

          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
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
              title="Explore a city"
              description="Pick a city from the dropdown to browse verified listings, maps, and nearby intelligence."
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
              Map view
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="h-[420px]">
              <RealEstateMap markers={mapMarkers} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Search className="h-4 w-4 text-primary" />
              What you get
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground space-y-2">
            <p>Verified listings plotted on an OpenStreetMap canvas.</p>
            <p>Jump to any property detail page for price intelligence, AI analysis, and nearby facilities.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}