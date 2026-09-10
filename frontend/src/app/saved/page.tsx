"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { savedApi } from "@/lib/api";
import type { SavedPropertyItem } from "@/lib/types";
import PropertyCard from "@/components/property-card";
import { Button } from "@/components/ui/button";
import { Heart, Loader2, Search } from "lucide-react";
import Link from "next/link";

export default function SavedPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [savedProperties, setSavedProperties] = useState<SavedPropertyItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/auth/login");
    }
  }, [isLoading, isAuthenticated, router]);

  const fetchSavedProperties = async () => {
    try {
      setLoading(true);
      const data = await savedApi.getSavedProperties();
      setSavedProperties(data);
    } catch (err) {
      console.error("Failed to fetch saved properties", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      void Promise.resolve().then(fetchSavedProperties);
    }
  }, [isAuthenticated]); // The request is deliberately deferred to avoid a synchronous effect update.

  if (isLoading || (isAuthenticated && loading)) {
    return (
      <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return null; // Redirecting...
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight">Saved Properties</h1>
        <p className="text-muted-foreground mt-2">
          Properties you have saved for later review.
        </p>
      </div>

      {savedProperties.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {savedProperties.map((item) => (
            <PropertyCard
              key={item.property.id}
              property={{ ...item.property, is_saved: true }}
              onSaveToggle={fetchSavedProperties}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-20 bg-card rounded-2xl border border-border/60 shadow-sm">
          <Heart className="w-16 h-16 mx-auto text-muted-foreground/30 mb-4" />
          <h3 className="text-xl font-semibold">No saved properties yet</h3>
          <p className="text-muted-foreground mt-2 max-w-sm mx-auto">
            When you see a property you like, click the heart icon to save it here for easy access.
          </p>
          <Link href="/search">
            <Button className="mt-6 gradient-primary text-white border-0">
              <Search className="w-4 h-4 mr-2" />
              Explore Properties
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}
