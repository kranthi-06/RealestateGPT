"use client";

import Link from "next/link";
import { useState, FormEvent, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Search,
  LocateFixed,
  Home,
  KeyRound,
  MapPin,
  Building2,
  Sparkles,
  Brain,
  ArrowRight,
  ChevronRight,
  CheckCircle2,
  GitCompare,
} from "lucide-react";
import { propertiesApi } from "@/lib/api";

const quickActions = [
  { href: "/search?listing_type=sale", label: "Buy", icon: Home, prefix: "🏠" },
  { href: "/search?listing_type=rent", label: "Rent", icon: KeyRound, prefix: "🔑" },
  { href: "/search?property_type=plot", label: "Plots", icon: MapPin, prefix: "🗺️" },
  { href: "/search?property_type=commercial", label: "Commercial", icon: Building2, prefix: "🏢" },
];

const fallbackCities = [
  "Hyderabad",
  "Bangalore",
  "Mumbai",
  "Pune",
  "Chennai",
  "Delhi NCR",
  "Kolkata",
  "Ahmedabad",
  "Jaipur",
  "Surat",
  "Lucknow",
  "Nagpur",
];

const howItWorks = [
  {
    step: "01",
    title: "AI Search",
    body: "Describe what you want in plain language — budgets, localities, amenities, proximity.",
    icon: Sparkles,
  },
  {
    step: "02",
    title: "Evaluate with Scores",
    body: "Every listing gets 6 AI scores, pros/cons, real distances, and price benchmarks.",
    icon: Brain,
  },
  {
    step: "03",
    title: "Compare & Decide",
    body: "Side-by-side tables, affordability, and AI recommendation to close with confidence.",
    icon: GitCompare,
  },
];

export default function HomePage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [cities, setCities] = useState<string[] | null>(null);
  const [citiesError, setCitiesError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    propertiesApi
      .getCities()
      .then((list) => {
        if (!cancelled) setCities(Array.isArray(list) ? list.slice(0, 18) : null);
      })
      .catch(() => {
        if (!cancelled) setCitiesError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSearch = (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setIsSearching(true);
    const params = new URLSearchParams();
    params.set("q", query.trim());
    router.push(`/search?${params.toString()}`);
    setIsSearching(false);
  };

  const displayCities = cities ?? (!citiesError ? null : fallbackCities);

  return (
    <div className="min-h-screen bg-background">
      <section className="py-12 sm:py-16 lg:py-20">
        <div className="page-shell">
          <div className="mx-auto max-w-4xl text-center">
            <Badge variant="default" className="mb-5 gap-1.5 px-3 py-1 text-[11px] uppercase tracking-wider animate-in animate-stagger-1">
              <Sparkles className="h-3 w-3" />
              AI · Search · Real Estate Intelligence
            </Badge>

            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-foreground animate-in animate-stagger-2">
              Search smarter. <span className="text-primary">Decide faster.</span>
            </h1>

            <p className="mt-4 text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto animate-in animate-stagger-3">
              A decision engine for real estate — natural-language search, AI-scored listings,
              real nearby-facility distances, and side-by-side comparisons grounded in live data.
            </p>

            <form onSubmit={handleSearch} className="mt-10 max-w-3xl mx-auto animate-in animate-stagger-4">
              <div className="group/card relative">
                <div className="absolute -inset-[1px] rounded-2xl bg-gradient-to-b from-primary/20 via-primary/10 to-transparent opacity-60 blur-sm transition-opacity group-hover/card:opacity-100 pointer-events-none" aria-hidden />
                <div className="relative flex items-stretch gap-2 rounded-2xl border border-border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-primary/20 focus-within:border-primary/40">
                  <div className="flex flex-1 items-center gap-2 px-3">
                    <Search className="h-5 w-5 shrink-0 text-primary" />
                    <Input
                      placeholder='Try "2 BHK under ₹40L near a hospital in Hyderabad"'
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      className="h-12 border-0 bg-transparent px-0 text-base placeholder:text-muted-foreground/60 focus-visible:ring-0 focus-visible:ring-offset-0"
                      aria-label="Search properties with AI"
                    />
                  </div>
                  <Button
                    type="submit"
                    size="lg"
                    disabled={isSearching || !query.trim()}
                    className="h-12 rounded-xl px-6 gap-2"
                  >
                    {isSearching ? (
                      <>
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Searching
                      </>
                    ) : (
                      <>
                        Search
                        <ArrowRight className="h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
              <p className="mt-3 text-[11px] text-muted-foreground">
                Verified listings · Server-side location lookup · No frontend API keys
              </p>
            </form>

            <div className="mt-8 flex flex-wrap items-center justify-center gap-2 animate-in animate-stagger-5">
              {quickActions.map((a) => (
                <Link
                  key={a.href}
                  href={a.href}
                  className="group inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3.5 py-2 text-sm font-medium text-foreground transition-all hover:border-primary/30 hover:bg-primary/5 hover:text-primary"
                >
                  <span aria-hidden className="text-sm">{a.prefix}</span>
                  {a.label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="py-10 sm:py-14">
        <div className="page-shell">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
            <div>
              <span className="eyebrow">Popular locations</span>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                Browse cities with live inventory
              </h2>
            </div>
            <Link href="/search" className="text-sm font-medium link">
              View all search <ChevronRight className="ml-0.5 inline h-4 w-4 align-[-2px]" />
            </Link>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 md:grid-cols-4 lg:grid-cols-6">
            {displayCities === null && !citiesError
              ? Array.from({ length: 12 }).map((_, i) => (
                  <div key={i} className="rounded-xl border border-border bg-card p-3">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="mt-2 h-3 w-1/2" />
                  </div>
                ))
              : (displayCities ?? fallbackCities).slice(0, 12).map((city) => (
                  <Link
                    key={city}
                    href={`/search?city=${encodeURIComponent(city)}`}
                    className="group rounded-xl border border-border bg-card p-3 sm:p-3.5 transition-all hover:border-primary/30 hover:shadow-sm"
                  >
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <MapPin className="h-3 w-3" />
                      City
                    </div>
                    <div className="mt-1 flex items-baseline justify-between gap-2">
                      <h3 className="truncate text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                        {city}
                      </h3>
                      <ArrowRight className="h-3.5 w-3.5 shrink-0 translate-x-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
                    </div>
                    {cities && (
                      <Badge variant="outline" className="mt-2 px-1.5 py-0 text-[10px]">
                        Live catalog
                      </Badge>
                    )}
                  </Link>
                ))}
          </div>
          {citiesError && displayCities && (
            <p className="mt-3 text-[11px] text-muted-foreground">
              * City list is an illustrative sample; catalog API was temporarily unreachable.
            </p>
          )}
        </div>
      </section>

      <section className="py-10 sm:py-14 border-y border-border/50 bg-muted/20">
        <div className="page-shell">
          <div className="mb-8 text-center max-w-2xl mx-auto">
            <span className="eyebrow">How it works</span>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
              From query to decision in 3 steps
            </h2>
          </div>

          <div className="grid gap-4 md:grid-cols-3 md:gap-5">
            {howItWorks.map((w, i) => {
              const Icon = w.icon;
              return (
                <Card key={w.step} className="overflow-hidden">
                  <CardContent className="p-5 sm:p-6">
                    <div className="flex items-center justify-between">
                      <Badge variant="default" className="gap-1 px-2 py-0.5 text-[10px] font-mono">
                        STEP {w.step}
                      </Badge>
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <Icon className="h-4.5 w-4.5" />
                      </div>
                    </div>
                    <h3 className="mt-4 text-base font-semibold text-foreground sm:text-lg">{w.title}</h3>
                    <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">{w.body}</p>
                    <div className="mt-5 flex items-center gap-1 text-xs text-muted-foreground">
                      {Array.from({ length: 3 }).map((_, j) => (
                        <CheckCircle2
                          key={j}
                          className={`h-3.5 w-3.5 ${j <= i ? "text-primary" : "text-border"}`}
                        />
                      ))}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      </section>

      <section className="py-10 sm:py-12">
        <div className="page-shell">
          <div className="grid gap-4 md:grid-cols-[1.4fr_1fr]">
            <Card>
              <CardContent className="p-5 sm:p-6">
                <Badge variant="outline" className="gap-1 text-[10px] uppercase tracking-wide">
                  <Sparkles className="h-3 w-3" />
                  Try the AI Assistant
                </Badge>
                <h3 className="mt-3 text-xl font-semibold text-foreground">
                  Talk to RealEstateGPT — not a generic chatbot
                </h3>
                <p className="mt-1.5 text-sm text-muted-foreground">
                  Ask for investment advice, area analysis, shortlists, or comparisons.
                  Every reply is grounded in your saved data, listings, and backend tools.
                </p>
                <Button asChild className="mt-4 gap-1.5">
                  <Link href="/assistant">
                    Open AI Assistant <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-5 sm:p-6">
                <Badge variant="outline" className="gap-1 text-[10px] uppercase tracking-wide">
                  <LocateFixed className="h-3 w-3" />
                  Near you
                </Badge>
                <h3 className="mt-3 text-xl font-semibold text-foreground">
                  Search around your current location
                </h3>
                <p className="mt-1.5 text-sm text-muted-foreground">
                  Grant browser location access on the Search page to find verified listings
                  within a radius of you — or search by city, locality, or address.
                </p>
                <Button asChild variant="outline" className="mt-4 gap-1.5">
                  <Link href="/search">
                    Search near me <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>
    </div>
  );
}
