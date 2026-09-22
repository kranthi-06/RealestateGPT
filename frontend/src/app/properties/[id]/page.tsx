"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import PropertyCard from "@/components/property-card";
import { NearbyPlaces } from "@/components/nearby-places";
import { RealEstateMap } from "@/components/real-estate-map";
import { FinanceInsights } from "@/components/finance-insights";
import { PriceIntelligencePanel } from "@/components/price-intelligence-panel";
import { propertiesApi, savedApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { LivePlace, Property } from "@/lib/types";
import { formatDistanceToNow } from "date-fns";
import {
  formatPrice, formatArea, formatPricePerSqft, getPropertyTypeLabel,
  getFurnishingLabel, capitalize,
} from "@/lib/format";
import {
  Heart, MapPin, BedDouble, Bath, Maximize2, Building2, CheckCircle2,
  Star, ArrowLeft, Layers, Calendar, Compass, Car, Shield, Info, Ruler, Image as ImageIcon,
  ChevronLeft, ChevronRight, X
} from "lucide-react";

export default function PropertyDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [property, setProperty] = useState<Property | null>(null);
  const [nearbyPlaces, setNearbyPlaces] = useState<LivePlace[]>([]);
  const [similar, setSimilar] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [isSaved, setIsSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  
  // Gallery state
  const [activeImageIdx, setActiveImageIdx] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const propertyId = Number(params.id);

  useEffect(() => {
    if (!propertyId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    Promise.all([propertiesApi.get(propertyId), propertiesApi.getSimilar(propertyId)])
      .then(([prop, sim]) => { setProperty(prop); setIsSaved(prop.is_saved || false); setSimilar(sim); })
      .catch(console.error)
      .finally(() => setLoading(false));
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
            <Skeleton className="h-96 w-full rounded-2xl" />
            <Skeleton className="h-8 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-48 w-full rounded-2xl" />
          </div>
          <div className="space-y-4">
            <Skeleton className="h-[400px] w-full rounded-2xl" />
          </div>
        </div>
      </div>
    );
  }

  if (!property) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-32 text-center">
        <Building2 className="w-20 h-20 mx-auto text-muted-foreground/20 mb-6" />
        <h2 className="text-2xl font-bold tracking-tight">Property Not Found</h2>
        <p className="text-muted-foreground mt-2 mb-8">This property may have been removed or is no longer available.</p>
        <Button variant="default" size="lg" onClick={() => router.push("/search")}>
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
    { icon: Shield, label: "Construction", value: property.construction_status ? capitalize(property.construction_status) : null },
  ].filter((d) => d.value);
  
  const images = property.images || [];
  // For migration compat
  if (images.length === 0 && property.image_urls) {
      property.image_urls.split(",").forEach(url => {
          images.push({ url: url.trim(), category: "other", display_order: 0, rights_status: "unknown", fetched_at: "" });
      });
  }
  const hasImages = images.length > 0;
  
  const freshnessTime = property.last_verified_at 
    ? formatDistanceToNow(new Date(property.last_verified_at), { addSuffix: true }) 
    : (property.last_seen_at ? formatDistanceToNow(new Date(property.last_seen_at), { addSuffix: true }) : null);

  return (
    <div className="bg-background min-h-screen pb-24">
      {/* Lightbox */}
      {lightboxOpen && hasImages && (
        <div className="fixed inset-0 z-50 bg-black/95 flex flex-col">
          <div className="p-4 flex justify-between items-center text-white">
            <span className="text-sm font-medium">{activeImageIdx + 1} / {images.length}</span>
            <button onClick={() => setLightboxOpen(false)} className="p-2 hover:bg-white/10 rounded-full transition-colors">
              <X className="w-6 h-6" />
            </button>
          </div>
          <div className="flex-1 relative flex items-center justify-center">
             <button 
               className="absolute left-4 p-3 rounded-full bg-black/50 text-white hover:bg-black/80 transition-colors"
               onClick={() => setActiveImageIdx(prev => prev > 0 ? prev - 1 : images.length - 1)}
             >
               <ChevronLeft className="w-8 h-8" />
             </button>
             <Image 
               src={images[activeImageIdx].url} 
               alt={images[activeImageIdx].alt || property.title}
               width={1200}
               height={800}
               unoptimized
               className="max-h-full max-w-full object-contain" 
             />
             <button 
               className="absolute right-4 p-3 rounded-full bg-black/50 text-white hover:bg-black/80 transition-colors"
               onClick={() => setActiveImageIdx(prev => prev < images.length - 1 ? prev + 1 : 0)}
             >
               <ChevronRight className="w-8 h-8" />
             </button>
          </div>
          {/* Thumbnails below lightbox */}
          <div className="h-24 p-2 flex gap-2 overflow-x-auto justify-center bg-black/50 mt-auto">
             {images.map((img, idx) => (
               <Image 
                 key={idx} 
                 src={img.url} 
                 alt="Thumbnail" 
                 width={100}
                 height={100}
                 unoptimized
                 onClick={() => setActiveImageIdx(idx)}
                 className={`h-full w-24 object-cover cursor-pointer rounded border-2 transition-all ${idx === activeImageIdx ? 'border-primary opacity-100' : 'border-transparent opacity-50 hover:opacity-100'}`}
               />
             ))}
          </div>
        </div>
      )}

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <button
          onClick={() => router.back()}
          className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-primary mb-6 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to search
        </button>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
          <div className="lg:col-span-2 space-y-8">
            {/* Gallery Section */}
            <div className="space-y-3">
              <div 
                className="relative h-[40vh] sm:h-[60vh] rounded-2xl overflow-hidden bg-muted cursor-pointer group"
                onClick={() => { if(hasImages) setLightboxOpen(true); }}
              >
                {hasImages ? (
                   <>
                     <Image 
                       src={images[activeImageIdx].url} 
                       alt={property.title} 
                       width={1200}
                       height={800}
                       unoptimized
                       className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-[1.02]" 
                     />
                     <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
                     <div className="absolute bottom-4 right-4 bg-black/70 backdrop-blur-md text-white text-sm font-medium px-4 py-2 rounded-lg flex items-center gap-2 shadow-lg">
                       <ImageIcon className="w-4 h-4" />
                       View all {images.length} photos
                     </div>
                   </>
                ) : (
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground/40 gap-3">
                    <Building2 className="w-20 h-20" />
                    <span className="font-medium text-lg">Photos unavailable</span>
                  </div>
                )}
                <div className="absolute top-4 left-4 flex gap-2 flex-col items-start">
                  {property.is_featured && (
                    <Badge className="bg-amber-500/90 backdrop-blur-sm text-white border-0 shadow-sm text-sm px-3 py-1">
                      <Star className="w-3.5 h-3.5 mr-1.5" /> Featured
                    </Badge>
                  )}
                  {property.verification_status === "verified" && (
                    <Badge className="bg-emerald-500/90 backdrop-blur-sm text-white border-0 shadow-sm text-sm px-3 py-1">
                      <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" /> Verified
                    </Badge>
                  )}
                </div>
              </div>
              
              {/* Thumbnail strip */}
              {images.length > 1 && (
                <div className="flex gap-3 overflow-x-auto pb-2 snap-x">
                   {images.slice(0, 6).map((img, idx) => (
                     <div 
                       key={idx} 
                       className={`relative h-20 w-32 shrink-0 rounded-xl overflow-hidden cursor-pointer snap-start ${idx === activeImageIdx ? 'ring-2 ring-primary ring-offset-2' : 'opacity-70 hover:opacity-100 transition-opacity'}`}
                       onClick={() => setActiveImageIdx(idx)}
                     >
                       <Image src={img.url} alt="thumbnail" width={150} height={100} unoptimized className="w-full h-full object-cover" />
                     </div>
                   ))}
                   {images.length > 6 && (
                     <div 
                       className="relative h-20 w-32 shrink-0 rounded-xl overflow-hidden cursor-pointer snap-start bg-muted flex items-center justify-center border"
                       onClick={() => { setActiveImageIdx(6); setLightboxOpen(true); }}
                     >
                       <span className="text-sm font-medium">+{images.length - 6} more</span>
                     </div>
                   )}
                </div>
              )}
            </div>

            {/* Title & Metadata */}
            <div>
              <div className="flex items-start justify-between gap-4">
                 <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-foreground">{property.title}</h1>
              </div>
              
              <div className="flex items-center gap-1.5 mt-3 text-muted-foreground/80 text-sm">
                <MapPin className="w-4 h-4" />
                <span>
                  {property.address || property.locality || ""}{property.locality ? ", " : ""}
                  {property.city}{property.state ? `, ${property.state}` : ""}
                  {property.pincode ? ` - ${property.pincode}` : ""}
                </span>
              </div>
              
              <div className="flex items-center gap-4 mt-4 flex-wrap">
                 {property.status && property.status !== 'unknown' && (
                    <Badge variant={property.status === 'active' ? 'default' : 'secondary'} className="uppercase tracking-wider font-bold">
                       {property.status}
                    </Badge>
                 )}
                 {freshnessTime ? (
                    <span className="text-sm text-muted-foreground bg-muted px-3 py-1 rounded-full">
                      Verified {freshnessTime}
                    </span>
                 ) : (
                    <span className="text-sm text-muted-foreground/80 bg-muted px-3 py-1 rounded-full">
                      Availability not recently verified
                    </span>
                 )}
                 {property.builder_name && (
                   <span className="text-sm text-muted-foreground">
                     by <span className="font-semibold text-foreground">{property.builder_name}</span>
                   </span>
                 )}
              </div>
            </div>

            <Separator className="bg-border/50" />

            {/* Description */}
            {property.description && (
              <section>
                <h2 className="text-xl font-bold mb-4 tracking-tight">About this Property</h2>
                <div className="text-[15px] text-muted-foreground leading-relaxed whitespace-pre-line">
                  {property.description}
                </div>
              </section>
            )}

            {/* Key Details */}
            <section>
              <h2 className="text-xl font-bold mb-5 tracking-tight">Key Details</h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-y-6 gap-x-4">
                {details.map((d) => (
                  <div key={d.label} className="flex flex-col gap-1">
                    <div className="flex items-center gap-2 text-muted-foreground mb-1">
                      <d.icon className="w-4 h-4" />
                      <span className="text-sm">{d.label}</span>
                    </div>
                    <span className="font-semibold text-foreground">{d.value}</span>
                  </div>
                ))}
              </div>
            </section>

            <Separator className="bg-border/50" />

            {/* Amenities */}
            {property.amenities.length > 0 && (
              <section>
                <h2 className="text-xl font-bold mb-5 tracking-tight">Amenities</h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-y-4 gap-x-4">
                  {property.amenities.map((amenity) => (
                    <div key={amenity.id} className="flex items-center gap-3">
                      <div className="p-2 rounded-full bg-emerald-500/10 text-emerald-600">
                        <CheckCircle2 className="w-4 h-4" />
                      </div>
                      <span className="text-[15px] font-medium text-foreground/80">{amenity.name}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Location & Map */}
            <section>
              <div className="mb-5 flex justify-between items-end">
                <div>
                  <h2 className="text-xl font-bold tracking-tight">Location Intelligence</h2>
                  <p className="mt-1 text-sm text-muted-foreground">Explore actual POIs and distances using OpenStreetMap.</p>
                </div>
              </div>
              <div className="rounded-2xl overflow-hidden border shadow-sm">
                <RealEstateMap markers={[
                  { id: property.id, latitude: property.latitude, longitude: property.longitude, title: property.title, kind: "property" },
                  ...nearbyPlaces.map((place) => ({ id: place.place_id || place.name, latitude: place.latitude, longitude: place.longitude, title: place.name, subtitle: place.distance_km != null ? `${place.distance_km.toFixed(1)} km` : undefined, kind: "place" as const })),
                ]} />
              </div>
              <div className="mt-6 bg-card rounded-2xl border shadow-sm p-1">
                <NearbyPlaces propertyId={property.id} onPlacesChange={setNearbyPlaces} />
              </div>
            </section>
          </div>

          {/* Sticky Sidebar */}
          <div className="space-y-6">
            <Card className="p-6 border shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl sticky top-24">
              <div className="mb-2">
                <span className="text-3xl font-extrabold text-foreground tracking-tight">
                  {formatPrice(property.price)}
                </span>
                {property.listing_type === 'rent' && <span className="text-muted-foreground ml-1">/ month</span>}
              </div>
              
              {property.price_per_sqft && property.listing_type === 'sale' && (
                <p className="text-[15px] text-muted-foreground font-medium">
                  {formatPricePerSqft(property.price_per_sqft)}
                </p>
              )}
              
              {property.maintenance_charge && (
                <div className="mt-4 p-3 bg-muted rounded-xl flex justify-between items-center text-sm">
                  <span className="text-muted-foreground">Maintenance</span>
                  <span className="font-semibold">+ ₹{property.maintenance_charge.toLocaleString("en-IN")}/mo</span>
                </div>
              )}

              <Separator className="my-6" />

              <div className="space-y-3">
                {isAuthenticated ? (
                  <Button
                    size="lg"
                    className={`w-full text-base font-semibold rounded-xl h-12 ${isSaved ? "bg-muted text-foreground hover:bg-muted/80 border" : "gradient-primary text-white border-0 shadow-md"}`}
                    variant={isSaved ? "outline" : "default"}
                    onClick={handleSave}
                    disabled={saving}
                  >
                    <Heart className={`w-5 h-5 mr-2 ${isSaved ? "fill-red-500 text-red-500" : ""}`} />
                    {isSaved ? "Saved" : "Save Property"}
                  </Button>
                ) : (
                  <Link href="/auth/login" className="block">
                    <Button variant="outline" size="lg" className="w-full text-base font-semibold rounded-xl h-12 border-2">
                      <Heart className="w-5 h-5 mr-2 text-muted-foreground" />
                      Sign in to Save
                    </Button>
                  </Link>
                )}
                <Link href={`/compare?ids=${property.id}`} className="block">
                  <Button variant="secondary" size="lg" className="w-full text-base font-semibold rounded-xl h-12">
                    Compare with Others
                  </Button>
                </Link>
                
                <div className="mt-4 pt-4 border-t text-center">
                  <p className="text-xs text-muted-foreground">
                    Source: <span className="font-medium">{property.source || "Platform"}</span>
                  </p>
                  {property.source_url && (
                    <a href={property.source_url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline mt-1 block">
                      View original listing
                    </a>
                  )}
                </div>
              </div>
            </Card>

            <FinanceInsights propertyId={property.id} listedPrice={property.price} />
            
            {/* Real price intelligence computed only from stored, observed history */}
            <PriceIntelligencePanel
              propertyId={property.id}
              listingType={property.listing_type}
            />
          </div>
        </div>

        {/* Similar Properties */}
        {similar.length > 0 && (
          <div className="mt-16 pt-10 border-t">
            <h2 className="text-2xl font-bold mb-8 tracking-tight">Similar Properties</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {similar.slice(0,4).map((p) => (
                <PropertyCard key={p.id} property={p} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
