"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { propertiesApi } from "@/lib/api";
import type { PriceIntelligence as PriceIntelligenceData } from "@/lib/types";
import { formatPrice, timeAgo } from "@/lib/format";
import { TrendingDown, TrendingUp, Minus, LineChart, ShieldCheck } from "lucide-react";

/**
 * Price intelligence panel — displays ONLY data computed from stored,
 * observed price history. When there is not enough history it says so
 * instead of inventing numbers.
 */
export function PriceIntelligencePanel({
  propertyId,
  listingType,
}: {
  propertyId: number;
  listingType: string;
}) {
  const [data, setData] = useState<PriceIntelligenceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    propertiesApi
      .priceIntelligence(propertyId)
      .then((result) => {
        if (active) setData(result);
      })
      .catch(() => {
        if (active) setFailed(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [propertyId]);

  if (loading) {
    return (
      <Card className="rounded-2xl border-border/60 p-6">
        <Skeleton className="h-6 w-40" />
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      </Card>
    );
  }

  if (failed || !data || !data.available) {
    return (
      <Card className="rounded-2xl border-border/60 p-6">
        <h3 className="flex items-center gap-2 text-lg font-bold">
          <LineChart className="h-5 w-5 text-muted-foreground" />
          Price intelligence
        </h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Price intelligence is temporarily unavailable for this listing.
        </p>
      </Card>
    );
  }

  const changeIcon =
    data.price_change_pct == null ? (
      <Minus className="h-4 w-4" />
    ) : data.price_change_pct > 0 ? (
      <TrendingUp className="h-4 w-4" />
    ) : (
      <TrendingDown className="h-4 w-4" />
    );

  return (
    <Card className="rounded-2xl border-border/60 p-6">
      <h3 className="flex items-center gap-2 text-lg font-bold">
        <LineChart className="h-5 w-5 text-muted-foreground" />
        Price intelligence
      </h3>

      {!data.enough_history ? (
        <div className="mt-3 rounded-xl bg-muted/50 p-4 text-sm text-muted-foreground">
          {data.message || "Not enough verified history."}
          <p className="mt-1 text-xs">
            Charts appear only after at least two observed price observations from a live
            provider. Historical prices are never invented.
          </p>
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-xl border border-border/60 p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                {listingType === "rent" ? "Current rent" : "Current price"}
              </p>
              <p className="mt-1 text-lg font-bold">{formatPrice(data.current_price ?? 0)}</p>
              {listingType === "rent" && data.rent_period && (
                <p className="text-xs text-muted-foreground">per {data.rent_period}</p>
              )}
            </div>
            <div className="rounded-xl border border-border/60 p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Previous</p>
              <p className="mt-1 text-lg font-bold text-muted-foreground">
                {data.previous_price != null ? formatPrice(data.previous_price) : "—"}
              </p>
            </div>
            <div className="rounded-xl border border-border/60 p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Change</p>
              <p
                className={`mt-1 flex items-center gap-1 text-lg font-bold ${
                  data.price_change_pct == null
                    ? "text-muted-foreground"
                    : data.price_change_pct > 0
                      ? "text-red-600"
                      : "text-emerald-600"
                }`}
              >
                {changeIcon}
                {data.price_change_pct == null
                  ? "—"
                  : `${data.price_change_pct > 0 ? "+" : ""}${data.price_change_pct}%`}
              </p>
            </div>
            <div className="rounded-xl border border-border/60 p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Per sq.ft</p>
              <p className="mt-1 text-lg font-bold">
                {data.price_per_sqft != null
                  ? `₹${Math.round(data.price_per_sqft).toLocaleString("en-IN")}`
                  : data.rent_per_sqft != null
                    ? `₹${data.rent_per_sqft.toFixed(1)}/mo`
                    : "—"}
              </p>
            </div>
          </div>

          {data.history.length > 0 && (
            <ul className="mt-5 space-y-2">
              {data.history.slice(0, 5).map((entry, idx) => (
                <li
                  key={`${entry.changed_at}-${idx}`}
                  className="flex items-center justify-between rounded-lg border border-border/50 px-3 py-2 text-sm"
                >
                  <span className="text-muted-foreground">
                    {entry.changed_at ? timeAgo(entry.changed_at) : "Observed"}
                  </span>
                  <span className="font-medium">
                    {entry.old_price != null && entry.new_price != null
                      ? `${formatPrice(entry.old_price)} → ${formatPrice(entry.new_price)}`
                      : entry.change_type === "initial_listing"
                        ? "Initial listing"
                        : formatPrice(entry.new_price ?? 0)}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <p className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5" />
            {data.observations} observed price record{data.observations === 1 ? "" : "s"} ·
            calculated from stored history
          </p>
        </>
      )}
    </Card>
  );
}