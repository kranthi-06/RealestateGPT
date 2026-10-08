"use client";

import { useEffect, useMemo, useState } from "react";
import { Brain, ThumbsUp, AlertTriangle, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreCard } from "@/components/score-card";
import { AiScoreBadge } from "@/components/ai-score-badge";
import type { PriceIntelligence, Property, LiveNearbyResponse } from "@/lib/types";
import { propertiesApi, locationsApi } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Scores {
  overall: number;
  location: number;
  value: number;
  connectivity: number;
  amenities: number;
  growth: number;
}

interface AIAnalysisPanelProps {
  propertyId: number;
  property?: Property;
  priceIntel?: PriceIntelligence;
  nearbyByCategory?: Record<string, LiveNearbyResponse>;
  className?: string;
  compact?: boolean;
}

function computeScores(property?: Property, priceIntel?: PriceIntelligence, nearby?: Record<string, LiveNearbyResponse>): Scores | null {
  if (!property && !priceIntel && !nearby) return null;

  const parts: { key: keyof Scores; value: number }[] = [];

  if (nearby) {
    const counts = Object.fromEntries(
      Object.entries(nearby).map(([k, v]) => [k, v?.places?.length ?? 0])
    );
    const amenityKeys = ["school", "hospital", "restaurant", "supermarket", "bank", "park", "public_transport", "hotel"];
    const present = amenityKeys.filter((k) => (counts[k] ?? 0) > 0).length;
    const amenitiesScore = Math.round((present / amenityKeys.length) * 100);
    parts.push({ key: "amenities", value: amenitiesScore });

    const locKeys = ["school", "hospital", "public_transport", "restaurant"];
    const locPresent = locKeys.filter((k) => (counts[k] ?? 0) >= 1).length;
    const hasFar = locKeys.some((k) => {
      const places = nearby[k]?.places ?? [];
      return places.some(
        (p: { distance_km?: number }) => p.distance_km != null && p.distance_km < 1
      );
    });
    const locationScore = Math.min(100, Math.round((locPresent / locKeys.length) * 70 + (hasFar ? 30 : 0)));
    parts.push({ key: "location", value: locationScore });

    const transit = counts["public_transport"] ?? 0;
    const connectivityScore = Math.min(100, transit * 18 + (counts["restaurant"] ?? 0) * 5);
    parts.push({ key: "connectivity", value: connectivityScore });
  }

  if (priceIntel && property) {
    const area = property.area_sqft ?? 1;
    const psf = property.price / area;
    const refPsf = priceIntel.price_per_sqft ?? psf;
    const delta = refPsf > 0 ? (refPsf - psf) / refPsf : 0;
    const valueScore = Math.max(0, Math.min(100, 50 + delta * 300));
    parts.push({ key: "value", value: Math.round(valueScore) });

    let growthScore = 50;
    if (priceIntel.enough_history && priceIntel.change_observations > 2) {
      const pct = priceIntel.price_change_pct ?? 0;
      growthScore = Math.max(0, Math.min(100, 55 + pct * 8));
    } else if (property.property_age != null) {
      growthScore = Math.max(0, Math.min(100, 60 - property.property_age * 2));
    }
    parts.push({ key: "growth", value: Math.round(growthScore) });
  } else if (property && property.property_age != null) {
    const growthScore = Math.max(0, Math.min(100, 60 - property.property_age * 2));
    parts.push({ key: "growth", value: Math.round(growthScore) });
  }

  if (parts.length === 0) return null;

  const overall = Math.round(
    parts.reduce((sum, p) => sum + p.value, 0) / parts.length
  );

  return {
    overall,
    location: parts.find((p) => p.key === "location")?.value ?? 50,
    value: parts.find((p) => p.key === "value")?.value ?? 50,
    connectivity: parts.find((p) => p.key === "connectivity")?.value ?? 50,
    amenities: parts.find((p) => p.key === "amenities")?.value ?? 50,
    growth: parts.find((p) => p.key === "growth")?.value ?? 50,
  };
}

const CATEGORY_LABEL: Record<string, string> = {
  school: "Schools",
  hospital: "Hospitals",
  restaurant: "Restaurants",
  supermarket: "Supermarkets",
  bank: "Banks",
  park: "Parks",
  public_transport: "Transport",
  hotel: "Hotels",
};

export function AIAnalysisPanel({
  propertyId,
  property: propInput,
  priceIntel: intelInput,
  nearbyByCategory: nearbyInput,
  className,
  compact = false,
}: AIAnalysisPanelProps) {
  const [property, setProperty] = useState<Property | undefined>(propInput);
  const [priceIntel, setPriceIntel] = useState<PriceIntelligence | undefined>(intelInput);
  const [nearby, setNearby] = useState<Record<string, LiveNearbyResponse> | undefined>(nearbyInput);
  const [loading, setLoading] = useState(!propInput || !intelInput || !nearbyInput);

  useEffect(() => {
    if (propInput && intelInput && nearbyInput) return;
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) setLoading(true);
    });
    const tasks: Promise<void>[] = [];
    if (!propInput) tasks.push(propertiesApi.get(propertyId).then((p) => { if (!cancelled) setProperty(p); }));
    if (!intelInput) tasks.push(propertiesApi.priceIntelligence(propertyId).then((p) => { if (!cancelled) setPriceIntel(p); }));
    if (!nearbyInput) {
      const cats = ["school", "hospital", "public_transport", "restaurant", "supermarket", "park", "bank", "hotel"];
      Promise.all(
        cats.map((c) =>
          locationsApi.nearby(propertyId, c, 3).catch(() => ({ property_id: propertyId, category: c, radius_km: 3, source: "n/a", places: [] } as LiveNearbyResponse))
        )
      ).then((results) => {
        if (cancelled) return;
        const map: Record<string, LiveNearbyResponse> = {};
        results.forEach((r) => {
          if (r && r.category) map[r.category] = r;
        });
        setNearby(map);
      });
    }
    Promise.all(tasks).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [propertyId, propInput, intelInput, nearbyInput]);

  const scores = useMemo(() => computeScores(property, priceIntel, nearby), [property, priceIntel, nearby]);

  const whyPoints = useMemo(() => {
    const out: string[] = [];
    if (!property) return out;
    if (nearby) {
      (Object.keys(CATEGORY_LABEL) as (keyof typeof CATEGORY_LABEL)[]).forEach((k) => {
        const n = nearby[k]?.places?.length ?? 0;
        if (n >= 3) out.push(`${n} ${CATEGORY_LABEL[k].toLowerCase()} within 3 km.`);
      });
    }
    if (priceIntel && property.area_sqft) {
      const psf = property.price / property.area_sqft;
      const ref = priceIntel.price_per_sqft;
      if (ref && ref > psf) {
        out.push(`Priced below locality avg (₹${Math.round(psf).toLocaleString("en-IN")} vs ₹${Math.round(ref).toLocaleString("en-IN")}/sq.ft).`);
      }
    }
    if (property.bedrooms && property.bedrooms >= 2 && property.area_sqft && property.area_sqft > 800) {
      out.push("Sized for a family layout.");
    }
    if (property.verification_status === "verified") out.push("Listing is verified.");
    return out.slice(0, 5);
  }, [property, nearby, priceIntel]);

  const concerns = useMemo(() => {
    const out: string[] = [];
    if (!property) return out;
    if (nearby) {
      if ((nearby["hospital"]?.places?.length ?? 0) === 0) out.push("No hospital found within 3 km.");
      if ((nearby["school"]?.places?.length ?? 0) === 0) out.push("No school found within 3 km.");
      if ((nearby["public_transport"]?.places?.length ?? 0) === 0) out.push("Limited public transport nearby.");
    }
    if (priceIntel && priceIntel.price_change_pct != null && priceIntel.price_change_pct < -2) {
      out.push(`Locality prices declining (${priceIntel.price_change_pct.toFixed(1)}% recent change).`);
    }
    if (property.property_age != null && property.property_age > 15) {
      out.push(`Property age ${property.property_age} years — renovations may be required.`);
    }
    if (!nearby && !priceIntel) {
      out.push("Limited intelligence data available; expand sample radius or verify offline.");
    }
    return out.slice(0, 5);
  }, [property, nearby, priceIntel]);

  const recommendation = useMemo(() => {
    if (!scores) return { label: "Insufficient data", tone: "outline", detail: "Cannot compute a recommendation at this time." };
    if (scores.overall >= 80) return { label: "Strong Buy", tone: "success", detail: "This property scores highly across most dimensions." };
    if (scores.overall >= 65) return { label: "Good Consider", tone: "default", detail: "Balanced profile; verify the specific concerns below." };
    if (scores.overall >= 45) return { label: "Conditional", tone: "warning", detail: "Some risks; use AI Assistant for deeper analysis." };
    return { label: "Caution", tone: "destructive", detail: "Multiple risk factors; conduct site and legal verification." };
  }, [scores]);

  return (
    <Card className={cn(className)}>
      <CardHeader className={cn("flex flex-row flex-wrap items-start justify-between gap-3", compact && "p-4 pb-2")}>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-primary" />
            <CardTitle className={cn("font-semibold", compact ? "text-sm" : "text-base")}>AI Analysis</CardTitle>
          </div>
          <CardDescription className="text-xs">
            Based on nearby facilities, price intelligence &amp; property profile
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {scores && <AiScoreBadge score={scores.overall} size="md" />}
          <Badge variant={recommendation.tone as "default" | "secondary" | "destructive" | "outline"} className="text-xs">
            {recommendation.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className={cn("space-y-5", compact && "p-4 pt-0")}>
        {loading || !scores ? (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="space-y-2 rounded-xl border border-border p-3">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-5 w-10" />
                <Skeleton className="h-1.5 w-full" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <ScoreCard label="Overall" value={scores.overall} variant="primary" />
            <ScoreCard label="Location" value={scores.location} />
            <ScoreCard label="Value for Money" value={scores.value} />
            <ScoreCard label="Connectivity" value={scores.connectivity} />
            <ScoreCard label="Amenities" value={scores.amenities} />
            <ScoreCard label="Area Growth" value={scores.growth} />
          </div>
        )}

        <p className="rounded-lg bg-primary/5 border border-primary/20 px-3 py-2 text-sm text-foreground">
          <Info className="mr-1.5 inline h-3.5 w-3.5 align-[-2px] text-primary" />
          {recommendation.detail}
          {property && (
            <>
              {" "}Reference price: <strong className="tabular-nums">{formatPrice(property.price, property.currency)}</strong>
              {property.area_sqft && <> · {property.area_sqft.toLocaleString("en-IN")} sq.ft</>}
            </>
          )}
        </p>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-border bg-background p-4">
            <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground">
              <ThumbsUp className="h-4 w-4 text-green-600" />
              Why this property?
            </div>
            {loading || whyPoints.length === 0 ? (
              whyPoints.length === 0 && !loading ? (
                <p className="text-xs text-muted-foreground">Insufficient data for positives.</p>
              ) : (
                <div className="space-y-2">
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-3 w-5/6" />
                  <Skeleton className="h-3 w-4/6" />
                </div>
              )
            ) : (
              <ul className="space-y-1.5">
                {whyPoints.map((w, i) => (
                  <li key={i} className="flex gap-2 text-xs text-muted-foreground">
                    <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-green-500" />
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-xl border border-border bg-background p-4">
            <div className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-foreground">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Potential concerns
            </div>
            {loading || concerns.length === 0 ? (
              concerns.length === 0 && !loading ? (
                <p className="text-xs text-muted-foreground">No red flags detected in sample data.</p>
              ) : (
                <div className="space-y-2">
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-3 w-5/6" />
                </div>
              )
            ) : (
              <ul className="space-y-1.5">
                {concerns.map((w, i) => (
                  <li key={i} className="flex gap-2 text-xs text-muted-foreground">
                    <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <p className="pt-1 text-[11px] text-muted-foreground">
          Scores are synthesised from backend endpoints and not financial advice. Always verify with legal and on-site due diligence.
        </p>
      </CardContent>
    </Card>
  );
}

export default AIAnalysisPanel;
