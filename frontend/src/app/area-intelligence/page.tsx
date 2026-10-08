"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { propertiesApi, locationsApi } from "@/lib/api";
import type { Property, LiveNearbyResponse } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { ScoreCard } from "@/components/score-card";
import { NearbyFacilitiesPanel } from "@/components/nearby-facilities-panel";
import { PropertyListRow } from "@/components/property-list-row";
import { Brain, TrendingUp, Home, Building2, MapPin, Loader2 } from "lucide-react";

const NEARBY_CATEGORIES = [
  "hospitals",
  "schools",
  "restaurants",
  "hotels",
  "shopping_malls",
  "metro_stations",
  "bus_stops",
  "railway_stations",
] as const;

export default function AreaIntelligencePage() {
  const [cities, setCities] = useState<string[]>([]);
  const [localities, setLocalities] = useState<string[]>([]);
  const [selectedCity, setSelectedCity] = useState("");
  const [selectedLocality, setSelectedLocality] = useState("");
  const [properties, setProperties] = useState<Property[]>([]);
  const [nearbyFacilities, setNearbyFacilities] = useState<Partial<Record<string, LiveNearbyResponse>>>({});
  const [loading, setLoading] = useState(false);
  const [localitiesLoading, setLocalitiesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* ── Load cities once ── */
  useEffect(() => {
    propertiesApi.getCities().then(setCities).catch(() => setError("Failed to load cities"));
  }, []);

  /* ── Load localities when city changes ── */
  const handleCityChange = useCallback((city: string) => {
    setSelectedCity(city);
    setSelectedLocality("");
    setLocalities([]);
    if (!city) return;
    setLocalitiesLoading(true);
    propertiesApi
      .getLocalities(city)
      .then(setLocalities)
      .catch(() => setError("Failed to load localities"))
      .finally(() => setLocalitiesLoading(false));
  }, []);

  /* ── Fetch area data ── */
  const fetchAreaData = useCallback(async () => {
    if (!selectedCity || !selectedLocality) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await propertiesApi.list({
        city: selectedCity,
        locality: selectedLocality,
        page_size: 50,
      });
      setProperties(resp.properties);

      // Fetch nearby facilities if a geocoded property is available
      if (resp.properties.length > 0 && resp.properties[0].latitude && resp.properties[0].longitude) {
        const refId = resp.properties[0].id;
        const facilityData: Partial<Record<string, LiveNearbyResponse>> = {};
        await Promise.allSettled(
          NEARBY_CATEGORIES.map(async (cat) => {
            try {
              facilityData[cat] = await locationsApi.nearby(refId, cat, 3, "WALK");
            } catch {
              // gracefully degrade per category
            }
          }),
        );
        setNearbyFacilities(facilityData);
      }
    } catch {
      setError("Failed to load area data");
    } finally {
      setLoading(false);
    }
  }, [selectedCity, selectedLocality]);

  /* ── Sync URL params ── */
  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedCity) params.set("city", selectedCity);
    if (selectedLocality) params.set("locality", selectedLocality);
    window.history.replaceState({}, "", `/area-intelligence?${params.toString()}`);
  }, [selectedCity, selectedLocality]);

  /* ── Market snapshot ── */
  const marketSnapshot = useMemo(() => {
    if (properties.length === 0) return null;
    const prices = properties.map((p) => p.price).filter((p): p is number => p !== null && p !== undefined);
    const pricePerSqft = properties
      .map((p) => (p.price && p.area_sqft && p.area_sqft > 0 ? p.price / p.area_sqft : null))
      .filter((v): v is number => v !== null);
    const avgPrice = prices.length ? Math.round(prices.reduce((a, b) => a + b, 0) / prices.length) : 0;
    const avgPricePerSqft = pricePerSqft.length
      ? Math.round(pricePerSqft.reduce((a, b) => a + b, 0) / pricePerSqft.length)
      : 0;
    const sortedPrices = [...prices].sort((a, b) => a - b);
    const medianPrice = sortedPrices.length ? sortedPrices[Math.floor(sortedPrices.length / 2)] : 0;
    return {
      avgPrice,
      medianPrice,
      avgPricePerSqft,
      inventory: properties.length,
      propertyTypes: [...new Set(properties.map((p) => p.property_type).filter(Boolean))],
    };
  }, [properties]);

  /* ── Location scores (averaged across area properties) ── */
  const locationScores = useMemo(() => {
    if (properties.length === 0) return null;
    // These score fields don't exist on the Property type, so we cast and gracefully
    // handle their absence by defaulting to the overall score average.
    type ScoredProperty = Property & {
      overall_score?: number;
      value_score?: number;
      connectivity_score?: number;
      amenities_score?: number;
      growth_score?: number;
    };
    const scored = properties as ScoredProperty[];
    const scores = scored.map((p) => p.overall_score).filter((s): s is number => s != null);
    if (scores.length === 0) return null;
    const avg = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length);
    const min = Math.min(...scores);
    const max = Math.max(...scores);
    return {
      overall: avg,
      location: avg,
      value: Math.round(scored.reduce((a, b) => a + (b.value_score ?? avg), 0) / scored.length),
      connectivity: Math.round(scored.reduce((a, b) => a + (b.connectivity_score ?? avg), 0) / scored.length),
      amenities: Math.round(scored.reduce((a, b) => a + (b.amenities_score ?? avg), 0) / scored.length),
      growth: Math.round(scored.reduce((a, b) => a + (b.growth_score ?? avg), 0) / scored.length),
      range: `${min}–${max}`,
      sampleSize: scores.length,
    };
  }, [properties]);

  const formatINR = (n: number) => new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(n);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-foreground mb-2">Area Intelligence</h1>
        <p className="text-muted-foreground">
          Data-driven insights for any locality: pricing, infrastructure, and livability scores.
        </p>
      </div>

      {/* ── Search controls ── */}
      <Card className="rounded-2xl border-border/60 p-5 mb-6">
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-foreground mb-1.5">City</label>
            <Select
              value={selectedCity}
              onChange={(e) => handleCityChange(e.target.value)}
              className="w-full"
              placeholder="Select a city"
              options={cities.map((c) => ({ value: c, label: c }))}
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm font-medium text-foreground mb-1.5">Locality</label>
            <Select
              value={selectedLocality}
              onChange={(e) => setSelectedLocality(e.target.value)}
              disabled={!selectedCity || localitiesLoading || localities.length === 0}
              className="w-full"
              placeholder={
                localitiesLoading
                  ? "Loading…"
                  : localities.length === 0
                    ? selectedCity ? "No localities found" : "Select a city first"
                    : "Select a locality"
              }
              options={localities.map((l) => ({ value: l, label: l }))}
            />
          </div>
          <div className="flex items-end">
            <Button
              onClick={fetchAreaData}
              disabled={!selectedCity || !selectedLocality || loading}
            >
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Brain className="mr-2 h-4 w-4" />}
              Analyze
            </Button>
          </div>
        </div>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
      </Card>

      {/* ── Market Snapshot ── */}
      {marketSnapshot && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-foreground mb-4 flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-primary" />
            Market Snapshot
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Card className="rounded-2xl border-border/60 p-4">
              <p className="text-sm text-muted-foreground mb-1">Avg Price</p>
              <p className="text-2xl font-bold text-foreground">₹{formatINR(marketSnapshot.avgPrice / 1e7)} Cr</p>
            </Card>
            <Card className="rounded-2xl border-border/60 p-4">
              <p className="text-sm text-muted-foreground mb-1">Median Price</p>
              <p className="text-2xl font-bold text-foreground">₹{formatINR(marketSnapshot.medianPrice / 1e7)} Cr</p>
            </Card>
            <Card className="rounded-2xl border-border/60 p-4">
              <p className="text-sm text-muted-foreground mb-1">Avg ₹/sqft</p>
              <p className="text-2xl font-bold text-foreground">₹{formatINR(marketSnapshot.avgPricePerSqft)}</p>
            </Card>
            <Card className="rounded-2xl border-border/60 p-4">
              <p className="text-sm text-muted-foreground mb-1">Active Listings</p>
              <p className="text-2xl font-bold text-foreground">{marketSnapshot.inventory}</p>
            </Card>
          </div>
          {marketSnapshot.propertyTypes.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {marketSnapshot.propertyTypes.map((t) => (
                <Badge key={t} variant="secondary" className="capitalize">
                  {t}
                </Badge>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ── Location Scores ── */}
      {locationScores && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-foreground mb-4 flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            Location Scores{" "}
            <span className="text-sm font-normal text-muted-foreground">
              (based on {locationScores.sampleSize} properties)
            </span>
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-4">
            <ScoreCard
              label="Overall"
              value={locationScores.overall}
              max={100}
              showBar
              icon={<Brain className="h-4 w-4" />}
              className="lg:col-span-1"
            />
            <ScoreCard label="Location" value={locationScores.location} max={100} showBar icon={<MapPin className="h-4 w-4" />} />
            <ScoreCard label="Value" value={locationScores.value} max={100} showBar icon={<Building2 className="h-4 w-4" />} />
            <ScoreCard label="Connectivity" value={locationScores.connectivity} max={100} showBar icon={<TrendingUp className="h-4 w-4" />} />
            <ScoreCard label="Amenities" value={locationScores.amenities} max={100} showBar icon={<Home className="h-4 w-4" />} />
            <ScoreCard label="Growth" value={locationScores.growth} max={100} showBar icon={<TrendingUp className="h-4 w-4" />} />
            <Card className="rounded-2xl border-border/60 p-4 flex flex-col justify-center items-center text-center bg-primary/5">
              <p className="text-sm text-muted-foreground mb-1">Score Range</p>
              <p className="text-2xl font-bold text-primary">{locationScores.range}</p>
            </Card>
          </div>
        </section>
      )}

      {/* ── Infrastructure & Amenities ── */}
      {Object.keys(nearbyFacilities).length > 0 && (
        <section className="mb-8">
          <h2 className="text-xl font-semibold text-foreground mb-4 flex items-center gap-2">
            <Building2 className="h-5 w-5 text-primary" />
            Infrastructure & Amenities
          </h2>
          <NearbyFacilitiesPanel
            preloaded={nearbyFacilities}
            compact
            className="border border-border/60 rounded-2xl"
          />
        </section>
      )}

      {/* ── Property Listings ── */}
      {properties.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-foreground flex items-center gap-2">
              <Home className="h-5 w-5 text-primary" />
              Properties in {selectedLocality}, {selectedCity}
            </h2>
            <span className="text-sm text-muted-foreground">{properties.length} listings</span>
          </div>
          <div className="space-y-2">
            {properties.slice(0, 20).map((prop) => (
              <PropertyListRow key={prop.id} property={prop} showDistance={false} />
            ))}
          </div>
          {properties.length > 20 && (
            <p className="mt-4 text-sm text-muted-foreground text-center">
              Showing 20 of {properties.length} properties.{" "}
              <a
                href={`/search?city=${encodeURIComponent(selectedCity)}&locality=${encodeURIComponent(selectedLocality)}`}
                className="text-primary hover:underline"
              >
                View all
              </a>
            </p>
          )}
        </section>
      )}

      {/* ── Empty state ── */}
      {!selectedCity && (
        <Card className="rounded-2xl border-border/60 p-12 text-center">
          <Brain className="h-12 w-12 text-muted-foreground/30 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-foreground mb-2">Select a city and locality to begin</h3>
          <p className="text-muted-foreground">
            Choose from the dropdowns above to see market analytics, infrastructure data, and AI-powered location scores.
          </p>
        </Card>
      )}
    </div>
  );
}