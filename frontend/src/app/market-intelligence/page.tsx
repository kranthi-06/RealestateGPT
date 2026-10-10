"use client";

import { Suspense, useCallback, useEffect, useRef, useState, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  TrendingUp,
  Building2,
  Home,
  MapPin,
  Loader2,
  AlertTriangle,
  Search,
  SearchX,
  Globe2,
  IndianRupee,
  KeyRound,
  LandPlot,
  BarChart3,
  Info,
  RotateCcw,
} from "lucide-react";
import { marketApi, locationsApi, propertiesApi, ApiError } from "@/lib/api";
import type { LivePlace, MarketSnapshotResponse, PriceStat, ExternalMarketResearch, ExternalStatBlock, ExternalStatistics } from "@/lib/types";
import { BarChart, ComparisonBars, LineChart } from "@/components/charts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const PROPERTY_TYPES = [
  { value: "", label: "All property types" },
  { value: "apartment", label: "Apartment / Flat" },
  { value: "house", label: "House / Villa" },
  { value: "plot", label: "Plot / Land" },
  { value: "commercial", label: "Commercial" },
  { value: "pg", label: "PG / Co-living" },
];

const BHK_OPTIONS = [
  { value: "", label: "Any BHK" },
  { value: "1", label: "1 BHK" },
  { value: "2", label: "2 BHK" },
  { value: "3", label: "3 BHK" },
  { value: "4", label: "4 BHK" },
  { value: "5", label: "5+ BHK" },
];

const NEARBY_CATEGORIES = [
  { key: "hospital", label: "Hospitals" },
  { key: "school", label: "Schools" },
  { key: "restaurant", label: "Restaurants" },
  { key: "metro", label: "Metro / Transport" },
  { key: "mall", label: "Shopping" },
  { key: "park", label: "Parks" },
] as const;

/* ─── External market intelligence (separate data source) ─────────────────── */

const EXTERNAL_KIND_LABELS: Record<string, string> = {
  asking_price: "Asking price",
  rent: "Rent",
  price_per_sqft: "Price per sq.ft",
  price_per_sqm: "Price per sq.m",
  trend: "Trend note",
};

function externalCurrencyLabel(code: string): string {
  const labels: Record<string, string> = { INR: "₹", USD: "$", GBP: "£", EUR: "€", AED: "AED " };
  return labels[code] ?? `${code} `;
}

function formatExternalAmount(
  value: number | null | undefined,
  currency: string,
  unit?: string | null
): string {
  if (value == null || !Number.isFinite(value)) return "Data unavailable";
  const symbol = externalCurrencyLabel(currency);
  const formatted = value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  if (unit === "per_month") return `${symbol}${formatted}/month`;
  if (unit === "per_night") return `${symbol}${formatted}/night`;
  if (unit === "per_sqft") return `${symbol}${formatted}/sq.ft`;
  if (unit === "per_sqm") return `${symbol}${formatted}/sq.m`;
  return `${symbol}${formatted}`;
}

function ExternalStatCard({
  label,
  stat,
  unit,
  hint,
  icon: Icon,
}: {
  label: string;
  stat?: ExternalStatBlock | null;
  unit?: string | null;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
}) {
  const available = Boolean(stat?.available && stat?.sample_size);
  return (
    <div className="rounded-2xl border border-border/60 bg-card p-4 sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        {Icon && <Icon className="h-4 w-4 shrink-0 text-muted-foreground/60" />}
      </div>
      <p className="mt-2 text-xl font-bold tabular-nums sm:text-2xl text-foreground">
        {available ? formatExternalAmount(stat?.median, stat?.currency ?? "INR", unit) : "Data unavailable"}
      </p>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        {available ? (
          <>
            <p className="text-xs text-muted-foreground">
              {stat!.sample_size} external observation{stat!.sample_size === 1 ? "" : "s"}
              {stat!.median != null && stat!.min != null && stat!.max != null
                ? ` · range ${formatExternalAmount(stat!.min, stat!.currency ?? "INR", unit)} – ${formatExternalAmount(stat!.max, stat!.currency ?? "INR", unit)}`
                : ""}
            </p>
            {!stat!.is_measured && (
              <Badge variant="outline" className="gap-1 border-amber-300/60 bg-amber-50/60 text-[10px] text-amber-800">
                <AlertTriangle className="h-2.5 w-2.5" />
                Low sample
              </Badge>
            )}
          </>
        ) : (
          <p className="text-xs text-muted-foreground">
            {hint ?? "No retrieved observation for this metric."}
          </p>
        )}
      </div>
    </div>
  );
}

function ExternalMarketSection({ research }: { research: ExternalMarketResearch }) {
  const status = research.status;
  const stats = (research.statistics ?? {}) as Partial<ExternalStatistics>;
  const resolved = research.resolved ?? {};
  const sources = research.sources ?? [];
  const observations = research.observations ?? [];

  if (status === "not_configured") {
    return (
      <Card className="mb-6 border-border/60" data-testid="external-market-section">
        <CardContent className="flex flex-col items-center justify-center py-10 text-center">
          <Globe2 className="h-12 w-12 text-muted-foreground/30" />
          <h2 className="mt-4 text-base font-semibold text-foreground">External market research unavailable</h2>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            {research.message ??
              "No web search provider is configured for this deployment, so no external observations could be retrieved. Verified catalogue statistics are still shown below."}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Missing metrics are reported as unavailable — never estimated.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (status === "unavailable") {
    return (
      <Card className="mb-6 border-border/60" data-testid="external-market-section">
        <CardContent className="flex flex-col items-center justify-center py-10 text-center">
          <AlertTriangle className="h-12 w-12 text-amber-500/60" />
          <h2 className="mt-4 text-base font-semibold text-foreground">External market search is temporarily unavailable</h2>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            {research.message ?? "The external search provider did not respond. No figures were retrieved and nothing has been estimated."}
          </p>
        </CardContent>
      </Card>
    );
  }

  if (status === "no_results") {
    return (
      <Card className="mb-6 border-border/60" data-testid="external-market-section">
        <CardContent className="flex flex-col items-center justify-center py-10 text-center">
          <SearchX className="h-12 w-12 text-muted-foreground/30" />
          <h2 className="mt-4 text-base font-semibold text-foreground">No external market data found</h2>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            {research.message ??
              "No external market information with usable figures was retrieved for this location. Metrics that could not be found are reported as unavailable rather than estimated."}
          </p>
        </CardContent>
      </Card>
    );
  }

  const trendLabels: Record<string, string> = {
    up: "Sources describe prices rising",
    down: "Sources describe prices falling",
    flat: "Sources describe stable prices",
    mixed: "Sources disagree on direction",
  };

  return (
    <div className="mb-6 space-y-4" data-testid="external-market-section">
      <Card className="border-amber-300/50 bg-amber-50/30">
        <CardContent className="p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Globe2 className="h-4 w-4 text-amber-700" />
                <h2 className="text-base font-semibold text-foreground">External market research</h2>
                <Badge variant="outline" className="border-amber-400/60 bg-amber-100/60 text-[10px] text-amber-900">
                  External observations · not verified inventory
                </Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                Retrieved from public web sources by the backend. Asking prices and published
                estimates only — nothing here is a verified listing or a guaranteed market rate.
              </p>
            </div>
            <div className="text-right text-[11px] text-muted-foreground">
              <p>
                Retrieved {new Date(research.generated_at).toLocaleString("en-IN")}
              </p>
              {research.cache?.hit && (
                <p>
                  Cached result · {research.cache.age_seconds ?? 0}s old
                </p>
              )}
              {research.provider && <p>Search provider: {research.provider}</p>}
            </div>
          </div>

          {resolved.found && (
            <p className="mt-3 text-xs text-muted-foreground">
              <span className="font-semibold text-foreground">Location matched: </span>
              {resolved.formatted_address ?? research.location_input}
              {resolved.country ? ` · ${resolved.country}` : ""}
              {resolved.latitude != null && resolved.longitude != null
                ? ` (${resolved.latitude.toFixed(4)}, ${resolved.longitude.toFixed(4)})`
                : ""}
              {" · "}provider: {resolved.provider ?? "n/a"}
            </p>
          )}

          {research.ai_summary?.text && (
            <div className="mt-3 rounded-xl border border-border/60 bg-background/80 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {research.ai_summary.label}
              </p>
              <p className="mt-1 text-sm text-foreground">{research.ai_summary.text}</p>
              {research.ai_summary.model && (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {research.ai_summary.provider ?? "AI"} · {research.ai_summary.model} · every figure
                  above was validated against the retrieved observations
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Statistics from retrieved observations */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <ExternalStatCard
          label="Median asking price"
          stat={stats.asking_price}
          icon={IndianRupee}
          hint="No retrieved asking-price observation."
        />
        <ExternalStatCard
          label="Typical rent"
          stat={stats.rent_monthly}
          unit="per_month"
          icon={KeyRound}
          hint="No retrieved rent observation."
        />
        <ExternalStatCard
          label="Price per sq.ft"
          stat={stats.price_per_sqft}
          unit="per_sqft"
          icon={LandPlot}
          hint="No retrieved per-sq.ft observation."
        />
        <div className="rounded-2xl border border-border/60 bg-card p-4 sm:p-5">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Gross rental yield
            </p>
            <TrendingUp className="h-4 w-4 shrink-0 text-muted-foreground/60" />
          </div>
          <p className="mt-2 text-xl font-bold tabular-nums sm:text-2xl text-foreground">
            {stats.rental_yield?.gross_rental_yield_pct != null
              ? `${stats.rental_yield.gross_rental_yield_pct.toFixed(2)}%`
              : "Data unavailable"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {stats.rental_yield?.basis ??
              "Requires both an external asking price and an external rent observation."}
          </p>
        </div>
      </div>

      {stats.trend_direction && (
        <p className="text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">Trend: </span>
          {trendLabels[stats.trend_direction] ?? stats.trend_direction}
          {stats.trend_basis ? ` — ${stats.trend_basis}` : ""}
        </p>
      )}

      {/* Observations */}
      {observations.length > 0 && (
        <Card className="border-border/60">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">
              Retrieved observations ({observations.length})
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Each figure is paired with the page it came from. Nothing is aggregated across
              currencies, and no value is estimated.
            </p>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="border-b border-border/60 text-left text-xs text-muted-foreground">
                    <th className="pb-2 pr-3 font-medium">Metric</th>
                    <th className="pb-2 pr-3 font-medium">Value</th>
                    <th className="pb-2 pr-3 font-medium">Beds</th>
                    <th className="pb-2 font-medium">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {observations.map((obs, index) => (
                    <tr key={`${obs.source.url}-${obs.kind}-${index}`} className="border-b border-border/30 last:border-0">
                      <td className="py-2.5 pr-3 text-foreground">
                        {EXTERNAL_KIND_LABELS[obs.kind] ?? obs.kind}
                      </td>
                      <td className="py-2.5 pr-3 tabular-nums text-foreground">
                        {obs.kind === "trend"
                          ? (obs.unit ?? "—")
                          : formatExternalAmount(obs.value, obs.currency, obs.unit)}
                      </td>
                      <td className="py-2.5 pr-3 tabular-nums text-muted-foreground">
                        {obs.bedrooms != null ? `${obs.bedrooms} BHK` : "—"}
                      </td>
                      <td className="py-2.5">
                        <a
                          href={obs.source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline"
                        >
                          {obs.source.domain || "source"}
                        </a>
                        {obs.source.published_at && (
                          <span className="ml-1.5 text-[11px] text-muted-foreground">
                            published {new Date(obs.source.published_at).toLocaleDateString("en-IN")}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Sources */}
      {sources.length > 0 && (
        <Card className="border-border/60 bg-muted/20">
          <CardContent className="p-4 sm:p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Sources used ({sources.length})
            </p>
            <ul className="mt-2 space-y-1.5">
              {sources.slice(0, 12).map((source) => (
                <li key={source.url} className="text-xs text-muted-foreground">
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium text-primary hover:underline"
                  >
                    {source.title || source.domain}
                  </a>{" "}
                  <span className="text-muted-foreground/70">
                    · {source.domain}
                    {source.published_at
                      ? ` · published ${new Date(source.published_at).toLocaleDateString("en-IN")}`
                      : " · publication date unavailable"}
                    {source.retrieved_at
                      ? ` · retrieved ${new Date(source.retrieved_at).toLocaleString("en-IN")}`
                      : ""}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* â”€â”€ Indian currency formatting â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

function inr(value: number | null | undefined, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: 0 })}`;
}

/** Compact Indian notation: 95.5 L, 1.2 Cr, 45.5 K. */
function inrCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1_00_00_000) return `₹${(value / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `₹${(value / 1_00_000).toFixed(abs >= 10_000_00 ? 0 : 1)} L`;
  if (abs >= 1_000) return `₹${(value / 1_000).toFixed(1)} K`;
  return `₹${value.toFixed(0)}`;
}

function num(value: number | null | undefined, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", { maximumFractionDigits: digits });
}

/* â”€â”€ Small presentational pieces â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  measured = true,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
  measured?: boolean;
  tone?: "default" | "primary" | "success" | "warning";
}) {
  const toneClass =
    tone === "primary"
      ? "text-primary"
      : tone === "success"
        ? "text-emerald-600"
        : tone === "warning"
          ? "text-amber-600"
          : "text-foreground";
  return (
    <div className="rounded-2xl border border-border/60 bg-card p-4 sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        {Icon && <Icon className="h-4 w-4 shrink-0 text-muted-foreground/60" />}
      </div>
      <p className={`mt-2 text-xl font-bold tabular-nums sm:text-2xl ${toneClass}`}>{value}</p>
      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        {!measured && (
          <Badge variant="outline" className="gap-1 border-amber-300/60 bg-amber-50/60 text-[10px] text-amber-800">
            <AlertTriangle className="h-2.5 w-2.5" />
            Low sample
          </Badge>
        )}
      </div>
    </div>
  );
}

function RangeBlock({
  title,
  icon: Icon,
  stat,
  unit,
  rangeLabel,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  stat: PriceStat;
  unit: "price" | "psf" | "psq_yard";
  rangeLabel: string;
}) {
  const empty = stat.sample_size === 0;
  const fmt =
    unit === "psq_yard"
      ? (v: number | null) => (v == null ? "—" : `₹${num(v)}`)
      : unit === "psf"
        ? (v: number | null) => (v == null ? "—" : `₹${num(v)}/sq.ft`)
        : (v: number | null) => inrCompact(v);

  return (
    <Card className="border-border/60">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Icon className="h-4 w-4 text-primary" />
          {title}
          <Badge variant="outline" className="ml-auto text-[10px] font-normal tabular-nums">
            {stat.sample_size} listing{stat.sample_size === 1 ? "" : "s"}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {empty ? (
          <p className="rounded-lg border border-dashed border-border bg-muted/20 px-3 py-4 text-center text-xs text-muted-foreground">
            No verified listings with this data type in the selected area.
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex items-baseline justify-between gap-2">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Median</p>
                <p className="text-lg font-bold tabular-nums text-foreground">{fmt(stat.median)}</p>
              </div>
              <div className="text-right">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Range (P25–P75)</p>
                <p className="text-sm font-medium tabular-nums text-muted-foreground">
                  {fmt(stat.p25)} – {fmt(stat.p75)}
                </p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 border-t border-border/50 pt-3 text-center">
              <div>
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Low</p>
                <p className="text-xs font-semibold tabular-nums">{fmt(stat.min)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Average</p>
                <p className="text-xs font-semibold tabular-nums">{fmt(stat.mean)}</p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">High</p>
                <p className="text-xs font-semibold tabular-nums">{fmt(stat.max)}</p>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground">{rangeLabel}</p>
            {!stat.is_measured && (
              <p className="text-[11px] text-amber-700">
                Small sample — treat as indicative, not a market rate.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* â”€â”€ Main page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

function MarketIntelligenceContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [locationText, setLocationText] = useState(
    () =>
      searchParams.get("locality") ||
      searchParams.get("city") ||
      ""
  );
  const [listingType, setListingType] = useState<"sale" | "rent">(
    (searchParams.get("listing_type") as "sale" | "rent") || "sale"
  );
  const [propertyType, setPropertyType] = useState(searchParams.get("property_type") || "");
  const [bedrooms, setBedrooms] = useState(searchParams.get("bedrooms") || "");

  const [snapshot, setSnapshot] = useState<MarketSnapshotResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nearby, setNearby] = useState<Record<string, LivePlace[]>>({});
  const [nearbyLoading, setNearbyLoading] = useState(false);
  const [lastSearched, setLastSearched] = useState<string>("");

  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* Parse "City, State" / "Locality, City" / plain text into city + locality. */
  const parseLocation = useCallback((raw: string): { city?: string; locality?: string } => {
    const parts = raw
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean);
    if (parts.length === 0) return {};
    if (parts.length === 1) return { city: parts[0] };
    const [first, second] = parts;
    // "Banjara Hills, Hyderabad" â†’ locality=first, city=second
    // "Nandyal, Andhra Pradesh" â†’ city=first, state=second (best effort)
    if (/state|pradesh|nadu|bengal|karnataka|telangana|maharashtra|gujarat|rajasthan/i.test(second)) {
      return { city: first };
    }
    return { locality: first, city: second };
  }, []);

  const loadNearby = useCallback(async (city: string, locality: string) => {
    setNearbyLoading(true);
    try {
      // Geocode the searched location so facility search works for ANY place.
      const geocodeQuery = locality ? `${locality}, ${city}` : city;
      let geo: { latitude: number; longitude: number } | null = null;
      try {
        const geoData = await locationsApi.geocode(geocodeQuery);
        geo = { latitude: geoData.latitude, longitude: geoData.longitude };
      } catch {
        geo = null;
      }
      if (!geo) {
        // Fall back to the centroid of stored listings for the searched area.
        try {
          const res = await propertiesApi.list({
            city,
            ...(locality ? { locality } : {}),
            page_size: 1,
          });
          const first = res.properties[0];
          if (first && first.latitude != null && first.longitude != null) {
            geo = { latitude: first.latitude, longitude: first.longitude };
          }
        } catch {
          geo = null;
        }
      }
      if (!geo) {
        setNearby({});
        return;
      }
      const entries = await Promise.all(
        NEARBY_CATEGORIES.map(async (cat) => {
          try {
            const res = await locationsApi.nearbyCoordinates(
              geo!.latitude,
              geo!.longitude,
              cat.key,
              5
            );
            return [cat.key, res.places ?? []] as const;
          } catch {
            return [cat.key, []] as const;
          }
        })
      );
      setNearby(Object.fromEntries(entries));
    } catch {
      setNearby({});
    } finally {
      setNearbyLoading(false);
    }
  }, []);

  const loadInsights = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text) {
        setError("Enter a city or locality to see market data.");
        return;
      }
      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const { city, locality } = parseLocation(text);
      if (!city && !locality) {
        setError("Enter a city or locality to see market data.");
        return;
      }

      setLoading(true);
      setError(null);
      setSnapshot(null);
      setNearby({});
      try {
        const res = await marketApi.insights({
          city,
          locality,
          listing_type: listingType,
          property_type: propertyType || undefined,
          bedrooms: bedrooms ? Number(bedrooms) : undefined,
        });
        if (controller.signal.aborted) return;
        setSnapshot(res);
        setLastSearched(text);
        if (res.totals.listings > 0 && (city || locality)) {
          void loadNearby(city || locality!, locality || "");
        }
      } catch (caught) {
        if (controller.signal.aborted) return;
        if (caught instanceof ApiError) {
          if (caught.status === 422) {
            setError("Enter a city or locality to see market data.");
          } else if (caught.status >= 500) {
            setError("Market data is temporarily unavailable. Please try again.");
          } else {
            setError(caught.message);
          }
        } else {
          setError("Could not load market data. Check your connection and try again.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    },
    [parseLocation, listingType, propertyType, bedrooms, loadNearby]
  );

  /* Auto-load from URL params (city/locality) so links from Explore / Search work. */
  const initialLoadRef = useRef(false);
  useEffect(() => {
    if (initialLoadRef.current) return;
    const city = searchParams.get("city");
    const locality = searchParams.get("locality");
    const initial = locality || city;
    if (initial) {
      initialLoadRef.current = true;
      // One-time URL-driven initial fetch (deep link from Explore / Search).
      // setState happens inside the async loader, not as a render sync.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void loadInsights(locality && city ? `${locality}, ${city}` : initial);
    }
  }, [searchParams, loadInsights]);

  /* Re-run when filter dropdowns change and a search is already active. */
  useEffect(() => {
    if (!lastSearched) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void loadInsights(lastSearched);
    }, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listingType, propertyType, bedrooms]);

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void loadInsights(locationText);
  };

  const reset = () => {
    setLocationText("");
    setListingType("sale");
    setPropertyType("");
    setBedrooms("");
    setSnapshot(null);
    setError(null);
    setNearby({});
    setLastSearched("");
  };

  const areaLabel = useMemo(() => {
    if (!snapshot) return "";
    const q = snapshot.query;
    if (q.locality && q.city) return `${q.locality}, ${q.city}`;
    return q.locality || q.city || "Selected area";
  }, [snapshot]);

  const trend = (snapshot?.trend ?? {}) as Record<string, unknown>;
  const hasTrend = trend.available === true;
  const coverage = (snapshot?.coverage ?? {}) as Record<string, unknown>;
  const insufficient = snapshot?.insufficient_data ?? null;

  return (
    <div className="page-shell py-6 sm:py-8">
      {/* Header */}
      <div className="mb-6">
        <Badge variant="outline" className="mb-3 gap-1.5 border-primary/30 bg-primary/5 text-primary">
          <BarChart3 className="h-3 w-3" />
          Market Intelligence
        </Badge>
        <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          Real estate data for any location
        </h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Two clearly separated sources: statistics measured from verified listings stored in our
          catalogue, and external market research retrieved from public web sources. Estimates are
          labelled, small samples are flagged, and we never invent prices or trends.
        </p>
      </div>

      {/* Search + Filters */}
      <Card className="mb-6 border-border/60">
        <CardContent className="space-y-4 p-4 sm:p-5">
          <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                value={locationText}
                onChange={(e) => setLocationText(e.target.value)}
                placeholder='e.g. "Nandyal, Andhra Pradesh" or "Banjara Hills, Hyderabad"'
                className="h-11 rounded-xl border-border/70 bg-background pl-9 text-sm"
                aria-label="Search city or locality"
                disabled={loading}
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={loading || !locationText.trim()} className="h-11 rounded-xl gap-1.5 px-5">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <BarChart3 className="h-4 w-4" />}
                Analyze
              </Button>
              {(snapshot || locationText) && (
                <Button type="button" variant="outline" onClick={reset} disabled={loading} className="h-11 rounded-xl gap-1.5">
                  <RotateCcw className="h-4 w-4" />
                  Reset
                </Button>
              )}
            </div>
          </form>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Buy / Rent</label>
              <div className="flex rounded-lg border border-border bg-background p-0.5">
                <button
                  type="button"
                  onClick={() => setListingType("sale")}
                  className={`flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md text-xs font-medium transition-colors ${
                    listingType === "sale" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Home className="h-3.5 w-3.5" />
                  Buy
                </button>
                <button
                  type="button"
                  onClick={() => setListingType("rent")}
                  className={`flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md text-xs font-medium transition-colors ${
                    listingType === "rent" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <KeyRound className="h-3.5 w-3.5" />
                  Rent
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Property type</label>
              <Select
                value={propertyType}
                onChange={(e) => setPropertyType(e.target.value)}
                className="h-9 text-sm"
                options={PROPERTY_TYPES}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Locality (from stored data)</label>
              <Select
                value={""}
                onChange={(e) => {
                  const value = e.target.value;
                  if (!value) return;
                  const city = snapshot?.query.city;
                  const next = city ? `${value}, ${city}` : value;
                  setLocationText(next);
                  void loadInsights(next);
                }}
                className="h-9 text-sm"
                disabled={!snapshot || snapshot.localities.length === 0}
                options={[
                  {
                    value: "",
                    label:
                      snapshot && snapshot.localities.length > 0
                        ? `All localities (${snapshot.localities.length})`
                        : "Search a location first",
                  },
                  ...(snapshot?.localities.map((l) => ({ value: l, label: l })) ?? []),
                ]}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">BHK</label>
              <Select
                value={bedrooms}
                onChange={(e) => setBedrooms(e.target.value)}
                className="h-9 text-sm"
                options={BHK_OPTIONS}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="mb-6 flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-2xl" />
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-56 rounded-2xl" />
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !snapshot && !error && (
        <Card className="border-border/60">
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <MapPin className="h-14 w-14 text-muted-foreground/30" />
            <h2 className="mt-4 text-base font-semibold text-foreground">Search a city or locality</h2>
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">
              Enter any city or neighbourhood — for example “Nandyal, Andhra Pradesh” or
              “Banjara Hills, Hyderabad”. Data is not limited to a fixed list of cities.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {!loading && snapshot && (
        <div className="space-y-6">
          {/* External market intelligence — a separate, clearly identified source */}
          {snapshot.external && <ExternalMarketSection research={snapshot.external} />}

          {/* Insufficient data banner */}
          {insufficient && (
            <div className="flex items-start gap-3 rounded-xl border border-amber-200/60 bg-amber-50/50 px-4 py-3">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
              <div>
                <p className="text-sm font-medium text-amber-900">Limited data for {areaLabel}</p>
                <p className="mt-0.5 text-xs text-amber-800/90">{insufficient.reason}</p>
              </div>
            </div>
          )}

          {/* Overview stats */}
          <div>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold text-foreground">
                Overview · <span className="text-primary">{areaLabel}</span>
              </h2>
              <span className="text-xs text-muted-foreground">
                {snapshot.totals.listings} verified listing
                {snapshot.totals.listings === 1 ? "" : "s"} ·{" "}
                {snapshot.totals.sale} sale / {snapshot.totals.rent} rent
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                label="Apartments (median)"
                value={inrCompact(snapshot.apartments.prices.median)}
                hint={`from ${snapshot.apartments.prices.sample_size} listings`}
                icon={Building2}
                measured={snapshot.apartments.prices.is_measured}
              />
              <StatCard
                label="Avg ₹/sq.ft (sale)"
                value={
                  snapshot.apartments.price_per_sqft.median != null
                    ? inr(snapshot.apartments.price_per_sqft.median)
                    : snapshot.houses.price_per_sqft.median != null
                      ? inr(snapshot.houses.price_per_sqft.median)
                      : "—"
                }
                hint="apartments, else houses"
                icon={IndianRupee}
                measured={
                  snapshot.apartments.price_per_sqft.is_measured ||
                  snapshot.houses.price_per_sqft.is_measured
                }
              />
              <StatCard
                label="Typical rent (median)"
                value={inrCompact(snapshot.rents.monthly.median)}
                hint="per month"
                icon={KeyRound}
                measured={snapshot.rents.monthly.is_measured}
              />
              <StatCard
                label="Gross rental yield"
                value={
                  snapshot.indicators.gross_rental_yield_pct != null
                    ? `${num(snapshot.indicators.gross_rental_yield_pct, 2)}%`
                    : "—"
                }
                hint="median rent / median price"
                icon={TrendingUp}
                tone={snapshot.indicators.gross_rental_yield_pct != null ? "success" : "default"}
              />
            </div>
          </div>

          {/* Price blocks */}
          <div>
            <h2 className="mb-3 text-lg font-semibold text-foreground">Sale prices</h2>
            <div className="grid gap-4 lg:grid-cols-2">
              <RangeBlock
                title="Apartments"
                icon={Building2}
                stat={snapshot.apartments.prices}
                unit="price"
                rangeLabel="Verified apartment sale listings in the selected area."
              />
              <RangeBlock
                title="Houses / Villas"
                icon={Home}
                stat={snapshot.houses.prices}
                unit="price"
                rangeLabel="Verified house/villa sale listings in the selected area."
              />
              <RangeBlock
                title="Plots / Land"
                icon={LandPlot}
                stat={snapshot.land.prices}
                unit="price"
                rangeLabel="Verified plot/land sale listings in the selected area."
              />
              <RangeBlock
                title="Land price per sq. yard"
                icon={LandPlot}
                stat={snapshot.land.price_per_sq_yard}
                unit="psq_yard"
                rangeLabel="Derived from plot price and area (1 sq. yard = 9 sq.ft)."
              />
            </div>
          </div>

          {/* Price per sqft + rents */}
          <div className="grid gap-4 lg:grid-cols-2">
            <RangeBlock
              title="Apartment ₹/sq.ft"
              icon={IndianRupee}
              stat={snapshot.apartments.price_per_sqft}
              unit="psf"
              rangeLabel="Per-square-foot asking price from verified apartment listings."
            />
            <RangeBlock
              title="House / villa ₹/sq.ft"
              icon={IndianRupee}
              stat={snapshot.houses.price_per_sqft}
              unit="psf"
              rangeLabel="Per-square-foot asking price from verified house listings."
            />
          </div>

          <div>
            <h2 className="mb-3 text-lg font-semibold text-foreground">Rents</h2>
            <div className="grid gap-4 lg:grid-cols-2">
              <RangeBlock
                title="Typical monthly rent"
                icon={KeyRound}
                stat={snapshot.rents.monthly}
                unit="price"
                rangeLabel="Monthly asking rent normalised from verified rent listings."
              />
              <RangeBlock
                title="Rent ₹/sq.ft per month"
                icon={KeyRound}
                stat={snapshot.rents.price_per_sqft_monthly}
                unit="psf"
                rangeLabel="Monthly rent divided by carpet/built-up area."
              />
            </div>
          </div>

          {/* Asking-price distribution */}
          {snapshot.price_distribution.length > 0 && (
            <Card className="border-border/60">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                  <BarChart3 className="h-4 w-4 text-primary" />
                  Asking-price distribution
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  How the {snapshot.apartments.prices.sample_size || snapshot.houses.prices.sample_size}{" "}
                  sale listing
                  {snapshot.apartments.prices.sample_size === 1 ? "" : "s"} in scope are spread across
                  price bands. Buckets are derived from the observed values.
                </p>
              </CardHeader>
              <CardContent className="pt-0">
                <BarChart
                  data={snapshot.price_distribution.map((bucket) => ({
                    label: bucket.label
                      ? bucket.label.length > 14
                        ? `${bucket.label.slice(0, 13)}…`
                        : bucket.label
                      : "—",
                    value: bucket.count,
                    hint: `${bucket.label}: ${bucket.count} listing${bucket.count === 1 ? "" : "s"}`,
                  }))}
                  ariaLabel="Number of listings per asking-price band"
                />
              </CardContent>
            </Card>
          )}

          {/* Trend */}
          <Card className="border-border/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <TrendingUp className="h-4 w-4 text-primary" />
                Observed price trend
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              {!hasTrend ? (
                <p className="rounded-lg border border-dashed border-border bg-muted/20 px-3 py-6 text-center text-xs text-muted-foreground">
                  {(trend.reason as string) ||
                    "Not enough observed price changes in this area to show a trend."}
                  <br className="hidden sm:block" />
                  <span className="mt-1 block">
                    RealEstateGPT only reports trends from recorded price changes, never from
                    generated projections.
                  </span>
                </p>
              ) : (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-baseline gap-3">
                    <span className="text-2xl font-bold tabular-nums text-foreground">
                      {trend.change_pct != null
                        ? `${(trend.change_pct as number) > 0 ? "+" : ""}${num(trend.change_pct as number, 1)}%`
                        : "—"}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {trend.from_month as string} â†’ {trend.to_month as string}
                    </span>
                    <Badge variant="outline" className="text-[10px] tabular-nums">
                      {trend.observations as number} observed change
                      {(trend.observations as number) === 1 ? "" : "s"}
                    </Badge>
                  </div>
                  {snapshot.price_history.length > 0 && (
                    <div className="pt-1">
                      <LineChart
                        data={snapshot.price_history.map((p) => ({
                          label: p.month,
                          value: p.avg_price,
                          hint:
                            p.avg_price != null
                              ? `${p.month}: ${inrCompact(p.avg_price)} from ${p.observations} observed change${p.observations === 1 ? "" : "s"}`
                              : undefined,
                        }))}
                        valueFormat={inrCompact}
                        ariaLabel="Observed monthly asking price, from recorded price changes"
                      />
                    </div>
                  )}
                  {trend.is_measured === false && (
                    <p className="text-[11px] text-amber-700">
                      Fewer than {coverage.minimum_sample as number} observations — indicative only.
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Locality comparison */}
          {snapshot.locality_comparison.length > 0 && (
            <Card className="border-border/60">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                  <MapPin className="h-4 w-4 text-primary" />
                  Locality comparison
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                {snapshot.locality_comparison.some((row) => row.median_price != null) && (
                  <div className="mb-5">
                    <ComparisonBars
                      data={snapshot.locality_comparison.map((row) => ({
                        label: row.locality,
                        value: row.median_price,
                        hint:
                          row.median_price != null
                            ? `${row.locality}: median ${inrCompact(row.median_price)} from ${row.listings} listing${row.listings === 1 ? "" : "s"}${row.measured ? "" : " (low sample)"}`
                            : undefined,
                      }))}
                      valueFormat={inrCompact}
                      bestIsHighest={false}
                      ariaLabel="Median asking price by locality"
                    />
                  </div>
                )}
                <div className="overflow-x-auto">
                <table className="w-full min-w-[480px] text-sm">
                  <thead>
                    <tr className="border-b border-border/60 text-left text-xs text-muted-foreground">
                      <th className="pb-2 pr-3 font-medium">Locality</th>
                      <th className="pb-2 pr-3 font-medium">Listings</th>
                      <th className="pb-2 pr-3 font-medium">Median price</th>
                      <th className="pb-2 font-medium">Avg ₹/sq.ft</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.locality_comparison.map((row) => (
                      <tr key={row.locality} className="border-b border-border/30 last:border-0">
                        <td className="py-2.5 pr-3 font-medium text-foreground">
                          {row.locality}
                          {!row.measured && (
                            <span className="ml-1.5 text-[10px] text-amber-700">low sample</span>
                          )}
                        </td>
                        <td className="py-2.5 pr-3 tabular-nums text-muted-foreground">{row.listings}</td>
                        <td className="py-2.5 pr-3 tabular-nums text-foreground">
                          {row.median_price != null ? inrCompact(row.median_price) : "—"}
                        </td>
                        <td className="py-2.5 tabular-nums text-foreground">
                          {row.avg_price_per_sqft != null ? inr(row.avg_price_per_sqft) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
                <p className="mt-3 text-[11px] text-muted-foreground">
                  Localities with fewer than {coverage.minimum_sample as number} listings are shown but
                  marked as indicative in the source data.
                </p>
              </CardContent>
            </Card>
          )}

          {/* Nearby infrastructure */}
          <Card className="border-border/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <Building2 className="h-4 w-4 text-primary" />
                Nearby infrastructure
                <button
                  type="button"
                  onClick={() => areaLabel && void loadNearby(snapshot.query.city || areaLabel, snapshot.query.locality || "")}
                  className="ml-auto text-[11px] font-normal text-primary hover:underline"
                >
                  {nearbyLoading ? "Loading…" : "Refresh"}
                </button>
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              {nearbyLoading ? (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <Skeleton key={i} className="h-20 rounded-xl" />
                  ))}
                </div>
              ) : Object.values(nearby).every((list) => list.length === 0) ? (
                <p className="rounded-lg border border-dashed border-border bg-muted/20 px-3 py-6 text-center text-xs text-muted-foreground">
                  Nearby facility data is not available for this location right now
                  (OpenStreetMap/Overpass may be rate-limiting). Try again shortly.
                </p>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {NEARBY_CATEGORIES.map((cat) => {
                    const list = nearby[cat.key] ?? [];
                    return (
                      <div key={cat.key} className="rounded-xl border border-border/60 bg-background p-3">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-semibold text-foreground">{cat.label}</p>
                          <Badge variant="outline" className="text-[10px] tabular-nums">
                            {list.length}
                          </Badge>
                        </div>
                        {list.length === 0 ? (
                          <p className="mt-2 text-[11px] text-muted-foreground">None found nearby.</p>
                        ) : (
                          <ul className="mt-2 space-y-1">
                            {list.slice(0, 4).map((place) => (
                              <li key={place.place_id ?? place.name} className="text-[11px] text-muted-foreground">
                                <span className="font-medium text-foreground">{place.name}</span>
                                {place.address ? ` · ${place.address}` : ""}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Data provenance */}
          <Card className="border-border/60 bg-muted/20">
            <CardContent className="space-y-3 p-4 sm:p-5">
              <div className="flex items-start gap-2">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="space-y-2 text-xs text-muted-foreground">
                  <p>
                    <span className="font-semibold text-foreground">Source: </span>
                    {snapshot.source}. Generated {new Date(snapshot.generated_at).toLocaleString("en-IN")}.
                  </p>
                  <p>
                    <span className="font-semibold text-foreground">Data class: </span>
                    Asking prices from verified stored listings. Figures marked
                    <Badge variant="outline" className="mx-1 border-amber-300/60 bg-amber-50/60 text-[10px] text-amber-800">
                      Low sample
                    </Badge>
                    are derived from fewer than {coverage.minimum_sample as number} listings and are
                    indicative only.
                  </p>
                  <p>
                    <span className="font-semibold text-foreground">Not shown here: </span>
                    government transaction data, registry prices, or third-party market feeds. No
                    estimate in this page is a guaranteed or exact market rate. Rental yield and
                    price-to-rent ratios are calculated from the medians above, not from appraiser
                    valuations.
                  </p>
                  <p className="pt-1">
                    <button
                      type="button"
                      onClick={() => {
                        const q = snapshot.query;
                        const params = new URLSearchParams();
                        if (q.city) params.set("city", q.city);
                        if (q.locality) params.set("locality", q.locality);
                        router.push(`/search?${params.toString()}`);
                      }}
                      className="font-medium text-primary hover:underline"
                    >
                      View the individual listings used for these statistics â†’
                    </button>
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

export default function MarketIntelligencePage() {
  return (
    <Suspense
      fallback={
        <div className="page-shell flex min-h-screen items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      }
    >
      <MarketIntelligenceContent />
    </Suspense>
  );
}
