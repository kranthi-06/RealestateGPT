"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
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
 * Google Search style result card for WEB-DISCOVERED properties.
 *
 * Displays:
 * - Favicon + Website name + Full breadcrumb URL
 * - Bold clickable title linking directly to the original website
 * - Descriptive snippet / summary
 * - Key property metadata (Price, BHK, Locality)
 * - Thumbnail image on the right (when available)
 * - Clickable "View Website" button
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
        // preserve previous state
      } finally {
        setSavingInProgress(false);
      }
    },
    [isAuthenticated, isSaved, discovery.id, savingInProgress, onSaveToggle]
  );

  const sourceLabel =
    discovery.source_name || discovery.source_domain || "Web portal";
  const domain =
    discovery.source_domain ||
    (() => {
      try {
        return new URL(discovery.url).hostname.replace("www.", "");
      } catch {
        return "website";
      }
    })();

  const faviconUrl = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=64`;
  const safeImageUrl =
    discovery.image_url &&
    (discovery.image_url.startsWith("http://") || discovery.image_url.startsWith("https://"))
      ? discovery.image_url
      : null;

  // Format breadcrumb-like URL: e.g. https://www.magicbricks.com › 2-bhk-flats...
  const displayUrl = (() => {
    try {
      const u = new URL(discovery.url);
      const pathParts = u.pathname.split("/").filter(Boolean);
      const breadcrumb = pathParts.slice(0, 2).join(" › ");
      return `${u.origin}${breadcrumb ? ` › ${breadcrumb}` : ""}`;
    } catch {
      return discovery.url;
    }
  })();

  const area = discovery.area || discovery.area_sqft;

  return (
    <div className="group relative rounded-2xl border border-border/80 bg-card p-4 sm:p-5 shadow-xs hover:border-primary/40 hover:shadow-md transition-all duration-200">
      <div className="flex flex-col sm:flex-row gap-4 justify-between items-start">
        {/* Main content column */}
        <div className="flex-1 min-w-0 space-y-2.5">
          {/* Header row: Favicon + Source name + Breadcrumb */}
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="relative h-6 w-6 shrink-0 overflow-hidden rounded-full border border-border/60 bg-muted/50 p-0.5 flex items-center justify-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={faviconUrl}
                alt={sourceLabel}
                className="h-4 w-4 rounded-full object-contain"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = "none";
                }}
              />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-xs font-semibold text-foreground tracking-tight">
                  {sourceLabel}
                </span>
                <span className="text-[11px] text-muted-foreground/70 truncate max-w-[280px]">
                  {displayUrl}
                </span>
              </div>
            </div>
            <Badge
              variant="outline"
              className="ml-auto shrink-0 gap-1 border-amber-300/50 bg-amber-50/50 text-[10px] text-amber-800 font-medium"
            >
              <Globe2 className="h-3 w-3 text-amber-600" />
              Web Result
            </Badge>
          </div>

          {/* Title: Google Search style blue/primary link */}
          <div>
            <a
              href={discovery.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block font-semibold text-base sm:text-lg text-primary hover:underline leading-snug line-clamp-2"
            >
              {discovery.title}
            </a>
          </div>

          {/* Snippet / Description */}
          {discovery.description && (
            <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed line-clamp-3">
              {discovery.description}
            </p>
          )}

          {/* Tags row: Price, BHK, Locality, Freshness */}
          <div className="flex items-center flex-wrap gap-2 pt-1 text-xs">
            {discovery.price != null && discovery.currency && (
              <Badge variant="secondary" className="font-semibold text-emerald-800 bg-emerald-50">
                {formatPrice(discovery.price, discovery.currency)}
                {discovery.transaction_type === "rent" && " / mo"}
              </Badge>
            )}
            {discovery.bedrooms != null && (
              <Badge variant="outline" className="gap-1 border-border/80">
                <BedDouble className="h-3 w-3 text-muted-foreground" />
                {getBedroomLabel(discovery.bedrooms)}
              </Badge>
            )}
            {(discovery.locality || discovery.city) && (
              <Badge variant="outline" className="gap-1 border-border/80">
                <MapPin className="h-3 w-3 text-muted-foreground" />
                {[discovery.locality, discovery.city].filter(Boolean).join(", ")}
              </Badge>
            )}
            {area != null && area > 0 && (
              <span className="text-xs text-muted-foreground">
                {Math.round(area).toLocaleString("en-IN")} sq.ft
              </span>
            )}
          </div>

          {/* Action row: View Website button */}
          <div className="pt-2 flex items-center gap-2">
            <a
              href={discovery.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors shadow-xs"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              View Website
            </a>

            {isAuthenticated && (
              <Button
                size="sm"
                variant={isSaved ? "secondary" : "outline"}
                className="h-7 rounded-lg text-xs px-2"
                onClick={handleSave}
                disabled={savingInProgress}
                aria-label={isSaved ? "Remove saved discovery" : "Save discovery"}
              >
                <Heart className={`h-3.5 w-3.5 ${isSaved ? "fill-amber-500 text-amber-500" : ""}`} />
              </Button>
            )}

            {discovery.freshness_label && (
              <span className="ml-auto text-[11px] text-muted-foreground flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {discovery.freshness_label}
              </span>
            )}
          </div>
        </div>

        {/* Thumbnail on the right (if available) */}
        {safeImageUrl && (
          <div className="shrink-0 w-full sm:w-36 h-28 sm:h-28 overflow-hidden rounded-xl border border-border/60 bg-muted/40 relative">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={safeImageUrl}
              alt={discovery.title}
              className="w-full h-full object-cover rounded-xl group-hover:scale-105 transition-transform duration-300"
              loading="lazy"
              onError={(e) => {
                const parent = (e.target as HTMLElement).parentElement;
                if (parent) parent.style.display = "none";
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
