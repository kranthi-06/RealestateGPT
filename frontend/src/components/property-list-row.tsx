"use client";

import Link from "next/link";
import {
  MapPin,
  BedDouble,
  Maximize2,
  Building2,
  Heart,
  ArrowRight,
  Navigation,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { AiScoreBadge } from "@/components/ai-score-badge";
import type { Property } from "@/lib/types";
import {
  formatPrice,
  formatArea,
  getBedroomLabel,
  getPropertyTypeLabel,
} from "@/lib/format";
import { savedApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";

interface PropertyListRowProps {
  property: Property;
  showDistance?: boolean;
  distanceKm?: number;
  nearbyFacilities?: string[];
  aiScore?: number;
  onCompareToggle?: (id: number) => void;
  isCompareSelected?: boolean;
  showCompare?: boolean;
  showSave?: boolean;
  className?: string;
}

const typeBadgeVariant: Record<string, "default" | "secondary" | "outline" | "success"> = {
  apartment: "default",
  villa: "success",
  house: "secondary",
  plot: "outline",
  pg: "outline",
  commercial: "secondary",
};

export function PropertyListRow({
  property,
  showDistance = false,
  distanceKm,
  nearbyFacilities,
  aiScore,
  onCompareToggle,
  isCompareSelected = false,
  showCompare = true,
  showSave = true,
  className,
}: PropertyListRowProps) {
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
      } catch {
        /* no-op */
      } finally {
        setSavingInProgress(false);
      }
    },
    [isAuthenticated, isSaved, property.id, savingInProgress]
  );

  const firstImage =
    property.images?.[0]?.url ??
    (typeof property.image_urls === "string" && property.image_urls
      ? property.image_urls.split(",")[0]
      : undefined);

  const locality = property.locality || property.city;
  const typeLabel = getPropertyTypeLabel(property.property_type);
  const bhk = property.bedrooms ? getBedroomLabel(property.bedrooms) : null;

  return (
    <article
      className={cn(
        "group relative flex flex-col gap-3 rounded-xl border border-border bg-card p-3.5 transition-all hover:border-primary/30 hover:shadow-sm sm:flex-row sm:items-stretch sm:gap-4",
        isCompareSelected && "border-primary/60 ring-1 ring-primary/20",
        className
      )}
    >
      {showCompare && (
        <button
          type="button"
          onClick={() => onCompareToggle?.(property.id)}
          aria-label={`Toggle compare for ${property.title}`}
          aria-pressed={isCompareSelected}
          className={cn(
            "absolute right-3 top-3 z-10 flex h-5 w-5 items-center justify-center rounded border transition-all",
            isCompareSelected
              ? "border-primary bg-primary text-primary-foreground"
              : "border-border bg-background text-transparent hover:border-primary/50 hover:text-muted-foreground"
          )}
        >
          <Check className="h-3 w-3" strokeWidth={3} />
        </button>
      )}

      {firstImage && (
        <div className="relative h-24 w-full shrink-0 overflow-hidden rounded-lg bg-slate-100 sm:h-auto sm:w-32">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={firstImage}
            alt={property.title}
            loading="lazy"
            className="h-full w-full object-cover"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col gap-2.5">
        <div className="flex flex-wrap items-center gap-1.5 pr-8 sm:pr-0">
          <Badge
            variant={typeBadgeVariant[property.property_type] ?? "default"}
            className="gap-1"
          >
            <Building2 className="h-3 w-3" />
            {typeLabel}
          </Badge>
          {bhk && (
            <Badge variant="outline" className="gap-1">
              <BedDouble className="h-3 w-3" />
              {bhk}
            </Badge>
          )}
          {showDistance && distanceKm != null && (
            <Badge variant="secondary" className="gap-1">
              <Navigation className="h-3 w-3" />
              {distanceKm < 1
                ? `${Math.round(distanceKm * 1000)} m`
                : `${distanceKm.toFixed(1)} km`}
            </Badge>
          )}
          {aiScore != null && <AiScoreBadge score={aiScore} />}
        </div>

        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h3 className="min-w-0 truncate text-sm font-semibold text-foreground sm:text-base">
            {property.title}
          </h3>
          <div className="text-base font-bold tabular-nums text-foreground sm:text-lg">
            {formatPrice(property.price, property.currency)}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {property.area_sqft != null && (
            <span className="inline-flex items-center gap-1">
              <Maximize2 className="h-3 w-3" />
              {formatArea(property.area_sqft)}
            </span>
          )}
          <span className="inline-flex items-center gap-1">
            <MapPin className="h-3 w-3" />
            <span className="truncate">{locality}</span>
            {property.city && property.locality ? ` · ${property.city}` : ""}
          </span>
        </div>

        {nearbyFacilities && nearbyFacilities.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {nearbyFacilities.slice(0, 4).map((f) => (
              <span
                key={f}
                className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700"
              >
                {f}
              </span>
            ))}
          </div>
        )}

        <div className="mt-auto flex items-center justify-between gap-2 pt-1">
          <div className="text-[11px] text-muted-foreground">
            {property.verification_status === "verified" ? (
              <Badge variant="success" className="px-1.5 py-0 text-[10px]">
                Verified
              </Badge>
            ) : (
              <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
                {property.verification_status || "Unverified"}
              </Badge>
            )}
            {property.price_per_sqft && property.currency && (
              <span className="ml-2 tabular-nums">
                ₹{Math.round(property.price_per_sqft).toLocaleString("en-IN")}/sq.ft
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            {showSave && isAuthenticated && (
              <Button
                variant="ghost"
                size="icon"
                onClick={handleSave}
                disabled={savingInProgress}
                aria-label={isSaved ? "Unsave property" : "Save property"}
                className="h-8 w-8"
              >
                <Heart
                  className={cn(
                    "h-4 w-4 transition-colors",
                    isSaved ? "fill-red-500 text-red-500" : "text-muted-foreground"
                  )}
                />
              </Button>
            )}
            <Button asChild size="sm" className="gap-1">
              <Link href={`/properties/${property.id}`}>
                View Details
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        </div>
      </div>
    </article>
  );
}

export default PropertyListRow;
