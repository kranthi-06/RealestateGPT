"use client";

/**
 * Global saved-property state.
 *
 * The heart of every card asks the same question — "is this property saved?" —
 * on search results, property details, AI recommendations and the Saved page.
 * Each page used to answer it from a one-time prop, so a save made on one page
 * was invisible on the next. This provider keeps a single source of truth:
 * the set of saved ids hydrated from the server once, then updated
 * optimistically on every save/unsave.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { savedApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

interface SavedContextValue {
  savedIds: ReadonlySet<number>;
  isSaved: (propertyId: number) => boolean;
  hydrate: () => Promise<void>;
  toggleSaved: (propertyId: number) => Promise<"saved" | "unsaved" | "failed">;
  /** Version counter so lists can re-fetch when the set changes. */
  revision: number;
}

const SavedContext = createContext<SavedContextValue | undefined>(undefined);

export function SavedProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set());
  const [revision, setRevision] = useState(0);

  const hydrate = useCallback(async () => {
    if (!isAuthenticated) {
      setSavedIds(new Set());
      setRevision((v) => v + 1);
      return;
    }
    try {
      const { property_ids } = await savedApi.getSavedIds();
      setSavedIds(new Set(property_ids));
    } catch {
      // Keep the current set: a failed hydrate must not wipe valid state.
    } finally {
      setRevision((v) => v + 1);
    }
  }, [isAuthenticated]);

  // Hydrate once per session, and again whenever the auth state changes, so a
  // refresh or a new sign-in shows the correct state everywhere.
  useEffect(() => {
    // ``hydrate`` sets state; queue it so React does not warn about a
    // synchronous setState inside the effect body.
    const id = window.setTimeout(() => void hydrate(), 0);
    return () => window.clearTimeout(id);
  }, [hydrate]);

  const isSaved = useCallback((propertyId: number) => savedIds.has(propertyId), [savedIds]);

  const toggleSaved = useCallback(
    async (propertyId: number) => {
      if (!isAuthenticated) return "failed";
      const wasSaved = savedIds.has(propertyId);
      // Optimistic update: the heart turns immediately and rolls back on error.
      setSavedIds((current) => {
        const next = new Set(current);
        if (wasSaved) next.delete(propertyId);
        else next.add(propertyId);
        return next;
      });
      setRevision((v) => v + 1);
      try {
        if (wasSaved) {
          await savedApi.unsaveProperty(propertyId);
        } else {
          await savedApi.saveProperty(propertyId);
        }
        return wasSaved ? "unsaved" : "saved";
      } catch {
        setSavedIds((current) => {
          const next = new Set(current);
          if (wasSaved) next.add(propertyId);
          else next.delete(propertyId);
          return next;
        });
        setRevision((v) => v + 1);
        return "failed";
      }
    },
    [isAuthenticated, savedIds]
  );

  const value = useMemo(
    () => ({ savedIds, isSaved, hydrate, toggleSaved, revision }),
    [savedIds, isSaved, hydrate, toggleSaved, revision]
  );

  return <SavedContext.Provider value={value}>{children}</SavedContext.Provider>;
}

export function useSaved() {
  const context = useContext(SavedContext);
  if (context === undefined) {
    throw new Error("useSaved must be used within a SavedProvider");
  }
  return context;
}
