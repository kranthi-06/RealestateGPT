"use client";

import { useState } from "react";
import { LocateFixed, Loader2, MapPin } from "lucide-react";
import { searchApi, ApiError } from "@/lib/api";
import type { Property } from "@/lib/types";
import { Button } from "@/components/ui/button";
import PropertyCard from "@/components/property-card";
import { EmptyState } from "@/components/empty-state";

export default function NearMePage() {
  const [loading, setLoading] = useState(false); const [error, setError] = useState<string>(); const [properties, setProperties] = useState<Property[] | null>(null);
  const locate = () => { if (!navigator.geolocation) { setError("This browser does not support location access. Use Search to enter a location manually."); return; } setLoading(true); setError(undefined); navigator.geolocation.getCurrentPosition(async ({ coords }) => { try { const response = await searchApi.nearMe({ latitude: coords.latitude, longitude: coords.longitude, radius_km: 5 }); setProperties(response.properties); } catch (caught) { setError(caught instanceof ApiError ? caught.message : "We couldn’t load nearby properties. Please try again."); } finally { setLoading(false); } }, () => { setLoading(false); setError("Location access was not granted. Your location was not stored; use Search to enter an area manually."); }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }); };
  return <main className="product-shell py-10 sm:py-16"><section className="surface-inset rounded-3xl px-6 py-14 text-center sm:px-12"><span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary"><MapPin className="size-6" /></span><p className="eyebrow mt-5">Location intelligence</p><h1 className="product-heading mt-3 text-5xl">What&apos;s around you?</h1><p className="mx-auto mt-4 max-w-xl leading-7 text-muted-foreground">Find verified properties within five kilometres of your current location. We only ask your browser after you choose to continue.</p><Button onClick={locate} disabled={loading} className="mt-7 rounded-xl">{loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <LocateFixed className="mr-2 size-4" />}Use my location</Button>{error ? <p role="alert" className="mx-auto mt-5 max-w-lg text-sm text-destructive">{error}</p> : null}</section>{properties ? <section className="mt-10"><h2 className="product-heading text-3xl">Nearby verified inventory</h2>{properties.length ? <div className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">{properties.map((property) => <PropertyCard key={property.id} property={property} />)}</div> : <div className="mt-6"><EmptyState title="No verified properties nearby." description="There may be limited inventory in this area. Try a wider search with a city or locality." actionHref="/search" actionLabel="Search by location" /></div>}</section> : null}</main>;
}
