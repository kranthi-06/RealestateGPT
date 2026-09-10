"use client";

import Link from "next/link";
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
} from "lucide-react";
import type { Property } from "@/lib/types";
import { formatPrice, formatArea, getBedroomLabel, getPropertyTypeLabel, getFurnishingLabel } from "@/lib/format";
import { savedApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useState, useCallback } from "react";

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

  return (
    <Link href={`/properties/${property.id}`}>
      <Card className="group overflow-hidden border border-border/60 hover:border-primary/30 hover:shadow-xl transition-all duration-300 cursor-pointer h-full flex flex-col">
        {/* Image placeholder */}
        <div className="relative h-48 bg-gradient-to-br from-primary/10 via-accent to-secondary overflow-hidden">
          <div className="absolute inset-0 flex items-center justify-center">
            <Building2 className="w-16 h-16 text-primary/20" />
          </div>

          {/* Badges */}
          <div className="absolute top-3 left-3 flex gap-1.5">
            {property.is_featured && (
              <Badge className="bg-amber-500 text-white border-0 text-xs shadow-md">
                <Star className="w-3 h-3 mr-1" />
                Featured
              </Badge>
            )}
            {property.verification_status === "verified" && (
              <Badge variant="secondary" className="bg-emerald-500/90 text-white border-0 text-xs shadow-md">
                <CheckCircle2 className="w-3 h-3 mr-1" />
                Verified
              </Badge>
            )}
          </div>

          {/* Save button */}
          {isAuthenticated && (
            <button
              onClick={handleSave}
              className="absolute top-3 right-3 w-8 h-8 rounded-full bg-white/90 dark:bg-black/50 flex items-center justify-center shadow-md hover:scale-110 transition-transform"
            >
              <Heart
                className={`w-4 h-4 transition-colors ${
                  isSaved ? "fill-red-500 text-red-500" : "text-muted-foreground"
                }`}
              />
            </button>
          )}

          {/* Price overlay */}
          <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent p-3 pt-8">
            <p className="text-white font-bold text-xl tracking-tight">
              {formatPrice(property.price)}
            </p>
            {property.price_per_sqft && (
              <p className="text-white/70 text-xs">
                ₹{Math.round(property.price_per_sqft).toLocaleString("en-IN")}/sq.ft
              </p>
            )}
          </div>
        </div>

        {/* Content */}
        <div className="p-4 flex flex-col flex-1">
          <h3 className="font-semibold text-sm leading-tight line-clamp-2 group-hover:text-primary transition-colors">
            {property.title}
          </h3>

          <div className="flex items-center gap-1 mt-2 text-muted-foreground">
            <MapPin className="w-3.5 h-3.5 shrink-0" />
            <span className="text-xs truncate">
              {property.locality ? `${property.locality}, ` : ""}
              {property.city}
            </span>
          </div>

          {/* Property specs */}
          <div className="flex items-center gap-3 mt-3 text-xs text-muted-foreground">
            {property.bedrooms != null && (
              <div className="flex items-center gap-1">
                <BedDouble className="w-3.5 h-3.5" />
                <span>{getBedroomLabel(property.bedrooms)}</span>
              </div>
            )}
            {property.bathrooms != null && (
              <div className="flex items-center gap-1">
                <Bath className="w-3.5 h-3.5" />
                <span>{property.bathrooms} Bath</span>
              </div>
            )}
            {property.area_sqft != null && (
              <div className="flex items-center gap-1">
                <Maximize2 className="w-3.5 h-3.5" />
                <span>{formatArea(property.area_sqft)}</span>
              </div>
            )}
          </div>

          {/* Tags */}
          <div className="flex flex-wrap gap-1.5 mt-3">
            <Badge variant="outline" className="text-xs px-2 py-0.5 font-normal">
              {getPropertyTypeLabel(property.property_type)}
            </Badge>
            {property.furnishing && (
              <Badge variant="outline" className="text-xs px-2 py-0.5 font-normal">
                {getFurnishingLabel(property.furnishing)}
              </Badge>
            )}
          </div>

          {/* Builder */}
          {property.builder_name && (
            <p className="text-xs text-muted-foreground mt-auto pt-3 border-t border-border/40">
              by {property.builder_name}
            </p>
          )}

          {/* Compare checkbox */}
          {onCompareToggle && (
            <div className="mt-2 pt-2 border-t border-border/40">
              <Button
                variant={isCompareSelected ? "default" : "outline"}
                size="sm"
                className="w-full text-xs h-7"
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
