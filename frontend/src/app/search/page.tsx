"use client";

import { useState, useEffect, useCallback, Suspense, useRef, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import { Select } from "@/components/ui/select";
import { HorizontalFilters } from "@/components/horizontal-filters";
import PropertyCard from "@/components/property-card";
import WebDiscoveryCard from "@/components/web-discovery-card";
import { ApiError, searchApi } from "@/lib/api";
import {
  Search,
  MapPin,
  Building2,
  Loader2,
  LocateFixed,
  LocateOff,
  Clock3,
  Sparkles,
  Globe2,
  LayoutList,
  LayoutGrid,
  Navigation,
  ArrowRight,
} from "lucide-react";
import type { SearchFilters, SearchSectionsResponse, Property, SearchIntent, UnifiedSearchResponse } from "@/lib/types";
import { MAX_COMPARE, useCompare } from "@/lib/compare-context";
import { notifyCompareAdded, notifyCompareFull } from "@/lib/notify";

type LocState = "idle" | "pending" | "granted" | "denied" | "timeout" | "unsupported";

function NearMeBanner({
  locState,
  userCoords,
  onRequest,
  onClear,
  onRefresh,
}: {
  locState: LocState;
  userCoords: { lat: number; lng: number } | null;
  onRequest: () => void;
  onClear: () => void;
  onRefresh?: () => void;
}) {
  if (locState === "granted" && userCoords) {
    return (
      <div className="flex flex-col gap-2 rounded-xl border border-emerald-200/70 bg-emerald-50/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5 text-sm text-emerald-900">
          <LocateFixed className="h-4 w-4 shrink-0" />
          <span className="truncate">
            Searching near{" "}
            <span className="font-medium tabular-nums">
              {userCoords.lat.toFixed(4)}, {userCoords.lng.toFixed(4)}
            </span>
            <span className="text-emerald-700/70"> Â· within 5 km</span>
          </span>
        </div>
        <div className="flex gap-2">
          {onRefresh && (
            <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={onRefresh}>
              Refresh
            </Button>
          )}
          <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={onClear}>
            Use manual search
          </Button>
        </div>
      </div>
    );
  }

  const messages: Partial<
    Record<LocState, { icon: typeof LocateOff; title: string; note: string; retry?: boolean }>
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
      <div className="rounded-xl border border-amber-200/70 bg-amber-50/50 px-4 py-3">
        <div className="flex items-start gap-3">
          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-amber-900">{msg!.title}</p>
            <p className="mt-0.5 text-xs text-amber-800/80">{msg!.note}</p>
            {msg!.retry && (
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
    <div className="flex flex-col gap-3 rounded-xl border border-border/60 bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3 min-w-0">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Navigation className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">Find properties near you</p>
          <p className="text-xs text-muted-foreground truncate">
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
        {locState === "pending" ? "Requestingâ€¦" : "Allow location"}
      </Button>
    </div>
  );
}

function IntentChips({ intent }: { intent: SearchIntent | null }) {
  if (!intent) return null;
  const chips: string[] = [];
  if (intent.listing_type === "rent") chips.push("Rent");
  if (intent.listing_type === "sale") chips.push("Buy");
  if (intent.bedrooms != null) chips.push(`${intent.bedrooms} BHK`);
  if (intent.max_price != null) {
    const lakh = intent.max_price / 100000;
    chips.push(`Under â‚¹${lakh % 1 === 0 ? lakh.toFixed(0) : lakh.toFixed(1)}L`);
  }
  if (intent.min_price != null) chips.push("Premium");
  if (intent.city) chips.push(intent.city);
  if (intent.locality) chips.push(intent.locality);
  if (intent.property_type) chips.push(intent.property_type);
  if (intent.nearby_requirements?.length) {
    intent.nearby_requirements.forEach((req) =>
      chips.push(`Near ${req.type.replace("_", " ")}`)
    );
  }
  if (chips.length === 0) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2" aria-label="Interpreted search">
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Sparkles className="h-3 w-3" /> Interpreted
      </span>
      {chips.map((chip) => (
        <Badge
          key={chip}
          variant="secondary"
          className="rounded-md bg-primary/5 text-xs font-medium text-foreground"
        >
          {chip}
        </Badge>
      ))}
    </div>
  );
}

type SortKey = "relevance" | "price_asc" | "price_desc" | "newest";

function ResultHeader({
  totalCount,
  viewMode,
  onViewModeChange,
  sort,
  onSortChange,
}: {
  totalCount: number;
  viewMode: "list" | "grid";
  onViewModeChange: (m: "list" | "grid") => void;
  sort: SortKey;
  onSortChange: (s: SortKey) => void;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-sm">
        <h2 className="font-semibold text-foreground tabular-nums">
          {totalCount} result{totalCount === 1 ? "" : "s"}
        </h2>
      </div>
      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-1 rounded-lg border border-border bg-card p-0.5 sm:flex">
          <button
            type="button"
            onClick={() => onViewModeChange("list")}
            className={`inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium transition-colors ${
              viewMode === "list" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
            }`}
            aria-label="List view"
          >
            <LayoutList className="h-3.5 w-3.5" />
            List
          </button>
          <button
            type="button"
            onClick={() => onViewModeChange("grid")}
            className={`inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium transition-colors ${
              viewMode === "grid" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
            }`}
            aria-label="Grid view"
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            Grid
          </button>
        </div>
        <Select
          value={sort}
          onChange={(e) => onSortChange(e.target.value as SortKey)}
          className="h-8 w-[160px] text-xs"
          options={[
            { value: "relevance", label: "Relevance" },
            { value: "price_asc", label: "Price: Low to High" },
            { value: "price_desc", label: "Price: High to Low" },
            { value: "newest", label: "Newest" },
          ]}
        />
      </div>
    </div>
  );
}

function sortedProperties(items: Property[], sort: SortKey): Property[] {
  const copy = [...items];
  switch (sort) {
    case "price_asc":
      return copy.sort((a, b) => a.price - b.price);
    case "price_desc":
      return copy.sort((a, b) => b.price - a.price);
    case "newest":
      return copy.sort((a, b) => {
        const ak = a.first_seen_at ?? a.created_at;
        const bk = b.first_seen_at ?? b.created_at;
        return new Date(bk).getTime() - new Date(ak).getTime();
      });
    default:
      return items;
  }
}

function VerifiedSections({
  sections,
  onCompareToggle,
  compareIds,
  viewMode,
  sort,
}: {
  sections: SearchSectionsResponse["sections"];
  onCompareToggle: (id: number) => void;
  compareIds: number[];
  viewMode: "list" | "grid";
  sort: SortKey;
}) {
  if (!sections || sections.length === 0) return null;
  const selected = new Set(compareIds);
  return (
    <div className="space-y-8">
      {sections.map((section, idx) => {
        const items = sortedProperties(section.items, sort);
        return (
          <section key={section.id || idx}>
            <div className="mb-3 flex items-end justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold tracking-tight text-foreground sm:text-lg">
                  {section.title}
                </h3>
                <p className="text-xs text-muted-foreground tabular-nums">
                  {section.count} propert{section.count === 1 ? "y" : "ies"}
                </p>
              </div>
            </div>
            {viewMode === "grid" ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {items.map((property) => (
                  <PropertyCard
                    key={property.id}
                    property={property}
                    variant="grid"
                    onCompareToggle={onCompareToggle}
                    isCompareSelected={selected.has(property.id)}
                  />
                ))}
              </div>
            ) : (
              <div className="space-y-2">
                {items.map((property) => (
                  <PropertyCard
                    key={property.id}
                    property={property}
                    variant="list"
                    onCompareToggle={onCompareToggle}
                    isCompareSelected={selected.has(property.id)}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

export function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [sectionsData, setSectionsData] = useState<SearchSectionsResponse | null>(null);
  const [unifiedData, setUnifiedData] = useState<UnifiedSearchResponse | null>(null);
  const [includeWeb, setIncludeWeb] = useState(true);
  const [intent, setIntent] = useState<SearchIntent | null>(null);
  const [filters, setFilters] = useState<SearchFilters>({
    q: searchParams.get("q") || "",
    city: searchParams.get("city") || undefined,
    listing_type: searchParams.get("listing_type") || undefined,
    property_type: searchParams.get("property_type") || undefined,
  });
  const [locState, setLocState] = useState<LocState>("idle");
  const [userCoords, setUserCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
  const [sort, setSort] = useState<SortKey>("relevance");
  const compare = useCompare();

  const locationTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const filtersRef = useRef(filters);
  const coordsRef = useRef(userCoords);
  const includeWebRef = useRef(includeWeb);
  const fetchAbortRef = useRef<AbortController | null>(null);
  const fetchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastClientErrorRef = useRef<number>(0);
  const lastSignatureRef = useRef<string>("");
  const requestCacheRef = useRef<Map<string, { timestamp: number; data: UnifiedSearchResponse }>>(new Map());
  const inFlightRef = useRef<Set<string>>(new Set());

  useEffect(() => { filtersRef.current = filters; }, [filters]);
  useEffect(() => { coordsRef.current = userCoords; }, [userCoords]);
  useEffect(() => { includeWebRef.current = includeWeb; }, [includeWeb]);

  const requestSignature = useMemo(
    () =>
      JSON.stringify({
        q: filters.q,
        city: filters.city,
        min_bedrooms: filters.min_bedrooms,
        max_bedrooms: filters.max_bedrooms,
        bathrooms: filters.bathrooms,
        min_price: filters.min_price,
        max_price: filters.max_price,
        property_type: filters.property_type,
        listing_type: filters.listing_type,
        furnishing: filters.furnishing,
        min_area: filters.min_area,
        max_area: filters.max_area,
        construction_status: filters.construction_status,
        radius_km: filters.radius_km,
        amenities: filters.amenities,
      }) +
      "|" +
      (userCoords ? `${userCoords.lat.toFixed(6)}_${userCoords.lng.toFixed(6)}` : "none") +
      "|" +
      String(includeWeb),
    [filters, userCoords, includeWeb]
  );

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

  const resetFilters = () => {
    setFilters(({ q, city, listing_type, property_type }) => ({
      q, city, listing_type, property_type,
    }));
  };

  const fetchProperties = useCallback(async (opts?: { isUserInitiated?: boolean }) => {
    const isUserInitiated = opts?.isUserInitiated ?? false;
    const now = Date.now();
    // Back-off only applies to repeated automatic retries of the SAME failed
    // request. A changed query, filter set or location always proceeds, so
    // adjusting filters never appears to be ignored.
    const signatureChanged = lastSignatureRef.current !== requestSignature;
    if (
      !isUserInitiated &&
      !signatureChanged &&
      lastClientErrorRef.current > 0 &&
      now - lastClientErrorRef.current < 5000
    ) {
      return;
    }
    lastSignatureRef.current = requestSignature;

    const cacheKey = requestSignature;
    const cached = requestCacheRef.current.get(cacheKey);
    if (cached && now - cached.timestamp < 30000) {
      setSectionsData({ sections: cached.data.sections });
      setUnifiedData(cached.data);
      setIntent(cached.data.parsed || null);
      setLoading(false);
      return;
    }

    if (inFlightRef.current.has(cacheKey)) {
      return;
    }
    inFlightRef.current.add(cacheKey);

    if (fetchAbortRef.current) {
      fetchAbortRef.current.abort();
    }
    const controller = new AbortController();
    fetchAbortRef.current = controller;
    setLoading(true);
    setSearchError(null);
    try {
      const currentFilters = filtersRef.current;
      const currentCoords = coordsRef.current;
      const currentIncludeWeb = includeWebRef.current;
      const params: SearchFilters = { ...currentFilters };
      if (currentCoords) {
        params.latitude = currentCoords.lat;
        params.longitude = currentCoords.lng;
        params.radius_km = currentFilters.radius_km ?? 5.0;
      }
      const unifiedQuery = (
        currentFilters.q?.trim() ||
        (currentCoords
          ? `properties near ${currentCoords.lat.toFixed(4)}, ${currentCoords.lng.toFixed(4)}`
          : "")
      ).trim();
      if (!unifiedQuery) {
        setSectionsData(null);
        setUnifiedData(null);
        setSearchError("Type a search or allow location for near-me results.");
        setLoading(false);
        return;
      }
      const data = await searchApi.unified(
        {
          query: unifiedQuery,
          location: currentCoords
            ? {
                latitude: currentCoords.lat,
                longitude: currentCoords.lng,
                radius_km: currentFilters.radius_km ?? 5.0,
              }
            : undefined,
          filters: params,
          include_web: currentIncludeWeb,
          limit: 24,
        },
        controller.signal
      );
      requestCacheRef.current.set(cacheKey, { timestamp: now, data });
      setSectionsData({ sections: data.sections });
      setUnifiedData(data);
      setIntent(data.parsed || null);
      lastClientErrorRef.current = 0;
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        return;
      }
      setSectionsData(null);
      setUnifiedData(null);
      if (err instanceof ApiError) {
        if (err.status >= 400 && err.status < 500) {
          lastClientErrorRef.current = Date.now();
        }
        if (err.status === 401) {
          setSearchError("Please sign in again before searching.");
        } else if (err.status === 422) {
          setSearchError("Check your search and filters, then try again.");
        } else if (err.status === 429) {
          setSearchError("Search is rate-limited. Please wait a moment and try again.");
        } else if (err.status >= 500) {
          setSearchError("We couldn't load property results. Please try again.");
        } else {
          setSearchError(err.message || "We couldn't load property results. Please try again.");
        }
      } else {
        setSearchError("We couldn't load property results. Check your connection and try again.");
      }
    } finally {
      inFlightRef.current.delete(cacheKey);
      if (fetchAbortRef.current === controller) {
        fetchAbortRef.current = null;
      }
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [requestSignature]);

  useEffect(() => {
    if (fetchDebounceRef.current) clearTimeout(fetchDebounceRef.current);
    fetchDebounceRef.current = setTimeout(() => fetchProperties(), 300);
    return () => {
      if (fetchDebounceRef.current) clearTimeout(fetchDebounceRef.current);
      if (fetchAbortRef.current) fetchAbortRef.current.abort();
    };
  }, [requestSignature, fetchProperties]);

  const toggleCompare = useCallback((id: number) => {
    if (compare.has(id)) {
      compare.remove(id);
      return;
    }
    if (compare.isFull) {
      notifyCompareFull(MAX_COMPARE);
      return;
    }
    compare.add(id);
    notifyCompareAdded();
  }, [compare]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (fetchDebounceRef.current) {
      clearTimeout(fetchDebounceRef.current);
      fetchDebounceRef.current = null;
    }
    if (filters.q?.trim()) {
      router.replace(`/search?q=${encodeURIComponent(filters.q.trim())}`, { scroll: false });
    }
    fetchProperties({ isUserInitiated: true });
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

  const totalCount = unifiedData?.verified_total ?? sectionsData?.sections.reduce((s, sec) => s + sec.count, 0) ?? 0;

  const webNotice =
    unifiedData?.metadata?.web_message ? (
      <div className="mb-4 flex items-start gap-2 rounded-lg border border-amber-200/50 bg-amber-50/10 px-3 py-2 text-xs text-amber-900/90">
        <Globe2 className="h-4 w-4 shrink-0" />
        <span>{unifiedData.metadata.web_message}</span>
      </div>
    ) : null;

  return (
    <div className="min-h-screen bg-background">
      {/* Search Bar - Sticky at top */}
      <div className="sticky top-[65px] z-30 border-b border-border/60 bg-background/90 backdrop-blur">
        <div className="page-shell py-3">
          <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                value={filters.q || ""}
                onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
                placeholder='Try "3 BHK under â‚¹90L near metro in Hyderabad"'
                className="h-10 rounded-xl border-border/70 bg-card pl-9 pr-3 text-sm shadow-sm focus-visible:ring-primary"
                aria-label="Search properties"
              />
            </div>
            <Button type="submit" className="h-10 rounded-xl px-5 gap-1.5 text-sm font-medium shadow-sm">
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              Search
            </Button>
          </form>
        </div>
      </div>

      {/* Main Content */}
      <div className="page-shell py-5">
        {/* Near Me Banner */}
        <div className="mb-4">
          <NearMeBanner
            locState={locState}
            userCoords={userCoords}
            onRequest={requestLocation}
            onClear={clearLocation}
            onRefresh={() => fetchProperties({ isUserInitiated: true })}
          />
        </div>

        {/* Horizontal Filters */}
        <div className="mb-4">
          <HorizontalFilters
            filters={filters}
            onChange={(next) => setFilters(next)}
            onReset={resetFilters}
          />
        </div>

        {/* Include Web Toggle */}
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-border/50 bg-card/40 px-3 py-2 text-xs">
          <input
            id="include-web"
            type="checkbox"
            checked={includeWeb}
            onChange={(e) => setIncludeWeb(e.target.checked)}
            className="mt-0.5 h-3.5 w-3.5 rounded accent-amber-600"
          />
          <label htmlFor="include-web" className="text-muted-foreground">
            Include web listings
            <span className="text-muted-foreground/70"> Â· bounded web discovery, labeled separately</span>
          </label>
        </div>

        {/* Compare selection summary: the persistent bar lives in the layout. */}
        {compare.ids.length > 0 && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/60 bg-card px-3 py-2 text-sm">
            <div className="flex items-center gap-2">
              <Badge variant="default" className="tabular-nums px-2 py-0.5 text-[11px]">
                {compare.ids.length}
              </Badge>
              <span>
                propert{compare.ids.length === 1 ? "y" : "ies"} selected for comparison
              </span>
            </div>
            <Link href={`/compare?ids=${compare.ids.join(",")}`}>
              <Button size="sm" className="h-8 gap-1" disabled={compare.ids.length < 2}>
                Open comparison
                <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </div>
        )}

        {/* Results */}
        <main className="min-w-0">
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Card key={i}>
                  <CardContent className="flex gap-4 p-3.5">
                    <Skeleton className="h-24 w-32 shrink-0 rounded-lg sm:block" />
                    <div className="min-w-0 flex-1 space-y-2">
                      <Skeleton className="h-4 w-2/3" />
                      <Skeleton className="h-3 w-1/2" />
                      <Skeleton className="h-3 w-full" />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : searchError ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                <Building2 className="h-14 w-14 text-muted-foreground/30" />
                <h3 className="mt-4 text-base font-semibold text-foreground">
                  Search is temporarily unavailable
                </h3>
                <p className="mt-2 max-w-sm text-sm text-muted-foreground">{searchError}</p>
                <div className="mt-5 flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => fetchProperties({ isUserInitiated: true })}
                  >
                    Retry search
                  </Button>
                  <Button variant="ghost" size="sm" onClick={clearSearch}>
                    Clear
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : (sectionsData && sectionsData.sections.length > 0) ||
            (unifiedData && unifiedData.web_discoveries.length > 0) ? (
            <>
              <IntentChips intent={intent} />

              {(unifiedData && (unifiedData.verified_total > 0 || unifiedData.web_total > 0)) && (
                <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
                  <Badge variant="outline" className="rounded-md tabular-nums">
                    {unifiedData.verified_total} Verified
                  </Badge>
                  {unifiedData.web_total > 0 && (
                    <Badge
                      variant="secondary"
                      className="rounded-md bg-amber-500/15 text-amber-800 tabular-nums"
                    >
                      {unifiedData.web_total} Web discoveries
                    </Badge>
                  )}
                </div>
              )}

              {webNotice}

              {sectionsData?.sections && sectionsData.sections.length > 0 && (
                <Tabs defaultValue="verified" className="w-full">
                  <TabsList variant="line" className="mb-3 h-auto w-full justify-start rounded-none border-b border-border p-0">
                    <TabsTrigger value="verified" className="h-8 text-xs">
                      Verified ({totalCount})
                    </TabsTrigger>
                    {unifiedData && unifiedData.web_discoveries.length > 0 && (
                      <TabsTrigger value="web" className="h-8 text-xs">
                        Web ({unifiedData.web_discoveries.length})
                      </TabsTrigger>
                    )}
                  </TabsList>

                  <TabsContent value="verified">
                    <ResultHeader
                      totalCount={totalCount}
                      viewMode={viewMode}
                      onViewModeChange={setViewMode}
                      sort={sort}
                      onSortChange={setSort}
                    />
                    <VerifiedSections
                      sections={sectionsData.sections}
                      onCompareToggle={toggleCompare}
                      compareIds={compare.ids}
                      viewMode={viewMode}
                      sort={sort}
                    />
                  </TabsContent>

                  {unifiedData && unifiedData.web_discoveries.length > 0 && (
                    <TabsContent value="web">
                      <div className="mb-3 flex items-center gap-2">
                        <Badge
                          variant="secondary"
                          className="rounded-md bg-amber-500/15 text-amber-800 text-xs"
                        >
                          <Globe2 className="h-3.5 w-3.5" /> Web Discovery
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          Â· {unifiedData.metadata?.cache_hit ? "cached" : "live search"}
                        </span>
                      </div>
                      <p className="mb-4 text-xs text-muted-foreground/90">
                        These listings were discovered from web sources and are not verified inventory.
                        Check the original source for current availability.
                      </p>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                        {unifiedData.web_discoveries.map((d) => (
                          <WebDiscoveryCard key={d.id} discovery={d} />
                        ))}
                      </div>
                    </TabsContent>
                  )}
                </Tabs>
              )}

              {(!sectionsData || sectionsData.sections.length === 0) &&
                unifiedData &&
                unifiedData.web_discoveries.length > 0 && (
                  <>
                    <div className="mb-3 flex items-center gap-2">
                      <Badge
                        variant="secondary"
                        className="rounded-md bg-amber-500/15 text-amber-800 text-xs"
                      >
                        <Globe2 className="h-3.5 w-3.5" /> Web Discoveries
                      </Badge>
                    </div>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                      {unifiedData.web_discoveries.map((d) => (
                        <WebDiscoveryCard key={d.id} discovery={d} />
                      ))}
                    </div>
                  </>
                )}
            </>
          ) : webNotice ? (
            <div>
              <IntentChips intent={intent} />
              {webNotice}
            </div>
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                <MapPin className="h-14 w-14 text-muted-foreground/30" />
                <h3 className="mt-4 text-base font-semibold text-foreground">No properties found</h3>
                <p className="mt-2 max-w-sm text-sm text-muted-foreground">
                  Nothing in the current inventory matches these criteria. Adjust location, filters, or
                  budget â€” or ask the AI assistant for guidance.
                </p>
                <div className="mt-5 flex gap-2">
                  <Button variant="outline" size="sm" onClick={clearSearch}>
                    Clear search
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => router.push("/assistant")}
                    className="gap-1"
                  >
                    <Sparkles className="h-4 w-4" />
                    Ask assistant
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </main>
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
