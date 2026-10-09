"use client";

import { useMemo, useState, FormEvent } from "react";
import {
  Calculator,
  Loader2,
  Home,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  IndianRupee,
  Percent,
  CalendarClock,
  Wallet,
  Banknote,
  Info,
} from "lucide-react";
import { financeApi, ApiError } from "@/lib/api";
import type { EmiResult, AffordabilityResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/* ── Indian formatting helpers ───────────────────────────────────────── */

/** Full Indian-grouped rupee string, e.g. ₹1,23,45,678. */
function inr(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

/** Compact Indian notation: ₹45.5 L / ₹1.20 Cr / ₹95 K. */
function inrCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1_00_00_000) return `${sign}₹${(abs / 1_00_00_000).toFixed(2)} Cr`;
  if (abs >= 1_00_000) return `${sign}₹${(abs / 1_00_000).toFixed(abs >= 10_00_000 ? 0 : 1)} L`;
  if (abs >= 1_000) return `${sign}₹${(abs / 1_000).toFixed(1)} K`;
  return `${sign}₹${abs.toFixed(0)}`;
}

function pct(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

/** Accept only digits, and never return NaN. */
function digits(raw: string): string {
  return raw.replace(/[^\d]/g, "");
}

/** Accept a positive decimal number (for interest rates). */
function decimal(raw: string): string {
  const cleaned = raw.replace(/[^\d.]/g, "");
  const parts = cleaned.split(".");
  return parts.length > 2 ? `${parts[0]}.${parts.slice(1).join("")}` : cleaned;
}

function toNumber(raw: string, fallback: number): number {
  const n = Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

/* ── Small pieces ────────────────────────────────────────────────────── */

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
        Figures assume the rate and tenure you enter, ignore processing fees, insurance, stamp duty
        and registration charges, and do not reflect any lender&apos;s eligibility rules or credit
        assessment. Actual loan terms are decided only by the lender after reviewing your documents.
      </p>
    </div>
  );
}

/* ── EMI Calculator ──────────────────────────────────────────────────── */

function EmiCalculator() {
  const [principal, setPrincipal] = useState("4000000");
  const [rate, setRate] = useState("8.5");
  const [years, setYears] = useState("20");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EmiResult | null>(null);

  const principalNum = toNumber(principal, 0);
  const rateNum = toNumber(rate, 0);
  const yearsNum = toNumber(years, 0);

  const validationError = useMemo(() => {
    if (principal === "" || principalNum <= 0) return "Enter a loan amount greater than zero.";
    if (rate === "" || rateNum <= 0 || rateNum > 50) return "Enter an interest rate between 0 and 50%.";
    if (years === "" || yearsNum <= 0 || yearsNum > 40) return "Enter a tenure between 0 and 40 years.";
    return null;
  }, [principal, principalNum, rate, rateNum, years, yearsNum]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (validationError) {
      setResult(null);
      setError(validationError);
      return;
    }
    setLoading(true);
    try {
      const res = await financeApi.emi({
        principal: principalNum,
        annual_interest_rate: rateNum,
        tenure_years: yearsNum,
      });
      setResult(res);
    } catch (caught) {
      setResult(null);
      setError(
        caught instanceof ApiError
          ? caught.message === "Request failed"
            ? "Could not calculate EMI. Check the values and try again."
            : caught.message
          : "Could not calculate EMI. Check your connection and try again."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <InputCard
        title="Loan details"
        description="Enter the amount you plan to borrow and the terms your lender quoted."
        icon={Calculator}
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Loan amount" hint="Total principal borrowed">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                inputMode="numeric"
                placeholder="e.g. 4000000"
                className="pl-9 tabular-nums"
                value={principal}
                onChange={(e) => setPrincipal(digits(e.target.value))}
              />
            </div>
          </Field>
          <Field label="Interest rate (% p.a.)">
            <div className="relative">
              <Percent className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                inputMode="decimal"
                placeholder="e.g. 8.5"
                className="pl-9 tabular-nums"
                value={rate}
                onChange={(e) => setRate(decimal(e.target.value))}
              />
            </div>
          </Field>
          <Field label="Tenure (years)">
            <div className="relative">
              <CalendarClock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                inputMode="numeric"
                placeholder="e.g. 20"
                className="pl-9 tabular-nums"
                value={years}
                onChange={(e) => setYears(digits(e.target.value))}
              />
            </div>
          </Field>
        </div>
        {validationError && !error && (
          <p className="text-xs text-muted-foreground">{validationError}</p>
        )}
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button type="submit" onClick={submit} disabled={loading} className="w-full gap-2 rounded-xl sm:w-auto">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
          Calculate EMI
        </Button>
      </InputCard>

      {result && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-primary/30 bg-primary/5 p-5 sm:p-6">
            <p className="text-xs font-medium uppercase tracking-wide text-primary/80">
              Estimated monthly EMI
            </p>
            <p className="mt-2 text-3xl font-bold text-primary tabular-nums sm:text-4xl">
              {inr(result.monthly_emi)}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              per month for {result.tenure_years} year{result.tenure_years === 1 ? "" : "s"} at{" "}
              {result.annual_interest_rate}% p.a.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <ResultCard
              label="Principal"
              value={inr(result.principal)}
              compactValue={inrCompact(result.principal)}
              icon={Banknote}
            />
            <ResultCard
              label="Total interest"
              value={inr(result.total_interest)}
              compactValue={inrCompact(result.total_interest)}
              tone="warning"
              icon={Percent}
            />
            <ResultCard
              label="Total repayment"
              value={inr(result.total_repayment)}
              compactValue={inrCompact(result.total_repayment)}
              icon={Wallet}
            />
          </div>

          <Card className="border-border/60">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Breakdown</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 pt-0 sm:grid-cols-2">
              <div className="rounded-lg border border-border/60 bg-background px-3 py-2.5">
                <p className="text-xs text-muted-foreground">Principal share of total</p>
                <p className="text-sm font-semibold tabular-nums text-foreground">
                  {result.total_repayment > 0
                    ? pct((result.principal / result.total_repayment) * 100)
                    : "—"}
                </p>
              </div>
              <div className="rounded-lg border border-border/60 bg-background px-3 py-2.5">
                <p className="text-xs text-muted-foreground">Interest share of total</p>
                <p className="text-sm font-semibold tabular-nums text-foreground">
                  {result.total_repayment > 0
                    ? pct((result.total_interest / result.total_repayment) * 100)
                    : "—"}
                </p>
              </div>
              <div className="rounded-lg border border-border/60 bg-background px-3 py-2.5">
                <p className="text-xs text-muted-foreground">Number of instalments</p>
                <p className="text-sm font-semibold tabular-nums text-foreground">
                  {Math.round(result.tenure_years * 12)}
                </p>
              </div>
              <div className="rounded-lg border border-border/60 bg-background px-3 py-2.5">
                <p className="text-xs text-muted-foreground">Formula</p>
                <p className="text-sm font-semibold text-foreground">
                  EMI = P·r·(1+r)ⁿ / ((1+r)ⁿ − 1)
                </p>
              </div>
            </CardContent>
          </Card>

          <EstimateNote />
        </div>
      )}
    </div>
  );
}

/* ── Affordability Calculator ────────────────────────────────────────── */

function AffordabilityCalculator() {
  const [income, setIncome] = useState("150000");
  const [existingEmi, setExistingEmi] = useState("0");
  const [downPayment, setDownPayment] = useState("1000000");
  const [propertyPrice, setPropertyPrice] = useState("");
  const [rate, setRate] = useState("8.5");
  const [years, setYears] = useState("20");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AffordabilityResult | null>(null);

  const incomeNum = toNumber(income, 0);
  const existingEmiNum = toNumber(existingEmi, 0);
  const downPaymentNum = toNumber(downPayment, 0);
  const propertyPriceNum = toNumber(propertyPrice, 0);
  const rateNum = toNumber(rate, 0);
  const yearsNum = toNumber(years, 0);

  const validationError = useMemo(() => {
    if (income === "" || incomeNum <= 0) return "Enter your monthly income (greater than zero).";
    if (existingEmi !== "" && existingEmiNum < 0) return "Existing EMI cannot be negative.";
    if (incomeNum > 0 && existingEmiNum >= incomeNum) {
      return "Existing EMI must be lower than your monthly income.";
    }
    if (downPayment !== "" && downPaymentNum < 0) return "Down payment cannot be negative.";
    if (propertyPrice !== "" && propertyPriceNum < 0) return "Property price cannot be negative.";
    if (rate === "" || rateNum <= 0 || rateNum > 50) return "Enter an interest rate between 0 and 50%.";
    if (years === "" || yearsNum <= 0 || yearsNum > 40) return "Enter a tenure between 0 and 40 years.";
    return null;
  }, [
    income, incomeNum, existingEmi, existingEmiNum,
    downPayment, downPaymentNum, propertyPrice, propertyPriceNum,
    rate, rateNum, years, yearsNum,
  ]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (validationError) {
      setResult(null);
      setError(validationError);
      return;
    }
    setLoading(true);
    try {
      const res = await financeApi.affordability({
        monthly_income: incomeNum,
        existing_obligations: existingEmiNum,
        down_payment: downPaymentNum,
        property_price: propertyPriceNum > 0 ? propertyPriceNum : undefined,
        annual_interest_rate: rateNum,
        tenure_years: yearsNum,
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
  };

  const status = useMemo(() => {
    if (!result) return null;
    const ratio = result.emi_to_income_ratio;
    if (!result.affordable) {
      return {
        label: "Not affordable",
        icon: XCircle,
        tone: "danger" as const,
        note: "The required EMI is above what this income supports.",
      };
    }
    if (ratio <= 30) {
      return {
        label: "Comfortable",
        icon: CheckCircle2,
        tone: "success" as const,
        note: "EMI stays within 30% of your gross monthly income.",
      };
    }
    if (ratio <= 40) {
      return {
        label: "Manageable",
        icon: ShieldCheck,
        tone: "primary" as const,
        note: "EMI is between 30% and 40% of income — workable but with less buffer.",
      };
    }
    return {
      label: "Stretched",
      icon: AlertTriangle,
      tone: "warning" as const,
      note: "EMI exceeds 40% of gross income. Most lenders will cap below this.",
    };
  }, [result]);

  const requiredDownPayment =
    propertyPriceNum > 0 ? Math.max(0, propertyPriceNum - result!.max_loan_amount) : null;
  const downPaymentGap =
    requiredDownPayment != null ? downPaymentNum - requiredDownPayment : null;

  return (
    <div className="space-y-5">
      <InputCard
        title="Your financial profile"
        description="These are your inputs. Everything below the button is calculated from them."
        icon={Home}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Monthly income" hint="Gross take-home monthly income">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                inputMode="numeric"
                placeholder="e.g. 150000"
                className="pl-9 tabular-nums"
                value={income}
                onChange={(e) => setIncome(digits(e.target.value))}
              />
            </div>
          </Field>
          <Field label="Existing monthly EMI" hint="All current loan instalments combined">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                inputMode="numeric"
                placeholder="e.g. 15000"
                className="pl-9 tabular-nums"
                value={existingEmi}
                onChange={(e) => setExistingEmi(digits(e.target.value))}
              />
            </div>
          </Field>
          <Field label="Available down payment" hint="Cash you can put down now">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                inputMode="numeric"
                placeholder="e.g. 1000000"
                className="pl-9 tabular-nums"
                value={downPayment}
                onChange={(e) => setDownPayment(digits(e.target.value))}
              />
            </div>
          </Field>
          <Field label="Target property price" hint="Optional — checks a specific property">
            <div className="relative">
              <IndianRupee className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                inputMode="numeric"
                placeholder="e.g. 8000000"
                className="pl-9 tabular-nums"
                value={propertyPrice}
                onChange={(e) => setPropertyPrice(digits(e.target.value))}
              />
            </div>
          </Field>
          <Field label="Interest rate (% p.a.)">
            <div className="relative">
              <Percent className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                inputMode="decimal"
                placeholder="e.g. 8.5"
                className="pl-9 tabular-nums"
                value={rate}
                onChange={(e) => setRate(decimal(e.target.value))}
              />
            </div>
          </Field>
          <Field label="Loan tenure (years)">
            <div className="relative">
              <CalendarClock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
              <Input
                inputMode="numeric"
                placeholder="e.g. 20"
                className="pl-9 tabular-nums"
                value={years}
                onChange={(e) => setYears(digits(e.target.value))}
              />
            </div>
          </Field>
        </div>
        {validationError && !error && (
          <p className="text-xs text-muted-foreground">{validationError}</p>
        )}
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button type="submit" onClick={submit} disabled={loading} className="w-full gap-2 rounded-xl sm:w-auto">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
          Calculate affordability
        </Button>
      </InputCard>

      {result && status && (
        <div className="space-y-4">
          {/* Status */}
          <Card
            className={cn(
              "border-border/60",
              status.tone === "success" && "border-emerald-200/60 bg-emerald-50/40",
              status.tone === "primary" && "border-primary/30 bg-primary/5",
              status.tone === "warning" && "border-amber-200/60 bg-amber-50/40",
              status.tone === "danger" && "border-destructive/30 bg-destructive/5"
            )}
          >
            <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <span
                  className={cn(
                    "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl",
                    status.tone === "success" && "bg-emerald-100 text-emerald-700",
                    status.tone === "primary" && "bg-primary/10 text-primary",
                    status.tone === "warning" && "bg-amber-100 text-amber-700",
                    status.tone === "danger" && "bg-destructive/10 text-destructive"
                  )}
                >
                  <status.icon className="h-5 w-5" />
                </span>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Affordability status
                  </p>
                  <Badge
                    className={cn(
                      "mt-1",
                      status.tone === "success" && "bg-emerald-100 text-emerald-700",
                      status.tone === "primary" && "bg-primary/10 text-primary",
                      status.tone === "warning" && "bg-amber-100 text-amber-700",
                      status.tone === "danger" && "bg-destructive/10 text-destructive"
                    )}
                  >
                    {status.label}
                  </Badge>
                  <p className="mt-1 text-sm text-muted-foreground">{status.note}</p>
                </div>
              </div>
              <div className="shrink-0 text-left sm:text-right">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">
                  EMI-to-income
                </p>
                <p className="text-2xl font-bold tabular-nums text-foreground">
                  {pct(result.emi_to_income_ratio)}
                </p>
                <p className="text-xs text-muted-foreground">ideal ≤ 30% · max 40%</p>
              </div>
            </CardContent>
          </Card>

          {/* Core results */}
          <div className="grid gap-4 sm:grid-cols-2">
            <ResultCard
              label="Maximum affordable EMI"
              value={inr(result.max_monthly_emi)}
              compactValue={inrCompact(result.max_monthly_emi)}
              hint="Your income after existing EMIs, capped at 50%"
              icon={Calculator}
              tone="primary"
              large
            />
            <ResultCard
              label="Estimated eligible loan amount"
              value={inr(result.max_loan_amount)}
              compactValue={inrCompact(result.max_loan_amount)}
              hint={`At ${pct(rateNum, 1)} p.a. over ${yearsNum} years`}
              icon={Banknote}
              tone="primary"
              large
            />
            <ResultCard
              label="Maximum affordable property price"
              value={inr(result.max_property_price)}
              compactValue={inrCompact(result.max_property_price)}
              hint="Eligible loan + available down payment"
              icon={Home}
              tone="success"
              large
            />
            <ResultCard
              label="Net monthly income"
              value={inr(Math.max(0, incomeNum - existingEmiNum))}
              compactValue={inrCompact(Math.max(0, incomeNum - existingEmiNum))}
              hint="Gross income minus existing obligations"
              icon={Wallet}
            />
          </div>

          {/* Property-specific check */}
          {propertyPriceNum > 0 && requiredDownPayment != null && downPaymentGap != null && (
            <Card className="border-border/60">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Home className="h-4 w-4 text-primary" />
                  Property-specific check
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2 text-sm">
                  <span className="text-muted-foreground">Target property price</span>
                  <span className="font-semibold tabular-nums text-foreground">
                    {inr(propertyPriceNum)}
                  </span>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2 text-sm">
                  <span className="text-muted-foreground">Required down payment</span>
                  <span className="font-semibold tabular-nums text-foreground">
                    {inr(requiredDownPayment)}
                  </span>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2 text-sm">
                  <span className="text-muted-foreground">Your available down payment</span>
                  <span className="font-semibold tabular-nums text-foreground">
                    {inr(downPaymentNum)}
                  </span>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 text-base">
                  <span className="font-semibold text-foreground">
                    {downPaymentGap >= 0 ? "Surplus" : "Shortfall"}
                  </span>
                  <span
                    className={cn(
                      "font-bold tabular-nums",
                      downPaymentGap >= 0 ? "text-emerald-600" : "text-destructive"
                    )}
                  >
                    {inr(Math.abs(downPaymentGap))}
                  </span>
                </div>
                {downPaymentGap < 0 && (
                  <p className="text-xs text-amber-700">
                    You would need {inr(Math.abs(downPaymentGap))} more cash, or a larger loan than
                    this income supports.
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Assumptions */}
          <Card className="border-border/60">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <ShieldCheck className="h-4 w-4 text-primary" />
                Assumptions used
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
              <ul className="space-y-2 text-sm text-muted-foreground">
                {result.assumptions.map((assumption, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                    <span>{assumption}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <EstimateNote />
        </div>
      )}
    </div>
  );
}

/* ── Page ────────────────────────────────────────────────────────────── */

export default function AffordabilityPage() {
  const [tab, setTab] = useState("affordability");

  return (
    <div className="page-shell py-6 sm:py-10">
      <div className="mb-8">
        <Badge variant="outline" className="mb-3 gap-1.5 border-primary/30 bg-primary/5 text-primary">
          <Calculator className="h-3 w-3" />
          Financial Intelligence
        </Badge>
        <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          Plan your home loan with confidence
        </h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Work out what you can afford, or the EMI on a loan you are considering. Indian financial
          terms, rupee formatting, and deterministic maths — never an AI guess.
        </p>
      </div>

      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList className="mb-6 grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="affordability" className="gap-1.5">
            <Home className="h-4 w-4" />
            Affordability
          </TabsTrigger>
          <TabsTrigger value="emi" className="gap-1.5">
            <Calculator className="h-4 w-4" />
            EMI Calculator
          </TabsTrigger>
        </TabsList>
        <TabsContent value="affordability">
          <AffordabilityCalculator />
        </TabsContent>
        <TabsContent value="emi">
          <EmiCalculator />
        </TabsContent>
      </Tabs>
    </div>
  );
}
