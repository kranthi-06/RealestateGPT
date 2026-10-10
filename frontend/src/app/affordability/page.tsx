"use client";

import { useEffect, useMemo, useRef, useState, useCallback, FormEvent, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  Calculator,
  Loader2,
  Home,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  IndianRupee,
  Percent,
  CalendarClock,
  Wallet,
  Banknote,
  Info,
  PiggyBank,
  Receipt,
  TrendingDown,
} from "lucide-react";
import { financeApi, ApiError } from "@/lib/api";
import type { FullAffordabilityResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/* â”€â”€ Indian formatting helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

function inr(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "â€”";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function inrCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "â€”";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_00_00_000) return `${sign}â‚¹${(abs / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `${sign}â‚¹${(abs / 1_00_000).toFixed(abs >= 10_00_000 ? 0 : 1)} L`;
  if (abs >= 1_000) return `${sign}â‚¹${(abs / 1_000).toFixed(1)} K`;
  return `${sign}â‚¹${abs.toFixed(0)}`;
}

function pct(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "â€”";
  return `${value.toFixed(digits)}%`;
}

/** Accept only digits, and never return NaN. */
function digits(raw: string): string {
  return raw.replace(/[^\d]/g, "");
}

function decimal(raw: string): string {
  const cleaned = raw.replace(/[^\d.]/g, "");
  const parts = cleaned.split(".");
  return parts.length > 2 ? `${parts[0]}.${parts.slice(1).join("")}` : cleaned;
}

function toNumber(raw: string, fallback: number): number {
  const n = Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

/* â”€â”€ Small pieces â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

function InputCard({
  title,
  description,
  icon: Icon,
  children,
}: {
  title: string;
  description?: string;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <Card className="border-border/60">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="h-4 w-4" />
          </span>
          {title}
        </CardTitle>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </CardHeader>
      <CardContent className="space-y-4 pt-0">{children}</CardContent>
    </Card>
  );
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

function ResultCard({
  label,
  value,
  compactValue,
  hint,
  icon: Icon,
  tone = "default",
  large = false,
}: {
  label: string;
  value: string;
  compactValue?: string;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
  tone?: "default" | "primary" | "success" | "warning" | "danger";
  large?: boolean;
}) {
  const toneClass =
    tone === "primary"
      ? "text-primary"
      : tone === "success"
        ? "text-emerald-600"
        : tone === "warning"
          ? "text-amber-600"
          : tone === "danger"
            ? "text-destructive"
            : "text-foreground";
  return (
    <Card
      className={cn(
        "border-border/60",
        tone === "primary" && "border-primary/30 bg-primary/5",
        tone === "success" && "border-emerald-200/60 bg-emerald-50/40",
        tone === "warning" && "border-amber-200/60 bg-amber-50/40",
        tone === "danger" && "border-destructive/30 bg-destructive/5"
      )}
    >
      <CardContent className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
          {Icon && <Icon className="h-4 w-4 shrink-0 text-muted-foreground/60" />}
        </div>
        <p
          className={cn(
            "mt-2 font-bold tabular-nums leading-tight break-words",
            large ? "text-2xl sm:text-3xl" : "text-lg sm:text-xl",
            toneClass
          )}
        >
          {value}
        </p>
        {compactValue && (
          <p className="mt-0.5 text-sm font-medium tabular-nums text-muted-foreground">
            {compactValue}
          </p>
        )}
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

function EstimateNote() {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-border/60 bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <p>
        <span className="font-semibold text-foreground">These are estimates, not approvals.</span>{" "}
        Figures use the income, savings, rate, tenure and transaction-cost rates you enter. They do not
        reflect any lender&apos;s eligibility rules, credit assessment or property valuation. Actual
        loan terms are decided only by the lender after reviewing your documents.
      </p>
    </div>
  );
}

/* â”€â”€ Affordability calculator â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

function AffordabilityCalculator() {
  const searchParams = useSearchParams();

  const [income, setIncome] = useState("70000");
  const [existingEmi, setExistingEmi] = useState("0");
  const [savings, setSavings] = useState("1200000");
  const [downPayment, setDownPayment] = useState("1000000");
  const [propertyPrice, setPropertyPrice] = useState("");
  const [rate, setRate] = useState("8.5");
  const [years, setYears] = useState("20");
  const [maintenance, setMaintenance] = useState("3000");
  const [propertyTax, setPropertyTax] = useState("12000");
  const [insurance, setInsurance] = useState("0");
  const [other, setOther] = useState("0");
  const [stampDuty, setStampDuty] = useState("5");
  const [registration, setRegistration] = useState("1");
  const [brokerage, setBrokerage] = useState("1");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FullAffordabilityResult | null>(null);
  const prefilled = useRef(false);

  // Deep links from a property detail page carry ?price=â€¦&tenure=â€¦&down=â€¦
  // Apply them once so the property is checked with the user's own finances.
  useEffect(() => {
    if (prefilled.current) return;
    const price = searchParams.get("price");
    const tenure = searchParams.get("tenure");
    const down = searchParams.get("down");
    const id = window.setTimeout(() => {
      if (price) setPropertyPrice(digits(price));
      if (tenure) setYears(digits(tenure));
      if (down) setDownPayment(digits(down));
      prefilter: void down;
      prefilled.current = true;
    }, 0);
    return () => window.clearTimeout(id);
  }, [searchParams]);

  const incomeNum = toNumber(income, 0);
  const existingEmiNum = toNumber(existingEmi, 0);
  const savingsNum = toNumber(savings, 0);
  const downPaymentNum = toNumber(downPayment, 0);
  const propertyPriceNum = toNumber(propertyPrice, 0);
  const rateNum = toNumber(rate, 0);
  const yearsNum = toNumber(years, 0);
  const maintenanceNum = toNumber(maintenance, 0);
  const propertyTaxNum = toNumber(propertyTax, 0);
  const insuranceNum = toNumber(insurance, 0);
  const otherNum = toNumber(other, 0);
  const stampDutyNum = toNumber(stampDuty, 0);
  const registrationNum = toNumber(registration, 0);
  const brokerageNum = toNumber(brokerage, 0);

  const validationError = useMemo(() => {
    if (income === "" || incomeNum <= 0) return "Enter a monthly income greater than zero.";
    if (rate === "" || rateNum <= 0 || rateNum > 50) return "Enter an interest rate between 0 and 50%.";
    if (years === "" || yearsNum <= 0 || yearsNum > 40) return "Enter a tenure between 0 and 40 years.";
    if (existingEmiNum < 0) return "Existing EMI cannot be negative.";
    if (downPaymentNum < 0) return "Down payment cannot be negative.";
    if (savingsNum < 0) return "Savings cannot be negative.";
    if (propertyPrice !== "" && propertyPriceNum <= 0) {
      return "Enter a property price greater than zero, or leave it blank.";
    }
    if (stampDutyNum < 0 || registrationNum < 0 || brokerageNum < 0) {
      return "Transaction-cost percentages cannot be negative.";
    }
    return null;
  }, [
    income, incomeNum, rate, rateNum, years, yearsNum, existingEmiNum, downPaymentNum,
    savingsNum, propertyPrice, propertyPriceNum, stampDutyNum, registrationNum, brokerageNum,
  ]);

  const submit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      setError(null);
      if (validationError) {
        setResult(null);
        setError(validationError);
        return;
      }
      setLoading(true);
      try {
        const res = await financeApi.fullAffordability({
          monthly_income: incomeNum,
          existing_obligations: existingEmiNum,
          savings: savingsNum,
          down_payment: downPaymentNum,
          property_price: propertyPriceNum > 0 ? propertyPriceNum : undefined,
          annual_interest_rate: rateNum,
          tenure_years: yearsNum,
          maintenance_monthly: maintenanceNum,
          property_tax_annual: propertyTaxNum,
          insurance_annual: insuranceNum,
          other_monthly: otherNum,
          stamp_duty_pct: stampDutyNum,
          registration_pct: registrationNum,
          brokerage_pct: brokerageNum,
        });
        setResult(res);
      } catch (caught) {
        setResult(null);
        setError(
          caught instanceof ApiError
            ? caught.message === "Request failed"
              ? "Could not calculate affordability. Check the values and try again."
              : caught.message
            : "Could not calculate affordability. Check your connection and try again."
        );
      } finally {
        setLoading(false);
      }
    },
    [
      validationError, incomeNum, existingEmiNum, savingsNum, downPaymentNum, propertyPriceNum,
      rateNum, yearsNum, maintenanceNum, propertyTaxNum, insuranceNum, otherNum,
      stampDutyNum, registrationNum, brokerageNum,
    ]
  );

  type Tone = "success" | "warning" | "danger";
  const status = useMemo(() => {
    if (!result) return null;
    // Trust the server's verdict, which accounts for both EMI capacity and
    // the cash needed upfront â€” not the price on its own.
    const tone: Tone =
      result.verdict === "not_affordable" ? "danger"
      : result.verdict === "strained" ? "warning"
      : "success";
    const label =
      result.verdict === "not_affordable" ? "Not affordable"
      : result.verdict === "strained" ? "Manageable but tight"
      : "Comfortable";
    const note =
      result.verdict === "not_affordable"
        ? "The required monthly outflow is above what this income supports."
        : result.verdict === "strained"
          ? "Workable, but the recurring costs leave a thin buffer."
          : "The monthly outflow stays within your capacity on these inputs.";
    const icon =
      result.verdict === "not_affordable" ? XCircle
      : result.verdict === "strained" ? AlertTriangle
      : CheckCircle2;
    return { label, icon, tone, note };
  }, [result]);

  const toneClasses: Record<Tone, string> = {
    success: "border-emerald-200/60 bg-emerald-50/40",
    warning: "border-amber-200/60 bg-amber-50/40",
    danger: "border-destructive/30 bg-destructive/5",
  };
  const badgeClasses: Record<Tone, string> = {
    success: "bg-emerald-100 text-emerald-700",
    warning: "bg-amber-100 text-amber-700",
    danger: "bg-destructive/10 text-destructive",
  };
  const iconClasses: Record<Tone, string> = {
    success: "bg-emerald-100 text-emerald-700",
    warning: "bg-amber-100 text-amber-700",
    danger: "bg-destructive/10 text-destructive",
  };

  const assessment = result?.property_assessment ?? null;

  return (
    <div className="space-y-5">
      <InputCard
        title="Your financial profile"
        description="These are your inputs. Everything below the button is calculated from them."
        icon={Home}
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Monthly income" hint="Gross take-home monthly income">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="numeric" placeholder="e.g. 70000" className="pl-9 tabular-nums" value={income} onChange={(e) => setIncome(digits(e.target.value))} />
            </div>
          </Field>
          <Field label="Existing monthly EMI" hint="All current loan instalments combined">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="numeric" placeholder="e.g. 12000" className="pl-9 tabular-nums" value={existingEmi} onChange={(e) => setExistingEmi(digits(e.target.value))} />
            </div>
          </Field>
          <Field label="Available savings" hint="Total cash you can access">
            <div className="relative">
              <PiggyBank className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="numeric" placeholder="e.g. 1200000" className="pl-9 tabular-nums" value={savings} onChange={(e) => setSavings(digits(e.target.value))} />
            </div>
          </Field>
          <Field label="Down payment" hint="Cash you will put down">
            <div className="relative">
              <Wallet className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="numeric" placeholder="e.g. 1000000" className="pl-9 tabular-nums" value={downPayment} onChange={(e) => setDownPayment(digits(e.target.value))} />
            </div>
          </Field>
          <Field label="Target property price" hint="Optional â€” checks a specific property">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="numeric" placeholder="e.g. 5000000" className="pl-9 tabular-nums" value={propertyPrice} onChange={(e) => setPropertyPrice(digits(e.target.value))} />
            </div>
          </Field>
          <Field label="Interest rate (% p.a.)">
            <div className="relative">
              <Percent className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="decimal" placeholder="e.g. 8.5" className="pl-9 tabular-nums" value={rate} onChange={(e) => setRate(decimal(e.target.value))} />
            </div>
          </Field>
          <Field label="Loan tenure (years)">
            <div className="relative">
              <CalendarClock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="numeric" placeholder="e.g. 20" className="pl-9 tabular-nums" value={years} onChange={(e) => setYears(digits(e.target.value))} />
            </div>
          </Field>
        </div>
      </InputCard>

      <InputCard
        title="Recurring costs and transaction charges"
        description="Estimates you can adjust. They are assumptions, not quotes."
        icon={Receipt}
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Maintenance (â‚¹/month)">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="numeric" placeholder="e.g. 3000" className="pl-9 tabular-nums" value={maintenance} onChange={(e) => setMaintenance(digits(e.target.value))} />
            </div>
          </Field>
          <Field label="Property tax (â‚¹/year)">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="numeric" placeholder="e.g. 12000" className="pl-9 tabular-nums" value={propertyTax} onChange={(e) => setPropertyTax(digits(e.target.value))} />
            </div>
          </Field>
          <Field label="Insurance (â‚¹/year)">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="numeric" placeholder="e.g. 0" className="pl-9 tabular-nums" value={insurance} onChange={(e) => setInsurance(digits(e.target.value))} />
            </div>
          </Field>
          <Field label="Other (â‚¹/month)">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="numeric" placeholder="e.g. 0" className="pl-9 tabular-nums" value={other} onChange={(e) => setOther(digits(e.target.value))} />
            </div>
          </Field>
          <Field label="Stamp duty (%)" hint="State-dependent; 5% is a common default">
            <div className="relative">
              <Percent className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="decimal" placeholder="e.g. 5" className="pl-9 tabular-nums" value={stampDuty} onChange={(e) => setStampDuty(decimal(e.target.value))} />
            </div>
          </Field>
          <Field label="Registration (%)">
            <div className="relative">
              <Percent className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="decimal" placeholder="e.g. 1" className="pl-9 tabular-nums" value={registration} onChange={(e) => setRegistration(decimal(e.target.value))} />
            </div>
          </Field>
          <Field label="Brokerage (%)">
            <div className="relative">
              <Percent className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input inputMode="decimal" placeholder="e.g. 1" className="pl-9 tabular-nums" value={brokerage} onChange={(e) => setBrokerage(decimal(e.target.value))} />
            </div>
          </Field>
        </div>
        {validationError && !error && <p className="text-xs text-muted-foreground">{validationError}</p>}
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button
          type="submit"
          onClick={submit}
          disabled={loading}
          className="w-full gap-2 rounded-xl sm:w-auto"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
          Calculate affordability
        </Button>
      </InputCard>

      {result && status && (
        <div className="space-y-4">
          <Card
            className={cn(
              "border-border/60",
              toneClasses[status.tone]
            )}
          >
            <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <span
                  className={cn(
                    "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl",
                    iconClasses[status.tone]
                  )}
                >
                  <status.icon className="h-5 w-5" />
                </span>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Affordability status
                  </p>
                  <Badge className={cn("mt-1", badgeClasses[status.tone])}>
                    {status.label}
                  </Badge>
                  <p className="mt-1 text-sm text-muted-foreground">{status.note}</p>
                </div>
              </div>
              <div className="shrink-0 text-left sm:text-right">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">EMI-to-income</p>
                <p className="text-2xl font-bold tabular-nums text-foreground">
                  {pct(result.emi_to_income_ratio)}
                </p>
                <p className="text-xs text-muted-foreground">ideal â‰¤ 30% Â· max 40%</p>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <ResultCard
              label="Maximum affordable EMI"
              value={inr(result.max_monthly_emi)}
              compactValue={inrCompact(result.max_monthly_emi)}
              hint="Net income capped at 50%"
              icon={Calculator}
              tone="primary"
              large
            />
            <ResultCard
              label="Estimated eligible loan"
              value={inr(result.max_loan_amount)}
              compactValue={inrCompact(result.max_loan_amount)}
              hint="At your rate and tenure"
              icon={Banknote}
            />
            <ResultCard
              label="Maximum property price"
              value={inr(result.max_property_price)}
              compactValue={inrCompact(result.max_property_price)}
              hint="Loan plus your down payment"
              icon={Home}
            />
            <ResultCard
              label="Net monthly income"
              value={inr(result.net_monthly_income)}
              compactValue={inrCompact(result.net_monthly_income)}
              hint="After existing loan obligations"
              icon={Wallet}
            />
          </div>

          {/* Property-specific assessment: EMI, cash, and what is left over. */}
          {assessment && (
            <>
              <h3 className="pt-2 text-base font-semibold">Purchase assessment</h3>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <ResultCard
                  label="Monthly EMI"
                  value={inr(assessment.monthly_emi)}
                  compactValue={inrCompact(assessment.monthly_emi)}
                  hint={`${pct(assessment.emi_to_income_ratio_pct)} of gross income`}
                  icon={Calculator}
                  tone={assessment.emi_within_capacity ? "success" : "danger"}
                  large
                />
                <ResultCard
                  label="Loan required"
                  value={inr(assessment.loan_required)}
                  compactValue={inrCompact(assessment.loan_required)}
                  hint="After your down payment"
                  icon={Banknote}
                />
                <ResultCard
                  label="Upfront costs"
                  value={inr(assessment.total_cash_required)}
                  compactValue={inrCompact(assessment.total_cash_required)}
                  hint="Down payment, stamp duty, registration, brokerage and fees"
                  icon={Receipt}
                />
                <ResultCard
                  label="Cash after purchase"
                  value={inr(assessment.cash_available_after_purchase)}
                  compactValue={inrCompact(assessment.cash_available_after_purchase)}
                  hint={
                    assessment.cash_is_sufficient
                      ? "Savings cover the upfront cost"
                      : `Shortfall of ${inrCompact(assessment.cash_shortfall)}`
                  }
                  icon={PiggyBank}
                  tone={assessment.cash_is_sufficient ? "success" : "danger"}
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <ResultCard
                  label="Total monthly outflow"
                  value={inr(assessment.total_monthly_outflow)}
                  compactValue={inrCompact(assessment.total_monthly_outflow)}
                  hint="EMI plus recurring ownership costs"
                  icon={TrendingDown}
                />
                <ResultCard
                  label="Income left each month"
                  value={inr(assessment.remaining_income_monthly)}
                  compactValue={inrCompact(assessment.remaining_income_monthly)}
                  hint="After EMI and ownership costs"
                  icon={Wallet}
                  tone={assessment.remaining_income_monthly >= 0 ? "default" : "danger"}
                />
                <ResultCard
                  label="Total interest payable"
                  value={inr(assessment.total_interest)}
                  compactValue={inrCompact(assessment.total_interest)}
                  hint="Over the full tenure"
                  icon={Banknote}
                />
              </div>

              {!assessment.is_affordable && (
                <ErrorNote>
                  On these inputs this property is not affordable: the EMI, the upfront cash, or both,
                  exceed your capacity. This is not a lender decision â€” see the note below.
                </ErrorNote>
              )}
            </>
          )}

          <div className="rounded-xl border border-border/60 bg-muted/30 px-4 py-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Assumptions behind these numbers
            </p>
            <ul className="space-y-1 text-xs text-muted-foreground">
              {result.assumptions.map((line, i) => (
                <li key={i}>â€¢ {line}</li>
              ))}
              <li>â€¢ Transaction costs use the stamp duty, registration and brokerage rates you entered.</li>
            </ul>
            <p className="mt-3 text-xs text-muted-foreground">{result.affordability_note}</p>
          </div>

          <EstimateNote />
        </div>
      )}

      <p className="text-sm text-muted-foreground">
        Looking at a specific listing? {" "}
        <Link href="/saved" className="text-primary hover:underline">
          Open your saved properties
        </Link>{" "}
        and use &ldquo;Check affordability&rdquo; to prefill its asking price.
      </p>
    </div>
  );
}

export default function AffordabilityPage() {
  return (
    <div className="container-page py-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900">Affordability</h1>
        <p className="mt-2 max-w-2xl text-slate-600">
          Work out what you can actually borrow and buy â€” the EMI, the cash you need up front, and
          what is left of your income and savings afterwards.
        </p>
      </div>
      <Suspense fallback={<div className="h-64 animate-pulse rounded-xl bg-slate-100" />}>
        <AffordabilityCalculator />
      </Suspense>
    </div>
  );
}
