"use client";

import Link from "next/link";
import Image from "next/image";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Heart,
  MapPin,
  BedDouble,
  Bath,
  Maximize2,
  Building2,
  CheckCircle2,
  Star,
  Image as ImageIcon,
  Clock
} from "lucide-react";
import type { Property } from "@/lib/types";
import { formatPrice, formatArea, getBedroomLabel } from "@/lib/format";
import { savedApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useState, useCallback } from "react";
import { formatDistanceToNow } from "date-fns";

interface PropertyCardProps {
  property: Property;
  onCompareToggle?: (id: number) => void;
  isCompareSelected?: boolean;
  onSaveToggle?: () => void;
}

export default function PropertyCard({
  property,
  onCompareToggle,
  isCompareSelected,
  onSaveToggle,
}: PropertyCardProps) {
  const { isAuthenticated } = useAuth();
  const [isSaved, setIsSaved] = useState(property.is_saved || false);
  const [savingInProgress, setSavingInProgress] = useState(false);

  const handleSave = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!isAuthenticated || savingInProgress) return;
      setSavingInProgress(true);
      try {
        if (isSaved) {
          await savedApi.unsaveProperty(property.id);
          setIsSaved(false);
        } else {
          await savedApi.saveProperty(property.id);
          setIsSaved(true);
        }
        onSaveToggle?.();
      } catch {
        // Keep the previous state when the persisted update fails.
      } finally {
        setSavingInProgress(false);
      }
    },
    [isAuthenticated, isSaved, property.id, savingInProgress, onSaveToggle]
  );

  const images = property.images || [];
  const primaryImage = images.length > 0 ? images[0].url : (property.image_urls ? property.image_urls.split(",")[0] : null);
  const imageCount = images.length || (property.image_urls ? property.image_urls.split(",").length : 0);

  const freshnessTime = property.last_verified_at 
    ? formatDistanceToNow(new Date(property.last_verified_at), { addSuffix: true }) 
    : (property.last_seen_at ? formatDistanceToNow(new Date(property.last_seen_at), { addSuffix: true }) : null);

  return (
    <Link href={`/properties/${property.id}`} className="block h-full outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-[1.25rem]">
      <Card className="group overflow-hidden border border-border/40 surface-raised hover:border-primary/30 hover:-translate-y-1 transition-all duration-300 cursor-pointer h-full flex flex-col rounded-[1.25rem]">
        <div className="relative h-56 bg-muted overflow-hidden">
          {primaryImage ? (
            <Image 
              src={primaryImage} 
              alt={property.title} 
              width={600}
              height={400}
              className="object-cover w-full h-full group-hover:scale-105 transition-transform duration-500 ease-out"
              unoptimized
            />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground/50 gap-2">
              <Building2 className="w-12 h-12" />
              <span className="text-xs font-medium">Photos unavailable</span>
            </div>
          )}

          {/* Badges */}
          <div className="absolute top-3 left-3 flex flex-col gap-1.5 items-start">
            {property.is_featured && (
              <Badge className="bg-amber-500/90 hover:bg-amber-500 text-white border-0 text-xs shadow-sm backdrop-blur-sm">
                <Star className="w-3 h-3 mr-1" />
                Featured
              </Badge>
            )}
            {property.verification_status === "verified" && (
              <Badge variant="secondary" className="bg-emerald-500/90 hover:bg-emerald-500 text-white border-0 text-xs shadow-sm backdrop-blur-sm">
                <CheckCircle2 className="w-3 h-3 mr-1" />
                Verified
              </Badge>
            )}
            {property.status && property.status !== 'active' && property.status !== 'unknown' && (
              <Badge variant="destructive" className="border-0 text-xs shadow-sm backdrop-blur-sm uppercase tracking-wider">
                {property.status}
              </Badge>
            )}
          </div>

          {/* Photo Count */}
          {imageCount > 0 && (
            <div className="absolute bottom-3 right-3 bg-black/60 backdrop-blur-md text-white text-[10px] font-medium px-2 py-1 rounded-md flex items-center gap-1 shadow-sm">
              <ImageIcon className="w-3 h-3" />
              {imageCount}
            </div>
          )}

          {/* Save button */}
          {isAuthenticated && (
            <button
              onClick={handleSave}
              className="absolute top-3 right-3 w-8 h-8 rounded-full bg-white/90 dark:bg-black/50 flex items-center justify-center shadow-sm hover:scale-110 transition-transform backdrop-blur-sm"
            >
              <Heart
                className={`w-4 h-4 transition-colors ${
                  isSaved ? "fill-red-500 text-red-500" : "text-muted-foreground"
                }`}
              />
            </button>
          )}

          {/* Gradient Overlay for text readability if price moved inside image */}
        </div>

        {/* Content */}
        <div className="p-5 flex flex-col flex-1">
          <div className="flex justify-between items-start gap-2 mb-1">
            <h3 className="font-semibold text-[15px] leading-tight line-clamp-2 text-foreground group-hover:text-primary transition-colors">
              {property.title}
            </h3>
          </div>
          
          <div className="mb-3">
             <p className="text-foreground font-bold text-xl tracking-tight">
              {formatPrice(property.price)}
              {property.listing_type === 'rent' && <span className="text-sm font-normal text-muted-foreground ml-1">/mo</span>}
            </p>
            {property.price_per_sqft && property.listing_type === 'sale' && (
              <p className="text-muted-foreground text-xs">
                ₹{Math.round(property.price_per_sqft).toLocaleString("en-IN")}/sq.ft
              </p>
            )}
          </div>

          <div className="flex items-center gap-1.5 text-muted-foreground mb-4">
            <MapPin className="w-3.5 h-3.5 shrink-0" />
            <span className="text-xs truncate">
              {property.locality ? `${property.locality}, ` : ""}
              {property.city}
            </span>
          </div>

          {/* Property specs */}
          <div className="flex items-center gap-4 text-[13px] text-muted-foreground mt-auto pb-4 border-b border-border/50">
            {property.bedrooms != null && (
              <div className="flex items-center gap-1.5">
                <BedDouble className="w-4 h-4" />
                <span>{getBedroomLabel(property.bedrooms)}</span>
              </div>
            )}
            {property.bathrooms != null && (
              <div className="flex items-center gap-1.5">
                <Bath className="w-4 h-4" />
                <span>{property.bathrooms} ba</span>
              </div>
            )}
            {property.area_sqft != null && (
              <div className="flex items-center gap-1.5">
                <Maximize2 className="w-4 h-4" />
                <span>{formatArea(property.area_sqft)}</span>
              </div>
            )}
          </div>

          <div className="pt-3 flex items-center justify-between">
             <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground/80">
                {freshnessTime ? (
                  <>
                    <Clock className="w-3 h-3" />
                    <span>Updated {freshnessTime}</span>
                  </>
                ) : (
                   <span>Source: {property.source || "Platform"}</span>
                )}
             </div>
             
             {property.builder_name && (
                <span className="text-[11px] text-muted-foreground/80 truncate max-w-[100px]">
                  by {property.builder_name}
                </span>
             )}
          </div>

          {/* Compare checkbox */}
          {onCompareToggle && (
            <div className="mt-3">
              <Button
                variant={isCompareSelected ? "default" : "secondary"}
                size="sm"
                className="w-full text-xs h-8 rounded-lg font-medium"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onCompareToggle(property.id);
                }}
              >
                {isCompareSelected ? "✓ Added to Compare" : "Add to Compare"}
              </Button>
            </div>
          )}
        </div>
      </Card>
    </Link>
  );
}
