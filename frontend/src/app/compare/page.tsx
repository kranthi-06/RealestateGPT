"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { propertiesApi, comparisonsApi } from "@/lib/api";
import type { Property } from "@/lib/types";
import { formatPrice, formatArea, getPropertyTypeLabel, getBedroomLabel } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { AiScoreBadge } from "@/components/ai-score-badge";
import { Search, X, MapPin, TrendingUp, TrendingDown, Minus, Save, AlertCircle } from "lucide-react";

interface PropertyWithScores extends Property {
  aiScore?: number;
  valueScore?: number;
}

function ComparePageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const idsParam = searchParams.get("ids");

  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingComparison, setSavingComparison] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    const fetchProperties = async () => {
      if (!idsParam) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const ids = idsParam.split(",").map((id) => parseInt(id.trim())).filter((id) => !isNaN(id));

        if (ids.length === 0) {
          setLoading(false);
          return;
        }

        const fetchedProperties = await propertiesApi.bulk(ids);
        setProperties(fetchedProperties);
      } catch {
        setError("Failed to fetch properties for comparison.");
      } finally {
        setLoading(false);
      }
    };

    fetchProperties();
  }, [idsParam]);

  const removeProperty = (idToRemove: number) => {
    const newIds = properties.map((p) => p.id).filter((id) => id !== idToRemove);
    if (newIds.length > 0) {
      router.push(`/compare?ids=${newIds.join(",")}`);
    } else {
      router.push("/compare");
    }
  };

  const handleSaveComparison = async () => {
    if (properties.length < 2) {
      setSaveError("Select at least 2 properties to save a comparison.");
      return;
    }

    setSavingComparison(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      const propertyIds = properties.map((p) => p.id);
      await comparisonsApi.create(propertyIds);
      setSaveSuccess(true);
    } catch {
      setSaveError("Failed to save comparison. Please try again.");
    } finally {
      setSavingComparison(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-10">
        <Skeleton className="h-10 w-64 mb-8" />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px] border-collapse">
            <thead>
              <tr>
                <th className="w-48 px-4 py-3 text-left text-sm font-medium text-muted-foreground border-b border-border">Attribute</th>
                {[1, 2, 3].map((i) => (
                  <th key={i} className="w-[200px] px-4 py-3 text-left text-sm font-medium text-muted-foreground border-b border-border">
                    <Skeleton className="h-4 w-24" />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                "Price",
                "Area",
                "BHK",
                "Property Type",
                "School Distance",
                "Hospital Distance",
                "Restaurant Distance",
                "Transport Distance",
                "AI Score",
                "Value Score",
              ].map((row) => (
                <tr key={row}>
                  <td className="w-48 px-4 py-3 text-sm font-medium text-muted-foreground border-b border-border/50">
                    <Skeleton className="h-4 w-20" />
                  </td>
                  {[1, 2, 3].map((i) => (
                    <td key={i} className="px-4 py-3 border-b border-border/50">
                      <Skeleton className="h-4 w-24" />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  if (!idsParam || properties.length === 0) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-20 text-center">
        <div className="w-16 h-16 mx-auto text-muted-foreground/30 mb-4 flex items-center justify-center">
          <TrendingUp className="w-8 h-8" />
        </div>
        <h2 className="text-2xl font-bold">Compare Properties</h2>
        <p className="text-muted-foreground mt-2 max-w-md mx-auto">
          Select properties from the search page to compare their features, prices, and locations side-by-side.
        </p>
        <Link href="/search">
          <Button className="mt-6 gradient-primary text-white border-0 gap-2">
            <Search className="w-4 h-4" />
            Find Properties to Compare
          </Button>
        </Link>
      </div>
    );
  }

  const propertyData = properties.map((p) => {
    // Note: AI scores are computed on property detail page using nearby facilities + price intelligence
    // They are not available from the bulk properties API. Show N/A here with link to full analysis.
    return { ...p, aiScore: undefined, valueScore: undefined } as PropertyWithScores;
  });

  const rows = [
    {
      label: "Price",
      render: (p: Property) => (
        <span className="font-bold text-base">{formatPrice(p.price)}</span>
      ),
      better: "lower" as const,
    },
    {
      label: "Area (sq ft)",
      render: (p: Property) => (
        <span>{p.area_sqft ? formatArea(p.area_sqft) : "N/A"}</span>
      ),
      better: "higher" as const,
    },
    {
      label: "BHK",
      render: (p: Property) => (
        <span>{getBedroomLabel(p.bedrooms)}</span>
      ),
      better: "higher" as const,
    },
    {
      label: "Property Type",
      render: (p: Property) => (
        <Badge variant="secondary" className="font-normal">{getPropertyTypeLabel(p.property_type)}</Badge>
      ),
      better: "none" as const,
    },
    {
      label: "School Distance",
      render: () => (
        <span className="text-muted-foreground">Data unavailable</span>
      ),
      better: "lower" as const,
    },
    {
      label: "Hospital Distance",
      render: () => (
        <span className="text-muted-foreground">Data unavailable</span>
      ),
      better: "lower" as const,
    },
    {
      label: "Restaurant Distance",
      render: () => (
        <span className="text-muted-foreground">Data unavailable</span>
      ),
      better: "lower" as const,
    },
    {
      label: "Transport Distance",
      render: () => (
        <span className="text-muted-foreground">Data unavailable</span>
      ),
      better: "lower" as const,
    },
    {
      label: "AI Score",
      render: (p: PropertyWithScores) => (
        p.aiScore != null ? (
          <AiScoreBadge score={p.aiScore} />
        ) : (
          <span className="text-muted-foreground text-xs">See property details</span>
        )
      ),
      better: "higher" as const,
    },
    {
      label: "Value Score",
      render: (p: PropertyWithScores) => (
        p.valueScore != null ? (
          <AiScoreBadge score={p.valueScore} />
        ) : (
          <span className="text-muted-foreground text-xs">See property details</span>
        )
      ),
      better: "higher" as const,
    },
  ];

  return (
    <div className="max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Property Comparison</h1>
          <p className="text-muted-foreground mt-1">
            Comparing {properties.length} properties side-by-side
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {properties.length < 4 && (
            <Link href="/search">
              <Button variant="outline" className="gap-2">
                <Search className="w-4 h-4" />
                Add Another
              </Button>
            </Link>
          )}
          {properties.length >= 2 && (
            <Button
              onClick={handleSaveComparison}
              disabled={savingComparison}
              className="gap-2"
              variant="default"
            >
              <Save className="w-4 h-4" />
              {savingComparison ? "Saving..." : "Save Comparison"}
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-destructive/10 text-destructive p-4 rounded-lg mb-6 flex items-center gap-2">
          <MapPin className="w-5 h-5" />
          {error}
        </div>
      )}

      {(saveError || saveSuccess) && (
        <div
          className={`p-4 rounded-lg mb-6 flex items-center gap-2 ${
            saveError ? "bg-destructive/10 text-destructive" : "bg-emerald-50 text-emerald-800 border border-emerald-100"
          }`}
        >
          {saveError ? <AlertCircle className="w-5 h-5" /> : <TrendingUp className="w-5 h-5" />}
          {saveError || "Comparison saved successfully!"}
        </div>
      )}

      <ScrollArea className="w-full rounded-xl border border-border/60 bg-card shadow-sm">
        <table className="w-full min-w-[900px] border-collapse">
          <thead>
            <tr className="bg-muted/50">
              <th className="w-48 px-4 py-3 text-left text-sm font-semibold text-foreground border-b border-border sticky left-0 z-10 bg-card">
                Attribute
              </th>
              {propertyData.map((p) => (
                <th key={p.id} className="w-[200px] px-4 py-3 text-left text-sm font-semibold text-foreground border-b border-border">
                  <div className="flex items-center gap-2">
                    <Link href={`/properties/${p.id}`} className="font-medium truncate block" style={{ maxWidth: "140px" }}>
                      {p.title || `${p.property_type} in ${p.locality || p.city}`}
                    </Link>
                    <button
                      onClick={() => removeProperty(p.id)}
                      className="w-6 h-6 rounded-full bg-background border border-border shadow-sm flex items-center justify-center hover:bg-destructive hover:text-white hover:border-transparent transition-colors flex-shrink-0"
                      title="Remove from comparison"
                      aria-label={`Remove ${p.title || "property"} from comparison`}
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIdx) => {
              const values = propertyData.map((p) => row.render(p));
              const numericValues = propertyData.map((p) => {
                const record = p as unknown as Record<string, unknown>;
                const val = record[row.label.toLowerCase().replace(/\s+/g, "_")] ??
                  (row.label === "Price" ? p.price :
                  row.label === "Area (sq ft)" ? p.area_sqft :
                  row.label === "BHK" ? p.bedrooms :
                  row.label === "AI Score" ? p.aiScore :
                  row.label === "Value Score" ? p.valueScore :
                  0);
                return typeof val === "number" ? val : 0;
              });
              const bestIdx = row.better === "higher" ? numericValues.indexOf(Math.max(...numericValues))
                : row.better === "lower" ? numericValues.indexOf(Math.min(...numericValues.filter(v => v > 0)))
                : -1;
              const worstIdx = row.better === "higher" ? numericValues.indexOf(Math.min(...numericValues.filter(v => v > 0)))
                : row.better === "lower" ? numericValues.indexOf(Math.max(...numericValues))
                : -1;

              return (
                <tr key={row.label} className={rowIdx % 2 === 0 ? "bg-background" : "bg-muted/30"}>
                  <td className="w-48 px-4 py-3 text-sm font-medium text-muted-foreground border-b border-border/50 sticky left-0 z-10 bg-inherit">
                    {row.label}
                  </td>
                  {values.map((value, colIdx) => (
                    <td key={colIdx} className="px-4 py-3 border-b border-border/50">
                      <div className="flex items-center gap-1.5">
                        {row.better !== "none" && colIdx === bestIdx && (
                          <span title="Best in class">
                            <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />
                          </span>
                        )}
                        {row.better !== "none" && colIdx === worstIdx && (
                          <span title="Lowest in class">
                            <TrendingDown className="w-3.5 h-3.5 text-destructive" />
                          </span>
                        )}
                        {row.better !== "none" && colIdx !== bestIdx && colIdx !== worstIdx && numericValues[colIdx] > 0 && (
                          <Minus className="w-3.5 h-3.5 text-muted-foreground/40" />
                        )}
                        <span className="text-sm">{value}</span>
                      </div>
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>

      {/* AI Recommendation Block */}
      <div className="mt-8 rounded-xl border border-border/60 bg-card shadow-sm p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <h3 className="text-lg font-semibold">AI Recommendation</h3>
            <p className="text-sm text-muted-foreground">Automated analysis based on price, location, amenities, and market data</p>
          </div>
        </div>

        {(() => {
          const lowestPrice = propertyData.reduce((best, current) => 
            (current.price > 0 && current.price < best.price ? current : best), propertyData[0]);

          // AI scores are computed on the property detail page using nearby facilities + price intelligence
          // They require per-property API calls which aren't done in bulk comparison

          return (
            <div className="space-y-3">
              <div className="p-4 bg-blue-50 rounded-lg border border-blue-100">
                <p className="font-medium text-blue-800">
                  <strong>AI Scores:</strong> Available on individual property detail pages
                </p>
                <p className="text-sm text-blue-700 mt-1">
                  Click &quot;View Details&quot; on any property to see full AI analysis with 6 scored dimensions (Location, Value, Connectivity, Amenities, Growth, Overall) plus pros/cons.
                </p>
              </div>

              {propertyData.length > 1 && (
                <div className="p-4 bg-amber-50 rounded-lg border border-amber-100">
                  <p className="font-medium text-amber-800">
                    <strong>Most Affordable:</strong> {lowestPrice.title || `${lowestPrice.property_type} in ${lowestPrice.locality || lowestPrice.city}`}
                    ({formatPrice(lowestPrice.price)})
                  </p>
                  <p className="text-sm text-amber-700 mt-1">
                    Lowest absolute price among compared properties. Verify condition and location fit.
                  </p>
                </div>
              )}

              <div className="p-4 bg-muted/30 rounded-lg border border-border/50">
                <p className="font-medium text-foreground">
                  <strong>Next Steps:</strong>
                </p>
                <ul className="text-sm text-muted-foreground mt-2 space-y-1 list-disc list-inside">
                  <li>Click property title to view full AI analysis, nearby facilities, and price intelligence.</li>
                  <li>Use the Affordability Calculator to check loan eligibility for your shortlisted property.</li>
                  <li>Save this comparison for later review from your Saved page.</li>
                </ul>
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center py-20"><Skeleton className="w-full h-96 max-w-4xl mx-auto rounded-xl" /></div>}>
      <ComparePageContent />
    </Suspense>
  );
}
