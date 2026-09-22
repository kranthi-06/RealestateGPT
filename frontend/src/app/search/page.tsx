"use client";

import { useState, useEffect, useCallback, Suspense, useRef } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import PropertyCard from "@/components/property-card";
import WebDiscoveryCard from "@/components/web-discovery-card";
import { ApiError, searchApi } from "@/lib/api";
import { Search, SlidersHorizontal, MapPin, Building2, Loader2, Navigation, LocateFixed, LocateOff, Clock3, Command, Sparkles, Globe2 } from "lucide-react";
import type { SearchFilters, SearchSectionsResponse, Property, SearchIntent, UnifiedSearchResponse } from "@/lib/types";
/* Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Near-Me permission UX (explicit, honest) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */
type LocState = "idle" | "pending" | "granted" | "denied" | "timeout" | "unsupported";

function NearMeCard({
  locState,
  userCoords,
  onRequest,
  onClear,
}: {
  locState: LocState;
  userCoords: { lat: number; lng: number } | null;
  onRequest: () => void;
  onClear: () => void;
}) {
  if (locState === "granted" && userCoords) {
    return (
      <div className="flex items-center justify-between gap-4 rounded-xl border border-emerald-200/70 bg-emerald-50/60 px-4 py-3">
        <div className="flex items-center gap-2.5 text-sm text-emerald-900">
          <LocateFixed className="h-4 w-4" />
          <span>
            Searching near{" "}
            <span className="font-medium">
              {userCoords.lat.toFixed(4)}, {userCoords.lng.toFixed(4)}
            </span>
            <span className="text-emerald-700/70"> Ã‚Â· within 5 km</span>
          </span>
        </div>
        <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={onClear}>
          Use manual search
        </Button>
      </div>
    );
  }

  const messages: Partial<
    Record<LocState, { icon: typeof LocateOff; title: string; note: string }>
  > = {
    denied: {
      icon: LocateOff,
      title: "Location access was denied",
      note: "You can still search by city, locality, or address. Your location is never used unless you allow it.",
    },
    timeout: {
      icon: Clock3,
      title: "Location request timed out",
      note: "Your browser did not respond in time. Retry, or continue with a manual search.",
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
      <div className="rounded-xl border border-amber-200/70 bg-amber-50/50 px-4 py-3">
        <div className="flex items-start gap-3">
          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
          <div>
            <p className="text-sm font-medium text-amber-900">{msg!.title}</p>
            <p className="mt-0.5 text-xs text-amber-800/80">{msg!.note}</p>
            {locState === "timeout" && (
              <Button variant="outline" size="sm" className="mt-2 h-8 text-xs" onClick={onRequest}>
                Retry location
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border/60 bg-card/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Navigation className="h-4 w-4" />
        </span>
        <div>
          <p className="text-sm font-medium text-foreground">Find properties near you</p>
          <p className="text-xs text-muted-foreground">
            Allow location access to search within a radius of your current position.
          </p>
        </div>
      </div>
      <Button size="sm" onClick={onRequest} disabled={locState === "pending"} className="shrink-0 rounded-lg">
        {locState === "pending" ? (
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
        ) : (
          <LocateFixed className="mr-2 h-3.5 w-3.5" />
        )}
        {locState === "pending" ? "RequestingÃ¢â‚¬Â¦" : "Allow location"}
      </Button>
    </div>
  );
}

/* ---- Intent chips (from /search/parse when the backend exposes it) ---- */

function IntentChips({ intent }: { intent: SearchIntent | null }) {
  if (!intent) return null;
  const chips: string[] = [];
  if (intent.listing_type === "rent") chips.push("Rent");
  if (intent.listing_type === "sale") chips.push("Buy");
  if (intent.bedrooms != null) chips.push(`${intent.bedrooms} BHK`);
  if (intent.max_price != null) {
    const lakh = intent.max_price / 100000;
    chips.push(`Under Ã¢â€šÂ¹${lakh % 1 === 0 ? lakh.toFixed(0) : lakh.toFixed(1)}L`);
  }
  if (intent.min_price != null) chips.push("Premium");
  if (intent.city) chips.push(intent.city);
  if (intent.locality) chips.push(intent.locality);
  if (intent.property_type) chips.push(intent.property_type);
  if (intent.nearby_requirements?.length) {
    intent.nearby_requirements.forEach((req) => chips.push(`Near ${req.type.replace("_", " ")}`));
  }
  if (chips.length === 0) return null;
  return (
    <div className="mb-5 flex flex-wrap items-center gap-2" aria-label="Interpreted search">
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Command className="h-3 w-3" /> Interpreted
      </span>
      {chips.map((chip) => (
        <Badge key={chip} variant="secondary" className="rounded-md bg-primary/5 text-xs font-medium text-foreground">
          {chip}
        </Badge>
      ))}
    </div>
  );
}

/* Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Filter controls (desktop bar + mobile drawer share this) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */

function FilterControls({
  filters,
  onChange,
}: {
  filters: SearchFilters;
  onChange: (patch: Partial<SearchFilters>) => void;
}) {
  const bedrooms = filters.bedrooms ?? "";
  const listingType = filters.listing_type ?? "";
  const furnishing = filters.furnishing ?? "";
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
      <label className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Listing</span>
        <select
          value={listingType}
          onChange={(e) => onChange({ listing_type: e.target.value })}
          className="h-9 rounded-lg border border-border bg-card px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          <option value="">Any</option>
          <option value="sale">Buy</option>
          <option value="rent">Rent</option>
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Bedrooms</span>
        <select
          value={String(bedrooms)}
          onChange={(e) => onChange({ bedrooms: e.target.value ? Number(e.target.value) : undefined })}
          className="h-9 rounded-lg border border-border bg-card px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          <option value="">Any</option>
          <option value="1">1 BHK</option>
          <option value="2">2 BHK</option>
          <option value="3">3 BHK</option>
          <option value="4">4+ BHK</option>
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Max budget</span>
        <select
          value={filters.max_price ? String(filters.max_price) : ""}
          onChange={(e) => onChange({ max_price: e.target.value ? Number(e.target.value) : undefined })}
          className="h-9 rounded-lg border border-border bg-card px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          <option value="">Any</option>
          <option value="5000000">Ã¢â€šÂ¹50 L</option>
          <option value="7500000">Ã¢â€šÂ¹75 L</option>
          <option value="10000000">Ã¢â€šÂ¹1 Cr</option>
          <option value="15000000">Ã¢â€šÂ¹1.5 Cr</option>
          <option value="25000000">Ã¢â€šÂ¹2.5 Cr</option>
          <option value="50000000">Ã¢â€šÂ¹5 Cr</option>
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Furnishing</span>
        <select
          value={furnishing}
          onChange={(e) => onChange({ furnishing: e.target.value })}
          className="h-9 rounded-lg border border-border bg-card px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          <option value="">Any</option>
          <option value="furnished">Furnished</option>
          <option value="semi-furnished">Semi-furnished</option>
          <option value="unfurnished">Unfurnished</option>
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Bathrooms</span>
        <select
          value={filters.bathrooms ? String(filters.bathrooms) : ""}
          onChange={(e) => onChange({ bathrooms: e.target.value ? Number(e.target.value) : undefined })}
          className="h-9 rounded-lg border border-border bg-card px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          <option value="">Any</option>
          <option value="1">1+</option>
          <option value="2">2+</option>
          <option value="3">3+</option>
        </select>
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Parking</span>
        <select
          value={filters.parking ? String(filters.parking) : ""}
          onChange={(e) => onChange({ parking: e.target.value ? Number(e.target.value) : undefined })}
          className="h-9 rounded-lg border border-border bg-card px-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          <option value="">Any</option>
          <option value="1">1+ space</option>
          <option value="2">2+ spaces</option>
        </select>
      </label>
    </div>
  );
}

/* Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Dynamic search sections (counts reflect real inventory) Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */

function SearchSections({
  sections,
  onCompareToggle,
  compareIds,
}: {
  sections: SearchSectionsResponse["sections"];
  onCompareToggle: (id: number) => void;
  compareIds: Set<number>;
}) {
  if (!sections || sections.length === 0) return null;
  return (
    <div className="space-y-12">
      {sections.map((section, idx) => (
        <div key={section.id || idx}>
          <div className="mb-6 flex items-end justify-between">
            <div>
              <h2 className="text-2xl font-bold tracking-tight text-foreground">{section.title}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {section.count} propert{section.count === 1 ? "y" : "ies"} in this group
              </p>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {section.items.map((property: Property) => (
              <PropertyCard
                key={property.id}
                property={property}
                onCompareToggle={onCompareToggle}
                isCompareSelected={compareIds.has(property.id)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/* Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ Main page shell Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬ */

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [sectionsData, setSectionsData] = useState<SearchSectionsResponse | null>(null);
  const [unifiedData, setUnifiedData] = useState<UnifiedSearchResponse | null>(null);
  const [includeWeb, setIncludeWeb] = useState(true);
  const [intent, setIntent] = useState<SearchIntent | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<SearchFilters>({
    q: searchParams.get("q") || "",
  });
  const [compareIds, setCompareIds] = useState<Set<number>>(new Set());
  const [locState, setLocState] = useState<LocState>("idle");
  const [userCoords, setUserCoords] = useState<{ lat: number; lng: number } | null>(null);

  const locationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const requestLocation = () => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setLocState("unsupported");
      return;
    }
    setLocState("pending");
    if (locationTimer.current) clearTimeout(locationTimer.current);
    locationTimer.current = setTimeout(() => {
      setLocState((current) => (current === "pending" ? "timeout" : current));
    }, 10000);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (locationTimer.current) clearTimeout(locationTimer.current);
        setUserCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setLocState("granted");
      },
      () => {
        if (locationTimer.current) clearTimeout(locationTimer.current);
        setLocState("denied");
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
    );
  };

  const clearLocation = () => {
    if (locationTimer.current) clearTimeout(locationTimer.current);
    setUserCoords(null);
    setLocState("idle");
  };

  const patchFilters = useCallback((patch: Partial<SearchFilters>) => {
    setFilters((current) => ({ ...current, ...patch }));
  }, []);

  const fetchProperties = useCallback(async () => {
    setLoading(true);
    setSearchError(null);
    try {
      const params: SearchFilters = { ...filters };
      if (userCoords) {
        params.latitude = userCoords.lat;
        params.longitude = userCoords.lng;
        params.radius_km = 5.0;
      }
      // Unified search: verified inventory + (optional) bounded web discovery.
      const data = await searchApi.unified({
        query: filters.q?.trim() || "",
        location: userCoords
          ? { latitude: userCoords.lat, longitude: userCoords.lng, radius_km: 5.0 }
          : undefined,
        filters: params,
        include_web: includeWeb,
        limit: 12,
      });
      setSectionsData({ sections: data.sections });
      setUnifiedData(data);
      setIntent(data.parsed || null);
    } catch (err: unknown) {
      setSectionsData(null);
      setUnifiedData(null);
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setSearchError("Please sign in again before searching.");
        } else if (err.status === 422) {
          setSearchError("Check your search and filters, then try again.");
        } else if (err.status >= 500) {
          setSearchError("We couldn't load property results. Please try again.");
        } else {
          setSearchError(err.message || "We couldn't load property results. Please try again.");
        }
      } else {
        setSearchError("We couldn't load property results. Check your connection and try again.");
      }
    } finally {
      setLoading(false);
    }
  }, [filters, userCoords, includeWeb]);
  useEffect(() => {
    const timer: ReturnType<typeof setTimeout> = setTimeout(() => fetchProperties(), 0);
    return () => clearTimeout(timer);
  }, [fetchProperties]);

  const toggleCompare = useCallback((id: number) => {
    setCompareIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (filters.q?.trim()) {
      router.replace(`/search?q=${encodeURIComponent(filters.q.trim())}`, { scroll: false });
    }
    fetchProperties();
  };

  const clearSearch = () => {
    setFilters({});
    setUserCoords(null);
    setLocState("idle");
    setSectionsData(null);
    setIntent(null);
    if (locationTimer.current) clearTimeout(locationTimer.current);
    router.replace("/search", { scroll: false });
  };
  const webNotice =
    unifiedData?.metadata?.web_message ? (
      <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-200/50 bg-amber-50/10 px-3 py-2 text-xs text-amber-900/90">
        <Globe2 className="h-4 w-4 shrink-0" />
        <span>{unifiedData.metadata.web_message}</span>
      </div>
    ) : null;

  return (
    <div className="min-h-screen bg-background">
      {/* Hero search */}
      <div className="border-b border-border/60 bg-gradient-to-b from-background to-muted/30">
        <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <h1 className="max-w-2xl text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            Find the right property Ã¢â‚¬â€ the reasons included.
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Search by neighbourhood, budget, BHK, or a place like &quot;near metro&quot;. Every result
            section reflects actual inventory Ã¢â‚¬â€ nothing is padded.
          </p>

          <form onSubmit={onSubmit} className="mt-6">
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="relative flex-1">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground/70" />
                <Input
                  value={filters.q || ""}
                  onChange={(e) => patchFilters({ q: e.target.value })}
                  placeholder={"Try \"3BHK under 90 lakhs near metro in Hyderabad\""}
                  className="h-14 rounded-xl border-border/70 bg-card pl-12 pr-4 text-[15px] shadow-sm focus-visible:ring-primary"
                  aria-label="Search properties"
                />
              </div>
              <Button type="submit" className="h-14 rounded-xl px-8 text-[15px] font-semibold shadow-sm">
                {loading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Search className="mr-2 h-4 w-4" />
                )}
                Search
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-14 rounded-xl px-4 sm:hidden"
                onClick={() => setShowFilters((v) => !v)}
                aria-expanded={showFilters}
              >
                <SlidersHorizontal className="mr-2 h-4 w-4" />
                Filters
              </Button>
            </div>
          </form>

          <div className="mt-5 space-y-3">
            <NearMeCard
              locState={locState}
              userCoords={userCoords}
              onRequest={requestLocation}
              onClear={clearLocation}
            />
            {userCoords && locState === "granted" && (
              <Button size="sm" variant="outline" className="rounded-lg" onClick={fetchProperties}>
                <LocateFixed className="mr-2 h-3.5 w-3.5" />
                Refresh near me
              </Button>
            )}
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        {/* Filters */}
        {showFilters && (
          <div className="mb-8 rounded-[1.25rem] border border-border/60 surface p-4 shadow-soft">
            <div className="mb-3 flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm font-medium text-foreground">
                <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
                Filter results
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-xs text-muted-foreground"
                onClick={() => {
                  setFilters(({ q }) => ({ q }));
                  setTimeout(fetchProperties, 0);
                }}
              >
                Reset filters
              </Button>
            </div>
            <FilterControls filters={filters} onChange={patchFilters} />
            <div className="mt-4 flex justify-end">
              <Button size="sm" className="rounded-lg" onClick={fetchProperties}>
                Apply filters
              </Button>
            </div>
          </div>
        )}

        <div className="mb-4 flex items-center gap-2 rounded-xl border border-border/50 bg-card/40 px-3 py-2 text-sm">
          <input
            id="include-web"
            type="checkbox"
            checked={includeWeb}
            onChange={(e) => setIncludeWeb(e.target.checked)}
            className="h-4 w-4 rounded accent-amber-600"
          />
          <label htmlFor="include-web" className="text-muted-foreground">
            Include web listings
            <span className="text-muted-foreground/70"> · bounded web discovery, labeled separately</span>
          </label>
        </div>

        {/* Compare bar */}
        {compareIds.size > 0 && (
          <div className="sticky top-4 z-10 mb-8 flex items-center justify-between rounded-xl border border-border/60 bg-card/95 p-4 shadow-sm backdrop-blur-md">
            <span className="text-sm font-medium">
              {compareIds.size} propert{compareIds.size === 1 ? "y" : "ies"} selected for comparison
            </span>
            <div className="flex gap-3">
              <Button variant="ghost" size="sm" onClick={() => setCompareIds(new Set())}>
                Clear
              </Button>
              <Button
                size="sm"
                className="rounded-lg"
                disabled={compareIds.size < 2}
                onClick={() => router.push(`/compare?ids=${Array.from(compareIds).join(",")}`)}
              >
                Compare
              </Button>
            </div>
          </div>
        )}

        {/* Results */}
        {loading ? (
          <div className="space-y-12">
            <div>
              <Skeleton className="mb-6 h-8 w-48" />
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Card key={i} className="overflow-hidden rounded-xl border-border/40">
                    <Skeleton className="h-48 w-full" />
                    <div className="space-y-4 p-5">
                      <Skeleton className="h-5 w-3/4" />
                      <Skeleton className="h-4 w-1/2" />
                      <Skeleton className="h-4 w-full" />
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          </div>
        ) : searchError ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/50 py-24 text-center">
            <Building2 className="h-16 w-16 text-muted-foreground/30" />
            <h3 className="mt-5 text-xl font-semibold text-foreground">Search is temporarily unavailable</h3>
            <p className="mt-2 max-w-sm text-muted-foreground">
              {searchError}
            </p>
            <Button variant="outline" className="mt-6 rounded-lg" onClick={fetchProperties}>
              Retry search
            </Button>
          </div>
        ) : (sectionsData && sectionsData.sections.length > 0) || (unifiedData && unifiedData.web_discoveries.length > 0) ? (
          <div>
            <IntentChips intent={intent} />

            {(unifiedData && (unifiedData.verified_total > 0 || unifiedData.web_total > 0)) && (
              <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
                <Badge variant="outline" className="rounded-md">{unifiedData.verified_total} Verified</Badge>
                <Badge variant="secondary" className="rounded-md bg-amber-500/15 text-amber-800">{unifiedData.web_total} Web discoveries</Badge>
              </div>
            )}

            {webNotice}

            <SearchSections
              sections={sectionsData?.sections || []}
              onCompareToggle={toggleCompare}
              compareIds={compareIds}
            />

            {unifiedData && unifiedData.web_discoveries.length > 0 && (
              <section className="mt-10">
                <div className="mb-4 flex items-center gap-2">
                  <Badge variant="secondary" className="rounded-md bg-amber-500/15 text-amber-800 text-xs">
                    <Globe2 className="h-3.5 w-3.5" />
                    WEB DISCOVERY
                  </Badge>
                  <h2 className="text-xl font-semibold">Web Discoveries</h2>
                  <span className="text-sm text-muted-foreground">Â· {unifiedData.metadata?.cache_hit ? "cached" : "live search"}</span>
                </div>
                <p className="mb-4 text-xs text-muted-foreground/90">
                  These listings were discovered from web sources and are not verified inventory.
                  Check the original source for current availability.
                </p>
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
                  {unifiedData.web_discoveries.map((d) => (
                    <WebDiscoveryCard key={d.id} discovery={d} />
                  ))}
                </div>
              </section>
            )}
          </div>
        ) : webNotice ? (
          <div>
            <IntentChips intent={intent} />
            {webNotice}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/50 py-24 text-center">
            <MapPin className="h-16 w-16 text-muted-foreground/30" />
            <h3 className="mt-5 text-xl font-semibold text-foreground">No properties found</h3>
            <p className="mt-2 max-w-sm text-muted-foreground">
              Nothing in the current inventory matches these criteria. Adjust location, filters, or
              budget Ã¢â‚¬â€ or ask the AI assistant for guidance.
            </p>
            <div className="mt-6 flex gap-3">
              <Button variant="outline" className="rounded-lg" onClick={clearSearch}>
                Clear search
              </Button>
              <Button className="rounded-lg" onClick={() => router.push("/assistant")}>
                <Sparkles className="mr-2 h-4 w-4" />
                Ask the assistant
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      }
    >
      <SearchPageContent />
    </Suspense>
  );
}
