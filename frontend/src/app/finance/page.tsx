"use client";

import { FormEvent, useState } from "react";
import { Calculator, Loader2, Home, Shield, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { financeApi, ApiError } from "@/lib/api";
import type { EmiResult, AffordabilityResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

function FinancePageContent() {
  const [activeTab, setActiveTab] = useState<"emi" | "affordability">("affordability");

  const [emiPrincipal, setEmiPrincipal] = useState("5000000");
  const [emiRate, setEmiRate] = useState("8.5");
  const [emiYears, setEmiYears] = useState("20");
  const [emiLoading, setEmiLoading] = useState(false);
  const [emiError, setEmiError] = useState<string>();
  const [emiResult, setEmiResult] = useState<EmiResult | null>(null);

  const [affIncome, setAffIncome] = useState("150000");
  const [affDownPayment, setAffDownPayment] = useState("1000000");
  const [affExistingEmi, setAffExistingEmi] = useState("0");
  const [affRate, setAffRate] = useState("8.5");
  const [affYears, setAffYears] = useState("20");
  const [affPropertyPrice, setAffPropertyPrice] = useState("");
  const [affLoading, setAffLoading] = useState(false);
  const [affError, setAffError] = useState<string>();
  const [affResult, setAffResult] = useState<AffordabilityResult | null>(null);

  const money = (value: number) => new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);

  const pct = (value: number) => `${value.toFixed(1)}%`;

  const handleEmiSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setEmiLoading(true);
    setEmiError(undefined);
    try {
      const res = await financeApi.emi({
        principal: Number(emiPrincipal),
        annual_interest_rate: Number(emiRate),
        tenure_years: Number(emiYears),
      });
      setEmiResult(res);
    } catch (caught) {
      setEmiError(caught instanceof ApiError ? caught.message : "Could not calculate EMI. Try again.");
    } finally {
      setEmiLoading(false);
    }
  };

  const handleAffSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setAffLoading(true);
    setAffError(undefined);
    try {
      const res = await financeApi.affordability({
        monthly_income: Number(affIncome),
        existing_obligations: Number(affExistingEmi) || undefined,
        down_payment: Number(affDownPayment) || undefined,
        property_price: Number(affPropertyPrice) || undefined,
        annual_interest_rate: Number(affRate) || undefined,
        tenure_years: Number(affYears) || undefined,
      });
      setAffResult(res);
    } catch (caught) {
      setAffError(caught instanceof ApiError ? caught.message : "Could not calculate affordability. Try again.");
    } finally {
      setAffLoading(false);
    }
  };

  const getAffordabilityStatus = (result: AffordabilityResult) => {
    if (result.affordable && result.emi_to_income_ratio <= 30) {
      return { label: "Comfortable", icon: CheckCircle2, color: "bg-emerald-100 text-emerald-700 border-emerald-200", iconColor: "text-emerald-600" };
    }
    if (result.affordable && result.emi_to_income_ratio <= 40) {
      return { label: "Manageable", icon: Shield, color: "bg-blue-100 text-blue-700 border-blue-200", iconColor: "text-blue-600" };
    }
    if (result.affordable) {
      return { label: "Stretched", icon: AlertTriangle, color: "bg-amber-100 text-amber-700 border-amber-200", iconColor: "text-amber-600" };
    }
    return { label: "Not Affordable", icon: XCircle, color: "bg-destructive/10 text-destructive border-destructive/20", iconColor: "text-destructive" };
  };
  const status = affResult ? getAffordabilityStatus(affResult) : null;
  const StatusIcon = status?.icon || Shield;

  return (
    <main className="page-shell py-10 sm:py-16">
      <div className="max-w-4xl mx-auto">
        <div className="mb-10">
          <p className="eyebrow">Financial Intelligence</p>
          <h1 className="product-heading mt-3 text-4xl sm:text-5xl">Calculate what you can afford.</h1>
          <p className="mt-4 max-w-2xl leading-7 text-muted-foreground">
            Use our deterministic finance calculators to estimate EMIs and determine your true affordability.
            Calculations are illustrative and not financial advice.
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2 mb-6">
            <TabsTrigger value="affordability" className="gap-2">
              <Home className="w-4 h-4" />
              Affordability Calculator
            </TabsTrigger>
            <TabsTrigger value="emi" className="gap-2">
              <Calculator className="w-4 h-4" />
              EMI Calculator
            </TabsTrigger>
          </TabsList>

          <TabsContent value="affordability" className="space-y-6">
            <form onSubmit={handleAffSubmit} className="space-y-6">
              <Card className="border-border/60">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Home className="w-5 h-5 text-primary" />
                    Your Financial Profile
                  </CardTitle>
                  <p className="text-sm text-muted-foreground mt-1">Enter your details to see how much home you can afford.</p>
                </CardHeader>
                <CardContent className="space-y-5 pt-0">
                  <div className="grid gap-5 sm:grid-cols-2">
                    <label className="block text-sm font-medium">
                      Monthly Income (₹)
                      <Input
                        className="mt-2"
                        inputMode="numeric"
                        placeholder="e.g., 150000"
                        value={affIncome}
                        onChange={(e) => setAffIncome(e.target.value.replace(/[^0-9]/g, ""))}
                        required
                      />
                    </label>
                    <label className="block text-sm font-medium">
                      Down Payment (₹)
                      <Input
                        className="mt-2"
                        inputMode="numeric"
                        placeholder="e.g., 1000000"
                        value={affDownPayment}
                        onChange={(e) => setAffDownPayment(e.target.value.replace(/[^0-9]/g, ""))}
                      />
                    </label>
                  </div>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <label className="block text-sm font-medium">
                      Existing Monthly EMI (₹)
                      <Input
                        className="mt-2"
                        inputMode="numeric"
                        placeholder="e.g., 15000"
                        value={affExistingEmi}
                        onChange={(e) => setAffExistingEmi(e.target.value.replace(/[^0-9]/g, ""))}
                      />
                    </label>
                    <label className="block text-sm font-medium">
                      Target Property Price (₹) <span className="text-muted-foreground text-xs">(optional)</span>
                      <Input
                        className="mt-2"
                        inputMode="numeric"
                        placeholder="e.g., 8000000"
                        value={affPropertyPrice}
                        onChange={(e) => setAffPropertyPrice(e.target.value.replace(/[^0-9]/g, ""))}
                      />
                    </label>
                  </div>
                  <div className="grid gap-5 sm:grid-cols-3">
                    <label className="block text-sm font-medium">
                      Interest Rate (%)
                      <Input
                        className="mt-2"
                        inputMode="decimal"
                        placeholder="8.5"
                        value={affRate}
                        onChange={(e) => setAffRate(e.target.value)}
                      />
                    </label>
                    <label className="block text-sm font-medium">
                      Loan Tenure (years)
                      <Input
                        className="mt-2"
                        inputMode="numeric"
                        placeholder="20"
                        value={affYears}
                        onChange={(e) => setAffYears(e.target.value.replace(/[^0-9]/g, ""))}
                      />
                    </label>
                  </div>
                  {affError && (
                    <p role="alert" className="text-sm text-destructive flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" />
                      {affError}
                    </p>
                  )}
                  <Button type="submit" disabled={affLoading} className="w-full rounded-xl gap-2">
                    {affLoading ? <Loader2 className="size-4 animate-spin" /> : <Calculator className="size-4" />}
                    Calculate Affordability
                  </Button>
                </CardContent>
              </Card>

              {affResult && status && (
                <div className="space-y-6">
                  <div className="rounded-xl border border-border/60 bg-card p-6">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Affordability Status</p>
                        <div className="flex items-center gap-3 mt-2">
                          <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${status.color}`}>
                            <StatusIcon className={`w-6 h-6 ${status.iconColor}`} />
                          </div>
                          <div>
                            <Badge className={status.color.replace("bg-", "bg-").replace("text-", "text-").replace("border-", "border-")} variant="default">
                              {status.label}
                            </Badge>
                            <p className="text-sm text-muted-foreground mt-1">
                              DTI Ratio: {pct(affResult.emi_to_income_ratio)} (ideal ≤ 30%, max 40%)
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <Card className="border-border/60">
                      <CardContent className="p-5 text-center">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Max Monthly EMI</p>
                        <p className="mt-2 text-2xl font-bold text-primary">{money(affResult.max_monthly_emi)}</p>
                        <p className="text-xs text-muted-foreground mt-1">Based on 40% DTI cap</p>
                      </CardContent>
                    </Card>
                    <Card className="border-border/60">
                      <CardContent className="p-5 text-center">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Max Loan Amount</p>
                        <p className="mt-2 text-2xl font-bold">{money(affResult.max_loan_amount)}</p>
                        <p className="text-xs text-muted-foreground mt-1">At current rate & tenure</p>
                      </CardContent>
                    </Card>
                    <Card className="border-border/60">
                      <CardContent className="p-5 text-center">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Max Property Price</p>
                        <p className="mt-2 text-2xl font-bold">{money(affResult.max_property_price)}</p>
                        <p className="text-xs text-muted-foreground mt-1">Loan + down payment</p>
                      </CardContent>
                    </Card>
                    <Card className="border-border/60">
                      <CardContent className="p-5 text-center">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Recommended EMI</p>
                        <p className="mt-2 text-2xl font-bold text-emerald-600">{money(affResult.recommended_emi)}</p>
                        <p className="text-xs text-muted-foreground mt-1">At 30% DTI for comfort</p>
                      </CardContent>
                    </Card>
                  </div>

                  <Card className="border-border/60">
                    <CardHeader>
                      <CardTitle className="text-base flex items-center gap-2">
                        <Shield className="w-4 h-4" />
                        Key Assumptions
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-0">
                      <ul className="space-y-2 text-sm text-muted-foreground">
                        {affResult.assumptions.map((a, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                            {a}
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>

                  {affPropertyPrice && Number(affPropertyPrice) > 0 && (
                    <Card className="border-border/60">
                      <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4" />
                          Property-Specific Check
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="pt-0">
                        <div className="space-y-2 text-sm">
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Target Property Price</span>
                            <span className="font-medium">{money(Number(affPropertyPrice))}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Required Down Payment</span>
                            <span className="font-medium">{money(Number(affPropertyPrice) - affResult.max_loan_amount)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-muted-foreground">Your Available Down Payment</span>
                            <span className="font-medium">{money(Number(affDownPayment))}</span>
                          </div>
                          <Separator />
<div className="flex justify-between text-lg">
                            <span className="font-semibold">Gap / Surplus</span>
                            <span className={Number(affDownPayment) >= Number(affPropertyPrice) - affResult.max_loan_amount ? "text-emerald-600 font-semibold" : "text-destructive font-semibold"}>
                              {money(Number(affDownPayment) - (Number(affPropertyPrice) - affResult.max_loan_amount))}
                            </span>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )}
                </div>
              )}
            </form>
          </TabsContent>

          <TabsContent value="emi" className="space-y-6">
            <form onSubmit={handleEmiSubmit} className="space-y-6">
              <Card className="border-border/60">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Calculator className="w-5 h-5 text-primary" />
                    Loan Details
                  </CardTitle>
                  <p className="text-sm text-muted-foreground mt-1">Calculate monthly EMI for a given loan amount.</p>
                </CardHeader>
                <CardContent className="space-y-5 pt-0">
                  <div className="grid gap-5 sm:grid-cols-3">
                    <label className="block text-sm font-medium">
                      Loan Amount (₹)
                      <Input
                        className="mt-2"
                        inputMode="numeric"
                        placeholder="5000000"
                        value={emiPrincipal}
                        onChange={(e) => setEmiPrincipal(e.target.value.replace(/[^0-9]/g, ""))}
                        required
                      />
                    </label>
                    <label className="block text-sm font-medium">
                      Interest Rate (%)
                      <Input
                        className="mt-2"
                        inputMode="decimal"
                        placeholder="8.5"
                        value={emiRate}
                        onChange={(e) => setEmiRate(e.target.value)}
                        required
                      />
                    </label>
                    <label className="block text-sm font-medium">
                      Tenure (years)
                      <Input
                        className="mt-2"
                        inputMode="numeric"
                        placeholder="20"
                        value={emiYears}
                        onChange={(e) => setEmiYears(e.target.value.replace(/[^0-9]/g, ""))}
                        required
                      />
                    </label>
                  </div>
                  {emiError && (
                    <p role="alert" className="text-sm text-destructive flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" />
                      {emiError}
                    </p>
                  )}
                  <Button type="submit" disabled={emiLoading} className="w-full rounded-xl gap-2">
                    {emiLoading ? <Loader2 className="size-4 animate-spin" /> : <Calculator className="size-4" />}
                    Calculate EMI
                  </Button>
                </CardContent>
              </Card>

              {emiResult && (
                <div className="space-y-4">
                  <Card className="border-primary/20 bg-primary/5 border-border/60">
                    <CardContent className="p-6 text-center">
                      <p className="text-xs font-medium uppercase tracking-wide text-primary/80">Estimated Monthly EMI</p>
                      <p className="mt-2 text-4xl font-bold text-primary">{money(emiResult.monthly_emi)}</p>
                    </CardContent>
                  </Card>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Card className="border-border/60">
                      <CardContent className="p-5 text-center">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Total Interest</p>
                        <p className="mt-2 text-xl font-semibold">{money(emiResult.total_interest)}</p>
                      </CardContent>
                    </Card>
                    <Card className="border-border/60">
                      <CardContent className="p-5 text-center">
                        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Total Repayment</p>
                        <p className="mt-2 text-xl font-semibold">{money(emiResult.total_repayment)}</p>
                      </CardContent>
                    </Card>
                  </div>
                  <Card className="border-border/60">
                    <CardHeader>
                      <CardTitle className="text-base">Calculation Details</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-0">
                      <div className="space-y-2 text-sm text-muted-foreground">
                        <div className="flex justify-between"><span>Formula</span><span className="font-mono">{emiResult.formula}</span></div>
                        <div className="flex justify-between"><span>Principal</span><span>{money(emiResult.principal)}</span></div>
                        <div className="flex justify-between"><span>Annual Interest Rate</span><span>{emiResult.annual_interest_rate}%</span></div>
                        <div className="flex justify-between"><span>Tenure</span><span>{emiResult.tenure_years} years</span></div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              )}
            </form>
          </TabsContent>
        </Tabs>
      </div>
    </main>
  );
}

export default function FinancePage() {
  return <FinancePageContent />;
}
