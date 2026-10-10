"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  MapPin,
  BedDouble,
  Bath,
  Maximize2,
  Building2,
  CheckCircle2,
  Star,
  Clock,
  ArrowRight,
  ExternalLink,
  Brain,
} from "lucide-react";
import type { Property } from "@/lib/types";
import { formatPrice, formatArea, getBedroomLabel, formatPricePerSqft } from "@/lib/format";
import { useAuth } from "@/lib/auth-context";
import { formatDistanceToNow } from "date-fns";
import { PropertyListRow } from "@/components/property-list-row";
import { PropertyActions } from "@/components/property-actions";

interface PropertyCardProps {
  property: Property;
  variant?: "list" | "grid" | "compact" | "list-row";
  onCompareToggle?: (id: number) => void;
  isCompareSelected?: boolean;
  showDistance?: boolean;
  distanceKm?: number;
  nearbyFacilities?: string[];
  aiScore?: number;
  showAiScore?: boolean;
}

const propertyTypeLabels: Record<string, string> = {
  apartment: "Apartment",
  house: "House",
  villa: "Villa",
  plot: "Plot",
  pg: "PG/Coliving",
  hotel: "Hotel",
  commercial: "Commercial",
};

export default function PropertyCard({
  property,
  variant = "list",
  onCompareToggle,
  isCompareSelected,
  showDistance = false,
  distanceKm,
  nearbyFacilities,
  aiScore,
  showAiScore = false,
}: PropertyCardProps) {
  const { isAuthenticated } = useAuth();

  if (variant === "list-row") {
    return (
      <PropertyListRow
        property={property}
        showDistance={showDistance}
        distanceKm={distanceKm}
        nearbyFacilities={nearbyFacilities}
        aiScore={aiScore}
        onCompareToggle={onCompareToggle}
        isCompareSelected={isCompareSelected}
      />
    );
  }

  const images = property.images || [];
  const rawPrimary = images.length > 0 ? images[0].url : (property.image_urls ? property.image_urls.split(",")[0] : null);
  const primaryImage = rawPrimary && (rawPrimary.startsWith("http://") || rawPrimary.startsWith("https://")) ? rawPrimary : null;

  const freshnessTime = property.last_verified_at
    ? formatDistanceToNow(new Date(property.last_verified_at), { addSuffix: true })
    : (property.last_seen_at ? formatDistanceToNow(new Date(property.last_seen_at), { addSuffix: true }) : null);

  const price = formatPrice(property.price, property.currency);
  const pricePerSqft = property.listing_type === 'sale' ? formatPricePerSqft(property.price_per_sqft, property.currency) : null;
  const propertyType = propertyTypeLabels[property.property_type?.toLowerCase()] || property.property_type;
  const listingType = property.listing_type === 'rent' ? 'Rent' : 'Buy';

  // List variant (primary) - horizontal compact card
  if (variant === "list") {
    return (
      <Link
        href={`/properties/${property.id}`}
        className="block group outline-none focus-visible:ring-2 focus-visible:ring-primary"
        aria-label={`View ${property.title} details`}
      >
        <article className="card-surface card-hover flex gap-4 p-4">
          {/* Thumbnail */}
          <div className="relative h-24 w-32 sm:w-36 flex-shrink-0 rounded-lg overflow-hidden bg-muted">
            {primaryImage ? (
              <img
                src={primaryImage}
                alt={property.title}
                className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-300"
                loading="lazy"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-muted-foreground/50">
                <Building2 className="w-8 h-8" />
              </div>
            )}
            {/* Badges */}
            <div className="absolute top-2 left-2 flex flex-col gap-1">
              {property.is_featured && (
                <Badge className="badge-warning" variant="default">
                  <Star className="w-2.5 h-2.5 mr-1" />
                  Featured
                </Badge>
              )}
              {property.verification_status === "verified" && (
                <Badge className="badge-success" variant="default">
                  <CheckCircle2 className="w-2.5 h-2.5 mr-1" />
                  Verified
                </Badge>
              )}
              {property.status && property.status !== 'active' && property.status !== 'unknown' && (
                <Badge className="badge-destructive" variant="default">
                  {property.status}
                </Badge>
              )}
            </div>
            {/* Save + Compare actions */}
            {isAuthenticated && (
              <div className="absolute right-2 top-2">
                <PropertyActions propertyId={property.id} title={property.title} variant="icon" />
              </div>
            )}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0 flex flex-col justify-between">
            {/* Header */}
            <div>
              <div className="flex items-start justify-between gap-2 mb-1">
                <h3 className="font-semibold text-base leading-snug line-clamp-1 text-foreground group-hover:text-primary transition-colors pr-4">
                  {property.title}
                </h3>
                {showAiScore && aiScore != null && (
                  <div className="flex items-center gap-1 px-2 py-1 rounded-lg bg-primary/10 text-primary text-xs font-semibold">
                    <Brain className="w-3 h-3" />
                    {aiScore}
                  </div>
                )}
              </div>

              {/* Meta tags */}
              <div className="flex flex-wrap items-center gap-2 mb-2 text-xs text-muted-foreground">
                <Badge variant="outline" className="gap-1 h-5 px-2">
                  {listingType}
                </Badge>
                <Badge variant="outline" className="gap-1 h-5 px-2">
                  {propertyType}
                </Badge>
                {property.bedrooms != null && (
                  <Badge variant="outline" className="gap-1 h-5 px-2">
                    <BedDouble className="w-2.5 h-2.5" />
                    {getBedroomLabel(property.bedrooms)}
                  </Badge>
                )}
              </div>

              {/* Price */}
              <div className="flex items-baseline gap-3 mb-2">
                <span className="text-xl font-bold text-foreground">{price}</span>
                {property.listing_type === 'rent' && <span className="text-sm text-muted-foreground">/month</span>}
                {pricePerSqft && <span className="text-sm text-muted-foreground">{pricePerSqft}</span>}
              </div>

              {/* Location + Distance */}
              <div className="flex items-center gap-3 text-sm text-muted-foreground mb-3">
                <span className="flex items-center gap-1 truncate">
                  <MapPin className="w-3.5 h-3.5 shrink-0" />
                  {property.locality ? `${property.locality}, ` : ""}{property.city}
                </span>
                {showDistance && distanceKm != null && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent text-accent-foreground font-medium">
                    {distanceKm.toFixed(1)} km
                  </span>
                )}
              </div>
            </div>

            {/* Bottom section */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-border/50">
              {/* Specs */}
              <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                {property.bedrooms != null && (
                  <span className="flex items-center gap-1">
                    <BedDouble className="w-3.5 h-3.5" />
                    {getBedroomLabel(property.bedrooms)}
                  </span>
                )}
                {property.bathrooms != null && (
                  <span className="flex items-center gap-1">
                    <Bath className="w-3.5 h-3.5" />
                    {property.bathrooms} ba
                  </span>
                )}
                {property.area_sqft != null && (
                  <span className="flex items-center gap-1">
                    <Maximize2 className="w-3.5 h-3.5" />
                    {formatArea(property.area_sqft)}
                  </span>
                )}
              </div>

              {/* Meta */}
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                {freshnessTime && (
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    Updated {freshnessTime}
                  </span>
                )}
                {property.builder_name && (
                  <span className="truncate max-w-[120px]">by {property.builder_name}</span>
                )}
                {property.source_url && (
                  <a
                    href={property.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 hover:text-primary transition-colors"
                    onClick={(e) => e.stopPropagation()}
                    aria-label="View original listing"
                  >
                    <ExternalLink className="w-3 h-3" />
                    Source
                  </a>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                  }}
                >
                  <ArrowRight className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          </div>
        </article>
      </Link>
    );
  }

  // Compact variant - minimal for dense lists
  if (variant === "compact") {
    return (
      <Link
        href={`/properties/${property.id}`}
        className="block group"
        aria-label={`View ${property.title} details`}
      >
        <div className="card-surface p-3 hover:bg-accent/50 transition-colors">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-1">
                <h4 className="font-medium text-sm leading-snug text-foreground group-hover:text-primary transition-colors truncate">
                  {property.title}
                </h4>
                {showAiScore && aiScore != null && (
                  <Badge className="badge-primary gap-1">
                    <Brain className="w-2.5 h-2.5" />
                    {aiScore}
                  </Badge>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline" className="h-4 px-1.5">{listingType}</Badge>
                <Badge variant="outline" className="h-4 px-1.5">{propertyType}</Badge>
                {property.bedrooms != null && (
                  <Badge variant="outline" className="gap-0.5 h-4 px-1.5">
                    <BedDouble className="w-2.5 h-2.5" />
                    {getBedroomLabel(property.bedrooms)}
                  </Badge>
                )}
                <span className="text-muted-foreground">{price}{property.listing_type === 'rent' ? '/mo' : ''}</span>
                {showDistance && distanceKm != null && (
                  <span className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-accent text-accent-foreground font-medium text-[10px]">
                    {distanceKm.toFixed(1)} km
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1">
              {isAuthenticated && (
                <PropertyActions propertyId={property.id} title={property.title} variant="compact" />
              )}
              {onCompareToggle && (
                <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
              )}
            </div>
          </div>
        </div>
      </Link>
    );
  }

  // Grid variant - card with image on top
  return (
    <Link
      href={`/properties/${property.id}`}
      className="block group outline-none focus-visible:ring-2 focus-visible:ring-primary"
      aria-label={`View ${property.title} details`}
    >
      <article className="card-surface card-hover flex flex-col h-full overflow-hidden">
        <div className="relative h-48 bg-muted overflow-hidden">
          {primaryImage ? (
            <img
              src={primaryImage}
              alt={property.title}
              className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-300"
              loading="lazy"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-muted-foreground/50">
              <Building2 className="w-10 h-10" />
            </div>
          )}
          <div className="absolute top-2 left-2 flex flex-col gap-1">
            {property.is_featured && <Badge className="badge-warning"><Star className="w-2.5 h-2.5 mr-1" />Featured</Badge>}
            {property.verification_status === "verified" && <Badge className="badge-success"><CheckCircle2 className="w-2.5 h-2.5 mr-1" />Verified</Badge>}
          </div>
          {isAuthenticated && (
            <div className="absolute top-2 right-2">
              <PropertyActions propertyId={property.id} title={property.title} variant="icon" />
            </div>
          )}
        </div>
        <div className="p-4 flex flex-col flex-1">
          <h3 className="font-semibold text-base leading-snug line-clamp-2 text-foreground group-hover:text-primary transition-colors mb-2">
            {property.title}
          </h3>
          <div className="flex flex-wrap items-center gap-1.5 mb-2 text-xs">
            <Badge variant="outline" className="h-4 px-1.5">{listingType}</Badge>
            <Badge variant="outline" className="h-4 px-1.5">{propertyType}</Badge>
            {property.bedrooms != null && <Badge variant="outline" className="gap-0.5 h-4 px-1.5"><BedDouble className="w-2.5 h-2.5" />{getBedroomLabel(property.bedrooms)}</Badge>}
          </div>
          <div className="flex items-baseline gap-2 mb-2">
            <span className="text-lg font-bold text-foreground">{price}</span>
            {property.listing_type === 'rent' && <span className="text-sm text-muted-foreground">/month</span>}
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3">
            <MapPin className="w-3.5 h-3.5 shrink-0" />
            <span className="truncate">{property.locality ? `${property.locality}, ` : ""}{property.city}</span>
            {showDistance && distanceKm != null && <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent text-accent-foreground font-medium">{distanceKm.toFixed(1)} km</span>}
          </div>
          <div className="flex items-center gap-3 text-sm text-muted-foreground mt-auto pt-3 border-t border-border/50">
            {property.bedrooms != null && <span className="flex items-center gap-1"><BedDouble className="w-3.5 h-3.5" />{getBedroomLabel(property.bedrooms)}</span>}
            {property.bathrooms != null && <span className="flex items-center gap-1"><Bath className="w-3.5 h-3.5" />{property.bathrooms} ba</span>}
            {property.area_sqft != null && <span className="flex items-center gap-1"><Maximize2 className="w-3.5 h-3.5" />{formatArea(property.area_sqft)}</span>}
          </div>
        </div>
      </article>
    </Link>
  );
}