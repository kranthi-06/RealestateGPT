"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { discoveryApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { WebDiscoveryDetail } from "@/lib/types";
import { formatPrice, getBedroomLabel } from "@/lib/format";
import {
  ExternalLink, Globe2, Heart, MapPin, BedDouble, Maximize2,
  Building2, Shield, ArrowLeft, Info,
} from "lucide-react";

/** /discoveries/[id] Ã¢â‚¬â€ WEB-DISCOVERED listing detail (never verified inventory). */
export default function DiscoveryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [discovery, setDiscovery] = useState<WebDiscoveryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const discoveryId = params.id as string;

  useEffect(() => {
    if (!discoveryId) return;
    
    let mounted = true;
    discoveryApi
      .get(discoveryId)
      .then((detail) => {
        if (!mounted) return;
        setDiscovery(detail);
        setIsSaved(detail.saved || false);
      })
      .catch(() => {
        if (mounted) setNotFound(true);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
      
    return () => { mounted = false; };
  }, [discoveryId]);

  const handleSave = useCallback(async () => {
    if (!isAuthenticated || saving || !discovery) return;
    setSaving(true);
    try {
      if (isSaved) {
        await discoveryApi.unsave(discovery.id);
        setIsSaved(false);
      } else {
        await discoveryApi.save(discovery.id);
        setIsSaved(true);
      }
    } catch {
    } finally {
      setSaving(false);
    }
  }, [isAuthenticated, saving, isSaved, discovery]);

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="mt-4 h-96 w-full" />
      </div>
    );
  }

  if (notFound || !discovery) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-16 text-center">
        <Building2 className="h-16 w-16 text-muted-foreground/30" />
        <h1 className="mt-4 text-2xl font-bold">Discovery not found</h1>
        <p className="mt-2 text-muted-foreground">
          This web discovery may have expired (discoveries are short-lived) or the link is invalid.
        </p>
        <Button className="mt-6 rounded-lg" onClick={() => router.push("/search")}>
          Back to search
        </Button>
      </div>
    );
  }

  const priceLabel =
    discovery.price != null ? formatPrice(discovery.price) : "Price not available";
  const sourceLabel = discovery.source_name || discovery.source_domain || "Web source";
  const area = discovery.area || discovery.area_sqft;

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
      <Button variant="ghost" size="sm" className="mb-6" onClick={() => router.push("/search")}>
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to search
      </Button>

      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-xl border border-amber-300/40 bg-amber-50/10 px-4 py-3">
        <Badge variant="secondary" className="rounded-md bg-amber-500/15 text-amber-800">
          <Globe2 className="h-3.5 w-3.5" />
          WEB DISCOVERY
        </Badge>
        <span className="text-sm text-foreground/90">
          This listing was discovered from the web. Open the original source to verify current availability.
        </span>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        {/* Left: media + key facts */}
        <Card className="overflow-hidden rounded-xl border-border/40">
          <div className="relative h-72 bg-muted">
            {discovery.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={discovery.image_url} alt={discovery.title} className="object-cover w-full h-full" />
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground/50 gap-2">
                <Building2 className="h-16 w-16" />
                <span className="text-xs font-medium">No photo available</span>
              </div>
            )}
          </div>

          <div className="p-5">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">{discovery.title}</h1>
            <p className="mt-2 text-2xl font-bold tracking-tight">
              {discovery.price != null ? priceLabel : "Price not available"}
              {discovery.price != null && discovery.transaction_type === "rent" && (
                <span className="text-sm font-normal text-muted-foreground ml-1">/ month</span>
              )}
            </p>

            <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              {discovery.bedrooms != null && (
                <span className="flex items-center gap-1.5"><BedDouble className="h-4 w-4" />{getBedroomLabel(discovery.bedrooms)}</span>
              )}
              {area != null && area > 0 && (
                <span className="flex items-center gap-1.5"><Maximize2 className="h-4 w-4" />{Math.round(area).toLocaleString("en-IN")} sq.ft</span>
              )}
              <span className="flex items-center gap-1.5">
                <MapPin className="h-4 w-4" />
                {discovery.location_text || discovery.city || "Location not stated"}
              </span>
            </div>

            {discovery.description && (
              <p className="mt-4 text-sm text-muted-foreground leading-relaxed">{discovery.description}</p>
            )}

            <div className="mt-6">
              <a href={discovery.url} target="_blank" rel="noopener noreferrer" className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/80 h-8 text-sm font-medium">
                  <ExternalLink className="h-4 w-4" />
                  Open original listing
                </a>
            </div>
            <p className="mt-2 text-[11px] text-muted-foreground/80 text-center break-all">{discovery.url}</p>
          </div>
        </Card>
        {/* Right: extracted fields + provenance */}
        <Card className="rounded-xl border-border/40 p-5">
          <h2 className="text-lg font-semibold mb-4">Extracted details</h2>

          <dl className="space-y-3 text-sm">
            <DetailRow label="Source" value={sourceLabel} />
            <DetailRow label="Transaction" value={discovery.transaction_type === "rent" ? "Rent" : discovery.transaction_type === "sale" ? "Sale" : "Not stated"} />
            <DetailRow label="Furnishing" value={discovery.furnishing || "Not stated"} />
            <DetailRow label="Freshness" value={discovery.freshness_label || "Source page date unavailable"} />
            <DetailRow label="Discovered" value={discovery.discovered_at ? new Date(discovery.discovered_at).toLocaleString() : "Unknown"} />
            <DetailRow
              label="Extraction confidence"
              value={`${Math.round((discovery.confidence || 0) * 100)}% (${discovery.extraction_method || "snippet"})`}
            />
            <DetailRow label="Provider" value={discovery.provider || "web"} />
            {discovery.page_fetched_at && (
              <DetailRow label="Source page fetched" value={new Date(discovery.page_fetched_at).toLocaleString()} />
            )}
          </dl>

          <div className="mt-5 flex items-start gap-2 rounded-lg border border-border/50 bg-muted/40 p-3 text-xs text-muted-foreground">
            <Shield className="h-4 w-4 shrink-0" />
            <span>
              <strong className="text-foreground/90">What this means:</strong> only fields the source actually provided are shown.
              Missing price, area or BHK here means the source did not provide them. Nothing is estimated.
            </span>
          </div>

          <div className="mt-4 flex gap-3">
            {isAuthenticated && (
              <Button
                variant={isSaved ? "secondary" : "outline"}
                className="flex-1 rounded-lg"
                onClick={handleSave}
                disabled={saving}
              >
                <Heart className="mr-2 h-4 w-4" />
                {isSaved ? "Saved discovery" : "Save discovery"}
              </Button>
            )}
            <Button variant="ghost" className="flex-1 rounded-lg" onClick={() => router.push("/search")}>
              <Info className="mr-2 h-4 w-4" />
              New search
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-muted-foreground w-40 shrink-0">{label}</dt>
      <dd className="text-foreground text-right text-[13px] leading-snug break-words">{value}</dd>
    </div>
  );
}
