"use client";

import { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  GitCompare,
  Loader2,
  MapPin,
  Minus,
  Save,
  Search,
  ThumbsDown,
  ThumbsUp,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";
import { propertiesApi, comparisonsApi, marketApi } from "@/lib/api";
import type { MarketCompareResponse, Property } from "@/lib/types";
import { formatArea, formatPrice, getBedroomLabel, getPropertyTypeLabel } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { ErrorState } from "@/components/error-state";
import { PropertyActions } from "@/components/property-actions";
import { MAX_COMPARE, useCompare } from "@/lib/compare-context";
import { useAuth } from "@/lib/auth-context";
import { notify } from "@/lib/notify";
import { rankRow, summarize } from "@/lib/compare-analysis";
import { cn } from "@/lib/utils";

const NA = "Not available";

function formatCell(row: { key: string; unit?: string }, value: number | null): string {
  if (value == null) return NA;
  switch (row.unit) {
    case "price":
      return formatPrice(value);
    case "sqft":
      return `₹${Math.round(value).toLocaleString("en-IN")}/sq ft`;
    case "area":
      return formatArea(value);
    default:
      return String(value);
  }
}

export default function ComparePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-[1400px] px-4 py-10 sm:px-6 lg:px-8">
          <Skeleton className="mb-3 h-9 w-64" />
          <Skeleton className="mb-8 h-5 w-80" />
          <Skeleton className="h-96 rounded-xl" />
        </div>
      }
    >
      <ComparePageContent />
    </Suspense>
  );
}

function ComparePageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const compare = useCompare();
  const idsParam = searchParams.get("ids");
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingComparison, setSavingComparison] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [marketCities, setMarketCities] = useState<MarketCompareResponse | null>(null);

  const ids = useMemo(() => {
    if (!idsParam) return [];
    const parsed = idsParam
      .split(",")
      .map((id) => Number.parseInt(id.trim(), 10))
      .filter((id) => Number.isInteger(id) && id > 0);
    // Preserve order but drop duplicates, and respect the hard limit.
    return [...new Set(parsed)].slice(0, MAX_COMPARE);
  }, [idsParam]);

  // Keep the shared selection in step with the URL so the compare bar agrees
  // with the page, including after a refresh.
  useEffect(() => {
    if (ids.length === 0) return;
    const signature = ids.join(",");
    if (compare.ids.join(",") !== signature) {
      ids.forEach((id) => {
        if (!compare.has(id)) compare.add(id);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids.join(",")]);

  // One effect drives both loads: the properties for the comparison, and the
  // city-level asking-price context for them.
  useEffect(() => {
    const controller = new AbortController();

    if (ids.length === 0) {
      const id = window.setTimeout(() => {
        setProperties([]);
        setMarketCities(null);
        setLoading(false);
      }, 0);
      return () => {
        window.clearTimeout(id);
        controller.abort();
      };
    }

    const id = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      void (async () => {
        let fetched: Property[] = [];
        try {
          fetched = await propertiesApi.bulk(ids);
          if (controller.signal.aborted) return;
          setProperties(fetched);
        } catch {
          if (controller.signal.aborted) return;
          setError("The properties for this comparison could not be loaded. Please try again.");
          setProperties([]);
        } finally {
          if (!controller.signal.aborted) setLoading(false);
        }

        const cities = [...new Set(fetched.map((p) => p.city).filter(Boolean))] as string[];
        if (cities.length < 2) {
          if (!controller.signal.aborted) setMarketCities(null);
          return;
        }
        try {
          const data = await marketApi.compare(cities);
          if (!controller.signal.aborted) setMarketCities(data);
        } catch {
          if (!controller.signal.aborted) setMarketCities(null);
        }
      })();
    }, 0);

    return () => {
      window.clearTimeout(id);
      controller.abort();
    };
  }, [ids]);

  const removeProperty = useCallback(
    (idToRemove: number) => {
      compare.remove(idToRemove);
      const next = ids.filter((id) => id !== idToRemove);
      if (next.length > 0) router.replace(`/compare?ids=${next.join(",")}`);
      else router.replace("/compare");
    },
    [compare, ids, router]
  );

  const handleSaveComparison = useCallback(async () => {
    if (properties.length < 2) {
      setSaveError("Select at least 2 properties to save a comparison.");
      return;
    }
    setSavingComparison(true);
    setSaveError(null);
    try {
      await comparisonsApi.create(properties.map((p) => p.id));
      notify("Comparison saved", {
        description: "You can reopen it from the Compare page.",
        type: "success",
      });
    } catch {
      setSaveError("The comparison could not be saved. Please try again.");
    } finally {
      setSavingComparison(false);
    }
  }, [properties]);

  const summary = useMemo(() => summarize(properties), [properties]);

  if (loading) {
    return (
      <div className="mx-auto max-w-[1400px] px-4 py-10 sm:px-6 lg:px-8">
        <Skeleton className="mb-3 h-9 w-64" />
        <Skeleton className="mb-8 h-5 w-80" />
        <div className="overflow-hidden rounded-xl border border-border/60 bg-card shadow-sm">
          <div className="flex">
            <Skeleton className="h-16 w-48 shrink-0" />
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-16 flex-1" />
            ))}
          </div>
          {[...Array(9)].map((_, r) => (
            <div key={r} className="flex border-t border-border/50">
              <Skeleton className="h-12 w-48 shrink-0 rounded-none" />
              {[0, 1, 2].map((_, c) => (
                <Skeleton key={c} className="h-12 flex-1 rounded-none" />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (ids.length === 0 || properties.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20 text-center">
        <div className="mx-auto mb-4 flex size-16 items-center justify-center rounded-2xl bg-muted text-muted-foreground/40">
          <GitCompare className="size-8" />
        </div>
        <h2 className="text-2xl font-bold">Compare Properties</h2>
        <p className="mx-auto mt-2 max-w-md text-muted-foreground">
          Select two to four properties from search, your saved list, or an AI
          recommendation, then line them up side by side here.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Link href="/search">
            <Button className="gap-2">
              <Search className="size-4" />
              Find properties to compare
            </Button>
          </Link>
          {isAuthenticated && (
            <Link href="/saved">
              <Button variant="outline" className="gap-2">
                <Save className="size-4" />
                Open saved properties
              </Button>
            </Link>
          )}
        </div>
      </div>
    );
  }

  const summaryRows = summary.rows;

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-10 sm:px-6 lg:px-8">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Property Comparison</h1>
          <p className="mt-1 text-muted-foreground">
            Comparing {properties.length} propert{properties.length === 1 ? "y" : "ies"} side by side
            {properties.length < 2 && " — add at least one more for a useful comparison"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {properties.length < MAX_COMPARE && (
            <Link href="/search">
              <Button variant="outline" className="gap-2">
                <Search className="size-4" />
                Add another
              </Button>
            </Link>
          )}
          {properties.length >= 2 && (
            <Button onClick={handleSaveComparison} disabled={savingComparison} className="gap-2">
              {savingComparison ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Save className="size-4" />
              )}
              {savingComparison ? "Saving…" : "Save comparison"}
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-6">
          <ErrorState
            message={error}
            onRetry={() => {
              // Re-run the same load by resetting the ids effect's input.
              setLoading(true);
              setError(null);
              void propertiesApi
                .bulk(ids)
                .then((fetched) => {
                  setProperties(fetched);
                  setLoading(false);
                })
                .catch(() => {
                  setError("The properties for this comparison could not be loaded. Please try again.");
                  setLoading(false);
                });
            }}
          />
        </div>
      )}

      {saveError && (
        <div
          role="alert"
          className="mb-6 flex items-center gap-2 rounded-lg bg-destructive/10 p-4 text-destructive"
        >
          <AlertCircle className="size-5 shrink-0" />
          {saveError}
        </div>
      )}

      {summary.incomplete.length > 0 && (
        <div className="mb-6 flex items-start gap-2 rounded-lg border border-amber-200/70 bg-amber-50/60 p-4 text-sm text-amber-900">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <p>
            {summary.incomplete.length === properties.length
              ? "None of these records include an asking price, so price comparison is unavailable."
              : "Some records do not include an asking price, so price comparison is incomplete."}
          </p>
        </div>
      )}

      {/* ── Comparison table ─────────────────────────────────────────── */}
      <ScrollArea className="w-full rounded-xl border border-border/60 bg-card shadow-sm">
        <table className="w-full min-w-[900px] border-collapse">
          <thead>
            <tr className="bg-muted/50">
              <th className="sticky left-0 z-10 w-48 border-b border-border bg-card px-4 py-3 text-left text-sm font-semibold">
                Attribute
              </th>
              {properties.map((property) => (
                <th
                  key={property.id}
                  className="w-[220px] border-b border-border px-4 py-3 text-left align-top"
                >
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/properties/${property.id}`}
                        className="line-clamp-2 block text-sm font-semibold hover:text-primary"
                      >
                        {property.title}
                      </Link>
                      <p className="mt-1 flex items-center gap-1 text-xs font-normal text-muted-foreground">
                        <MapPin className="size-3 shrink-0" />
                        <span className="truncate">
                          {[property.locality, property.city].filter(Boolean).join(", ")}
                        </span>
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <Badge variant="secondary" className="font-normal">
                          {getPropertyTypeLabel(property.property_type)}
                        </Badge>
                        {property.bedrooms != null && (
                          <Badge variant="outline" className="font-normal">
                            {getBedroomLabel(property.bedrooms)}
                          </Badge>
                        )}
                        {property.verification_status === "verified" && (
                          <Badge className="badge-success gap-1 font-normal">
                            <CheckCircle2 className="size-2.5" />
                            Verified
                          </Badge>
                        )}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeProperty(property.id)}
                      className="flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-background shadow-sm transition-colors hover:border-transparent hover:bg-destructive hover:text-white"
                      title="Remove from comparison"
                      aria-label={`Remove ${property.title} from comparison`}
                    >
                      <X className="size-3.5" />
                    </button>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {summaryRows.map((row) => {
              const { best, worst } = rankRow(row, properties.map((p) => p.id));
              return (
                <tr key={row.key} className="odd:bg-background even:bg-muted/30">
                  <th
                    scope="row"
                    className="sticky left-0 z-10 w-48 border-b border-border/50 bg-inherit px-4 py-3 text-left align-top text-sm font-medium text-muted-foreground"
                  >
                    {row.label}
                    {row.hint && (
                      <span className="mt-0.5 block text-[11px] font-normal text-muted-foreground/70">
                        {row.hint}
                      </span>
                    )}
                  </th>
                  {properties.map((property, index) => {
                    const raw = row.values[property.id];
                    const comparable = raw != null;
                    const missing = row.key !== "price" && !comparable;
                    return (
                      <td key={property.id} className="border-b border-border/50 px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          {comparable && index === best && (
                            <span title="Best of the compared set">
                              <TrendingUp className="size-3.5 shrink-0 text-emerald-500" />
                            </span>
                          )}
                          {comparable && index === worst && (
                            <span title="Weakest of the compared set">
                              <TrendingDown className="size-3.5 shrink-0 text-destructive" />
                            </span>
                          )}
                          {comparable && index !== best && index !== worst && (
                            <Minus className="size-3.5 shrink-0 text-muted-foreground/40" />
                          )}
                          <span
                            className={cn(
                              "text-sm tabular-nums",
                              missing && "text-muted-foreground italic"
                            )}
                          >
                            {formatCell(row, raw)}
                          </span>
                        </div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}

            {/* Textual rows that cannot be ranked. */}
            <tr className="odd:bg-background even:bg-muted/30">
              <th
                scope="row"
                className="sticky left-0 z-10 w-48 border-b border-border/50 bg-inherit px-4 py-3 text-left text-sm font-medium text-muted-foreground"
              >
                Location
              </th>
              {properties.map((property) => (
                <td key={property.id} className="border-b border-border/50 px-4 py-3 text-sm">
                  {[property.locality, property.city, property.state].filter(Boolean).join(", ") || NA}
                </td>
              ))}
            </tr>
            <tr className="odd:bg-background even:bg-muted/30">
              <th
                scope="row"
                className="sticky left-0 z-10 w-48 border-b border-border/50 bg-inherit px-4 py-3 text-left text-sm font-medium text-muted-foreground"
              >
                Amenities
              </th>
              {properties.map((property) => {
                const amenities = (property.amenities ?? []).map((a) => a.name);
                return (
                  <td key={property.id} className="border-b border-border/50 px-4 py-3">
                    {amenities.length === 0 ? (
                      <span className="text-sm italic text-muted-foreground">None listed</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {amenities.slice(0, 8).map((name) => (
                          <span
                            key={name}
                            className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                          >
                            {name}
                          </span>
                        ))}
                        {amenities.length > 8 && (
                          <span className="text-[11px] text-muted-foreground">
                            +{amenities.length - 8} more
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                );
              })}
            </tr>
            <tr className="odd:bg-background even:bg-muted/30">
              <th
                scope="row"
                className="sticky left-0 z-10 w-48 border-b border-border/50 bg-inherit px-4 py-3 text-left text-sm font-medium text-muted-foreground"
              >
                Builder / project
              </th>
              {properties.map((property) => (
                <td key={property.id} className="border-b border-border/50 px-4 py-3 text-sm">
                  {[property.builder_name, property.project_name].filter(Boolean).join(" · ") || NA}
                </td>
              ))}
            </tr>
            <tr className="odd:bg-background even:bg-muted/30">
              <th
                scope="row"
                className="sticky left-0 z-10 w-48 border-b border-border/50 bg-inherit px-4 py-3 text-left text-sm font-medium text-muted-foreground"
              >
                Furnishing
              </th>
              {properties.map((property) => (
                <td key={property.id} className="border-b border-border/50 px-4 py-3 text-sm">
                  {property.furnishing || NA}
                </td>
              ))}
            </tr>
            <tr className="odd:bg-background even:bg-muted/30">
              <th
                scope="row"
                className="sticky left-0 z-10 w-48 border-b border-border/50 bg-inherit px-4 py-3 text-left text-sm font-medium text-muted-foreground"
              >
                Listing source
              </th>
              {properties.map((property) => (
                <td key={property.id} className="border-b border-border/50 px-4 py-3 text-sm">
                  {property.source || NA}
                  {property.is_synthetic && (
                    <span className="ml-1 text-xs text-muted-foreground">(demo record)</span>
                  )}
                </td>
              ))}
            </tr>
            <tr>
              <th
                scope="row"
                className="sticky left-0 z-10 w-48 bg-inherit px-4 py-3 text-left text-sm font-medium text-muted-foreground"
              >
                Actions
              </th>
              {properties.map((property) => (
                <td key={property.id} className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    {isAuthenticated ? (
                      <PropertyActions
                        propertyId={property.id}
                        title={property.title}
                        variant="buttons"
                      />
                    ) : (
                      <Link href={`/properties/${property.id}`}>
                        <Button variant="outline" size="sm" className="gap-1.5">
                          View details
                          <ArrowRight className="size-3.5" />
                        </Button>
                      </Link>
                    )}
                  </div>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>

      {/* ── Advantages and disadvantages ─────────────────────────────── */}
      {summary.insights.length > 0 && (
        <section className="mt-8" aria-labelledby="analysis-heading">
          <h2 id="analysis-heading" className="text-lg font-semibold">
            What the data says
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Derived only from the fields above. Missing fields are never filled in with
            estimates.
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {summary.insights.map((insight) => (
              <div
                key={insight.propertyId}
                className="rounded-xl border border-border/60 bg-card p-4 shadow-sm"
              >
                <h3 className="line-clamp-2 text-sm font-semibold">{insight.title}</h3>
                <div className="mt-3 space-y-3">
                  <div>
                    <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-emerald-700">
                      <ThumbsUp className="size-3.5" />
                      Advantages
                    </p>
                    {insight.advantages.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No measurable advantage on the compared fields.
                      </p>
                    ) : (
                      <ul className="space-y-1 text-sm">
                        {insight.advantages.map((item, i) => (
                          <li key={i} className="flex gap-2">
                            <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-500" />
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-destructive">
                      <ThumbsDown className="size-3.5" />
                      Trade-offs
                    </p>
                    {insight.disadvantages.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        No trade-off recorded on the compared fields.
                      </p>
                    ) : (
                      <ul className="space-y-1 text-sm">
                        {insight.disadvantages.map((item, i) => (
                          <li key={i} className="flex gap-2">
                            <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-amber-500" />
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Asking-price context from the same catalogue ─────────────── */}
      {marketCities && marketCities.cities.length > 1 && (
        <section className="mt-8 rounded-xl border border-border/60 bg-card p-5 shadow-sm">
          <h2 className="text-lg font-semibold">City asking-price context</h2>
          <p className="mt-1 text-sm text-muted-foreground">{marketCities.note}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {marketCities.cities.map((city) => (
              <div key={city.city} className="rounded-lg border border-border/50 p-3">
                <p className="font-medium">{city.city}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {city.sample_size} listing{city.sample_size === 1 ? "" : "s"} in scope
                  {city.median_price != null && ` · median ${formatPrice(city.median_price)}`}
                </p>
                {!city.is_measured && (
                  <Badge variant="outline" className="mt-2 border-amber-300/60 bg-amber-50/60 text-[10px] text-amber-800">
                    Low sample
                  </Badge>
                )}
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Source: {marketCities.source}. Generated {new Date(marketCities.generated_at).toLocaleString()}.
          </p>
        </section>
      )}

      {/* ── Next steps ───────────────────────────────────────────────── */}
      <div className="mt-8 rounded-xl border border-border/60 bg-muted/30 p-5">
        <h3 className="font-semibold">Next steps</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          <li>Open any property for full AI analysis, nearby facilities, and price intelligence.</li>
          <li>
            Use the{" "}
            <Link href="/affordability" className="text-primary hover:underline">
              Affordability calculator
            </Link>{" "}
            with your own income and savings.
          </li>
          <li>
            Run an{" "}
            <Link href="/finance" className="text-primary hover:underline">
              Investment analysis
            </Link>{" "}
            for EMI, yield, and cash flow on these listings.
          </li>
        </ul>
      </div>
    </div>
  );
}
