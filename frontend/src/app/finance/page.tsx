"use client";

import { useCallback, useMemo, useState, FormEvent, useEffect, useRef } from "react";
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
  Globe2,
  X,
  ExternalLink,
} from "lucide-react";
import { financeApi, propertiesApi, marketApi, ApiError } from "@/lib/api";
import type {
  InvestmentResponse,
  InvestmentSummary,
  Property,
  ExternalMarketResearch,
} from "@/lib/types";
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

/* ── analysis entries (catalogue / manual / external) ──────────────────── */

type EntrySource = "catalogue" | "manual" | "external";

interface AnalysisEntry {
  key: string;
  source: EntrySource;
  /** Catalogue property id (source === "catalogue"). */
  propertyId?: number;
  /** Manual label, or the external location label. */
  label: string;
  /** User-entered price (source === "manual"). */
  price?: number;
  /** External location (source === "external"). */
  location?: string;
  city?: string;
  locality?: string;
  areaSqft?: number;
}

const MAX_ANALYSIS_ENTRIES = 4;

const SOURCE_BADGES: Record<EntrySource, { label: string; className: string }> = {
  catalogue: { label: "Catalogue listing", className: "border-emerald-300/60 bg-emerald-50/60 text-emerald-800" },
  manual: { label: "Your price", className: "border-blue-300/60 bg-blue-50/60 text-blue-800" },
  external: { label: "External estimate", className: "border-amber-300/60 bg-amber-50/60 text-amber-800" },
};

function formatCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_00_00_000) return `${sign}₹${(abs / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `${sign}₹${(abs / 1_00_000).toFixed(abs >= 10_00_000 ? 0 : 1)} L`;
  if (abs >= 1_000) return `${sign}₹${(abs / 1_000).toFixed(1)} K`;
  return `${sign}₹${abs.toFixed(0)}`;
}

function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-foreground">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted-foreground">{hint}</span>}
      {error && (
        <span className="mt-1 block text-xs text-destructive">{error}</span>
      )}
    </label>
  );
}

function digits(raw: string): string {
  return raw.replace(/[^\d]/g, "");
}

function decimal(raw: string): string {
  const cleaned = raw.replace(/[^\d.-]/g, "");
  const parts = cleaned.split(".");
  return parts.length > 2 ? `${parts[0]}.${parts.slice(1).join("")}` : cleaned;
}

/** Parse a numeric input; returns the fallback when the text is unusable. */
function toNumber(raw: string, fallback: number): number {
  const n = Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

function Stat({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
  testId,
}: {
  label: string;
  value: string;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
  tone?: "default" | "success" | "danger" | "warning";
  testId?: string;
}) {
  const toneClass =
    tone === "success" ? "text-emerald-600"
    : tone === "danger" ? "text-destructive"
    : tone === "warning" ? "text-amber-600"
    : "text-foreground";
  return (
    <div className="rounded-xl border border-border/60 bg-card p-4" data-testid={testId}>
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
  const sourceMeta =
    item.price_source === "external_estimate"
      ? { label: "External estimate", className: "border-amber-300/60 bg-amber-50/60 text-amber-800" }
      : item.price_source === "user_input"
        ? { label: "Your price", className: "border-blue-300/60 bg-blue-50/60 text-blue-800" }
        : { label: "Verified listing", className: "border-emerald-300/60 bg-emerald-50/60 text-emerald-800" };
  return (
    <Card className="border-border/60">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">
              {item.property_id ? (
                <Link href={`/properties/${item.property_id}`} className="hover:text-primary">
                  {item.title}
                </Link>
              ) : (
                item.title
              )}
            </CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              {[item.locality, item.city].filter(Boolean).join(", ")}
              {item.area_sqft != null && ` · ${item.area_sqft.toLocaleString("en-IN")} sq ft`}
            </p>
          </div>
          <Badge variant="secondary" className={`shrink-0 ${sourceMeta.className}`}>
            {sourceMeta.label}
          </Badge>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          {item.price_source === "catalogue"
            ? `Verified asking price ${inr(item.asking_price)}`
            : `Analysis price ${inr(item.asking_price)}`}
          {item.price_per_sqft != null && ` · ${inr(Math.round(item.price_per_sqft))}/sq ft`}
          {" — every other figure below is an assumption you control."}
        </p>
        {item.price_source_note && (
          <p className="mt-1 text-[11px] text-muted-foreground">{item.price_source_note}</p>
        )}
        {item.external_sources && item.external_sources.length > 0 && (
          <div className="mt-1.5 space-y-0.5">
            {item.external_sources.slice(0, 3).map((source) => (
              <a
                key={source.url}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-[11px] text-primary hover:underline"
              >
                <ExternalLink className="h-3 w-3 shrink-0" />
                <span className="truncate">
                  {source.domain ?? source.title}
                  {source.published_at ? ` · published ${new Date(source.published_at).toLocaleDateString()}` : ""}
                </span>
              </a>
            ))}
          </div>
        )}
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
              testId="gross-yield-stat"
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
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<Property[]>([]);
  const [searching, setSearching] = useState(false);
  /** Up to four analysis entries from any source. */
  const [entries, setEntries] = useState<AnalysisEntry[]>([]);

  // Manual entry form.
  const [manualLabel, setManualLabel] = useState("");
  const [manualPrice, setManualPrice] = useState("");
  const [manualCity, setManualCity] = useState("");
  const [manualArea, setManualArea] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);

  // External-location research form.
  const [locationQuery, setLocationQuery] = useState("");
  const [researching, setResearching] = useState(false);
  const [research, setResearch] = useState<ExternalMarketResearch | null>(null);
  const [researchError, setResearchError] = useState<string | null>(null);

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
  const entriesRef = useRef(entries);
  useEffect(() => {
    entriesRef.current = entries;
  }, [entries]);

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

  const toggleCatalogueEntry = (property: Property) => {
    setEntries((current) => {
      const existing = current.find((e) => e.source === "catalogue" && e.propertyId === property.id);
      if (existing) return current.filter((e) => e !== existing);
      if (current.length >= MAX_ANALYSIS_ENTRIES) return current;
      return [
        ...current,
        {
          key: `cat-${property.id}`,
          source: "catalogue",
          propertyId: property.id,
          label: property.title,
        },
      ];
    });
  };

  const addManualEntry = () => {
    setManualError(null);
    const label = manualLabel.trim();
    const price = Number(manualPrice);
    if (!label) {
      setManualError("Give the property a short label so you can tell results apart.");
      return;
    }
    if (!Number.isFinite(price) || price <= 0) {
      setManualError("Enter a positive property price (the figure you want to model).");
      return;
    }
    if (entriesRef.current.length >= MAX_ANALYSIS_ENTRIES) {
      setManualError(`You can analyse at most ${MAX_ANALYSIS_ENTRIES} properties at once.`);
      return;
    }
    const area = manualArea.trim() ? Number(manualArea) : undefined;
    if (area !== undefined && (!Number.isFinite(area) || area <= 0)) {
      setManualError("Area must be a positive number of square feet, or left empty.");
      return;
    }
    setEntries((current) => [
      ...current,
      {
        key: `manual-${Date.now()}`,
        source: "manual",
        label,
        price,
        city: manualCity.trim() || undefined,
        areaSqft: area,
      },
    ]);
    setManualLabel("");
    setManualPrice("");
    setManualCity("");
    setManualArea("");
  };

  const runResearch = useCallback(async () => {
    const location = locationQuery.trim();
    if (!location) return;
    setResearching(true);
    setResearchError(null);
    setResearch(null);
    try {
      const data = await marketApi.external({ location });
      setResearch(data);
    } catch (caught) {
      setResearch(null);
      setResearchError(
        caught instanceof ApiError
          ? caught.message === "Request failed"
            ? "External market research is unavailable right now."
            : caught.message
          : "External market research is unavailable right now."
      );
    } finally {
      setResearching(false);
    }
  }, [locationQuery]);

  const addExternalEntry = () => {
    setResearchError(null);
    const location = locationQuery.trim();
    if (!location || !research) return;
    if (entriesRef.current.length >= MAX_ANALYSIS_ENTRIES) {
      setResearchError(`You can analyse at most ${MAX_ANALYSIS_ENTRIES} properties at once.`);
      return;
    }
    const asking = research.statistics?.asking_price;
    if (!asking?.available || !asking.median) {
      setResearchError(
        "No external asking-price observation is available for this location, so there is no price to analyse."
      );
      return;
    }
    setEntries((current) => [
      ...current,
      {
        key: `ext-${Date.now()}`,
        source: "external",
        location,
        label: location,
      },
    ]);
  };

  const removeEntry = (key: string) => {
    setEntries((current) => current.filter((e) => e.key !== key));
  };

  const submit = useCallback(
    async (event?: FormEvent) => {
      event?.preventDefault();
      setError(null);
      const current = entriesRef.current;
      if (current.length === 0) {
        setError(
          "Add at least one property to analyse — search the catalogue, enter a price, or look up a location."
        );
        return;
      }
      setLoading(true);
      try {
        const data = await financeApi.investment({
          property_ids: current.filter((e) => e.source === "catalogue").map((e) => e.propertyId!),
          manual_properties: current
            .filter((e) => e.source === "manual")
            .map((e) => ({
              label: e.label,
              price: e.price!,
              city: e.city,
              area_sqft: e.areaSqft,
            })),
          external_locations: current
            .filter((e) => e.source === "external")
            .map((e) => ({ location: e.location!, label: e.label })),
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
              ? "Could not run the investment analysis. Check your inputs and try again."
              : caught.message
            : "Could not run the investment analysis. Check your connection and try again."
        );
      } finally {
        setLoading(false);
      }
    },
    [monthlyRent, downPaymentPct, rate, years, maintenance, propertyTax, insurance,
      vacancy, stampDuty, registration, brokerage, baseAppreciation, holdingYears]
  );

  const best = useMemo(() => {
    if (!analysis) return null;
    const bestYield = analysis.items.find((i) => i.property_id === analysis.best_net_yield);
    const bestCash = analysis.items.find((i) => i.property_id === analysis.best_monthly_cash_flow);
    return { bestYield, bestCash, count: analysis.items.length };
  }, [analysis]);

  const askingStat = research?.statistics?.asking_price;
  const rentStat = research?.statistics?.rent_monthly;

  return (
    <div className="container-page py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Investment Intelligence</h1>
        <p className="mt-2 max-w-3xl text-slate-600">
          Model the money side of a purchase: loan and EMI, upfront charges, rental yield, monthly
          cash flow, and return scenarios. Analyse catalogue listings, a price you enter yourself, or
          an external market estimate — every other input is yours to change.
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
                Properties to analyse
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                Add up to four: catalogue listings, your own price, or an external market estimate.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Catalogue search */}
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  1 · Search the catalogue
                </label>
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
                  <ul className="mt-2 divide-y divide-border/60 rounded-lg border border-border/60">
                    {results.map((property) => {
                      const isSelected = entries.some(
                        (e) => e.source === "catalogue" && e.propertyId === property.id
                      );
                      return (
                        <li key={property.id} className="flex items-center gap-2 p-2.5">
                          <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => toggleCatalogueEntry(property)}
                              className="h-4 w-4 shrink-0 accent-primary"
                              aria-label={`Analyse ${property.title}`}
                            />
                            <span className="min-w-0">
                              <span className="block truncate text-sm font-medium">{property.title}</span>
                              <span className="block text-xs text-muted-foreground">
                                {[property.locality, property.city].filter(Boolean).join(", ")} ·{" "}
                                {inrCompact(property.price)} · verified listing
                              </span>
                            </span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              {/* Manual entry */}
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  2 · Or enter a price yourself
                </label>
                <div className="space-y-2">
                  <Input
                    value={manualLabel}
                    onChange={(e) => setManualLabel(e.target.value)}
                    placeholder="Label, e.g. “Hyderabad 3BHK (my budget)”"
                    aria-label="Property label"
                  />
                  <div className="flex gap-2">
                    <Input
                      value={manualPrice}
                      onChange={(e) => setManualPrice(digits(e.target.value))}
                      placeholder="Price (₹)"
                      inputMode="numeric"
                      aria-label="Property price"
                      className="flex-1"
                    />
                    <Input
                      value={manualArea}
                      onChange={(e) => setManualArea(digits(e.target.value))}
                      placeholder="Area sq.ft"
                      inputMode="numeric"
                      aria-label="Area in square feet"
                      className="w-28"
                    />
                  </div>
                  <div className="flex gap-2">
                    <Input
                      value={manualCity}
                      onChange={(e) => setManualCity(e.target.value)}
                      placeholder="City (optional)"
                      aria-label="City"
                      className="flex-1"
                    />
                    <Button type="button" variant="outline" onClick={addManualEntry}>
                      Add property
                    </Button>
                  </div>
                  {manualError && (
                    <p role="alert" className="text-xs text-destructive">
                      {manualError}
                    </p>
                  )}
                </div>
              </div>

              {/* External location research */}
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  3 · Or use external market research
                </label>
                <div className="flex gap-2">
                  <Input
                    value={locationQuery}
                    onChange={(e) => setLocationQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        void runResearch();
                      }
                    }}
                    placeholder="e.g. Hyderabad or London"
                    aria-label="Location for external market research"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void runResearch()}
                    disabled={researching || !locationQuery.trim()}
                    className="gap-1.5"
                  >
                    {researching ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Globe2 className="h-4 w-4" />
                    )}
                    Research
                  </Button>
                </div>

                {researching && <Skeleton className="mt-2 h-24 rounded-lg" />}

                {!researching && research && (
                  <div className="mt-2 rounded-lg border border-amber-300/50 bg-amber-50/40 p-3 text-xs">
                    {research.status === "ok" ? (
                      <>
                        <p className="font-semibold text-amber-900">
                          External observations for {research.location_input}
                        </p>
                        <dl className="mt-1.5 space-y-0.5 text-amber-900/90">
                          <div className="flex justify-between gap-2">
                            <dt>Median asking price</dt>
                            <dd className="tabular-nums">
                              {askingStat?.available && askingStat.median != null
                                ? formatCompact(askingStat.median)
                                : "Data unavailable"}
                            </dd>
                          </div>
                          <div className="flex justify-between gap-2">
                            <dt>Typical monthly rent</dt>
                            <dd className="tabular-nums">
                              {rentStat?.available && rentStat.median != null
                                ? formatCompact(rentStat.median)
                                : "Data unavailable"}
                            </dd>
                          </div>
                          <div className="flex justify-between gap-2">
                            <dt>Observations</dt>
                            <dd className="tabular-nums">{askingStat?.sample_size ?? 0} source(s)</dd>
                          </div>
                        </dl>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="mt-2 h-7 w-full text-xs"
                          onClick={addExternalEntry}
                          disabled={!askingStat?.available}
                        >
                          {askingStat?.available ? "Use as property price" : "No usable price retrieved"}
                        </Button>
                        {research.sources?.[0]?.url && (
                          <a
                            href={research.sources[0].url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="mt-1.5 flex items-center gap-1 text-[11px] text-primary hover:underline"
                          >
                            <ExternalLink className="h-3 w-3" />
                            {research.sources[0].domain}
                          </a>
                        )}
                      </>
                    ) : (
                      <p className="text-amber-900/90">
                        {research.message ??
                          (research.status === "not_configured"
                            ? "Web search is not configured for this deployment, so no external observations could be retrieved."
                            : research.status === "unavailable"
                              ? "External market search is temporarily unavailable."
                              : "No external market information with usable figures was found for this location.")}
                      </p>
                    )}
                  </div>
                )}
                {!researching && researchError && (
                  <p role="alert" className="mt-2 flex items-start gap-1.5 text-xs text-destructive">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    {researchError}
                  </p>
                )}
              </div>

              {/* Selected entries */}
              {entries.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-muted-foreground">
                    Selected ({entries.length}/{MAX_ANALYSIS_ENTRIES})
                  </p>
                  {entries.map((entry) => (
                    <div
                      key={entry.key}
                      className="flex items-center gap-2 rounded-lg border border-border/60 bg-muted/30 px-2.5 py-2"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{entry.label}</p>
                        <div className="flex items-center gap-1.5">
                          <Badge
                            variant="outline"
                            className={cn("text-[10px]", SOURCE_BADGES[entry.source].className)}
                          >
                            {SOURCE_BADGES[entry.source].label}
                          </Badge>
                          {entry.source === "manual" && entry.price != null && (
                            <span className="text-[11px] text-muted-foreground">
                              {inrCompact(entry.price)}
                            </span>
                          )}
                          {entry.source === "external" && entry.location && (
                            <span className="truncate text-[11px] text-muted-foreground">
                              {entry.location}
                            </span>
                          )}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeEntry(entry.key)}
                        className="rounded-full p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        aria-label={`Remove ${entry.label} from the analysis`}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => setEntries([])}
                  >
                    Clear all selections
                  </Button>
                </div>
              )}

              <Button
                type="submit"
                onClick={submit}
                disabled={loading}
                className="w-full gap-2"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Calculator className="h-4 w-4" />
                )}
                Run investment analysis
              </Button>
              {error && (
                <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  {error}
                </p>
              )}
              <p className="text-[11px] text-muted-foreground">
                All figures are computed by deterministic backend formulas on the inputs below —
                never generated by the AI model.
              </p>
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
              description="Add a catalogue listing, enter your own price, or run external market research — then adjust the assumptions and run the analysis."
              actionHref="/search"
              actionLabel="Browse properties"
            />
          )}

          {!loading && analysis && analysis.items.length === 0 && (
            <ErrorState
              message={
                analysis.skipped?.length
                  ? analysis.skipped.map((s) => `${s.reference}: ${s.reason}`).join(" ")
                  : "None of the selected properties could be analysed, so no analysis was produced."
              }
              onRetry={() => submit()}
            />
          )}

          {!loading && analysis && analysis.skipped && analysis.skipped.length > 0 && (
            <div className="flex items-start gap-2 rounded-xl border border-amber-200/60 bg-amber-50/50 px-4 py-3 text-xs text-amber-900">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <div>
                <p className="font-medium">Some entries could not be analysed</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-4">
                  {analysis.skipped.map((s) => (
                    <li key={s.reference}>
                      {s.reference} — {s.reason}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
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
                          {best.bestYield.property_id ? (
                            <Link
                              href={`/properties/${best.bestYield.property_id}`}
                              className="font-medium hover:underline"
                            >
                              {best.bestYield.title}
                            </Link>
                          ) : (
                            <span className="font-medium">{best.bestYield.title}</span>
                          )}
                        </p>
                      )}
                      {best.bestCash && (
                        <p className="flex items-center gap-2">
                          <Banknote className="h-4 w-4 text-primary" />
                          Best monthly cash flow:{" "}
                          {best.bestCash.property_id ? (
                            <Link
                              href={`/properties/${best.bestCash.property_id}`}
                              className="font-medium hover:underline"
                            >
                              {best.bestCash.title}
                            </Link>
                          ) : (
                            <span className="font-medium">{best.bestCash.title}</span>
                          )}
                        </p>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>

              {analysis.items.map((item) => (
                <PropertyInvestmentCard key={item.property_id ?? item.title} item={item} />
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
