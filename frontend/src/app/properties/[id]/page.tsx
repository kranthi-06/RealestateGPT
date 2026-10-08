"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Heart,
  MapPin,
  BedDouble,
  Bath,
  Maximize2,
  Building2,
  CheckCircle2,
  Star,
  Home as HomeIcon,
  Brain,
  GitCompare,
  Sparkles,
  ShieldCheck,
  CalendarDays,
  Compass,
  CarFront,
  Ruler,
  Layers,
  ExternalLink,
  Clock3,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select } from "@/components/ui/select";
import PropertyListRow from "@/components/property-list-row";
import { NearbyFacilitiesPanel } from "@/components/nearby-facilities-panel";
import { AIAnalysisPanel } from "@/components/ai-analysis-panel";
import { AiScoreBadge } from "@/components/ai-score-badge";
import { ScoreCard } from "@/components/score-card";
import { RealEstateMap } from "@/components/real-estate-map";
import type { MapMarker } from "@/components/real-estate-map";
import { propertiesApi, savedApi, financeApi } from "@/lib/api";
import type { PriceFairness } from "@/lib/types";
import { useAuth } from "@/lib/auth-context";
import type { Property, PriceIntelligence } from "@/lib/types";
import { formatDistanceToNow } from "date-fns";
import {
  formatPrice,
  formatArea,
  formatPricePerSqft,
  getPropertyTypeLabel,
  getFurnishingLabel,
  getBedroomLabel,
  capitalize,
} from "@/lib/format";
import { cn } from "@/lib/utils";

export default function PropertyDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [property, setProperty] = useState<Property | null>(null);
  const [priceIntel, setPriceIntel] = useState<PriceIntelligence | null>(null);
  const [priceFairness, setPriceFairness] = useState<PriceFairness | null>(null);
  const [similar, setSimilar] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [isSaved, setIsSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [emiPeriod, setEmiPeriod] = useState<string>("240");
  const [downPct, setDownPct] = useState<number>(20);
  const [emiResult, setEmiResult] = useState<{
    emi?: number;
    loan?: number;
    down?: number;
  } | null>(null);

  const propertyId = Number(params.id);

  useEffect(() => {
    if (!propertyId) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    Promise.all([
      propertiesApi.get(propertyId),
      propertiesApi.getSimilar(propertyId),
      propertiesApi.priceIntelligence(propertyId).catch(() => null),
      financeApi.fairness(propertyId).catch(() => null),
    ])
      .then(([prop, sim, intel, fairness]) => {
        setProperty(prop);
        setIsSaved(prop.is_saved || false);
        setSimilar(sim);
        setPriceIntel(intel);
        setPriceFairness(fairness);
      })
      .catch(() => setProperty(null))
      .finally(() => setLoading(false));
  }, [propertyId]);

  useEffect(() => {
    if (!property || !property.price) return;
    const loanAmount = property.price * (1 - downPct / 100);
    const tenureYears = Number(emiPeriod) / 12;
    financeApi
      .emi({ principal: loanAmount, annual_interest_rate: 8.75, tenure_years: tenureYears })
      .then((r) =>
        setEmiResult({
          emi: r.monthly_emi,
          loan: loanAmount,
          down: property.price - loanAmount,
        })
      )
      .catch(() => null);
  }, [property, emiPeriod, downPct]);

  const handleSave = async () => {
    if (!isAuthenticated || saving) return;
    setSaving(true);
    try {
      if (isSaved) {
        await savedApi.unsaveProperty(propertyId);
        setIsSaved(false);
      } else {
        await savedApi.saveProperty(propertyId);
        setIsSaved(true);
      }
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <main className="page-shell animate-fade-in py-6">
        <Skeleton className="h-6 w-40" />
        <Card className="mt-5">
          <CardContent className="p-6">
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[240px_1fr]">
              <Skeleton className="h-52 w-full rounded-2xl" />
              <div className="space-y-3">
                <Skeleton className="h-8 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
                <div className="grid grid-cols-4 gap-3 pt-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-16 rounded-xl" />
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Skeleton className="mt-6 h-[600px] w-full rounded-2xl" />
      </main>
    );
  }

  if (!property) {
    return (
      <main className="page-shell py-32 text-center">
        <Building2 className="mx-auto mb-6 h-20 w-20 text-muted-foreground/20" />
        <h2 className="text-2xl font-bold tracking-tight">
          Property Not Found
        </h2>
        <p className="mt-2 mb-8 text-muted-foreground">
          This property may have been removed or is no longer available.
        </p>
        <Button onClick={() => router.push("/search")}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Search
        </Button>
      </main>
    );
  }

  const images = (property.images ?? []).length
    ? property.images!
    : property.image_urls
      ? property.image_urls
          .split(",")
          .map((url) => ({
            url: url.trim(),
            category: "other",
            display_order: 0,
            rights_status: "unknown",
            fetched_at: "",
          }))
      : [];

  const coverImage = images[0]?.url;
  const freshnessTime = property.last_verified_at
    ? formatDistanceToNow(new Date(property.last_verified_at), {
        addSuffix: true,
      })
    : property.last_seen_at
      ? formatDistanceToNow(new Date(property.last_seen_at), {
          addSuffix: true,
        })
      : null;

  const keyDetails = [
    {
      icon: BedDouble,
      label: "Bedrooms",
      value:
        property.bedrooms != null ? getBedroomLabel(property.bedrooms) : null,
    },
    {
      icon: Bath,
      label: "Bathrooms",
      value:
        property.bathrooms != null ? `${property.bathrooms}` : null,
    },
    {
      icon: Maximize2,
      label: "Super Area",
      value: property.area_sqft ? formatArea(property.area_sqft) : null,
    },
    {
      icon: Ruler,
      label: "Carpet Area",
      value: property.carpet_area_sqft
        ? formatArea(property.carpet_area_sqft)
        : null,
    },
    {
      icon: Layers,
      label: "Floor",
      value:
        property.floor != null
          ? `${property.floor} of ${property.total_floors || "?"}`
          : null,
    },
    {
      icon: CalendarDays,
      label: "Property Age",
      value:
        property.property_age != null
          ? `${property.property_age} yrs`
          : null,
    },
    { icon: Compass, label: "Facing", value: property.facing },
    {
      icon: CarFront,
      label: "Parking",
      value:
        property.parking != null ? `${property.parking} spots` : null,
    },
    {
      icon: Building2,
      label: "Type",
      value: getPropertyTypeLabel(property.property_type),
    },
    {
      icon: ShieldCheck,
      label: "Furnishing",
      value: property.furnishing
        ? getFurnishingLabel(property.furnishing)
        : null,
    },
    {
      icon: Clock3,
      label: "Construction",
      value: property.construction_status
        ? capitalize(property.construction_status)
        : null,
    },
  ].filter((d) => d.value) as {
    icon: React.ComponentType<{ className?: string }>;
    label: string;
    value: string;
  }[];

  const mapMarkers: MapMarker[] = [
    {
      id: property.id,
      latitude: property.latitude,
      longitude: property.longitude,
      title: property.title || getPropertyTypeLabel(property.property_type),
      subtitle: [property.locality, property.city].filter(Boolean).join(", "),
      kind: "property",
    },
  ];

  const isRent = property.listing_type === "rent";

  return (
    <main className="page-shell animate-fade-in">
      <button
        onClick={() => router.back()}
        className="mt-6 mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      <Card className="overflow-hidden border-border/60 shadow-sm">
        <CardContent className="p-5 sm:p-6">
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[220px_1fr_300px]">
            <div className="relative h-[180px] overflow-hidden rounded-2xl border border-border/60 bg-accent/30 lg:h-[220px]">
              {coverImage ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={coverImage}
                  alt={property.title}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground/50">
                  <HomeIcon className="h-10 w-10" />
                  <span className="text-xs font-medium">
                    No cover image
                  </span>
                </div>
              )}
              <div className="absolute left-2 top-2 flex flex-col gap-1.5">
                {property.is_featured && (
                  <Badge className="bg-amber-500 text-white border-0">
                    <Star className="mr-1 h-3 w-3 fill-current" />
                    Featured
                  </Badge>
                )}
                {property.verification_status === "verified" && (
                  <Badge className="bg-emerald-500 text-white border-0">
                    <CheckCircle2 className="mr-1 h-3 w-3" />
                    Verified
                  </Badge>
                )}
              </div>
              {images.length > 1 && (
                <Badge
                  variant="outline"
                  className="absolute bottom-2 right-2 bg-background/90 backdrop-blur"
                >
                  +{images.length - 1} more
                </Badge>
              )}
            </div>

            <div className="min-w-0 flex flex-col">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h1 className="truncate text-2xl font-bold tracking-tight sm:text-3xl">
                    {property.title ||
                      `${getBedroomLabel(property.bedrooms ?? 0)} ${getPropertyTypeLabel(property.property_type)} in ${property.city}`}
                  </h1>
                  <p className="mt-1.5 flex items-center gap-1 text-sm text-muted-foreground">
                    <MapPin className="h-4 w-4 shrink-0" />
                    <span className="truncate">
                      {[
                        property.address,
                        property.locality,
                        property.city,
                        property.state,
                        property.pincode,
                      ]
                        .filter(Boolean)
                        .join(", ")}
                    </span>
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">
                      {getPropertyTypeLabel(property.property_type)}
                    </Badge>
                    {property.bedrooms != null && (
                      <Badge variant="secondary">
                        {getBedroomLabel(property.bedrooms)}
                      </Badge>
                    )}
                    {property.listing_type && (
                      <Badge
                        variant={
                          isRent ? "default" : "outline"
                        }
                        className={
                          !isRent
                            ? "border-primary/40 bg-primary/5 text-primary"
                            : ""
                        }
                      >
                        {isRent ? "For Rent" : "For Sale"}
                      </Badge>
                    )}
                    {property.project_name && (
                      <Badge variant="outline">
                        {property.project_name}
                      </Badge>
                    )}
                    {freshnessTime && (
                      <Badge variant="outline" className="text-[10px]">
                        Updated {freshnessTime}
                      </Badge>
                    )}
                    {property.rank_score != null && (
                      <AiScoreBadge
                        score={Math.round(property.rank_score * 100)}
                      />
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-extrabold tracking-tight tabular-nums sm:text-3xl">
                    {formatPrice(property.price, property.currency)}
                    {isRent && (
                      <span className="ml-1 text-sm font-medium text-muted-foreground">
                        /mo
                      </span>
                    )}
                  </div>
                  {!isRent && property.price_per_sqft ? (
                    <p className="mt-0.5 text-xs text-muted-foreground tabular-nums">
                      {formatPricePerSqft(property.price_per_sqft)}
                    </p>
                  ) : null}
                  {property.maintenance_charge ? (
                    <p className="mt-1 text-[11px] text-muted-foreground tabular-nums">
                      Maint. ₹
                      {property.maintenance_charge.toLocaleString("en-IN")}
                      /mo
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-5">
                <div className="rounded-xl border border-border bg-background p-2.5 text-center">
                  <div className="text-xs text-muted-foreground">
                    Bedrooms
                  </div>
                  <div className="mt-0.5 text-base font-semibold tabular-nums">
                    {property.bedrooms ?? "—"}
                  </div>
                </div>
                <div className="rounded-xl border border-border bg-background p-2.5 text-center">
                  <div className="text-xs text-muted-foreground">
                    Bathrooms
                  </div>
                  <div className="mt-0.5 text-base font-semibold tabular-nums">
                    {property.bathrooms ?? "—"}
                  </div>
                </div>
                <div className="rounded-xl border border-border bg-background p-2.5 text-center">
                  <div className="text-xs text-muted-foreground">Area</div>
                  <div className="mt-0.5 text-base font-semibold tabular-nums">
                    {property.area_sqft ? (
                      <span className="text-xs">
                        {formatArea(property.area_sqft)}
                      </span>
                    ) : (
                      "—"
                    )}
                  </div>
                </div>
                <div className="rounded-xl border border-border bg-background p-2.5 text-center">
                  <div className="text-xs text-muted-foreground">Type</div>
                  <div className="mt-0.5 truncate text-[13px] font-semibold">
                    {getPropertyTypeLabel(property.property_type)}
                  </div>
                </div>
                <div className="col-span-3 rounded-xl border border-border bg-background p-2.5 text-center sm:col-span-1">
                  <div className="text-xs text-muted-foreground">City</div>
                  <div className="mt-0.5 truncate text-[13px] font-semibold">
                    {property.city}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-2 lg:border-l lg:border-border/60 lg:pl-5 sticky top-24 lg:top-6 max-h-[calc(100vh-6rem)] overflow-y-auto">
              {isAuthenticated ? (
                <Button
                  onClick={handleSave}
                  disabled={saving}
                  variant={isSaved ? "outline" : "default"}
                  className="w-full justify-center rounded-xl"
                >
                  <Heart
                    className={cn(
                      "mr-2 h-4 w-4",
                      isSaved && "fill-red-500 text-red-500"
                    )}
                  />
                  {isSaved ? "Saved" : "Save Property"}
                </Button>
              ) : (
                <Button asChild variant="outline" className="w-full rounded-xl">
                  <Link href="/auth/login">
                    <Heart className="mr-2 h-4 w-4" /> Sign in to Save
                  </Link>
                </Button>
              )}
              <Button
                asChild
                variant="secondary"
                className="w-full justify-center rounded-xl"
              >
                <Link href={`/compare?ids=${property.id}`}>
                  <GitCompare className="mr-2 h-4 w-4" /> Compare
                </Link>
              </Button>
              <Button
                asChild
                variant="outline"
                className="w-full justify-center rounded-xl"
              >
                <Link
                  href={`/assistant?property_id=${property.id}`}
                  className="text-primary"
                >
                  <Brain className="mr-2 h-4 w-4" /> Ask AI about this
                </Link>
              </Button>
              {!isRent && (
                <Link
                  href={`/affordability?price=${property.price}`}
                  className="text-center text-[11px] text-muted-foreground underline-offset-2 hover:underline"
                >
                  Check affordability →
                </Link>
              )}
              <div className="mt-auto space-y-1 border-t border-border/50 pt-3 text-[11px] text-muted-foreground">
                <div className="flex items-center justify-between">
                  <span>Source</span>
                  <span className="font-medium text-foreground">
                    {property.source || "Platform"}
                  </span>
                </div>
                {property.source_url && (
                  <a
                    href={property.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-between text-primary hover:underline"
                  >
                    <span>Original listing</span>
                    <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <section className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[1fr_300px]">
        <Tabs defaultValue="overview" className="w-full">
          <TabsList
            variant="line"
            className="mb-4 h-auto w-full flex-wrap gap-0 rounded-none border-b border-border bg-transparent p-0"
          >
            {[
              { key: "overview", label: "Overview", Icon: Building2 },
              { key: "nearby", label: "Nearby Facilities", Icon: MapPin },
              { key: "price", label: "Price Intelligence", Icon: Sparkles },
              { key: "ai", label: "AI Analysis", Icon: Brain },
            ].map(({ key, label, Icon }) => (
              <TabsTrigger
                key={key}
                value={key}
                className="h-10 flex-none gap-1.5 px-4 text-xs sm:text-sm"
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{label}</span>
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="overview" className="mt-0 space-y-6 animate-fade-in">
            <div className="grid gap-5 lg:grid-cols-2">
              <Card>
                <CardHeader className="p-5 pb-3">
                  <CardTitle className="text-sm font-semibold">
                    Key Details
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-y-4 gap-x-3 p-5 pt-0 sm:grid-cols-3">
                  {keyDetails.map((d) => (
                    <div key={d.label} className="flex flex-col gap-1">
                      <div className="mb-0.5 flex items-center gap-1.5 text-muted-foreground">
                        <d.icon className="h-3.5 w-3.5" />
                        <span className="text-[11px]">{d.label}</span>
                      </div>
                      <span className="text-sm font-semibold">
                        {d.value}
                      </span>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="p-5 pb-3">
                  <CardTitle className="text-sm font-semibold">
                    Location on map
                  </CardTitle>
                  <CardDescription className="text-xs">
                    OpenStreetMap · no client-side provider keys
                  </CardDescription>
                </CardHeader>
                <CardContent className="p-5 pt-0">
                  <RealEstateMap markers={mapMarkers} />
                </CardContent>
              </Card>
            </div>

            {property.amenities?.length > 0 && (
              <Card>
                <CardHeader className="p-5 pb-3">
                  <CardTitle className="text-sm font-semibold">
                    Amenities
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      {property.amenities.length}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-5 pt-0">
                  <div className="grid grid-cols-2 gap-x-3 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
                    {property.amenities.map((a) => (
                      <div
                        key={a.id}
                        className="flex items-center gap-2 rounded-lg border border-border bg-background px-2.5 py-2"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                        <span className="truncate text-xs font-medium">
                          {a.name}
                        </span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {property.description && (
              <Card>
                <CardHeader className="p-5 pb-3">
                  <CardTitle className="text-sm font-semibold">
                    Listing description
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-5 pt-0">
                  <p className="text-sm leading-relaxed text-muted-foreground whitespace-pre-line">
                    {property.description}
                  </p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="nearby" className="mt-0 animate-fade-in">
            <NearbyFacilitiesPanel
              propertyId={property.id}
              radiusKm={3}
              className="w-full"
            />
          </TabsContent>

          <TabsContent value="price" className="mt-0 space-y-5 animate-fade-in">
            <div className="grid gap-5 lg:grid-cols-2">
              <Card>
                <CardHeader className="p-5 pb-3">
                  <CardTitle className="text-sm font-semibold">
                    Locality price intelligence
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Computed from observed MongoDB price history — never
                    synthetic.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 p-5 pt-0">
                  {!priceIntel ? (
                    <div className="space-y-2">
                      {Array.from({ length: 4 }).map((_, i) => (
                        <Skeleton key={i} className="h-10 w-full rounded-lg" />
                      ))}
                    </div>
                  ) : priceIntel.available ? (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <ScoreCard
                          label="Price / sq.ft"
                          value={0}
                          variant="neutral"
                          hideBar
                          prefix={
                            priceIntel.price_per_sqft
                              ? `₹${Math.round(priceIntel.price_per_sqft).toLocaleString("en-IN")}`
                              : "—"
                          }
                        />
                        <ScoreCard
                          label="Recent change"
                          value={0}
                          variant="neutral"
                          hideBar
                          prefix={
                            priceIntel.price_change_pct != null
                              ? `${priceIntel.price_change_pct >= 0 ? "+" : ""}${priceIntel.price_change_pct.toFixed(1)}%`
                              : "—"
                          }
                        />
                      </div>
                      <div className="rounded-xl border border-border bg-background p-4">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">
                            Observations
                          </span>
                          <span className="font-semibold tabular-nums">
                            {priceIntel.observations} listings
                          </span>
                        </div>
                        <div className="mt-2 flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">
                            Price changes
                          </span>
                          <span className="font-semibold tabular-nums">
                            {priceIntel.change_observations}
                          </span>
                        </div>
                        <div className="mt-2 flex items-center justify-between text-xs">
                          <span className="text-muted-foreground">
                            History depth
                          </span>
                          <Badge
                            variant={
                              priceIntel.enough_history
                                ? "success"
                                : "outline"
                            }
                            className="text-[10px]"
                          >
                            {priceIntel.enough_history
                              ? "Sufficient sample"
                              : "Sample limited"}
                          </Badge>
                        </div>
                      </div>
                      {priceIntel.history?.length > 0 && (
                        <div>
                          <p className="mb-2 text-xs font-medium text-muted-foreground">
                            Latest {Math.min(priceIntel.history.length, 5)}{" "}
                            changes
                          </p>
                          <ScrollArea className="h-40 rounded-xl border border-border">
                            <div className="space-y-1 p-3">
                              {priceIntel.history
                                .slice()
                                .reverse()
                                .slice(0, 10)
                                .map((h, i) => (
                                  <div
                                    key={i}
                                    className="flex items-center justify-between rounded-lg bg-background px-2.5 py-1.5 text-xs"
                                  >
                                    <span className="text-muted-foreground tabular-nums">
                                      {h.changed_at
                                        ? new Date(h.changed_at)
                                            .toISOString()
                                            .slice(0, 10)
                                        : "—"}
                                    </span>
                                    <span className="tabular-nums">
                                      {h.old_price != null &&
                                        `₹${Math.round(h.old_price).toLocaleString("en-IN")} → `}
                                      <strong>
                                        ₹
                                        {Math.round(
                                          h.new_price ?? h.old_price ?? 0
                                        ).toLocaleString("en-IN")}
                                      </strong>
                                    </span>
                                  </div>
                                ))}
                            </div>
                          </ScrollArea>
                        </div>
                      )}
                      {priceIntel.message && (
                        <p className="rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
                          {priceIntel.message}
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="rounded-lg border border-dashed border-border bg-background px-3 py-6 text-center text-xs text-muted-foreground">
                      No locality price intelligence yet for this property.
                      Refresh or verify with a manual locality search.
                    </p>
                  )}
                </CardContent>
              </Card>

              {priceFairness && (
                <Card>
                  <CardHeader className="p-5 pb-3">
                    <CardTitle className="text-sm font-semibold">
                      Price fairness
                    </CardTitle>
                    <CardDescription className="text-xs">
                      AI estimate vs listed price
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4 p-5 pt-0">
                    <div className="grid grid-cols-2 gap-3">
                      <ScoreCard
                        label="Listed price"
                        value={0}
                        variant="neutral"
                        hideBar
                        prefix={`₹${Math.round(priceFairness.listed_price).toLocaleString("en-IN")}`}
                      />
                      <ScoreCard
                        label="AI estimate"
                        value={0}
                        variant="neutral"
                        hideBar
                        prefix={`₹${Math.round(priceFairness.estimated_price).toLocaleString("en-IN")}`}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <ScoreCard
                        label="Lower bound"
                        value={0}
                        variant="neutral"
                        hideBar
                        prefix={`₹${Math.round(priceFairness.lower_bound).toLocaleString("en-IN")}`}
                      />
                      <ScoreCard
                        label="Upper bound"
                        value={0}
                        variant="neutral"
                        hideBar
                        prefix={`₹${Math.round(priceFairness.upper_bound).toLocaleString("en-IN")}`}
                      />
                    </div>
                    <div className="rounded-xl border border-border bg-background p-4">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Verdict</span>
                        <Badge
                          variant={
                            priceFairness.verdict === "undervalued"
                              ? "success"
                              : priceFairness.verdict === "overvalued"
                              ? "destructive"
                              : "default"
                          }
                          className="text-[10px]"
                        >
                          {priceFairness.verdict_label}
                        </Badge>
                      </div>
                      <div className="mt-2 flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Difference</span>
                        <span className="font-semibold tabular-nums">
                          {priceFairness.diff_pct >= 0 ? "+" : ""}
                          {priceFairness.diff_pct.toFixed(1)}%
                        </span>
                      </div>
                      {priceFairness.reasons?.length > 0 && (
                        <div className="mt-2 space-y-1">
                          <p className="text-xs font-medium text-muted-foreground">Reasons</p>
                          <ul className="space-y-0.5">
                            {priceFairness.reasons.map((r, i) => (
                              <li key={i} className="flex gap-2 text-xs text-muted-foreground">
                                <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                                <span>{r}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader className="p-5 pb-3">
                  <CardTitle className="text-sm font-semibold">
                    EMI & affordability teaser
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Use the full calculator on the Affordability page.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4 p-5 pt-0">
                  {isRent ? (
                    <p className="rounded-lg bg-muted px-3 py-4 text-center text-xs text-muted-foreground">
                      EMI calculator is available for sale listings only.
                      Switch to the Affordability page for rent coverage
                      analysis.
                    </p>
                  ) : (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="mb-1 block text-[11px] font-medium text-muted-foreground">
                            Down payment
                          </label>
                          <Select
                            value={String(downPct)}
                            onChange={(e) => setDownPct(Number(e.target.value))}
                            className="h-9"
                            options={[10, 15, 20, 25, 30, 40, 50].map((p) => ({ value: String(p), label: `${p}%` }))}
                          />
                        </div>
                        <div>
                          <label className="mb-1 block text-[11px] font-medium text-muted-foreground">
                            Tenure
                          </label>
                          <Select
                            value={emiPeriod}
                            onChange={(e) => setEmiPeriod(e.target.value)}
                            className="h-9"
                            options={[
                              { v: 120, l: "10 yr" },
                              { v: 180, l: "15 yr" },
                              { v: 240, l: "20 yr" },
                              { v: 300, l: "25 yr" },
                              { v: 360, l: "30 yr" },
                            ].map((o) => ({ value: String(o.v), label: o.l }))}
                          />
                        </div>
                      </div>
                      {emiResult ? (
                        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
                          <div className="text-[11px] uppercase tracking-wide text-primary/80">
                            Estimated EMI
                          </div>
                          <div className="mt-0.5 text-2xl font-extrabold tracking-tight tabular-nums">
                            ₹
                            {Math.round(
                              emiResult.emi ?? 0
                            ).toLocaleString("en-IN")}
                            <span className="ml-1 text-xs font-normal text-muted-foreground">
                              /month
                            </span>
                          </div>
                          <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                            <div>
                              <div className="text-muted-foreground">
                                Down payment
                              </div>
                              <div className="font-semibold tabular-nums">
                                ₹
                                {Math.round(
                                  emiResult.down ?? 0
                                ).toLocaleString("en-IN")}
                              </div>
                            </div>
                            <div>
                              <div className="text-muted-foreground">
                                Loan amount
                              </div>
                              <div className="font-semibold tabular-nums">
                                ₹
                                {Math.round(
                                  emiResult.loan ?? 0
                                ).toLocaleString("en-IN")}
                              </div>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          <Skeleton className="h-20 w-full rounded-xl" />
                        </div>
                      )}
                      <Button
                        asChild
                        variant="outline"
                        size="sm"
                        className="h-9 w-full rounded-lg text-xs"
                      >
                        <Link
                          href={`/affordability?price=${property.price}&tenure=${emiPeriod}&down=${downPct}`}
                        >
                          Open full affordability calculator →
                        </Link>
                      </Button>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="ai" className="mt-0 animate-fade-in">
            <AIAnalysisPanel
              propertyId={property.id}
              property={property}
              priceIntel={priceIntel ?? undefined}
              className="w-full"
            />
          </TabsContent>
        </Tabs>
      </section>

      {similar.length > 0 && (
        <section className="mt-10 border-t border-border/50 pt-6">
          <div className="mb-3 flex items-end justify-between">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">
                Similar properties
              </h2>
              <p className="text-xs text-muted-foreground">
                {similar.length} nearby alternatives from the same backend
                similarity query.
              </p>
            </div>
            <Badge variant="outline" className="text-[10px]">
              compare up to 4
            </Badge>
          </div>
          <div className="space-y-2.5">
            {similar.slice(0, 6).map((p) => (
              <PropertyListRow
                key={p.id}
                property={p}
                showSave={!!isAuthenticated}
                showCompare
              />
            ))}
          </div>
        </section>
      )}

      <div className="h-10" />
    </main>
  );
}
