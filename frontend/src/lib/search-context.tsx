"use client";

/**
 * Global search state — query, filters, results, pagination and preferences.
 *
 * Search state previously lived in the Search page's own ``useState``, so it
 * evaporated the moment the user navigated anywhere else and came back: the
 * query, the filters and the results were all gone. This provider keeps one
 * shared, durable copy of the search:
 *
 *   URL query params   → shareable/deep-link state (q, city, filters, sort)
 *   sessionStorage     → results + preferences for this tab (survives
 *                        client-side navigation and a full page reload)
 *   request cache      → identical signature reuses results without any
 *                        duplicate upstream request
 *
 * Saved properties and compare selections are deliberately NOT part of this
 * state: they live in their own providers, so clearing a search never touches
 * them.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { searchApi } from "@/lib/api";
import type {
  Property,
  SearchFilters,
  SearchIntent,
  SearchSectionsResponse,
  UnifiedSearchResponse,
} from "@/lib/types";

const STORAGE_KEY = "regpt_search_state_v1";
/** Results older than this are re-validated with the server before reuse. */
const RESULT_MAX_AGE_MS = 120_000;
/** Debounce window for filter-driven re- searches. */
const SEARCH_DEBOUNCE_MS = 300;

export type SortKey = "relevance" | "price_asc" | "price_desc" | "newest";

export interface SearchState {
  filters: SearchFilters;
  results: Property[];
  sections: SearchSectionsResponse["sections"];
  webDiscoveries: UnifiedSearchResponse["web_discoveries"];
  intent: SearchIntent | null;
  includeWeb: boolean;
  userCoords: { lat: number; lng: number } | null;
  sort: SortKey;
  viewMode: "list" | "grid";
  /** Signature of the request that produced the current results. */
  signature: string;
  /** When the current results were fetched (epoch ms). */
  fetchedAt: number;
  /** True once the results were produced by a completed request. */
  hasResults: boolean;
}

export type SearchStatus = "idle" | "loading" | "error" | "ready";

interface SearchContextValue {
  state: SearchState;
  status: SearchStatus;
  error: string | null;
  /** True once URL/sessionStorage hydration finished (avoids a flash). */
  hydrated: boolean;
  setFilters: (next: SearchFilters | ((current: SearchFilters) => SearchFilters)) => void;
  setIncludeWeb: (value: boolean) => void;
  setUserCoords: (coords: { lat: number; lng: number } | null) => void;
  setSort: (sort: SortKey) => void;
  setViewMode: (mode: "list" | "grid") => void;
  /** Explicit (user-initiated) search: always fetches. */
  runSearch: () => Promise<void>;
  /** Re-search with the current filters (used by filter changes). */
  refreshSearch: () => Promise<void>;
  /** Reset query + filters + results (never touches saved/compare state). */
  clearSearch: () => void;
  signature: string;
  /** Internal: the Search page pushes the live URL query string here. */
  syncUrlSearch?: (search: string) => void;
}

const EMPTY_STATE: SearchState = {
  filters: {},
  results: [],
  sections: [],
  webDiscoveries: [],
  intent: null,
  includeWeb: true,
  userCoords: null,
  sort: "relevance",
  viewMode: "list",
  signature: "",
  fetchedAt: 0,
  hasResults: false,
};

const SearchContext = createContext<SearchContextValue | undefined>(undefined);

/* ── helpers ─────────────────────────────────────────────────────────────── */

function filtersFromParams(params: URLSearchParams): SearchFilters {
  const filters: SearchFilters = {};
  const read = (key: string) => {
    const value = params.get(key);
    return value && value.trim() ? value : undefined;
  };
  const readNumber = (key: string) => {
    const raw = params.get(key);
    if (raw == null || raw.trim() === "") return undefined;
    const value = Number(raw);
    return Number.isFinite(value) ? value : undefined;
  };

  filters.q = read("q");
  filters.city = read("city");
  filters.locality = read("locality");
  filters.property_type = read("property_type");
  filters.listing_type = read("listing_type") as SearchFilters["listing_type"];
  filters.min_price = readNumber("min_price");
  filters.max_price = readNumber("max_price");
  filters.bedrooms = readNumber("bedrooms") as SearchFilters["bedrooms"];
  filters.min_bedrooms = readNumber("min_bedrooms");
  filters.max_bedrooms = readNumber("max_bedrooms");
  filters.bathrooms = readNumber("bathrooms");
  filters.min_area = readNumber("min_area");
  filters.max_area = readNumber("max_area");
  filters.furnishing = read("furnishing");
  filters.radius_km = readNumber("radius_km");
  const amenities = params.getAll("amenities").filter(Boolean);
  if (amenities.length) filters.amenities = amenities;
  // Strip undefined values so the object compares cleanly.
  return Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined && value !== "")
  ) as SearchFilters;
}

function paramsFromFilters(filters: SearchFilters): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) {
      value.forEach((item) => params.append(key, String(item)));
      return;
    }
    params.append(key, String(value));
  });
  return params.toString();
}

function signatureOf(
  filters: SearchFilters,
  userCoords: { lat: number; lng: number } | null,
  includeWeb: boolean
): string {
  return JSON.stringify({
    filters,
    coords: userCoords ? `${userCoords.lat.toFixed(6)}_${userCoords.lng.toFixed(6)}` : "none",
    includeWeb,
  });
}

function readStored(): Partial<SearchState> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as Partial<SearchState>;
  } catch {
    return null;
  }
}

function writeStored(state: SearchState): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Private mode / quota: search still works, it just won't be restored.
  }
}

export function SearchProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  const [state, setState] = useState<SearchState>(EMPTY_STATE);
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  /** Latest URL query string, pushed in by the Search page via the hook below. */
  const [urlSearch, setUrlSearch] = useState("");

  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** In-flight request cache so a repeat signature never re-hits the API. */
  const cacheRef = useRef<Map<string, { timestamp: number; data: UnifiedSearchResponse }>>(new Map());
  /** Guards against the same signature running twice concurrently. */
  const runningRef = useRef<Set<string>>(new Set());
  const hydratedRef = useRef(false);

  const signature = useMemo(
    () => signatureOf(state.filters, state.userCoords, state.includeWeb),
    [state.filters, state.userCoords, state.includeWeb]
  );

  /* ── hydration: URL first (deep links), then sessionStorage ───────────── */
  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;
    const params = new URLSearchParams(urlSearch || (typeof window !== "undefined" ? window.location.search : ""));
    const urlFilters = filtersFromParams(params);
    const stored = readStored();

    const urlSort = params.get("sort") as SortKey | null;
    const rawView = params.get("view");
    const urlView: "list" | "grid" | null = rawView === "grid" ? "grid" : rawView === "list" ? "list" : null;
    const hasUrlQuery = Object.keys(urlFilters).length > 0;

    setState((current) => {
      const base: SearchState = {
        ...current,
        filters: hasUrlQuery ? urlFilters : stored?.filters ?? {},
        sort: (urlSort ?? stored?.sort ?? "relevance") as SortKey,
        viewMode: (urlView ?? stored?.viewMode ?? "list") as "list" | "grid",
        includeWeb: stored?.includeWeb ?? true,
        userCoords: stored?.userCoords ?? null,
      };
      // Restore the previous results only when they are still fresh AND the
      // request signature matches the restored filters — otherwise the page
      // triggers a real search instead of showing stale data.
      const restoredSignature = signatureOf(base.filters, base.userCoords, base.includeWeb);
      const restoreResults =
        !hasUrlQuery &&
        stored &&
        stored.signature === restoredSignature &&
        Date.now() - (stored.fetchedAt ?? 0) < RESULT_MAX_AGE_MS;
      if (restoreResults) {
        return {
          ...base,
          results: stored?.results ?? [],
          sections: stored?.sections ?? [],
          webDiscoveries: stored?.webDiscoveries ?? [],
          intent: stored?.intent ?? null,
          signature: restoredSignature,
          fetchedAt: stored?.fetchedAt ?? 0,
          hasResults: Boolean(stored?.hasResults),
        };
      }
      return { ...base, signature: restoredSignature };
    });
    setHydrated(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ── persist to sessionStorage on every state change ─────────────────── */
  useEffect(() => {
    if (!hydrated) return;
    writeStored(state);
  }, [state, hydrated]);

  /* ── URL mirror (only on the search route, never scroll-jumping) ─────── */
  const lastMirroredRef = useRef<string | null>(null);
  useEffect(() => {
    if (!hydrated || pathname !== "/search") return;
    const query = paramsFromFilters(state.filters);
    const currentQuery =
      typeof window !== "undefined"
        ? window.location.search.replace(/^\?/, "")
        : "";
    if (currentQuery === query) {
      lastMirroredRef.current = query;
      return;
    }
    // Avoid fighting with a navigation that is already in flight.
    if (lastMirroredRef.current === currentQuery) return;
    lastMirroredRef.current = query;
    router.replace(query ? `/search?${query}` : "/search", { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.filters, hydrated, pathname, urlSearch]);

  /* ── the single fetch path ──────────────────────────────────────────── */
  const executeSearch = useCallback(
    async (current: SearchState, options: { force?: boolean } = {}) => {
      const requestSignature = signatureOf(current.filters, current.userCoords, current.includeWeb);
      const query = (current.filters.q ?? "").trim();

      if (!query && !current.userCoords) {
        setState((s) => ({ ...s, results: [], sections: [], webDiscoveries: [], intent: null, hasResults: false }));
        setStatus("idle");
        setError(null);
        return;
      }

      const cached = cacheRef.current.get(requestSignature);
      const now = Date.now();
      if (
        !options.force &&
        cached &&
        now - cached.timestamp < RESULT_MAX_AGE_MS
      ) {
        setState((s) => ({
          ...s,
          results: cached.data.verified_properties,
          sections: cached.data.sections,
          webDiscoveries: cached.data.web_discoveries,
          intent: cached.data.parsed ?? null,
          signature: requestSignature,
          fetchedAt: cached.timestamp,
          hasResults: true,
        }));
        setStatus("ready");
        setError(null);
        return;
      }

      if (runningRef.current.has(requestSignature)) return;
      runningRef.current.add(requestSignature);

      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setStatus("loading");
      setError(null);

      try {
        const unifiedQuery =
          query ||
          (current.userCoords
            ? `properties near ${current.userCoords.lat.toFixed(4)}, ${current.userCoords.lng.toFixed(4)}`
            : "");
        const data = await searchApi.unified(
          {
            query: unifiedQuery,
            location: current.userCoords
              ? {
                  latitude: current.userCoords.lat,
                  longitude: current.userCoords.lng,
                  radius_km: current.filters.radius_km ?? 5.0,
                }
              : undefined,
            filters: current.filters,
            include_web: current.includeWeb,
            limit: 24,
          },
          controller.signal
        );
        if (controller.signal.aborted) return;
        cacheRef.current.set(requestSignature, { timestamp: Date.now(), data });
        setState((s) => ({
          ...s,
          results: data.verified_properties,
          sections: data.sections,
          webDiscoveries: data.web_discoveries,
          intent: data.parsed ?? null,
          signature: requestSignature,
          fetchedAt: Date.now(),
          hasResults: true,
        }));
        setStatus("ready");
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        if (err && typeof err === "object" && "status" in err) {
          const apiError = err as { status: number; message?: string };
          if (apiError.status === 401) setError("Please sign in again before searching.");
          else if (apiError.status === 422) setError("Check your search and filters, then try again.");
          else if (apiError.status === 429) setError("Search is rate-limited. Please wait a moment and try again.");
          else if (apiError.status >= 500) setError("We couldn't load property results. Please try again.");
          else setError(apiError.message || "We couldn't load property results. Please try again.");
        } else {
          setError("We couldn't load property results. Check your connection and try again.");
        }
        setStatus("error");
      } finally {
        runningRef.current.delete(requestSignature);
        if (abortRef.current === controller) abortRef.current = null;
        if (!controller.signal.aborted) setStatus((s) => (s === "loading" ? "ready" : s));
      }
    },
    []
  );

  /* ── filter changes re-search automatically (debounced) ──────────────── */
  const lastSignatureRef = useRef<string>("");
  useEffect(() => {
    if (!hydrated) return;
    // Only the Search route auto-searches. Navigating to any other page must
    // never trigger a request: the shared state is restored, not re-run.
    if (pathname !== "/search") return;
    if (signature === lastSignatureRef.current) return;
    lastSignatureRef.current = signature;
    const hasQuery = (state.filters.q ?? "").trim() || state.userCoords;
    if (!hasQuery) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void executeSearch(state);
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [signature, state, hydrated, executeSearch, pathname]);

  /* ── public API ─────────────────────────────────────────────────────── */

  const runSearch = useCallback(async () => {
    await executeSearch(state, { force: true });
  }, [executeSearch, state]);

  const refreshSearch = useCallback(async () => {
    await executeSearch(state);
  }, [executeSearch, state]);

  const clearSearch = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    if (debounceRef.current) clearTimeout(debounceRef.current);
    cacheRef.current.clear();
    setState((current) => ({
      ...current,
      filters: {},
      results: [],
      sections: [],
      webDiscoveries: [],
      intent: null,
      signature: "",
      fetchedAt: 0,
      hasResults: false,
    }));
    setStatus("idle");
    setError(null);
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    if (pathname === "/search") router.replace("/search", { scroll: false });
  }, [pathname, router]);

  const value = useMemo<SearchContextValue>(
    () => ({
      state,
      status,
      error,
      hydrated,
      signature,
      setFilters: (next) =>
        setState((current) => ({
          ...current,
          filters:
            typeof next === "function" ? next(current.filters) : next,
        })),
      setIncludeWeb: (includeWeb) => setState((current) => ({ ...current, includeWeb })),
      setUserCoords: (userCoords) => setState((current) => ({ ...current, userCoords })),
      setSort: (sort) => setState((current) => ({ ...current, sort })),
      setViewMode: (viewMode) => setState((current) => ({ ...current, viewMode })),
      runSearch,
      refreshSearch,
      clearSearch,
      /** Internal: the Search page pushes the live URL query string here. */
      syncUrlSearch: (search: string) => setUrlSearch(search),
    }),
    [state, status, error, hydrated, signature, runSearch, refreshSearch, clearSearch]
  );

  return <SearchContext.Provider value={value}>{children}</SearchContext.Provider>;
}

export function useSearchState() {
  const context = useContext(SearchContext);
  if (context === undefined) {
    throw new Error("useSearchState must be used within a SearchProvider");
  }
  return context;
}

/**
 * Push the live URL query string into the search state. Must be called from a
 * component inside a Suspense boundary (it uses ``useSearchParams``), which is
 * why it lives apart from the provider itself: the provider is mounted in the
 * root layout, where a Suspense boundary would block every page.
 */
export function useSyncUrlSearch(search: string) {
  const { syncUrlSearch } = useSearchState();
  useEffect(() => {
    syncUrlSearch?.(search);
  }, [search, syncUrlSearch]);
}
