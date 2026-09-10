"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import PropertyCard from "@/components/property-card";
import { propertiesApi, savedApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Property } from "@/lib/types";
import {
  formatPrice, formatArea, formatPricePerSqft, getPropertyTypeLabel,
  getFurnishingLabel, capitalize,
} from "@/lib/format";
import {
  Heart, MapPin, BedDouble, Bath, Maximize2, Building2, CheckCircle2,
  Star, ArrowLeft, Layers, Calendar, Compass, Car, Shield, Info, Ruler,
} from "lucide-react";

export default function PropertyDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [property, setProperty] = useState<Property | null>(null);
  const [similar, setSimilar] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [isSaved, setIsSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const propertyId = Number(params.id);

  useEffect(() => {
    if (!propertyId) return;
    queueMicrotask(() => {
      setLoading(true);
      Promise.all([propertiesApi.get(propertyId), propertiesApi.getSimilar(propertyId)])
        .then(([prop, sim]) => { setProperty(prop); setIsSaved(prop.is_saved || false); setSimilar(sim); })
        .catch(console.error)
        .finally(() => setLoading(false));
    });
  }, [propertyId]);

  const handleSave = async () => {
    if (!isAuthenticated || saving) return;
    setSaving(true);
    try {
      if (isSaved) {
        await savedApi.unsaveProperty(propertyId);
        setIsSaved(false);
      } else {
        await savedApi.saveProperty(propertyId);
        setIsSaved(true);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Skeleton className="h-8 w-48 mb-6" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-6">
            <Skeleton className="h-80 w-full rounded-xl" />
            <Skeleton className="h-6 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-32 w-full" />
          </div>
          <div className="space-y-4">
            <Skeleton className="h-48 w-full rounded-xl" />
            <Skeleton className="h-32 w-full rounded-xl" />
          </div>
        </div>
      </div>
    );
  }

  if (!property) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center">
        <Building2 className="w-16 h-16 mx-auto text-muted-foreground/30 mb-4" />
        <h2 className="text-xl font-semibold">Property Not Found</h2>
        <p className="text-muted-foreground mt-2">This property may have been removed.</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push("/search")}>
          <ArrowLeft className="w-4 h-4 mr-2" /> Back to Search
        </Button>
      </div>
    );
  }

  const details = [
    { icon: BedDouble, label: "Bedrooms", value: property.bedrooms != null ? `${property.bedrooms} BHK` : null },
    { icon: Bath, label: "Bathrooms", value: property.bathrooms != null ? `${property.bathrooms}` : null },
    { icon: Maximize2, label: "Super Area", value: property.area_sqft ? formatArea(property.area_sqft) : null },
    { icon: Ruler, label: "Carpet Area", value: property.carpet_area_sqft ? formatArea(property.carpet_area_sqft) : null },
    { icon: Layers, label: "Floor", value: property.floor != null ? `${property.floor} of ${property.total_floors || "?"}` : null },
    { icon: Calendar, label: "Property Age", value: property.property_age != null ? `${property.property_age} years` : null },
    { icon: Compass, label: "Facing", value: property.facing },
    { icon: Car, label: "Parking", value: property.parking != null ? `${property.parking} spots` : null },
    { icon: Building2, label: "Type", value: getPropertyTypeLabel(property.property_type) },
    { icon: Info, label: "Furnishing", value: property.furnishing ? getFurnishingLabel(property.furnishing) : null },
    { icon: Shield, label: "Status", value: property.construction_status ? capitalize(property.construction_status) : null },
  ].filter((d) => d.value);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      {/* Back nav */}
      <button
        onClick={() => router.back()}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Hero Image */}
          <div className="relative h-72 sm:h-96 rounded-2xl overflow-hidden bg-gradient-to-br from-primary/10 via-accent to-secondary">
            <div className="absolute inset-0 flex items-center justify-center">
              <Building2 className="w-24 h-24 text-primary/15" />
            </div>
            <div className="absolute top-4 left-4 flex gap-2">
              {property.is_featured && (
                <Badge className="bg-amber-500 text-white border-0 shadow-md">
                  <Star className="w-3 h-3 mr-1" /> Featured
                </Badge>
              )}
              {property.verification_status === "verified" && (
                <Badge className="bg-emerald-500 text-white border-0 shadow-md">
                  <CheckCircle2 className="w-3 h-3 mr-1" /> Verified
                </Badge>
              )}
              {property.is_synthetic && (
                <Badge variant="outline" className="bg-white/80 text-xs">Demo Data</Badge>
              )}
            </div>
          </div>

          {/* Title & Location */}
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{property.title}</h1>
            <div className="flex items-center gap-1 mt-2 text-muted-foreground">
              <MapPin className="w-4 h-4" />
              <span>
                {property.address || property.locality || ""}{property.locality ? ", " : ""}
                {property.city}{property.state ? `, ${property.state}` : ""}
                {property.pincode ? ` - ${property.pincode}` : ""}
              </span>
            </div>
            {property.builder_name && (
              <p className="text-sm text-muted-foreground mt-1">
                by <span className="font-medium text-foreground">{property.builder_name}</span>
                {property.project_name && ` • ${property.project_name}`}
              </p>
            )}
          </div>

          {/* Description */}
          {property.description && (
            <Card className="p-5 border-border/60">
              <h2 className="font-semibold text-lg mb-3">About this Property</h2>
              <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">
                {property.description}
              </p>
            </Card>
          )}

          {/* Property Details Grid */}
          <Card className="p-5 border-border/60">
            <h2 className="font-semibold text-lg mb-4">Property Details</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              {details.map((d) => (
                <div key={d.label} className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                    <d.icon className="w-4 h-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">{d.label}</p>
                    <p className="text-sm font-medium">{d.value}</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Amenities */}
          {property.amenities.length > 0 && (
            <Card className="p-5 border-border/60">
              <h2 className="font-semibold text-lg mb-4">Amenities</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {property.amenities.map((amenity) => (
                  <div key={amenity.id} className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span>{amenity.name}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Price Card */}
          <Card className="p-5 border-border/60 sticky top-20">
            <div className="text-3xl font-bold text-gradient">
              {formatPrice(property.price)}
            </div>
            {property.price_per_sqft && (
              <p className="text-sm text-muted-foreground mt-1">
                {formatPricePerSqft(property.price_per_sqft)}
              </p>
            )}
            {property.maintenance_charge && (
              <p className="text-xs text-muted-foreground">
                + ₹{property.maintenance_charge.toLocaleString("en-IN")}/month maintenance
              </p>
            )}

            <Separator className="my-4" />

            {/* Quick specs */}
            <div className="flex items-center justify-around text-center">
              {property.bedrooms != null && (
                <div>
                  <p className="text-lg font-semibold">{property.bedrooms}</p>
                  <p className="text-xs text-muted-foreground">BHK</p>
                </div>
              )}
              {property.bathrooms != null && (
                <div>
                  <p className="text-lg font-semibold">{property.bathrooms}</p>
                  <p className="text-xs text-muted-foreground">Bath</p>
                </div>
              )}
              {property.area_sqft != null && (
                <div>
                  <p className="text-lg font-semibold">{Math.round(property.area_sqft)}</p>
                  <p className="text-xs text-muted-foreground">sq.ft</p>
                </div>
              )}
            </div>

            <Separator className="my-4" />

            {/* Actions */}
            <div className="space-y-2">
              {isAuthenticated ? (
                <Button
                  className={`w-full ${isSaved ? "" : "gradient-primary text-white border-0"}`}
                  variant={isSaved ? "outline" : "default"}
                  onClick={handleSave}
                  disabled={saving}
                >
                  <Heart className={`w-4 h-4 mr-2 ${isSaved ? "fill-red-500 text-red-500" : ""}`} />
                  {isSaved ? "Saved" : "Save Property"}
                </Button>
              ) : (
                <Link href="/auth/login" className="block">
                  <Button variant="outline" className="w-full">
                    <Heart className="w-4 h-4 mr-2" />
                    Sign in to Save
                  </Button>
                </Link>
              )}
              <Link href={`/compare?ids=${property.id}`} className="block">
                <Button variant="outline" className="w-full">
                  Compare with Others
                </Button>
              </Link>
            </div>
          </Card>

          {/* Info badge */}
          <Card className="p-4 border-border/60 bg-amber-50/50 dark:bg-amber-950/20 border-amber-200/50">
            <div className="flex gap-2">
              <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-medium text-amber-800 dark:text-amber-200">
                  AI Analysis Coming Soon
                </p>
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                  Price estimation, location intelligence, and AI recommendations will be available in Phase 2.
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>

      {/* Similar Properties */}
      {similar.length > 0 && (
        <div className="mt-12">
          <h2 className="text-xl font-bold mb-6">Similar Properties</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {similar.map((p) => (
              <PropertyCard key={p.id} property={p} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
