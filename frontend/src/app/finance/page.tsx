"use client";

import { useCallback, useMemo, useState, FormEvent } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Banknote,
  Calculator,
  Home,
  Info,
  Loader2,
  Percent,
  Receipt,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { financeApi, propertiesApi, ApiError } from "@/lib/api";
import type { InvestmentResponse, InvestmentSummary, Property } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/* ── helpers ─────────────────────────────────────────────────────────── */

function inr(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function inrCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_00_00_000) return `${sign}₹${(abs / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `${sign}₹${(abs / 1_00_000).toFixed(abs >= 10_00_000 ? 0 : 1)} L`;
  if (abs >= 1_000) return `${sign}₹${(abs / 1_000).toFixed(1)} K`;
  return `${sign}₹${abs.toFixed(0)}`;
}

function pct(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

function digits(raw: string): string {
  return raw.replace(/[^\d]/g, "");
}

function decimal(raw: string): string {
  const cleaned = raw.replace(/[^\d.-]/g, "");
  const parts = cleaned.split(".");
  return parts.length > 2 ? `${parts[0]}.${parts.slice(1).join("")}` : cleaned;
}

function toNumber(raw: string, fallback: number): number {
  const n = Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-foreground">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

function Stat({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
  tone?: "default" | "success" | "danger" | "warning";
}) {
  const toneClass =
    tone === "success" ? "text-emerald-600"
    : tone === "danger" ? "text-destructive"
    : tone === "warning" ? "text-amber-600"
    : "text-foreground";
  return (
    <div className="rounded-xl border border-border/60 bg-card p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        {Icon && <Icon className="h-4 w-4 shrink-0 text-muted-foreground/60" />}
      </div>
      <p className={cn("mt-2 text-lg font-bold tabular-nums sm:text-xl", toneClass)}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/* ── Scenario comparison ─────────────────────────────────────────────── */

function ScenarioGrid({ item }: { item: InvestmentSummary }) {
  const order: Array<{ key: string; label: string; hint: string }> = [
    { key: "conservative", label: "Conservative", hint: "Lowest assumption" },
    { key: "base", label: "Base", hint: "Central assumption" },
    { key: "optimistic", label: "Optimistic", hint: "Highest assumption" },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {order.map(({ key, label, hint }) => {
        const scenario = item.scenarios[key];
        if (!scenario) return null;
        const positive = scenario.total_return_pct >= 0;
        return (
          <div key={key} className="rounded-xl border border-border/60 bg-card p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold">{label}</p>
              <Badge variant="outline" className="text-[10px]">
                {pct(scenario.assumed_appreciation_pct, 1)} p.a.
              </Badge>
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>
            <p
              className={cn(
                "mt-3 text-xl font-bold tabular-nums",
                positive ? "text-emerald-600" : "text-destructive"
              )}
            >
              {pct(scenario.total_return_pct, 1)}
            </p>
            <p className="text-xs text-muted-foreground">
              over {item.scenarios[key] ? "the holding period" : ""}
            </p>
            <dl className="mt-3 space-y-1 text-xs">
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Final value</dt>
                <dd className="tabular-nums">{inrCompact(scenario.final_property_value)}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground">Annualised</dt>
                <dd className="tabular-nums">{pct(scenario.annualized_return_pct, 1)}</dd>
              </div>
            </dl>
          </div>
        );
      })}
    </div>
  );
}

function PropertyInvestmentCard({ item }: { item: InvestmentSummary }) {
  const netCashFlow = item.cash_flow.net_cash_flow_monthly;
  return (
    <Card className="border-border/60">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">
              <Link href={`/properties/${item.property_id}`} className="hover:text-primary">
                {item.title}
              </Link>
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {[item.locality, item.city].filter(Boolean).join(", ")}
              {item.area_sqft != null && ` · ${item.area_sqft.toLocaleString("en-IN")} sq ft`}
            </p>
          </div>
          <Badge variant="secondary" className="shrink-0">
            {item.verification_status === "verified" ? "Verified listing" : "Unverified listing"}
          </Badge>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Verified: asking price {inr(item.asking_price)}
          {item.price_per_sqft != null && ` · ${inr(Math.round(item.price_per_sqft))}/sq ft`}
          {" — every other figure below is an assumption you control."}
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Loan */}
        <div>
          <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Banknote className="h-4 w-4 text-muted-foreground" />
            Financing
          </h4>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Down payment" value={inr(item.loan.down_payment)} hint={`${pct(item.loan.ltv_pct, 0)} loan-to-value`} icon={Wallet} />
            <Stat label="Loan amount" value={inr(item.loan.loan_amount)} />
            <Stat label="Monthly EMI" value={inr(item.loan.monthly_emi)} hint={`${pct(item.loan.annual_interest_rate, 1)} over ${item.loan.tenure_years} years`} icon={Calculator} />
            <Stat label="Total interest" value={inr(item.loan.total_interest)} hint="Over the full tenure" />
          </div>
        </div>

        {/* Upfront + recurring */}
        <div>
          <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Receipt className="h-4 w-4 text-muted-foreground" />
            Purchase and ownership costs
          </h4>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Upfront costs"
              value={inr(item.upfront_costs.total_upfront)}
              hint={`Stamp duty ${inrCompact(item.upfront_costs.stamp_duty)} · registration ${inrCompact(item.upfront_costs.registration)} · brokerage ${inrCompact(item.upfront_costs.brokerage)}`}
              icon={Receipt}
            />
            <Stat label="Total cash needed" value={inr(item.total_cash_required)} hint="Down payment plus upfront costs" icon={Wallet} tone="warning" />
            <Stat label="Ownership cost" value={`${inr(item.ownership_expenses.monthly_total)}/mo`} hint={`${inr(item.ownership_expenses.annual_total)} a year`} icon={Home} />
            <Stat label="Total interest" value={inr(item.loan.total_interest)} />
          </div>
        </div>

        {/* Yield + cash flow */}
        <div>
          <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
            Yield and cash flow
          </h4>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Gross rental yield"
              value={pct(item.yields.gross_rental_yield_pct as number | null)}
              hint="Annual rent ÷ asking price"
              icon={Percent}
            />
            <Stat
              label="Net rental yield"
              value={pct(item.yields.net_rental_yield_pct as number | null)}
              hint="After ownership expenses"
              icon={Percent}
            />
            <Stat
              label="Net monthly cash flow"
              value={inr(netCashFlow)}
              hint="Rent minus EMI and ownership costs"
              icon={netCashFlow >= 0 ? TrendingUp : TrendingDown}
              tone={netCashFlow >= 0 ? "success" : "danger"}
            />
            <Stat
              label="Net annual cash flow"
              value={inr(item.cash_flow.net_cash_flow_annual)}
              icon={TrendingUp}
              tone={item.cash_flow.is_positive ? "success" : "danger"}
            />
          </div>
        </div>

        {/* Scenarios */}
        <div>
          <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
            Return scenarios
          </h4>
          <ScenarioGrid item={item} />
        </div>
      </CardContent>
    </Card>
  );
}

/* ── Page ────────────────────────────────────────────────────────────── */

export default function FinancePage() {
  const [propertyIds, setPropertyIds] = useState("");
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<Property[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);

  const [monthlyRent, setMonthlyRent] = useState("25000");
  const [downPaymentPct, setDownPaymentPct] = useState("20");
  const [rate, setRate] = useState("8.5");
  const [years, setYears] = useState("20");
  const [maintenance, setMaintenance] = useState("3000");
  const [propertyTax, setPropertyTax] = useState("12000");
  const [insurance, setInsurance] = useState("0");
  const [vacancy, setVacancy] = useState("5");
  const [stampDuty, setStampDuty] = useState("5");
  const [registration, setRegistration] = useState("1");
  const [brokerage, setBrokerage] = useState("1");
  const [baseAppreciation, setBaseAppreciation] = useState("5");
  const [holdingYears, setHoldingYears] = useState("5");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<InvestmentResponse | null>(null);

  const parseIds = useCallback((raw: string): number[] => {
    return raw
      .split(/[,\s]+/)
      .map((part) => Number.parseInt(part.trim(), 10))
      .filter((id) => Number.isInteger(id) && id > 0)
      .slice(0, 4);
  }, []);

  const ids = useMemo(() => {
    const parsed = parseIds(propertyIds);
    // Any explicitly selected listing is added to the set to analyse.
    const merged = [...new Set([...parsed, ...selected])];
    return merged.slice(0, 4);
  }, [parseIds, propertyIds, selected]);

  const runSearch = useCallback(async () => {
    const q = search.trim();
    if (!q) return;
    setSearching(true);
    try {
      const data = await propertiesApi.list({ q, page_size: 6 });
      setResults(data.properties);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, [search]);

  const toggleSelected = (property: Property) => {
    setSelected((current) => {
      if (current.includes(property.id)) return current.filter((id) => id !== property.id);
      if (current.length >= 4) return current;
      return [...current, property.id];
    });
  };

  const submit = useCallback(
    async (event?: FormEvent) => {
      event?.preventDefault();
      setError(null);
      if (ids.length === 0) {
        setError("Add at least one property to analyse — search for it or paste its ID.");
        return;
      }
      setLoading(true);
      try {
        const data = await financeApi.investment({
          property_ids: ids,
          monthly_rent: toNumber(monthlyRent, 0),
          down_payment_pct: toNumber(downPaymentPct, 20),
          annual_interest_rate: toNumber(rate, 8.5),
          tenure_years: toNumber(years, 20),
          maintenance_monthly: toNumber(maintenance, 0),
          property_tax_annual: toNumber(propertyTax, 0),
          insurance_annual: toNumber(insurance, 0),
          expected_vacancy_pct: toNumber(vacancy, 0),
          stamp_duty_pct: toNumber(stampDuty, 5),
          registration_pct: toNumber(registration, 1),
          brokerage_pct: toNumber(brokerage, 1),
          base_appreciation_pct: toNumber(baseAppreciation, 5),
          holding_years: toNumber(holdingYears, 5),
        });
        setAnalysis(data);
      } catch (caught) {
        setAnalysis(null);
        setError(
          caught instanceof ApiError
            ? caught.message === "Request failed"
              ? "Could not run the investment analysis. Check the property IDs and try again."
              : caught.message
            : "Could not run the investment analysis. Check your connection and try again."
        );
      } finally {
        setLoading(false);
      }
    },
    [
      ids, monthlyRent, downPaymentPct, rate, years, maintenance, propertyTax, insurance,
      vacancy, stampDuty, registration, brokerage, baseAppreciation, holdingYears,
    ]
  );

  const best = useMemo(() => {
    if (!analysis) return null;
    const bestYield = analysis.items.find((i) => i.property_id === analysis.best_net_yield);
    const bestCash = analysis.items.find((i) => i.property_id === analysis.best_monthly_cash_flow);
    return { bestYield, bestCash, count: analysis.items.length };
  }, [analysis]);

  return (
    <div className="container-page py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Investment Intelligence</h1>
        <p className="mt-2 max-w-3xl text-slate-600">
          Model the money side of a purchase: loan and EMI, upfront charges, rental yield, monthly
          cash flow, and return scenarios. Asking prices come from the catalogue; every other input
          is yours to change.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[380px,1fr]">
        {/* ── Controls ─────────────────────────────────────────────── */}
        <div className="space-y-5">
          <Card className="border-border/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Home className="h-4 w-4" />
                </span>
                Properties
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Search for listings, or paste up to four property IDs.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      void runSearch();
                    }
                  }}
                  placeholder="e.g. 2 BHK in Hyderabad"
                  aria-label="Search properties to analyse"
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void runSearch()}
                  disabled={searching || !search.trim()}
                >
                  {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : "Find"}
                </Button>
              </div>

              {results.length > 0 && (
                <ul className="divide-y divide-border/60 rounded-lg border border-border/60">
                  {results.map((property) => {
                    const isSelected = ids.includes(property.id);
                    return (
                      <li key={property.id} className="flex items-center gap-2 p-2.5">
                        <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2">
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelected(property)}
                            className="h-4 w-4 shrink-0 accent-primary"
                            aria-label={`Analyse ${property.title}`}
                          />
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium">{property.title}</span>
                            <span className="block text-xs text-muted-foreground">
                              {[property.locality, property.city].filter(Boolean).join(", ")} ·{" "}
                              {inrCompact(property.price)}
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}

              <Field label="Or enter property IDs" hint="Comma separated, e.g. 1587, 1588">
                <Input
                  value={propertyIds}
                  onChange={(e) => setPropertyIds(e.target.value)}
                  placeholder="1587, 1588"
                  inputMode="numeric"
                />
              </Field>

              {selected.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {selected.map((id) => (
                    <Badge key={id} variant="secondary" className="gap-1 pr-1">
                      #{id}
                      <button
                        type="button"
                        onClick={() => setSelected((c) => c.filter((x) => x !== id))}
                        className="ml-0.5 rounded-full p-0.5 hover:bg-destructive/10 hover:text-destructive"
                        aria-label={`Remove property ${id}`}
                      >
                        ×
                      </button>
                    </Badge>
                  ))}
                </div>
              )}

              <Button type="submit" onClick={submit} disabled={loading} className="w-full gap-2">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
                Run investment analysis
              </Button>
              {error && (
                <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  {error}
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Percent className="h-4 w-4" />
                </span>
                Assumptions
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                These are your inputs, not market data. Change any of them and re-run.
              </p>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field label="Monthly rent (₹)">
                <Input inputMode="numeric" value={monthlyRent} onChange={(e) => setMonthlyRent(digits(e.target.value))} />
              </Field>
              <Field label="Down payment (%)">
                <Input inputMode="decimal" value={downPaymentPct} onChange={(e) => setDownPaymentPct(decimal(e.target.value))} />
              </Field>
              <Field label="Interest rate (% p.a.)">
                <Input inputMode="decimal" value={rate} onChange={(e) => setRate(decimal(e.target.value))} />
              </Field>
              <Field label="Tenure (years)">
                <Input inputMode="numeric" value={years} onChange={(e) => setYears(digits(e.target.value))} />
              </Field>
              <Field label="Maintenance (₹/month)">
                <Input inputMode="numeric" value={maintenance} onChange={(e) => setMaintenance(digits(e.target.value))} />
              </Field>
              <Field label="Property tax (₹/year)">
                <Input inputMode="numeric" value={propertyTax} onChange={(e) => setPropertyTax(digits(e.target.value))} />
              </Field>
              <Field label="Insurance (₹/year)">
                <Input inputMode="numeric" value={insurance} onChange={(e) => setInsurance(digits(e.target.value))} />
              </Field>
              <Field label="Expected vacancy (%)">
                <Input inputMode="decimal" value={vacancy} onChange={(e) => setVacancy(decimal(e.target.value))} />
              </Field>
              <Field label="Stamp duty (%)">
                <Input inputMode="decimal" value={stampDuty} onChange={(e) => setStampDuty(decimal(e.target.value))} />
              </Field>
              <Field label="Registration (%)">
                <Input inputMode="decimal" value={registration} onChange={(e) => setRegistration(decimal(e.target.value))} />
              </Field>
              <Field label="Brokerage (%)">
                <Input inputMode="decimal" value={brokerage} onChange={(e) => setBrokerage(decimal(e.target.value))} />
              </Field>
              <Field label="Base appreciation (% p.a.)" hint="An assumption, never a forecast">
                <Input inputMode="decimal" value={baseAppreciation} onChange={(e) => setBaseAppreciation(decimal(e.target.value))} />
              </Field>
              <Field label="Holding period (years)">
                <Input inputMode="numeric" value={holdingYears} onChange={(e) => setHoldingYears(digits(e.target.value))} />
              </Field>
            </CardContent>
          </Card>
        </div>

        {/* ── Results ──────────────────────────────────────────────── */}
        <div className="space-y-5">
          {loading && (
            <div className="space-y-4">
              <Skeleton className="h-32 rounded-xl" />
              <Skeleton className="h-64 rounded-xl" />
            </div>
          )}

          {!loading && !analysis && (
            <EmptyState
              title="No analysis yet"
              description="Search for a property or enter its ID, adjust the assumptions, and run the analysis. Asking prices come from the catalogue; the rest is your input."
              actionHref="/search"
              actionLabel="Browse properties"
            />
          )}

          {!loading && analysis && analysis.items.length === 0 && (
            <ErrorState
              message="None of those property IDs matched a listing in the catalogue, so no analysis could be produced."
              onRetry={() => submit()}
            />
          )}

          {!loading && analysis && analysis.items.length > 0 && (
            <>
              <Card className="border-border/60 bg-primary/5">
                <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Analysed
                    </p>
                    <p className="text-2xl font-bold tabular-nums">
                      {analysis.items.length} propert{analysis.items.length === 1 ? "y" : "ies"}
                    </p>
                    <p className="mt-1 max-w-md text-sm text-muted-foreground">
                      {analysis.assumptions_note}
                    </p>
                  </div>
                  {best && best.count > 1 && (
                    <div className="space-y-2 text-sm">
                      {best.bestYield && (
                        <p className="flex items-center gap-2">
                          <TrendingUp className="h-4 w-4 text-emerald-600" />
                          Best net yield:{" "}
                          <Link href={`/properties/${best.bestYield.property_id}`} className="font-medium hover:underline">
                            {best.bestYield.title}
                          </Link>
                        </p>
                      )}
                      {best.bestCash && (
                        <p className="flex items-center gap-2">
                          <Banknote className="h-4 w-4 text-primary" />
                          Best monthly cash flow:{" "}
                          <Link href={`/properties/${best.bestCash.property_id}`} className="font-medium hover:underline">
                            {best.bestCash.title}
                          </Link>
                        </p>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>

              {analysis.items.map((item) => (
                <PropertyInvestmentCard key={item.property_id} item={item} />
              ))}

              <div className="flex items-start gap-2 rounded-xl border border-border/60 bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <p>
                  <span className="font-semibold text-foreground">Not a promise of returns.</span>{" "}
                  {analysis.disclaimer} Appreciation rates are assumptions you chose, not market
                  forecasts. Rental income is only realised if the property is actually let, and
                  vacancies, repairs and tax changes will alter the outcome.
                </p>
              </div>

              <p className="text-sm text-muted-foreground">
                Source: {analysis.source}. Generated {new Date(analysis.generated_at).toLocaleString()}.
              </p>
            </>
          )}

          {!loading && !analysis && (
            <div className="flex items-start gap-2 rounded-xl border border-border/60 bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <p>
                Every calculation uses the standard amortisation and yield formulas on the asking
                price plus your assumptions. Buy-side charges default to common Indian rates
                (stamp duty {stampDuty}%, registration {registration}%, brokerage {brokerage}%) — check
                your state&apos;s actual rates.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
