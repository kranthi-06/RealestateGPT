"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Heart,
  Search as SearchIcon,
  Trash2,
  Clock,
  Filter,
  RefreshCw,
  ArrowUpDown,
  X,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { savedApi } from "@/lib/api";
import type { SavedPropertyItem, SavedSearch, Property } from "@/lib/types";
import { PropertyListRow } from "@/components/property-list-row";
import PropertyCard from "@/components/property-card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { formatPrice } from "@/lib/format";
import { useSaved } from "@/lib/saved-context";
import { notify, notifyUnsaved } from "@/lib/notify";
import { cn } from "@/lib/utils";

type SortKey = "created_at" | "price_asc" | "price_desc";

const SORT_LABELS: Record<SortKey, string> = {
  created_at: "Recently saved",
  price_asc: "Price: low to high",
  price_desc: "Price: high to low",
};

export default function SavedPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const { hydrate, revision } = useSaved();

  const [savedProperties, setSavedProperties] = useState<SavedPropertyItem[]>([]);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchesLoading, setSearchesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"properties" | "searches">("properties");

  // Search / filter / sort state for the saved list.
  const [query, setQuery] = useState("");
  const [city, setCity] = useState("");
  const [sort, setSort] = useState<SortKey>("created_at");
  const [view, setView] = useState<"list" | "grid">("list");

  const fetchSavedProperties = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await savedApi.getSavedProperties();
      setSavedProperties(data);
    } catch {
      setError("Your shortlist could not be retrieved. Your saved properties have not been changed.");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSavedSearches = useCallback(async () => {
    try {
      setSearchesLoading(true);
      const data = await savedApi.getSavedSearches();
      setSavedSearches(data);
    } catch {
      setSavedSearches([]);
    } finally {
      setSearchesLoading(false);
    }
  }, []);

  // Fetch after auth settles. The callbacks set state, so they are invoked
  // from a queued microtask rather than synchronously inside the effect.
  useEffect(() => {
    if (!isAuthenticated) return;
    const id = window.setTimeout(() => {
      void fetchSavedProperties();
      void fetchSavedSearches();
    }, 0);
    return () => window.clearTimeout(id);
  }, [isAuthenticated, fetchSavedProperties, fetchSavedSearches]);

  // A save/unsave anywhere in the app refreshes this list so the two never
  // disagree — the exact bug where a freshly saved property was missing.
  const firstRevision = useRef(revision);
  useEffect(() => {
    if (!isAuthenticated || revision === firstRevision.current) return;
    const id = window.setTimeout(() => void fetchSavedProperties(), 0);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revision, isAuthenticated]);

  const handleUnsave = useCallback(
    async (propertyId: number, title?: string) => {
      // Optimistic removal; roll back and tell the user if the server refuses.
      const snapshot = savedProperties;
      setSavedProperties((current) => current.filter((item) => item.property_id !== propertyId));
      try {
        await savedApi.unsaveProperty(propertyId);
        await hydrate();
        notifyUnsaved(title);
      } catch {
        setSavedProperties(snapshot);
        notify("Could not remove that property", {
          description: "Your saved properties have not been changed.",
          type: "error",
        });
      }
    },
    [savedProperties, hydrate]
  );

  const handleDeleteSearch = useCallback(async (searchId: number) => {
    try {
      await savedApi.deleteSavedSearch(searchId);
      setSavedSearches((prev) => prev.filter((s) => s.id !== searchId));
      notify("Saved search deleted", { type: "info" });
    } catch {
      notify("Could not delete that saved search", { type: "error" });
    }
  }, []);

  const runSavedSearch = useCallback(
    (search: SavedSearch) => {
      const params = new URLSearchParams();
      if (search.city) params.set("city", search.city);
      if (search.property_type) params.set("property_type", search.property_type);
      if (search.min_price) params.set("min_price", String(search.min_price));
      if (search.max_price) params.set("max_price", String(search.max_price));
      if (search.bedrooms) params.set("bedrooms", String(search.bedrooms));
      if (search.query_text) params.set("q", search.query_text);
      router.push(`/search?${params.toString()}`);
    },
    [router]
  );

  const buildSearchChips = (search: SavedSearch) => {
    const chips: string[] = [];
    if (search.city) chips.push(search.city);
    if (search.property_type) chips.push(search.property_type);
    if (search.bedrooms) chips.push(`${search.bedrooms}BHK`);
    if (search.min_price || search.max_price) {
      const min = search.min_price ? `₹${formatPrice(search.min_price)}` : "Any";
      const max = search.max_price ? `₹${formatPrice(search.max_price)}` : "Any";
      chips.push(`${min} – ${max}`);
    }
    return chips;
  };

  const cities = useMemo(
    () => Array.from(new Set(savedProperties.map((i) => i.property.city).filter(Boolean))).sort(),
    [savedProperties]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let items = savedProperties.filter((item) => {
      const p = item.property;
      if (q && !`${p.title} ${p.locality ?? ""} ${p.city ?? ""}`.toLowerCase().includes(q)) return false;
      if (city && p.city !== city) return false;
      return true;
    });
    items = [...items].sort((a, b) => {
      if (sort === "price_asc") return a.property.price - b.property.price;
      if (sort === "price_desc") return b.property.price - a.property.price;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
    return items;
  }, [savedProperties, query, city, sort]);

  const hasFilters = Boolean(query.trim() || city);

  if (isLoading) {
    return (
      <div className="container-page py-8">
        <Skeleton className="h-9 w-40" />
        <Skeleton className="mt-3 h-5 w-72 max-w-full" />
        <div className="mt-8 space-y-3">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return (
    <div className="container-page py-8">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">Saved</h1>
          <p className="mt-2 text-slate-600">
            Your personal workspace — properties and searches you want to revisit.
          </p>
        </div>
        <Button variant="outline" onClick={() => void fetchSavedProperties()} className="gap-2">
          <RefreshCw className="size-3.5" />
          Refresh
        </Button>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="properties">
            <Heart className="mr-2 h-4 w-4" />
            Saved Properties
            <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-700">
              {savedProperties.length}
            </span>
          </TabsTrigger>
          <TabsTrigger value="searches">
            <SearchIcon className="mr-2 h-4 w-4" />
            Saved Searches
            <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
              {savedSearches.length}
            </span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="properties" className="mt-6">
          {error && (
            <div className="mb-6">
              <ErrorState message={error} onRetry={fetchSavedProperties} />
            </div>
          )}

          {/* Search, filter and sort controls — only shown when there is data. */}
          {!loading && savedProperties.length > 0 && (
            <div className="mb-5 flex flex-col gap-3 rounded-xl border border-border/60 bg-card p-3 sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search saved properties by title or locality…"
                  className="pl-9"
                  aria-label="Search saved properties"
                />
              </div>
              <select
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="h-9 rounded-lg border border-border bg-background px-3 text-sm"
                aria-label="Filter saved properties by city"
              >
                <option value="">All cities</option>
                {cities.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <div className="flex items-center gap-1 rounded-lg border border-border bg-background p-0.5">
                {(["list", "grid"] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setView(v)}
                    className={cn(
                      "rounded-md px-2.5 py-1 text-xs font-medium capitalize transition-colors",
                      view === v ? "bg-primary/10 text-primary" : "text-muted-foreground"
                    )}
                    aria-pressed={view === v}
                  >
                    {v}
                  </button>
                ))}
              </div>
              <label className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <ArrowUpDown className="size-3.5" />
                <span className="sr-only sm:not-sr-only">Sort</span>
                <select
                  value={sort}
                  onChange={(e) => setSort(e.target.value as SortKey)}
                  className="h-9 rounded-lg border border-border bg-background px-2 text-sm"
                  aria-label="Sort saved properties"
                >
                  {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                    <option key={key} value={key}>
                      {SORT_LABELS[key]}
                    </option>
                  ))}
                </select>
              </label>
              {hasFilters && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => {
                    setQuery("");
                    setCity("");
                  }}
                >
                  <X className="size-3.5" />
                  Clear
                </Button>
              )}
            </div>
          )}

          {loading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-24 rounded-xl" />
              ))}
            </div>
          ) : savedProperties.length === 0 ? (
            <EmptyState
              title="Your shortlist starts here."
              description="Save any home from search to keep the details, source, and freshness signal together for later."
              actionHref="/search"
              actionLabel="Explore properties"
            />
          ) : filtered.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border py-14 text-center">
              <Filter className="mx-auto size-8 text-muted-foreground/40" />
              <h3 className="mt-3 font-semibold text-foreground">No saved property matches those filters</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                You have {savedProperties.length} saved propert{savedProperties.length === 1 ? "y" : "ies"};
                try a different search or city.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => {
                  setQuery("");
                  setCity("");
                }}
              >
                Clear filters
              </Button>
            </div>
          ) : view === "grid" ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.map((item) => (
                <SavedPropertyCard
                  key={item.property.id}
                  item={item}
                  onUnsave={handleUnsave}
                />
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {filtered.map((item) => (
                <PropertyListRow
                  key={item.property.id}
                  property={{ ...item.property, is_saved: true }}
                  showDistance={false}
                />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="searches" className="mt-6">
          {searchesLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-32 rounded-xl" />
              ))}
            </div>
          ) : savedSearches.length > 0 ? (
            <div className="space-y-3">
              {savedSearches.map((search) => (
                <div
                  key={search.id}
                  className="card flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0 flex-1">
                    <div className="mb-2 flex items-center gap-2 text-sm text-slate-500">
                      <Clock className="h-3.5 w-3.5" />
                      <span>Saved {new Date(search.created_at).toLocaleDateString()}</span>
                      {search.name && (
                        <span className="ml-2 font-medium text-slate-900">{search.name}</span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {buildSearchChips(search).map((chip, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 px-2.5 py-1 text-xs text-slate-700"
                        >
                          <Filter className="h-3 w-3" />
                          {chip}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => runSavedSearch(search)} className="gap-1.5">
                      <SearchIcon className="h-3.5 w-3.5" />
                      Run search
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteSearch(search.id)}
                      className="text-red-600 hover:bg-red-50 hover:text-red-700"
                      aria-label={`Delete saved search ${search.name ?? search.id}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No saved searches yet."
              description="Save a search from the results page to re-run it anytime with one click."
              actionHref="/search"
              actionLabel="Search properties"
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

/** Grid card for a saved property with its own unsave action. */
function SavedPropertyCard({
  item,
  onUnsave,
}: {
  item: SavedPropertyItem;
  onUnsave: (id: number, title?: string) => void;
}) {
  const property: Property = { ...item.property, is_saved: true };
  const savedAgo = useMemo(() => {
    try {
      return new Date(item.created_at).toLocaleDateString();
    } catch {
      return "";
    }
  }, [item.created_at]);

  return (
    <div className="relative">
      <div className="absolute right-2 top-2 z-10 flex items-center gap-1.5">
        <Badge variant="secondary" className="bg-white/90 text-[10px] shadow-sm backdrop-blur-sm">
          Saved {savedAgo}
        </Badge>
        <button
          type="button"
          onClick={() => onUnsave(item.property_id, item.property.title)}
          className="flex size-7 items-center justify-center rounded-full bg-white/90 shadow-sm backdrop-blur-sm transition-transform hover:scale-110 dark:bg-black/50"
          aria-label={`Remove ${item.property.title} from saved`}
        >
          <Trash2 className="size-3.5 text-muted-foreground" />
        </button>
      </div>
      <PropertyCard property={property} variant="grid" />
    </div>
  );
}
