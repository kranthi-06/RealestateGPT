"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { financeApi } from "@/lib/api";
import type { AffordabilityResult, PriceEstimate, PriceFairness } from "@/lib/types";
import { formatPrice } from "@/lib/format";
import { Calculator, IndianRupee, Info, Loader2, ShieldCheck } from "lucide-react";

function EstimateFallback({ propertyId }: { propertyId: number }) {
  const [fairness, setFairness] = useState<PriceFairness | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    financeApi
      .fairness(propertyId)
      .then((value) => {
        if (active) setFairness(value);
      })
      .catch(() => {
        if (active) setLoadError("Price analysis is temporarily unavailable.");
      });
    return () => {
      active = false;
    };
  }, [propertyId]);

  if (loadError) return <p className="text-xs text-muted-foreground">{loadError}</p>;
  if (!fairness) return <Loader2 className="size-4 animate-spin text-muted-foreground" />;
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-muted-foreground">Estimated range</span>
        <span className="text-sm font-semibold">
          {formatPrice(fairness.lower_bound)} – {formatPrice(fairness.upper_bound)}
        </span>
      </div>
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-muted-foreground">Listed price</span>
        <span className="text-sm font-semibold">{formatPrice(fairness.listed_price)}</span>
      </div>
      <p className="text-xs text-muted-foreground">{fairness.verdict_label} · {fairness.diff_pct}% vs estimate</p>
    </div>
  );
}
function AffordabilityInput({ listedPrice }: { listedPrice: number }) {
  const [monthlyIncome, setMonthlyIncome] = useState("");
  const [result, setResult] = useState<AffordabilityResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const calculate = async (event: React.FormEvent) => {
    event.preventDefault();
    const income = Number(monthlyIncome);
    if (!income || income <= 0) return;
    setLoading(true);
    setError(null);
    try {
      const value = await financeApi.affordability({
        monthly_income: income,
        down_payment: Math.round(listedPrice * 0.2),
        property_price: listedPrice,
        annual_interest_rate: 8.5,
        tenure_years: 20,
      });
      setResult(value);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Affordability could not be calculated.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={calculate} className="space-y-3">
      <Input
        type="number"
        min={1}
        inputMode="numeric"
        placeholder="Your monthly income (₹)"
        value={monthlyIncome}
        onChange={(event) => setMonthlyIncome(event.target.value)}
      />
      <Button type="submit" size="sm" disabled={!monthlyIncome || loading} className="w-full">
        {loading ? <Loader2 className="size-4 animate-spin" /> : <Calculator className="size-4 mr-1.5" />} Check affordability
      </Button>
      {error && <p className="text-xs text-destructive">{error}</p>}
      {result && (
        <div className="space-y-1.5 border-t border-border/50 pt-3 text-sm">
          <div className="flex justify-between"><span className="text-muted-foreground">Max affordable price</span><span className="font-semibold">{formatPrice(result.max_property_price)}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Max monthly EMI</span><span className="font-semibold">{formatPrice(result.max_monthly_emi)}/mo</span></div>
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">This listing</span>
            {result.affordable ? (
              <Badge className="bg-emerald-600 text-white border-0">Affordable</Badge>
            ) : (
              <Badge variant="outline" className="text-amber-600 border-amber-300">Above budget</Badge>
            )}
          </div>
        </div>
      )}
    </form>
  );
}

export function FinanceInsights({ propertyId, listedPrice }: { propertyId: number; listedPrice: number }) {
  const [estimate, setEstimate] = useState<PriceEstimate | null>(null);

  useEffect(() => {
    let active = true;
    financeApi
      .estimate(propertyId)
      .then((value) => {
        if (active) setEstimate(value);
      })
      .catch(() => {
        if (active) setEstimate(null);
      });
    return () => {
      active = false;
    };
  }, [propertyId]);

  return (
    <Card className="p-4 border-border/60">
      <div className="mb-3 flex items-center gap-2">
        <ShieldCheck className="size-4 text-primary" />
        <h2 className="text-sm font-semibold">Financial intelligence</h2>
      </div>

      <div className="mb-4">
        <p className="text-xs text-muted-foreground mb-1.5">Estimated market range</p>
        {estimate ? (
          <div className="space-y-1.5 text-sm">
            <div className="flex items-baseline justify-between">
              <span className="text-muted-foreground">Floor – Ceiling</span>
              <span className="font-semibold">
                {formatPrice(estimate.lower_bound)} – {formatPrice(estimate.upper_bound)}
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-muted-foreground">Listed</span>
              <span className="font-semibold">{formatPrice(estimate.listed_price || listedPrice)}</span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {estimate.sample_size > 0
                ? `Derived from ${estimate.sample_size} catalogue comparables · ${estimate.model_version}`
                : "Heuristic estimate from the catalogue"}
            </p>
          </div>
        ) : (
          <EstimateFallback propertyId={propertyId} />
        )}
      </div>

      <div className="border-t border-border/50 pt-3">
        <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <IndianRupee className="size-3.5" /> Affordability for this listing
        </p>
        <AffordabilityInput listedPrice={listedPrice} />
      </div>

      <p className="mt-3 flex items-start gap-1.5 text-[11px] text-muted-foreground">
        <Info className="mt-0.5 size-3 shrink-0" />
        Estimates and EMI are deterministic calculations. Property facts come from the catalogue; nothing is invented here.
      </p>
    </Card>
  );
}