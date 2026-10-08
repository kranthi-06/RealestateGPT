"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { savedApi } from "@/lib/api";
import type { SavedPropertyItem, SavedSearch } from "@/lib/types";
import { PropertyListRow } from "@/components/property-list-row";
import { Loader2, Heart, Search, Trash2, Clock, Filter } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatPrice } from "@/lib/format";

export default function SavedPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [savedProperties, setSavedProperties] = useState<SavedPropertyItem[]>([]);
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchesLoading, setSearchesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"properties" | "searches">("properties");

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/auth/login");
    }
  }, [isLoading, isAuthenticated, router]);

  const fetchSavedProperties = async () => {
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
  };

  const fetchSavedSearches = async () => {
    try {
      setSearchesLoading(true);
      const data = await savedApi.getSavedSearches();
      setSavedSearches(data);
    } catch {
      console.error("Failed to load saved searches");
    } finally {
      setSearchesLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      void Promise.resolve().then(fetchSavedProperties);
      void Promise.resolve().then(fetchSavedSearches);
    }
  }, [isAuthenticated]);

  const handleUnsave = async (propertyId: number) => {
    try {
      await savedApi.unsaveProperty(propertyId);
      setSavedProperties((prev) => prev.filter((item) => item.property.id !== propertyId));
    } catch {
      setError("Failed to remove property from saved list.");
    }
  };

  const handleDeleteSearch = async (searchId: number) => {
    try {
      await savedApi.deleteSavedSearch(searchId);
      setSavedSearches((prev) => prev.filter((s) => s.id !== searchId));
    } catch {
      setError("Failed to delete saved search.");
    }
  };

  const runSavedSearch = (search: SavedSearch) => {
    const params = new URLSearchParams();
    if (search.city) params.set("city", search.city);
    if (search.property_type) params.set("property_type", search.property_type);
    if (search.min_price) params.set("min_price", String(search.min_price));
    if (search.max_price) params.set("max_price", String(search.max_price));
    if (search.bedrooms) params.set("bedrooms", String(search.bedrooms));
    if (search.query_text) params.set("q", search.query_text);
    router.push(`/search?${params.toString()}`);
  };

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

  if (isLoading || (isAuthenticated && loading)) {
    return (
      <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-green-600" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="container-page py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900">Saved</h1>
        <p className="mt-2 text-slate-600">Your personal workspace — properties and searches you want to revisit.</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="properties">
            <Heart className="mr-2 h-4 w-4" />
            Saved Properties <span className="ml-2 px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded-full">{savedProperties.length}</span>
          </TabsTrigger>
          <TabsTrigger value="searches">
            <Search className="mr-2 h-4 w-4" />
            Saved Searches <span className="ml-2 px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded-full">{savedSearches.length}</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="properties" className="mt-6">
          {error && (
            <div className="mb-6">
              <ErrorState message={error} onRetry={fetchSavedProperties} />
            </div>
          )}

          {loading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-20 animate-pulse bg-slate-100 rounded-lg" />
              ))}
            </div>
          ) : savedProperties.length > 0 ? (
            <div className="space-y-2">
              {savedProperties.map((item) => (
                <PropertyListRow
                  key={item.property.id}
                  property={{ ...item.property, is_saved: true }}
                  showDistance={false}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              title="Your shortlist starts here."
              description="Save any home from search to keep the details, source, and freshness signal together for later."
              actionHref="/search"
              actionLabel="Explore properties"
            />
          )}
        </TabsContent>

        <TabsContent value="searches" className="mt-6">
          {searchesLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-32 animate-pulse bg-slate-100 rounded-lg" />
              ))}
            </div>
          ) : savedSearches.length > 0 ? (
            <div className="space-y-3">
              {savedSearches.map((search) => (
                <div
                  key={search.id}
                  className="card p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
                      <Clock className="h-3.5 w-3.5" />
                      <span>Saved {new Date(search.created_at).toLocaleDateString()}</span>
                      {search.name && <span className="font-medium text-slate-900 ml-2">{search.name}</span>}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {buildSearchChips(search).map((chip, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-slate-100 text-slate-700 rounded-full border border-slate-200"
                        >
                          <Filter className="h-3 w-3" />
                          {chip}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => runSavedSearch(search)}
                      className="gap-1.5"
                    >
                      <Search className="h-3.5 w-3.5" />
                      Run search
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteSearch(search.id)}
                      className="text-red-600 hover:text-red-700 hover:bg-red-50"
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
