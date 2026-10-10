"use client";

/**
 * Global compare selection.
 *
 * The selection previously lived in one page's useState, so it vanished on
 * navigation or refresh — the very first reason the comparison flow felt
 * broken. Selection is now a shared, persisted store: add a property from
 * search, navigate away, come back, and it is still selected.
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

const STORAGE_KEY = "regpt_compare_ids_v1";
export const MAX_COMPARE = 4;

interface CompareContextValue {
  ids: number[];
  has: (propertyId: number) => boolean;
  toggle: (propertyId: number) => void;
  add: (propertyId: number) => void;
  remove: (propertyId: number) => void;
  clear: () => void;
  isFull: boolean;
}

const CompareContext = createContext<CompareContextValue | undefined>(undefined);

function readStored(): number[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((id): id is number => typeof id === "number" && Number.isInteger(id) && id > 0).slice(0, MAX_COMPARE);
  } catch {
    return [];
  }
}

function writeStored(ids: number[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // Storage can be unavailable (private mode); selection still works in-memory.
  }
}

export function CompareProvider({ children }: { children: ReactNode }) {
  const [ids, setIds] = useState<number[]>([]);
  const [hydrated, setHydrated] = useState(false);

  // Read persisted selection after mount so server and client markup agree.
  // ``useSyncExternalStore`` is the canonical way to read a browser-only
  // store without a hydration mismatch or an effect-triggered setState.
  useEffect(() => {
    const id = window.setTimeout(() => {
      setIds(readStored());
      setHydrated(true);
    }, 0);
    return () => window.clearTimeout(id);
  }, []);

  useEffect(() => {
    if (hydrated) writeStored(ids);
  }, [ids, hydrated]);

  // Keep multiple tabs in sync.
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) setIds(readStored());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const add = useCallback((propertyId: number) => {
    setIds((current) =>
      current.includes(propertyId) || current.length >= MAX_COMPARE
        ? current
        : [...current, propertyId]
    );
  }, []);

  const remove = useCallback((propertyId: number) => {
    setIds((current) => current.filter((id) => id !== propertyId));
  }, []);

  const toggle = useCallback((propertyId: number) => {
    setIds((current) => {
      if (current.includes(propertyId)) return current.filter((id) => id !== propertyId);
      if (current.length >= MAX_COMPARE) return current;
      return [...current, propertyId];
    });
  }, []);

  const clear = useCallback(() => setIds([]), []);

  const value = useMemo(
    () => ({
      ids,
      has: (propertyId: number) => ids.includes(propertyId),
      toggle,
      add,
      remove,
      clear,
      isFull: ids.length >= MAX_COMPARE,
    }),
    [ids, toggle, add, remove, clear]
  );

  return <CompareContext.Provider value={value}>{children}</CompareContext.Provider>;
}

export function useCompare() {
  const context = useContext(CompareContext);
  if (context === undefined) {
    throw new Error("useCompare must be used within a CompareProvider");
  }
  return context;
}
