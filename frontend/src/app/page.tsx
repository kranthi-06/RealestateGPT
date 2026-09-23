"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight, Bath, BedDouble, Bell, Bot, Building2, CheckCircle2,
  ChevronDown, CircleAlert, Heart, House, MapPin, Mic, Search,
  ShieldCheck, Sparkles, SquareStack, Store, UploadCloud, UsersRound,
} from "lucide-react";
import { propertiesApi, workersApi } from "@/lib/api";
import type { Property, WorkerStatus } from "@/lib/types";

const categories = [
  ["1 BHK", "Apartment"], ["2 BHK", "Apartment"], ["3 BHK", "Apartment"], ["4 BHK+", "Apartment"],
  ["Independent", "House"], ["Villas", "Villa"], ["PG & Coliving", "PG"], ["Hotels", "Hotel"],
];

function propertyImage(property: Property) {
  return property.images?.find((image) => image.rights_status !== "rejected")?.url ?? null;
}

function PropertyCard({ property }: { property: Property }) {
  const image = propertyImage(property);
  const price = new Intl.NumberFormat("en-IN", { style: "currency", currency: property.currency || "INR", maximumFractionDigits: 0 }).format(property.rent_amount || property.price);
  return <article className="group overflow-hidden rounded-xl border border-slate-100 bg-white shadow-[0_8px_24px_rgba(43,67,117,.08)] transition duration-200 hover:-translate-y-1 hover:shadow-[0_15px_30px_rgba(43,67,117,.14)]">
    <div className="relative grid h-32 place-items-center overflow-hidden bg-slate-100 text-slate-400">
      {image ? <img src={image} alt={property.title} className="h-full w-full object-cover transition duration-500 group-hover:scale-105" /> : <Building2 className="size-8" />}
      <span className="absolute left-2 top-2 rounded-full bg-white/90 px-2 py-1 text-[9px] font-bold text-slate-600">{property.verification_status}</span>
      <button aria-label={`Save ${property.title}`} className="absolute right-2 top-2 rounded-full bg-white/90 p-1.5 text-slate-500"><Heart className="size-4" /></button>
    </div>
    <div className="p-3"><p className="text-sm font-extrabold text-slate-900">{price} <span className="text-[10px] font-medium">{property.listing_type === "rent" ? "/ month" : ""}</span></p><p className="mt-1 line-clamp-1 text-xs font-semibold text-slate-700">{property.title}</p><p className="mt-1 line-clamp-1 text-[10px] text-slate-500">{property.locality ? `${property.locality}, ` : ""}{property.city}</p><div className="mt-2 flex items-center justify-between text-[10px] text-slate-500"><span className="inline-flex gap-1"><BedDouble className="size-3" /> {property.bedrooms ?? "—"}</span><span className="inline-flex gap-1"><Bath className="size-3" /> {property.bathrooms ?? "—"}</span><span>{property.area_sqft ? `${property.area_sqft.toLocaleString("en-IN")} sqft` : "—"}</span></div></div>
  </article>;
}

export default function LandingPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("Rent");
  const [featured, setFeatured] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [inventoryMessage, setInventoryMessage] = useState("");
  const [workerStatus, setWorkerStatus] = useState<WorkerStatus | null>(null);

  useEffect(() => {
    let active = true;
    Promise.allSettled([propertiesApi.getFeatured(), workersApi.status()]).then(([properties, workers]) => {
      if (!active) return;
      if (properties.status === "fulfilled") setFeatured(properties.value.filter((property) => !property.is_synthetic));
      else setInventoryMessage("Verified listings are temporarily unavailable.");
      if (workers.status === "fulfilled") {
        setWorkerStatus(workers.value);
        if (!workers.value.property_provider_configured) setInventoryMessage(workers.value.provider_message || "No licensed property-data provider is configured yet.");
      }
      setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    params.set("listing_type", mode.toLowerCase());
    router.push(`/search?${params.toString()}`);
  };

  const features = [[UploadCloud, "Real-time Data", "Inventory comes only from configured, authorized sources."], [MapPin, "Location Intelligence", "Live location providers add real local context."], [Bot, "AI Assistant", "Ask in natural language about verified inventory."], [ShieldCheck, "Verified Listings", "Listing provenance and freshness remain visible."], [SquareStack, "Smart Comparison", "Compare actual matches side by side."], [Bell, "Save & Track", "Save live listings and return to them later."]];
  const statusText = workerStatus?.property_provider_configured ? `Live provider: ${workerStatus.property_provider}` : "No provider configured";

  return <div className="bg-[#f6f9ff] text-[#0b1740]">
    <section className="relative overflow-hidden bg-[#251bd4] text-white"><div className="absolute inset-0 bg-[radial-gradient(circle_at_75%_20%,rgba(217,99,230,.9),transparent_23%),radial-gradient(circle_at_70%_52%,rgba(255,144,122,.9),transparent_25%),linear-gradient(120deg,#2b31d7_0%,#6e42dc_50%,#ff8b84_100%)]" /><div className="relative mx-auto max-w-[1500px] px-5 pb-7 pt-4 lg:px-8">
      <header className="flex items-center justify-between text-xs"><Link href="/" className="flex items-center gap-2 text-sm font-extrabold"><span className="grid size-6 place-items-center rounded-md bg-white text-indigo-600"><House className="size-4 fill-current" /></span>RealEstateGPT</Link><nav className="hidden gap-7 text-white/95 md:flex"><Link href="/search">Buy</Link><button onClick={() => setMode("Rent")}>Rent</button><a href="#categories">PG & Coliving</a><a href="#properties">Hotels</a><a href="#explore">Explore <ChevronDown className="ml-1 inline size-3" /></a><Link href="/assistant">AI Assistant</Link></nav><div className="flex items-center gap-3"><Link href="/auth/login?role=user">User sign in</Link><Link href="/auth/login?role=admin" className="rounded-lg border border-white/40 px-3 py-2 font-bold">Admin</Link><Link href="/auth/register" className="rounded-lg bg-[#3d42ff] px-4 py-2.5 font-bold shadow-lg shadow-indigo-900/30">Get Started</Link></div></header>
      <div className="grid min-h-[370px] items-center gap-9 pt-10 lg:grid-cols-[1fr_340px] lg:px-3"><div className="max-w-[620px]"><span className="inline-flex items-center gap-1 rounded-full bg-white/20 px-3 py-1.5 text-[10px] font-bold"><Sparkles className="size-3" /> Real-data property search</span><h1 className="mt-4 text-4xl font-black leading-[1.08] tracking-tight sm:text-5xl">Find your perfect<br />home with AI</h1><p className="mt-3 max-w-[530px] text-sm leading-6 text-white/95">Search verified properties, get live location insights and compare the options that match your needs.</p><p className="mt-5 inline-flex items-center gap-2 rounded-lg bg-slate-950/20 px-3 py-2 text-[10px] font-semibold"><span className={`size-2 rounded-full ${workerStatus?.property_provider_configured ? "bg-emerald-300" : "bg-amber-300"}`} />{statusText}</p></div>
      <form onSubmit={submit} className="rounded-2xl bg-white p-3 text-slate-800 shadow-2xl shadow-indigo-900/20"><div className="grid grid-cols-4 rounded-xl bg-[#f4f7ff] p-1 text-[10px] font-bold"><button type="button" onClick={() => setMode("Buy")} className={`rounded-lg py-2 ${mode === "Buy" ? "bg-white shadow text-indigo-600" : ""}`}>Buy</button><button type="button" onClick={() => setMode("Rent")} className={`rounded-lg py-2 ${mode === "Rent" ? "bg-white shadow text-indigo-600" : ""}`}>Rent</button><button type="button" onClick={() => router.push("/search?property_type=hotel")} className="py-2">Hotels</button><button type="button" onClick={() => router.push("/search?property_type=pg")} className="py-2">PG</button></div><div className="mt-3 flex items-center rounded-lg border border-slate-200 px-3 py-3"><Search className="size-4 text-indigo-500" /><input value={query} onChange={e => setQuery(e.target.value)} className="min-w-0 flex-1 px-2 text-[11px] outline-none" placeholder="City, locality, budget, or property type" /><Mic className="size-4 text-indigo-700" /></div><Link href="/near-me" className="mt-2 flex items-center gap-1 text-[9px] font-semibold text-indigo-600"><MapPin className="size-3" /> Use my current location</Link><div className="mt-3 grid grid-cols-3 gap-2 text-[9px]"><label>Listing<input value={mode} readOnly className="mt-1 w-full rounded-md border border-slate-200 p-2 text-[10px]" /></label><label>Property Type<select className="mt-1 w-full rounded-md border border-slate-200 p-2 text-[10px]"><option>Any</option><option>Apartment</option><option>House</option></select></label><label>Budget (₹)<select className="mt-1 w-full rounded-md border border-slate-200 p-2 text-[10px]"><option>Any</option></select></label></div><button className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-[#287bff] to-[#a317e9] py-3 text-[11px] font-bold text-white"><Search className="size-3" /> Search verified properties</button></form></div></div></section>
    <main className="mx-auto max-w-[1500px] space-y-4 px-5 py-4 lg:px-8"><section id="categories" className="rounded-xl bg-white p-3 shadow-sm"><div className="mb-3 flex items-center justify-between"><div><h2 className="font-bold">Explore by Category</h2><p className="text-[10px] text-slate-500">Search only the listing types you need.</p></div><Link href="/search" className="text-xs font-bold text-indigo-600">View all <ArrowRight className="inline size-3" /></Link></div><div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">{categories.map(([title, type]) => <button key={title} onClick={() => router.push(`/search?property_type=${encodeURIComponent(type)}`)} className="rounded-lg border border-slate-100 bg-gradient-to-br from-indigo-50 to-white p-3 text-left shadow-sm transition hover:border-indigo-200"><Building2 className="size-5 text-indigo-500" /><span className="mt-4 block text-[10px] font-bold">{title}</span><span className="block text-[9px] text-slate-500">View available listings</span></button>)}</div></section>
    <section className="rounded-xl bg-white p-3 shadow-sm"><h2 className="font-bold">Why RealEstateGPT?</h2><div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{features.map(([Icon, title, copy]) => { const C = Icon as typeof Bot; return <div key={String(title)} className="flex gap-3"><span className="grid size-8 shrink-0 place-items-center rounded-lg bg-indigo-50 text-indigo-600"><C className="size-4" /></span><div><h3 className="text-[11px] font-bold">{String(title)}</h3><p className="mt-1 text-[9px] text-slate-500">{String(copy)}</p></div></div>; })}</div></section>
    <section id="explore" className="grid gap-4 lg:grid-cols-[1fr_1fr]"><div className="relative min-h-36 overflow-hidden rounded-xl bg-gradient-to-br from-indigo-700 to-fuchsia-600 p-5 text-white"><div className="absolute -right-6 -top-10 size-44 rounded-full bg-white/10" /><div className="relative"><h2 className="text-lg font-bold">Discover properties<br />near you</h2><p className="mt-2 text-[10px] text-white/85">Use your device location only when you choose to search nearby.</p><Link href="/near-me" className="mt-4 inline-block rounded-md bg-white px-3 py-2 text-[10px] font-bold text-indigo-600">Find properties near me</Link></div></div><div className="rounded-xl bg-white p-5 shadow-sm"><p className="text-[10px] font-bold">Or search a specific location</p><form onSubmit={submit} className="mt-3 flex gap-2"><div className="flex flex-1 items-center rounded-lg border border-slate-200 px-3"><Search className="size-3 text-slate-400" /><input value={query} onChange={e => setQuery(e.target.value)} className="w-full p-2 text-[10px] outline-none" placeholder="Enter city, locality, or landmark" /></div><button className="rounded-lg bg-indigo-600 px-5 py-2 text-[10px] font-bold text-white">Search</button></form><p className="mt-4 text-[9px] text-slate-500">Search results reflect the current inventory; unavailable listings are never substituted with examples.</p></div></section>
    <section id="properties" className="grid gap-4 lg:grid-cols-[1.2fr_.8fr]"><div className="rounded-xl bg-white p-3 shadow-sm"><div className="flex items-center justify-between"><div><h2 className="font-bold">Featured verified properties</h2><p className="mt-1 text-[10px] text-slate-500">Only non-synthetic inventory is shown here.</p></div><Link href="/search" className="text-[10px] font-bold text-indigo-600">View all <ArrowRight className="inline size-3" /></Link></div>{loading ? <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-56 animate-pulse rounded-xl bg-slate-100" />)}</div> : featured.length ? <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">{featured.slice(0, 4).map((property) => <PropertyCard key={property.id} property={property} />)}</div> : <div className="mt-4 rounded-lg border border-dashed border-amber-200 bg-amber-50 p-5 text-sm text-amber-950"><div className="flex gap-3"><CircleAlert className="mt-0.5 size-5 shrink-0 text-amber-600" /><div><p className="font-bold">No verified inventory to show</p><p className="mt-1 text-xs text-amber-800">{inventoryMessage || "There are no live listings matching the featured criteria."}</p><Link href="/admin" className="mt-3 inline-block text-xs font-bold text-indigo-700">Open data operations <ArrowRight className="inline size-3" /></Link></div></div></div>}</div>
    <div className="rounded-xl bg-white p-5 shadow-sm"><div className="flex items-center gap-2"><span className="grid size-7 place-items-center rounded-lg bg-indigo-50"><Bot className="size-4 text-indigo-600" /></span><b className="text-xs">AI Assistant</b></div><div className="mt-5 text-center"><Bot className="mx-auto size-7 text-indigo-600" /><h2 className="mt-2 font-bold">Ask RealEstateGPT</h2><p className="mt-1 text-[10px] text-slate-500">Search the live catalogue and understand the results.</p><Link href="/assistant" className="mt-3 inline-block rounded-full bg-indigo-100 px-4 py-2 text-[10px] text-indigo-700">Ask about a property or location</Link></div><ul className="mt-5 space-y-2 text-[10px] text-slate-500"><li><CheckCircle2 className="mr-2 inline size-3 text-green-500" />Uses real inventory when available</li><li><CheckCircle2 className="mr-2 inline size-3 text-green-500" />Shows source and verification data</li><li><CheckCircle2 className="mr-2 inline size-3 text-green-500" />Never fabricates property matches</li></ul><Link href="/assistant" className="mt-4 flex items-center rounded-lg border border-slate-200 px-3 py-2 text-[10px] text-slate-500">Ask anything about real estate... <ArrowRight className="ml-auto size-3 text-indigo-600" /></Link></div></section>
    <section className="grid gap-4 pb-3 lg:grid-cols-[1fr_1fr]"><div className="rounded-xl bg-white p-5 shadow-sm"><h2 className="font-bold">Your property search, simplified</h2><p className="mt-2 text-xs text-slate-500">Search the live catalogue, then use location insights and comparison tools to decide.</p><Link href="/search" className="mt-4 inline-flex items-center gap-1 text-xs font-bold text-indigo-600">Start exploring <ArrowRight className="size-3" /></Link></div><div className="rounded-xl bg-white p-5 shadow-sm"><h2 className="font-bold">Data operations</h2><div className="mt-4 flex items-center justify-between text-center text-[10px] font-semibold text-slate-600"><span className="grid gap-2"><Store className="mx-auto size-5 text-indigo-600" />Authorized Source</span><ArrowRight className="size-4 text-indigo-400" /><span className="grid gap-2"><UsersRound className="mx-auto size-5 text-indigo-600" />Workers</span><ArrowRight className="size-4 text-indigo-400" /><span className="grid gap-2"><ShieldCheck className="mx-auto size-5 text-teal-500" />Verified Listings</span></div><Link href="/admin" className="mt-4 inline-block text-xs font-bold text-indigo-600">Open worker monitoring <ArrowRight className="inline size-3" /></Link></div></section></main>
  </div>;
}
