"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import PropertyCard from "@/components/property-card";
import {
  ArrowRight,
  Building2,
  Check,
  ChevronRight,
  CircleDollarSign,
  Compass,
  GraduationCap,
  HeartPulse,
  MapPin,
  Route,
  Send,
  ShieldCheck,
  Sparkles,
  TrainFront,
} from "lucide-react";
import { propertiesApi } from "@/lib/api";
import type { Property } from "@/lib/types";

const STARTING_POINTS = [
  "A 2BHK in Hyderabad under ₹70 lakh, near metro and schools",
  "A family home in Bangalore with a short office commute",
  "A rental-friendly investment property with a fair price",
];

const BUYER_SIGNALS = [
  { icon: TrainFront, label: "Metro", value: "12 min walk", tone: "bg-[#e9f1ee] text-[#1e5a4c]" },
  { icon: GraduationCap, label: "Schools", value: "3 nearby", tone: "bg-[#f7eee1] text-[#9a5a20]" },
  { icon: HeartPulse, label: "Healthcare", value: "1.4 km", tone: "bg-[#f7e9e8] text-[#9a3b37]" },
];

const STORY_STEPS = [
  {
    number: "01",
    title: "Start with the life you want to live.",
    copy: "Describe the school run, the commute, the budget, or the neighbourhood feeling. There is no filter maze to learn first.",
    accent: "bg-[#e7efe9] text-[#245347]",
  },
  {
    number: "02",
    title: "See the reasons behind each match.",
    copy: "Every shortlist surfaces the facts that moved it up or down: price, proximity, space, and the data still worth checking.",
    accent: "bg-[#f5e9db] text-[#9b5d20]",
  },
  {
    number: "03",
    title: "Take a clearer next step.",
    copy: "Compare homes side by side, save the ones that fit, and return to the decision with your context intact.",
    accent: "bg-[#e9ebf5] text-[#4b5d9d]",
  },
];

export default function LandingPage() {
  const router = useRouter();
  const [brief, setBrief] = useState(STARTING_POINTS[0]);
  const [featured, setFeatured] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let active = true;
    propertiesApi
      .getFeatured()
      .then((properties) => {
        if (active) setFeatured(properties);
      })
      .catch(() => {
        if (active) setLoadError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const beginConversation = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const prompt = brief.trim();
    if (prompt) sessionStorage.setItem("assistant_draft", prompt);
    router.push(prompt ? `/assistant?prompt=${encodeURIComponent(prompt)}` : "/assistant");
  };

  return (
    <div className="overflow-hidden bg-[#fbfaf7] text-[#182520]">
      <section className="relative border-b border-[#dedbd1] bg-[#f7f5ef]">
        <div className="pointer-events-none absolute inset-0 opacity-70 [background-image:radial-gradient(#c9d2c8_0.8px,transparent_0.8px)] [background-size:18px_18px]" />
        <div className="pointer-events-none absolute -right-32 top-12 size-[32rem] rounded-full bg-[#dfece4] blur-3xl" />
        <div className="pointer-events-none absolute -bottom-40 left-0 size-[28rem] rounded-full bg-[#f1e4d2] blur-3xl" />

        <div className="relative mx-auto grid max-w-7xl gap-12 px-4 py-16 sm:px-6 sm:py-20 lg:grid-cols-[0.92fr_1.08fr] lg:items-center lg:gap-16 lg:px-8 lg:py-24">
          <div className="max-w-xl">
            <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-[#ced9d0] bg-white/70 px-3 py-1.5 text-xs font-semibold tracking-[0.16em] text-[#315b4b] shadow-sm uppercase">
              <Sparkles className="size-3.5" />
              A calmer way to buy a home
            </div>
            <h1 className="font-display text-5xl leading-[0.98] tracking-[-0.055em] text-[#162620] sm:text-6xl lg:text-7xl">
              The home search should start with your story.
            </h1>
            <p className="mt-7 max-w-lg text-lg leading-8 text-[#56645e] sm:text-xl">
              Tell RealEstateGPT how you want life to feel. It turns your brief into a considered shortlist—grounded in property facts and connected location data.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3 text-sm text-[#4f6158]">
              <span className="inline-flex items-center gap-2"><ShieldCheck className="size-4 text-[#2d6a55]" /> Grounded recommendations</span>
              <span className="inline-flex items-center gap-2"><MapPin className="size-4 text-[#2d6a55]" /> Location-aware results</span>
            </div>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Link href="/search" className="group inline-flex items-center gap-2 text-sm font-semibold text-[#20382f] hover:text-[#496c5d]">
                Explore all homes
                <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <span className="hidden h-4 w-px bg-[#cfcabf] sm:block" />
              <p className="text-sm text-[#758078]">Start with a plain-language brief—no search syntax needed.</p>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-2xl lg:mx-0">
            <div className="absolute -inset-5 -z-10 rounded-[2.25rem] bg-[#dce9e0]/70 blur-2xl" />
            <div className="overflow-hidden rounded-[1.65rem] border border-[#d5ddd5] bg-[#fffefb] shadow-[0_28px_80px_-28px_rgba(24,49,40,0.38)]">
              <div className="flex items-center justify-between border-b border-[#e5e4de] px-5 py-4 sm:px-6">
                <div className="flex items-center gap-3">
                  <div className="flex size-10 items-center justify-center rounded-2xl bg-[#1c3a30] text-white shadow-sm">
                    <Compass className="size-5" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-[#1b2f28]">A preview of your guided brief</p>
                    <p className="mt-0.5 text-xs text-[#718077]">See how your criteria becomes a shortlist</p>
                  </div>
                </div>
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[#e8f3eb] px-2.5 py-1 text-[11px] font-semibold text-[#2e6952]"><span className="size-1.5 rounded-full bg-[#4d9c72]" /> Guided preview</span>
              </div>

              <div className="space-y-5 px-5 py-6 sm:px-6">
                <div className="ml-auto max-w-[88%] rounded-2xl rounded-br-md bg-[#1d3b31] px-4 py-3 text-sm leading-6 text-white shadow-sm">
                  We&apos;re moving to Hyderabad. A 2BHK under ₹70 lakh, close to a metro and good schools, feels right for us.
                </div>
                <div className="max-w-[94%] rounded-2xl rounded-bl-md bg-[#f0f4ef] px-4 py-4 text-sm leading-6 text-[#32453c]">
                  <p>I&apos;ve made proximity and family routine the priorities. Here&apos;s how I&apos;d begin your shortlist.</p>
                  <div className="mt-4 rounded-xl border border-[#d9e4da] bg-white p-3.5 shadow-sm">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[11px] font-bold tracking-[0.14em] text-[#698378] uppercase">Example shortlist</p>
                        <p className="mt-1 font-semibold text-[#1c332a]">HITEC City · Kondapur · Miyapur</p>
                      </div>
                      <div className="rounded-lg bg-[#e7f0e9] px-2 py-1 text-xs font-bold text-[#2e6a51]">86% fit</div>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2">
                      {BUYER_SIGNALS.map(({ icon: Icon, label, value, tone }) => (
                        <div key={label} className={`rounded-lg p-2.5 ${tone}`}>
                          <Icon className="size-3.5" />
                          <p className="mt-2 text-[10px] font-semibold uppercase tracking-wide opacity-70">{label}</p>
                          <p className="mt-0.5 text-xs font-bold">{value}</p>
                        </div>
                      ))}
                    </div>
                    <div className="mt-3 flex items-center gap-2 border-t border-[#e7e8e2] pt-3 text-xs text-[#65756c]">
                      <CircleDollarSign className="size-4 text-[#537764]" />
                      <span>Price range and suitability are explained for every match.</span>
                    </div>
                  </div>
                </div>

                <form onSubmit={beginConversation} className="rounded-2xl border border-[#d9ddd5] bg-white p-2 shadow-sm focus-within:border-[#7b9e8a] focus-within:ring-4 focus-within:ring-[#e2eee5]">
                  <textarea
                    aria-label="Describe the home you are looking for"
                    value={brief}
                    onChange={(event) => setBrief(event.target.value)}
                    rows={2}
                    className="block w-full resize-none border-0 bg-transparent px-3 py-2 text-sm leading-6 text-[#21362d] placeholder:text-[#8a958e] focus:outline-none"
                    placeholder="Describe the life you want this home to support…"
                  />
                  <div className="flex flex-col gap-2 border-t border-[#ebebe6] px-1 pt-2 sm:flex-row sm:items-center sm:justify-between">
                    <span className="px-2 text-xs text-[#77837c]">Your brief stays yours. The assistant uses authorised data only.</span>
                    <Button type="submit" className="shrink-0 rounded-xl bg-[#1d3c31] px-4 text-white shadow-sm hover:bg-[#284f41]">
                      Start with this brief <Send className="ml-2 size-3.5" />
                    </Button>
                  </div>
                </form>
              </div>
            </div>
            <div className="absolute -bottom-5 -left-3 hidden rounded-2xl border border-[#dfdfd7] bg-[#fffefb] px-4 py-3 shadow-[0_18px_30px_-20px_rgba(24,49,40,0.45)] sm:flex sm:items-center sm:gap-3">
              <div className="flex size-8 items-center justify-center rounded-full bg-[#f4e6d4] text-[#9a5c20]"><Route className="size-4" /></div>
              <div><p className="text-xs font-semibold text-[#32473d]">Less searching, more clarity</p><p className="text-[11px] text-[#7b867f]">The why is always visible.</p></div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-[#e5e2da] bg-[#fffefb]">
        <div className="mx-auto grid max-w-7xl grid-cols-1 divide-y divide-[#e8e5dc] px-4 sm:px-6 md:grid-cols-3 md:divide-x md:divide-y-0 lg:px-8">
          <div className="flex items-center gap-3 py-5 md:py-6"><span className="flex size-9 items-center justify-center rounded-full bg-[#e8f1ea] text-[#2e6a51]"><Check className="size-4" /></span><p className="text-sm text-[#536259]"><strong className="font-semibold text-[#22352d]">Ask naturally.</strong> Your words become clear criteria.</p></div>
          <div className="flex items-center gap-3 py-5 md:px-8 md:py-6"><span className="flex size-9 items-center justify-center rounded-full bg-[#f6ecdf] text-[#9b5f21]"><Check className="size-4" /></span><p className="text-sm text-[#536259]"><strong className="font-semibold text-[#22352d]">Verify context.</strong> See source and data-quality signals.</p></div>
          <div className="flex items-center gap-3 py-5 md:py-6 md:pl-8"><span className="flex size-9 items-center justify-center rounded-full bg-[#e9ecf5] text-[#4a5d9b]"><Check className="size-4" /></span><p className="text-sm text-[#536259]"><strong className="font-semibold text-[#22352d]">Decide deliberately.</strong> Compare the options that remain.</p></div>
        </div>
      </section>

      <section id="how-it-works" className="relative bg-[#1b3029] py-20 text-[#f6f4ec] sm:py-28">
        <div className="pointer-events-none absolute inset-0 opacity-20 [background-image:linear-gradient(90deg,transparent_49%,#aec4b2_50%,transparent_51%)] [background-size:34px_34px]" />
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:gap-20">
            <div>
              <p className="text-xs font-bold tracking-[0.18em] text-[#aac6b5] uppercase">A better path to yes</p>
              <h2 className="font-display mt-5 max-w-md text-4xl leading-tight tracking-[-0.035em] sm:text-5xl">Move from a feeling to a defensible shortlist.</h2>
              <p className="mt-6 max-w-md text-base leading-7 text-[#c3d0c8]">RealEstateGPT is designed for the moments between “we should move” and “this is the one.” It keeps the decision human and the evidence close at hand.</p>
              <Link href="/search" className="mt-9 inline-flex items-center gap-2 text-sm font-semibold text-[#f3dfbf] hover:text-white">Browse the current catalogue <ArrowRight className="size-4" /></Link>
            </div>
            <div className="space-y-3">
              {STORY_STEPS.map((step) => (
                <article key={step.number} className="group grid gap-5 rounded-2xl border border-white/10 bg-white/[0.045] p-5 transition-colors hover:bg-white/[0.08] sm:grid-cols-[3.5rem_1fr_auto] sm:items-center sm:p-6">
                  <span className={`flex size-12 items-center justify-center rounded-2xl text-sm font-bold ${step.accent}`}>{step.number}</span>
                  <div><h3 className="text-lg font-semibold tracking-tight text-white">{step.title}</h3><p className="mt-2 max-w-xl text-sm leading-6 text-[#bdcac2]">{step.copy}</p></div>
                  <ChevronRight className="hidden size-5 text-[#9db8a8] transition-transform group-hover:translate-x-1 sm:block" />
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="py-20 sm:py-28">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <div className="max-w-xl"><p className="text-xs font-bold tracking-[0.16em] text-[#638071] uppercase">A place to begin</p><h2 className="font-display mt-4 text-4xl tracking-[-0.04em] text-[#1b3029] sm:text-5xl">Homes worth a closer look.</h2><p className="mt-4 leading-7 text-[#67736c]">A small view of the current catalogue. Every listing is clearly marked when it is sample data.</p></div>
            <Link href="/search"><Button variant="outline" className="rounded-xl border-[#bac8bd] bg-transparent text-[#1d3b31] hover:bg-[#edf3ed]">View all homes <ArrowRight className="ml-2 size-4" /></Button></Link>
          </div>

          <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-3">
            {loading && Array.from({ length: 3 }).map((_, index) => <Card key={index} className="overflow-hidden border-[#e3e1d9]"><Skeleton className="h-56 w-full" /><div className="space-y-3 p-5"><Skeleton className="h-5 w-4/5" /><Skeleton className="h-4 w-1/2" /><Skeleton className="h-4 w-full" /></div></Card>)}
            {!loading && loadError && <div className="col-span-full rounded-2xl border border-dashed border-[#cfd6cf] bg-[#f4f6f2] p-10 text-center"><Building2 className="mx-auto size-8 text-[#6d8677]" /><h3 className="mt-4 font-semibold text-[#294337]">The catalogue is temporarily unavailable.</h3><p className="mt-2 text-sm text-[#68766e]">You can still use the guided assistant once the service is available.</p><Link href="/assistant"><Button className="mt-5 rounded-xl bg-[#1d3c31] text-white hover:bg-[#284f41]">Open assistant</Button></Link></div>}
            {!loading && !loadError && featured.slice(0, 3).map((property) => <PropertyCard key={property.id} property={property} />)}
            {!loading && !loadError && featured.length === 0 && <div className="col-span-full rounded-2xl border border-dashed border-[#cfd6cf] bg-[#f4f6f2] p-10 text-center"><Building2 className="mx-auto size-8 text-[#6d8677]" /><h3 className="mt-4 font-semibold text-[#294337]">No catalogue homes are available yet.</h3><p className="mt-2 text-sm text-[#68766e]">Try the assistant with the location and budget that matter to you.</p></div>}
          </div>
        </div>
      </section>

      <section className="mx-4 mb-4 overflow-hidden rounded-[1.8rem] bg-[#e8efe8] sm:mx-6 lg:mx-8">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-8 px-6 py-12 sm:px-10 lg:flex-row lg:items-center lg:px-14 lg:py-14">
          <div className="max-w-2xl"><p className="text-xs font-bold tracking-[0.16em] text-[#638071] uppercase">The next move, made clearer</p><h2 className="font-display mt-4 text-4xl tracking-[-0.04em] text-[#1b3029] sm:text-5xl">Bring us the real question.</h2><p className="mt-4 text-base leading-7 text-[#5a6c61]">A commute concern, a price you&apos;re unsure about, or a list of homes you cannot choose between—we&apos;ll help you make the trade-offs visible.</p></div>
          <Link href="/assistant"><Button size="lg" className="rounded-xl bg-[#1d3c31] px-6 text-white shadow-lg shadow-[#315b4b]/20 hover:bg-[#284f41]">Start your home brief <ArrowRight className="ml-2 size-4" /></Button></Link>
        </div>
      </section>

      <footer className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-10 text-sm text-[#6e7771] sm:px-6 md:flex-row md:items-center md:justify-between lg:px-8">
        <div className="flex items-center gap-2 font-semibold text-[#2b4439]"><span className="flex size-8 items-center justify-center rounded-lg bg-[#1d3c31] text-white"><Building2 className="size-4" /></span>RealEstateGPT</div>
        <div className="flex gap-5"><Link href="/search" className="hover:text-[#1d3c31]">Explore homes</Link><Link href="/assistant" className="hover:text-[#1d3c31]">AI assistant</Link><Link href="/auth/register" className="hover:text-[#1d3c31]">Create account</Link></div>
        <p>Demo catalogue only—not real listings.</p>
      </footer>
    </div>
  );
}
