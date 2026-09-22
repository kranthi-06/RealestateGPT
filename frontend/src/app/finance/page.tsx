"use client";

import { FormEvent, useState } from "react";
import { Calculator, Loader2 } from "lucide-react";
import { financeApi, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function FinancePage() {
  const [principal, setPrincipal] = useState("5000000");
  const [rate, setRate] = useState("8.5");
  const [years, setYears] = useState("20");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<{ monthly_emi: number; total_interest: number; total_repayment: number }>();
  const calculate = async (event: FormEvent) => {
    event.preventDefault(); setLoading(true); setError(undefined);
    try { setResult(await financeApi.emi({ principal: Number(principal), annual_interest_rate: Number(rate), tenure_years: Number(years) })); }
    catch (caught) { setError(caught instanceof ApiError ? caught.message : "We couldn’t calculate this payment. Try again."); }
    finally { setLoading(false); }
  };
  const money = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);
  return <main className="product-shell py-10 sm:py-16"><div className="grid gap-10 lg:grid-cols-[.9fr_1.1fr]"><section><p className="eyebrow">Financial intelligence</p><h1 className="product-heading mt-3 text-5xl">Make the monthly number clear.</h1><p className="mt-4 max-w-lg leading-7 text-muted-foreground">Explore an EMI using the platform&apos;s deterministic finance calculator. These calculations are illustrative, not financial advice.</p><form onSubmit={calculate} className="surface-raised mt-8 space-y-5 rounded-2xl p-6"><label className="block text-sm font-medium">Loan amount<Input className="mt-2" inputMode="numeric" value={principal} onChange={(e) => setPrincipal(e.target.value)} /></label><label className="block text-sm font-medium">Annual interest rate (%)<Input className="mt-2" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} /></label><label className="block text-sm font-medium">Tenure (years)<Input className="mt-2" inputMode="numeric" value={years} onChange={(e) => setYears(e.target.value)} /></label>{error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}<Button disabled={loading} className="w-full rounded-xl">{loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Calculator className="mr-2 size-4" />}Calculate EMI</Button></form></section><section className="surface-inset flex min-h-96 flex-col justify-center rounded-3xl p-6 sm:p-10">{result ? <><p className="eyebrow">Estimated monthly EMI</p><p className="product-heading mt-4 text-5xl text-primary">{money(result.monthly_emi)}</p><div className="mt-10 grid gap-4 sm:grid-cols-2"><Metric label="Total interest" value={money(result.total_interest)} /><Metric label="Total repayment" value={money(result.total_repayment)} /></div></> : <><Calculator className="size-9 text-primary" /><h2 className="product-heading mt-5 text-3xl">Your payment picture appears here.</h2><p className="mt-3 max-w-md text-muted-foreground">Enter the loan terms to calculate a real result from the finance API.</p></>}</section></div></main>;
}
function Metric({ label, value }: { label: string; value: string }) { return <div className="surface-raised rounded-2xl p-5"><p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p><p className="mt-2 text-xl font-semibold">{value}</p></div>; }
