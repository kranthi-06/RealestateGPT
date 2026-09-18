"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import PropertyCard from "@/components/property-card";
import { propertiesApi } from "@/lib/api";
import type { SearchFilters, SearchSectionsResponse, Property } from "@/lib/types";
import {
  Search, SlidersHorizontal, MapPin, Building2, Loader2, Navigation
} from "lucide-react";

// For dynamic section display
function SearchSections({ sections, onCompareToggle, compareIds }: { sections: any[], onCompareToggle: any, compareIds: Set<number> }) {
  if (!sections || sections.length === 0) return null;
  
  return (
    <div className="space-y-12">
      {sections.map((section, idx) => (
        <div key={section.id || idx}>
          <div className="flex items-end justify-between mb-6">
             <div>
                <h2 className="text-2xl font-bold tracking-tight text-foreground">{section.title}</h2>
                <p className="text-sm text-muted-foreground mt-1">{section.count} properties available</p>
             </div>
             {section.count > 4 && (
                <Button variant="link" className="text-primary pr-0">View all {section.title}</Button>
             )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
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

function SearchPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [sectionsData, setSectionsData] = useState<SearchSectionsResponse | null>(null);
  
  // Location states
  const [locationDenied, setLocationDenied] = useState(false);
  const [userCoords, setUserCoords] = useState<{lat: number, lng: number} | null>(null);

  const [filters, setFilters] = useState<SearchFilters>({
    q: searchParams.get("q") || "",
  });

  const [compareIds, setCompareIds] = useState<Set<number>>(new Set());

  const requestLocation = () => {
    if (!navigator.geolocation) {
       setLocationDenied(true);
       return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setLocationDenied(false);
      },
      () => {
        setLocationDenied(true);
      }
    );
  };

  const fetchProperties = useCallback(async () => {
    setLoading(true);
    try {
      const cleanFilters: Record<string, any> = {};
      Object.entries(filters).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") {
           cleanFilters[k] = v;
        }
      });
      if (userCoords) {
         cleanFilters.latitude = userCoords.lat;
         cleanFilters.longitude = userCoords.lng;
         cleanFilters.radius_km = 5.0; // default near me radius
      }
      
      // We call our new sections API via a direct fetch since it might not be in our api client yet
      const queryParams = new URLSearchParams();
      Object.entries(cleanFilters).forEach(([k, v]) => queryParams.append(k, String(v)));
      
      const token = typeof window !== 'undefined' ? localStorage.getItem("auth_token") : null;
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'}/search/sections?${queryParams.toString()}`, { headers });
      if (!res.ok) throw new Error("Failed to fetch sections");
      const result = await res.json();
      setSectionsData(result);
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setLoading(false);
    }
  }, [filters, userCoords]);

  useEffect(() => {
    void Promise.resolve().then(fetchProperties);
  }, [fetchProperties]);

  const toggleCompare = (id: number) => {
    setCompareIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 4) next.add(id);
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Search Header */}
      <div className="bg-muted/30 border-b border-border/40 py-8 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold tracking-tight text-foreground mb-6">Discover Properties</h1>
          
          <div className="flex flex-col sm:flex-row gap-4 max-w-4xl">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search by city, locality, or landmark..."
                className="pl-12 h-14 text-base rounded-xl shadow-sm border-border/50 bg-background focus-visible:ring-primary/20"
                value={filters.q || ""}
                onChange={(e) => setFilters(p => ({...p, q: e.target.value}))}
                onKeyDown={(e) => e.key === "Enter" && fetchProperties()}
              />
            </div>
            
            <div className="flex gap-3">
              <Button 
                variant="outline" 
                className="h-14 px-6 rounded-xl shadow-sm bg-background hover:bg-muted border-border/50 font-medium"
                onClick={requestLocation}
              >
                <Navigation className={`w-4 h-4 mr-2 ${userCoords ? "text-primary" : "text-muted-foreground"}`} />
                {userCoords ? "Near You" : "Use My Location"}
              </Button>
              
              <Button 
                className="h-14 px-8 rounded-xl shadow-sm font-semibold gradient-primary text-white border-0"
                onClick={fetchProperties}
              >
                Search
              </Button>
            </div>
          </div>
          
          {locationDenied && (
             <p className="text-destructive text-sm mt-3 ml-2">Location access was denied. Enter a city or locality manually to continue.</p>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Compare Bar */}
        {compareIds.size > 0 && (
          <div className="mb-8 p-4 bg-card border shadow-sm rounded-xl flex items-center justify-between sticky top-4 z-10 backdrop-blur-md bg-opacity-90">
            <span className="text-sm font-medium">
              {compareIds.size} properties selected for comparison
            </span>
            <div className="flex gap-3">
              <Button variant="ghost" size="sm" onClick={() => setCompareIds(new Set())}>
                Clear
              </Button>
              <Button
                size="sm"
                className="bg-primary text-primary-foreground font-medium rounded-lg"
                disabled={compareIds.size < 2}
                onClick={() => router.push(`/compare?ids=${Array.from(compareIds).join(",")}`)}
              >
                Compare
              </Button>
            </div>
          </div>
        )}

        {/* Results Grid */}
        {loading ? (
          <div className="space-y-12">
            <div>
               <Skeleton className="h-8 w-48 mb-6" />
               <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                 {Array.from({ length: 4 }).map((_, i) => (
                   <Card key={i} className="overflow-hidden rounded-xl border-border/40 shadow-sm">
                     <Skeleton className="h-48 w-full" />
                     <div className="p-5 space-y-4">
                       <Skeleton className="h-5 w-3/4" />
                       <Skeleton className="h-4 w-1/2" />
                       <Skeleton className="h-4 w-full" />
                     </div>
                   </Card>
                 ))}
               </div>
            </div>
          </div>
        ) : sectionsData && sectionsData.sections && sectionsData.sections.length > 0 ? (
          <SearchSections sections={sectionsData.sections} onCompareToggle={toggleCompare} compareIds={compareIds} />
        ) : (
          <div className="text-center py-24 bg-card rounded-2xl border border-border/40 shadow-sm">
            <Building2 className="w-16 h-16 mx-auto text-muted-foreground/30 mb-5" />
            <h3 className="text-xl font-semibold text-foreground">No properties found</h3>
            <p className="text-muted-foreground mt-2 max-w-sm mx-auto">We couldn't find any listings matching your criteria. Try adjusting your filters or search area.</p>
            <Button variant="outline" className="mt-6 rounded-lg font-medium" onClick={() => {
               setFilters({}); setUserCoords(null); setLocationDenied(false);
            }}>
              Clear Search
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-screen"><Loader2 className="w-8 h-8 animate-spin text-primary" /></div>}>
      <SearchPageContent />
    </Suspense>
  );
}
