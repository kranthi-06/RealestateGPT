"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import PropertyCard from "@/components/property-card";
import { propertiesApi } from "@/lib/api";
import type { PropertyListResponse, SearchFilters } from "@/lib/types";
import {
  Search, SlidersHorizontal, ChevronLeft, ChevronRight, X, Building2, Loader2,
} from "lucide-react";

const CITIES = ["Hyderabad", "Bangalore", "Mumbai", "Pune", "Chennai", "Gurgaon", "Greater Noida", "Kolkata"];
const PROPERTY_TYPES = ["apartment", "villa", "plot", "house"];
const FURNISHING_OPTIONS = ["furnished", "semi-furnished", "unfurnished"];
const SORT_OPTIONS = [
  { value: "created_at:desc", label: "Newest First" },
  { value: "price:asc", label: "Price: Low to High" },
  { value: "price:desc", label: "Price: High to Low" },
  { value: "area_sqft:desc", label: "Area: Largest First" },
];

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<PropertyListResponse | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  // Filters state from URL
  const [filters, setFilters] = useState<SearchFilters>({
    q: searchParams.get("q") || "",
    city: searchParams.get("city") || "",
    property_type: searchParams.get("property_type") || "",
    min_price: searchParams.get("min_price") ? Number(searchParams.get("min_price")) : undefined,
    max_price: searchParams.get("max_price") ? Number(searchParams.get("max_price")) : undefined,
    bedrooms: searchParams.get("bedrooms") ? Number(searchParams.get("bedrooms")) : undefined,
    furnishing: searchParams.get("furnishing") || "",
    sort_by: "created_at",
    sort_order: "desc",
    page: 1,
    page_size: 12,
  });

  // Compare state
  const [compareIds, setCompareIds] = useState<Set<number>>(new Set());

  const fetchProperties = useCallback(async () => {
    setLoading(true);
    try {
      const cleanFilters: SearchFilters = {};
      Object.entries(filters).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") {
          (cleanFilters as Record<string, unknown>)[k] = v;
        }
      });
      const result = await propertiesApi.list(cleanFilters);
      setData(result);
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void Promise.resolve().then(fetchProperties);
  }, [fetchProperties]);

  const updateFilter = (key: string, value: string | number | null | undefined) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value === null ? undefined : value,
      page: 1,
    }));
  };

  const clearFilters = () => {
    setFilters({ page: 1, page_size: 12, sort_by: "created_at", sort_order: "desc" });
  };

  const handleSort = (value: string | null) => {
    const [sortBy, sortOrder] = (value || "created_at:desc").split(":");
    setFilters((prev) => ({ ...prev, sort_by: sortBy, sort_order: sortOrder }));
  };

  const toggleCompare = (id: number) => {
    setCompareIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 4) next.add(id);
      return next;
    });
  };

  const activeFilterCount = [filters.city, filters.property_type, filters.min_price, filters.max_price, filters.bedrooms, filters.furnishing].filter(Boolean).length;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      {/* Search Bar */}
      <div className="flex gap-2 mb-6">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search properties..."
            className="pl-10"
            value={filters.q || ""}
            onChange={(e) => updateFilter("q", e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fetchProperties()}
          />
        </div>
        <Button variant="outline" className="gap-2" onClick={() => setShowFilters(!showFilters)}>
          <SlidersHorizontal className="w-4 h-4" />
          Filters
          {activeFilterCount > 0 && (
            <Badge className="ml-1 h-5 w-5 p-0 flex items-center justify-center text-xs">{activeFilterCount}</Badge>
          )}
        </Button>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <Card className="p-4 mb-6 border-border/60">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <Select value={filters.city || ""} onValueChange={(v) => updateFilter("city", v === "all" ? "" : v)}>
              <SelectTrigger><SelectValue placeholder="City" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Cities</SelectItem>
                {CITIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>

            <Select value={filters.property_type || ""} onValueChange={(v) => updateFilter("property_type", v === "all" ? "" : v)}>
              <SelectTrigger><SelectValue placeholder="Type" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                {PROPERTY_TYPES.map((t) => <SelectItem key={t} value={t} className="capitalize">{t}</SelectItem>)}
              </SelectContent>
            </Select>

            <Select value={filters.bedrooms?.toString() || ""} onValueChange={(v) => updateFilter("bedrooms", v === "all" ? undefined : Number(v))}>
              <SelectTrigger><SelectValue placeholder="Bedrooms" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any BHK</SelectItem>
                {[1, 2, 3, 4].map((b) => <SelectItem key={b} value={b.toString()}>{b} BHK</SelectItem>)}
              </SelectContent>
            </Select>

            <Input
              type="number"
              placeholder="Min Price"
              value={filters.min_price || ""}
              onChange={(e) => updateFilter("min_price", e.target.value ? Number(e.target.value) : undefined)}
            />

            <Input
              type="number"
              placeholder="Max Price"
              value={filters.max_price || ""}
              onChange={(e) => updateFilter("max_price", e.target.value ? Number(e.target.value) : undefined)}
            />

            <Select value={filters.furnishing || ""} onValueChange={(v) => updateFilter("furnishing", v === "all" ? "" : v)}>
              <SelectTrigger><SelectValue placeholder="Furnishing" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any Furnishing</SelectItem>
                {FURNISHING_OPTIONS.map((f) => <SelectItem key={f} value={f} className="capitalize">{f}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="flex justify-between mt-3">
            <Button variant="ghost" size="sm" onClick={clearFilters} className="text-muted-foreground">
              <X className="w-3 h-3 mr-1" /> Clear All
            </Button>
            <Button size="sm" onClick={fetchProperties} className="gradient-primary text-white border-0">
              Apply Filters
            </Button>
          </div>
        </Card>
      )}

      {/* Compare Bar */}
      {compareIds.size > 0 && (
        <div className="mb-4 p-3 bg-primary/5 border border-primary/20 rounded-xl flex items-center justify-between">
          <span className="text-sm font-medium">
            {compareIds.size} properties selected for comparison
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setCompareIds(new Set())}>
              Clear
            </Button>
            <Button
              size="sm"
              className="gradient-primary text-white border-0"
              disabled={compareIds.size < 2}
              onClick={() => router.push(`/compare?ids=${Array.from(compareIds).join(",")}`)}
            >
              Compare ({compareIds.size})
            </Button>
          </div>
        </div>
      )}

      {/* Results header */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-muted-foreground">
          {data ? (
            <>
              <span className="font-semibold text-foreground">{data.total}</span> properties found
            </>
          ) : (
            "Searching..."
          )}
        </p>
        <Select
          value={`${filters.sort_by}:${filters.sort_order}`}
          onValueChange={handleSort}
        >
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Sort by" />
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Results Grid */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className="overflow-hidden">
              <Skeleton className="h-48 w-full" />
              <div className="p-4 space-y-3">
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
                <Skeleton className="h-3 w-full" />
              </div>
            </Card>
          ))}
        </div>
      ) : data && data.properties.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {data.properties.map((property) => (
            <PropertyCard
              key={property.id}
              property={property}
              onCompareToggle={toggleCompare}
              isCompareSelected={compareIds.has(property.id)}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-20">
          <Building2 className="w-16 h-16 mx-auto text-muted-foreground/30 mb-4" />
          <h3 className="text-lg font-semibold">No properties found</h3>
          <p className="text-muted-foreground mt-1">Try adjusting your filters or search query.</p>
          <Button variant="outline" className="mt-4" onClick={clearFilters}>
            Clear All Filters
          </Button>
        </div>
      )}

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-8">
          <Button
            variant="outline"
            size="sm"
            disabled={data.page <= 1}
            onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page || 1) - 1 }))}
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-sm text-muted-foreground px-4">
            Page {data.page} of {data.total_pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={data.page >= data.total_pages}
            onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page || 1) + 1 }))}
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 animate-spin" /></div>}>
      <SearchPageContent />
    </Suspense>
  );
}
