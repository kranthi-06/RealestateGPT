"use client";

import Link from "next/link";
import Image from "next/image";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Building2,
  BedDouble,
  MapPin,
  ExternalLink,
  Globe2,
  Clock,
  Heart,
} from "lucide-react";
import type { WebDiscoveryCard as WebDiscoveryCardData } from "@/lib/types";
import { formatPrice, getBedroomLabel } from "@/lib/format";
import { discoveryApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useState, useCallback } from "react";

/**
 * Premium card for WEB-DISCOVERED properties.
 *
 * Visually and semantically distinct from verified inventory:
 * - "WEB DISCOVERY" badge (never the verified checkmark)
 * - Source name + discovery freshness (never "Updated X ago")
 * - "View original listing" external CTA that preserves the returned URL
 */
export default function WebDiscoveryCard({
  discovery,
  onSaveToggle,
}: {
  discovery: WebDiscoveryCardData;
  onSaveToggle?: () => void;
}) {
  const { isAuthenticated } = useAuth();
  const [isSaved, setIsSaved] = useState(discovery.saved || false);
  const [savingInProgress, setSavingInProgress] = useState(false);

  const handleSave = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!isAuthenticated || savingInProgress) return;
      setSavingInProgress(true);
      try {
        if (isSaved) {
          await discoveryApi.unsave(discovery.id);
          setIsSaved(false);
        } else {
          await discoveryApi.save(discovery.id);
          setIsSaved(true);
        }
        onSaveToggle?.();
      } catch {
        // keep previous state when the persisted update fails
      } finally {
        setSavingInProgress(false);
      }
    },
    [isAuthenticated, isSaved, discovery.id, savingInProgress, onSaveToggle]
  );

  const area = discovery.area || discovery.area_sqft;
  const sourceLabel =
    discovery.source_name || discovery.source_domain || "Web source";

  return (
    <Card className="group overflow-hidden border border-amber-300/30 surface-raised hover:border-amber-400/40 hover:-translate-y-1 transition-all duration-300 h-full flex flex-col rounded-[1.25rem]">
      {/* Image / neutral no-photo state */}
      <div className="relative h-48 bg-muted overflow-hidden">
        {discovery.image_url ? (
          <Image
            src={discovery.image_url}
            alt={discovery.title}
            width={600}
            height={400}
            className="object-cover w-full h-full"
            unoptimized
          />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground/50 gap-2">
            <Building2 className="h-12 w-12" />
            <span className="text-xs font-medium">No photo available</span>
          </div>
        )}
        {/* Badge: web discovery, never "verified" */}
        <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
          <Badge variant="secondary" className="rounded-md bg-amber-500/15 text-amber-800 text-[10px] font-semibold">
            <Globe2 className="h-3 w-3" />
            WEB DISCOVERY
          </Badge>
        </div>
      </div>
      {/* Body */}
      <Link href={`/discoveries/${discovery.id}`} className="block px-4 transition-colors">
        <h3 className="mb-1 font-semibold text-[15px] leading-tight line-clamp-2 text-foreground group-hover:text-primary">
          {discovery.title}
        </h3>
      </Link>

      <div className="mb-2 px-4">
        <p className="text-foreground font-bold text-xl tracking-tight">
          {discovery.price != null ? formatPrice(discovery.price) : "Price not available"}
          {discovery.price != null && discovery.transaction_type === "rent" && (
            <span className="text-sm font-normal text-muted-foreground ml-1">/ month</span>
          )}
        </p>
      </div>

      <div className="flex items-center gap-1.5 text-muted-foreground px-4 mb-3">
        <MapPin className="w-3.5 h-3.5 shrink-0" />
        <span className="text-xs truncate">
          {discovery.location_text ||
            (discovery.locality ? `${discovery.locality}, ` : "") ||
            discovery.city ||
            "Location not stated"}
        </span>
        {area != null && area > 0 && (
          <span className="text-xs text-muted-foreground/80">Ã‚Â· {Math.round(area).toLocaleString("en-IN")} sq.ft</span>
        )}
      </div>

      {/* Specs */}
      <div className="flex items-center gap-4 text-[13px] text-muted-foreground px-4 pb-3 border-b border-border/50">
        {discovery.bedrooms != null && (
          <div className="flex items-center gap-1.5">
            <BedDouble className="w-4 h-4" />
            <span>{getBedroomLabel(discovery.bedrooms)}</span>
          </div>
        )}
        {discovery.furnishing && (
          <span className="text-xs">{discovery.furnishing}</span>
        )}
      </div>

      {/* Source + freshness */}
      <div className="pt-2 flex items-center justify-between px-4 text-[11px] text-muted-foreground/80">
        <span className="flex items-center gap-1.5">
          <Clock className="w-3 h-3" />
          <span>{discovery.freshness_label || "Source page date unavailable"}</span>
        </span>
        <span className="truncate max-w-[120px]">Source: {sourceLabel}</span>
      </div>

      {/* CTAs */}
      <div className="pt-1 flex items-center gap-2 px-4">
        <a
          href={discovery.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/80 h-8 text-xs font-medium"
          onClick={(e) => e.stopPropagation()}
        >
          <ExternalLink className="h-3.5 w-3.5" />
          View original listing
        </a>
        {isAuthenticated && (
          <Button
            size="sm"
            variant={isSaved ? "secondary" : "outline"}
            className="rounded-lg text-xs h-8 px-2.5"
            onClick={handleSave}
            disabled={savingInProgress}
            aria-label={isSaved ? "Remove saved discovery" : "Save discovery"}
          >
            <Heart className={`h-3.5 w-3.5 ${isSaved ? "fill-amber-500" : ""}`} />
          </Button>
        )}
      </div>
    </Card>
  );
}
