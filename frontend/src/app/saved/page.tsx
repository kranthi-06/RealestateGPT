"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { savedApi } from "@/lib/api";
import type { SavedPropertyItem } from "@/lib/types";
import PropertyCard from "@/components/property-card";
import { Loader2 } from "lucide-react";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";

export default function SavedPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [savedProperties, setSavedProperties] = useState<SavedPropertyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/auth/login");
    }
  }, [isLoading, isAuthenticated, router]);

  const fetchSavedProperties = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await savedApi.getSavedProperties();
      setSavedProperties(data);
    } catch {
      setError("Your shortlist could not be retrieved. Your saved properties have not been changed.");
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
    <div className="product-shell py-10 sm:py-14">
      <div className="mb-8">
        <p className="eyebrow">Your shortlist</p>
        <h1 className="product-heading mt-3 text-4xl sm:text-5xl">Saved for a closer look.</h1>
        <p className="mt-3 text-muted-foreground">
          Keep the homes worth comparing in one calm, personal workspace.
        </p>
      </div>

      {error ? <ErrorState message={error} onRetry={fetchSavedProperties} /> : savedProperties.length > 0 ? (
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
        <EmptyState title="Your shortlist starts here." description="Save any home from search to keep the details, source, and freshness signal together for later." actionHref="/search" actionLabel="Explore properties" />
      )}
    </div>
  );
}
