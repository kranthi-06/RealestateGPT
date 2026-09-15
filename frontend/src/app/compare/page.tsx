"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { propertiesApi } from "@/lib/api";
import type { Property } from "@/lib/types";
import { formatPrice, formatArea, formatPricePerSqft, getPropertyTypeLabel, getFurnishingLabel, getBedroomLabel } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import {
  GitCompareArrows, Search, X, MapPin, CheckCircle2, AlertCircle
} from "lucide-react";
import PropertyCard from "@/components/property-card";

function ComparePageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const idsParam = searchParams.get("ids");
  
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchProperties = async () => {
      if (!idsParam) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      
      try {
        const ids = idsParam.split(",").map(id => parseInt(id.trim())).filter(id => !isNaN(id));
        
        if (ids.length === 0) {
          setLoading(false);
          return;
        }

        // Single bounded round-trip for the full comparison set.
        const fetchedProperties = await propertiesApi.bulk(ids);
        setProperties(fetchedProperties);
      } catch {
        setError("Failed to fetch properties for comparison.");
      } finally {
        setLoading(false);
      }
    };

    fetchProperties();
  }, [idsParam]);

  const removeProperty = (idToRemove: number) => {
    const newIds = properties.map(p => p.id).filter(id => id !== idToRemove);
    if (newIds.length > 0) {
      router.push(`/compare?ids=${newIds.join(",")}`);
    } else {
      router.push("/compare");
    }
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-10">
        <Skeleton className="h-10 w-64 mb-8" />
        <div className="flex gap-6 overflow-x-auto pb-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="min-w-[300px] flex-1">
              <Skeleton className="h-[400px] w-full rounded-xl" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!idsParam || properties.length === 0) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-20 text-center">
        <GitCompareArrows className="w-16 h-16 mx-auto text-muted-foreground/30 mb-4" />
        <h2 className="text-2xl font-bold">Compare Properties</h2>
        <p className="text-muted-foreground mt-2 max-w-md mx-auto">
          Select properties from the search page to compare their features, prices, and locations side-by-side.
        </p>
        <Link href="/search">
          <Button className="mt-6 gradient-primary text-white border-0">
            <Search className="w-4 h-4 mr-2" />
            Find Properties to Compare
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Property Comparison</h1>
          <p className="text-muted-foreground mt-1">
            Comparing {properties.length} properties side-by-side
          </p>
        </div>
        <div className="flex gap-2">
          {properties.length < 4 && (
            <Link href="/search">
              <Button variant="outline" className="gap-2">
                <Search className="w-4 h-4" />
                Add Another
              </Button>
            </Link>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-destructive/10 text-destructive p-4 rounded-lg mb-6 flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          {error}
        </div>
      )}

      {/* Comparison Table / Grid */}
      <ScrollArea className="w-full rounded-xl border border-border/60 bg-card shadow-sm pb-4">
        <div className="flex min-w-max p-4 gap-6">
          {/* Attributes Label Column - Hidden on mobile, visible on lg screens */}
          <div className="hidden lg:flex flex-col w-48 shrink-0 py-4 gap-y-4 font-medium text-sm text-muted-foreground pt-[320px]">
             <div className="h-10 flex items-center">Price</div>
             <div className="h-10 flex items-center">Price / sq.ft</div>
             <div className="h-10 flex items-center">Location</div>
             <div className="h-10 flex items-center">Type</div>
             <div className="h-10 flex items-center">Bedrooms</div>
             <div className="h-10 flex items-center">Bathrooms</div>
             <div className="h-10 flex items-center">Area</div>
             <div className="h-10 flex items-center">Status</div>
             <div className="h-10 flex items-center">Furnishing</div>
             <div className="h-10 flex items-center">Age</div>
             <div className="h-10 flex items-center">Facing</div>
          </div>

          {/* Property Columns */}
          {properties.map((property) => (
            <div key={property.id} className="flex flex-col w-[300px] sm:w-[350px] shrink-0">
              {/* Property Card Header */}
              <div className="relative mb-6">
                <button 
                  onClick={() => removeProperty(property.id)}
                  className="absolute -top-2 -right-2 z-10 w-8 h-8 rounded-full bg-background border border-border shadow-md flex items-center justify-center hover:bg-destructive hover:text-white transition-colors"
                  title="Remove from comparison"
                >
                  <X className="w-4 h-4" />
                </button>
                <PropertyCard property={property} />
              </div>

              {/* Attributes (Mobile inline labels, Desktop aligned) */}
              <div className="flex flex-col gap-y-4 text-sm px-2">
                <div className="h-10 flex items-center border-b border-border/50">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Price:</span>
                  <span className="font-bold text-base">{formatPrice(property.price)}</span>
                </div>
                
                <div className="h-10 flex items-center border-b border-border/50">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Price/sqft:</span>
                  {property.price_per_sqft ? formatPricePerSqft(property.price_per_sqft) : "N/A"}
                </div>
                
                <div className="h-10 flex items-center border-b border-border/50 truncate">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Location:</span>
                  <MapPin className="w-3.5 h-3.5 mr-1 text-muted-foreground shrink-0" />
                  <span className="truncate">{property.locality || property.city}</span>
                </div>

                <div className="h-10 flex items-center border-b border-border/50">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Type:</span>
                  <Badge variant="secondary" className="font-normal">{getPropertyTypeLabel(property.property_type)}</Badge>
                </div>

                <div className="h-10 flex items-center border-b border-border/50">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Bedrooms:</span>
                  {getBedroomLabel(property.bedrooms)}
                </div>

                <div className="h-10 flex items-center border-b border-border/50">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Bathrooms:</span>
                  {property.bathrooms ? `${property.bathrooms} Bath` : "N/A"}
                </div>

                <div className="h-10 flex items-center border-b border-border/50">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Area:</span>
                  {property.area_sqft ? formatArea(property.area_sqft) : "N/A"}
                </div>

                <div className="h-10 flex items-center border-b border-border/50">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Status:</span>
                  {property.construction_status ? <span className="capitalize">{property.construction_status}</span> : "N/A"}
                </div>

                <div className="h-10 flex items-center border-b border-border/50">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Furnishing:</span>
                  {property.furnishing ? getFurnishingLabel(property.furnishing) : "N/A"}
                </div>

                <div className="h-10 flex items-center border-b border-border/50">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Age:</span>
                  {property.property_age != null ? `${property.property_age} years` : "New"}
                </div>

                <div className="h-10 flex items-center border-b border-border/50">
                  <span className="lg:hidden text-muted-foreground mr-2 font-medium">Facing:</span>
                  {property.facing || "N/A"}
                </div>

                {/* Amenities List */}
                <div className="mt-4 pt-4">
                  <span className="font-medium mb-3 block">Top Amenities</span>
                  <div className="flex flex-col gap-2">
                    {property.amenities.slice(0, 5).map(a => (
                      <div key={a.id} className="flex items-center text-xs">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 mr-2 shrink-0" />
                        <span className="truncate">{a.name}</span>
                      </div>
                    ))}
                    {property.amenities.length > 5 && (
                      <div className="text-xs text-muted-foreground pl-5 pt-1">
                        + {property.amenities.length - 5} more
                      </div>
                    )}
                    {property.amenities.length === 0 && (
                      <div className="text-xs text-muted-foreground">None listed</div>
                    )}
                  </div>
                </div>

              </div>
            </div>
          ))}
        </div>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center py-20"><Skeleton className="w-full h-96 max-w-4xl mx-auto rounded-xl" /></div>}>
      <ComparePageContent />
    </Suspense>
  );
}
