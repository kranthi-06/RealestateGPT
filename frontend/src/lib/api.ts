/* RealEstateGPT - API Client */

import type {
  TokenResponse,
  Property,
  PropertyListResponse,
  SavedPropertyItem,
  SavedSearch,
  Comparison,
  SearchFilters,
  SearchSectionsResponse,
  SearchIntent,
  PriceIntelligence,
  WorkerStatus,
  WorkerRun,
  WebDiscoveryDetail,
  UnifiedSearchRequest,
  UnifiedSearchResponse,
  AdminStats,
  AdminUser,
  AuditLog,
  AdminAiUsage,
  User,
  AssistantResponse,
  DiscoverySearchResponse,
  MapProviderStatus,
  LiveNearbyResponse,
  EmiResult,
  AffordabilityResult,
  PriceEstimate,
  PriceFairness,
  RentalYield,
  Roi,
} from "./types";
import { resolveApiBase } from "./api-base";

const API_BASE = resolveApiBase();
const API_V1 = `${API_BASE}/api/v1`;

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("auth_token");
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_V1}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let message = "Request failed";
    try {
      const data = await res.json();
      if (data.detail && typeof data.detail === "object" && data.detail.message) {
        message = data.detail.message;
      } else {
        message = data.detail || data.message || message;
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiError(message, res.status);
  }

  return res.json();
}

// â”€â”€â”€ Auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const authApi = {
  register: (data: {
    email: string;
    full_name: string;
    password: string;
    phone?: string;
  }) => request<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(data) }),

  login: (data: { email: string; password: string }) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(data) }),

  getProfile: () => request<User>("/auth/me"),

  updateProfile: (data: {
    full_name?: string;
    phone?: string;
    preferred_cities?: string;
    budget_min?: number;
    budget_max?: number;
  }) => request<User>("/auth/me", { method: "PUT", body: JSON.stringify(data) }),
};

// â”€â”€â”€ Properties â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const propertiesApi = {
  list: (filters: SearchFilters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        params.append(key, String(value));
      }
    });
    return request<PropertyListResponse>(`/properties?${params.toString()}`);
  },

  get: (id: number) => request<Property>(`/properties/${id}`),

  priceIntelligence: (id: number) =>
    request<PriceIntelligence>(`/properties/${id}/price-intelligence`),

  bulk: (property_ids: number[]) =>
    request<Property[]>("/properties/bulk", {
      method: "POST",
      body: JSON.stringify({ property_ids }),
    }),

  getFeatured: () => request<Property[]>("/properties/featured"),

  getSimilar: (id: number) => request<Property[]>(`/properties/${id}/similar`),

  getCities: () => request<string[]>("/properties/cities"),

  getLocalities: (city: string) =>
    request<string[]>(`/properties/localities?city=${encodeURIComponent(city)}`),
};

// â”€â”€â”€ Saved â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const savedApi = {
  saveProperty: (property_id: number, notes?: string) =>
    request<{ id: number; message: string }>("/saved/properties", {
      method: "POST",
      body: JSON.stringify({ property_id, notes }),
    }),

  unsaveProperty: (property_id: number) =>
    request<{ message: string }>(`/saved/properties/${property_id}`, { method: "DELETE" }),

  getSavedProperties: () => request<SavedPropertyItem[]>("/saved/properties"),

  saveSearch: (data: {
    name: string;
    city?: string;
    property_type?: string;
    min_price?: number;
    max_price?: number;
    bedrooms?: number;
    query_text?: string;
  }) => request<SavedSearch>("/saved/searches", { method: "POST", body: JSON.stringify(data) }),

  getSavedSearches: () => request<SavedSearch[]>("/saved/searches"),

  deleteSavedSearch: (id: number) =>
    request<{ message: string }>(`/saved/searches/${id}`, { method: "DELETE" }),
};

// â”€â”€â”€ Comparisons â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const comparisonsApi = {
  create: (property_ids: number[], name?: string) =>
    request<Comparison>("/saved/comparisons", {
      method: "POST",
      body: JSON.stringify({ property_ids, name }),
    }),

  list: () => request<Comparison[]>("/saved/comparisons"),

  get: (id: number) => request<Comparison>(`/saved/comparisons/${id}`),

  delete: (id: number) =>
    request<{ message: string }>(`/saved/comparisons/${id}`, { method: "DELETE" }),
};

// â”€â”€â”€ Grounded AI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const aiApi = {
  assistant: (data: { message: string; conversation_id?: number; property_id?: number; compare_ids?: number[] }) =>
    request<AssistantResponse>("/ai/assistant", { method: "POST", body: JSON.stringify(data) }),
  search: (data: { query: string; limit?: number; user_filters?: Record<string, string | number | string[]> }) =>
    request<DiscoverySearchResponse>("/ai/search", { method: "POST", body: JSON.stringify(data) }),
};

// â”€â”€â”€ Dynamic search sections + intent parsing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const searchApi = {
  sections: (filters: SearchFilters) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        params.append(key, String(value));
      }
    });
    return request<SearchSectionsResponse>(`/search/sections?${params.toString()}`);
  },

  parse: (q: string) =>
    request<SearchIntent & { raw_text: string }>(`/search/parse?q=${encodeURIComponent(q)}`).then(
      (res) => res,
      (err: unknown) => {
        // Production backends deployed behind /api/backend may not expose
        // /search/parse yet (backend drift). When the endpoint is genuinely
        // missing (404/405) in production, degrade gracefully to "no interpreted
        // intent" instead of surfacing a crash. Do NOT swallow real validation
        // errors (422) from a backend that does implement the endpoint.
        if (err instanceof ApiError && err.status !== 200) {
          if (err.status === 404 || err.status === 405) {
            return null as unknown as SearchIntent & { raw_text: string };
          }
          throw err;
        }
        throw err;
      }
    ),

  nearMe: (data: {
    latitude: number;
    longitude: number;
    radius_km: number;
    q?: string;
    property_type?: string;
    listing_type?: string;
  }) => request<PropertyListResponse>("/search/near-me", { method: "POST", body: JSON.stringify(data) }),

  unified: (data: UnifiedSearchRequest) =>
    request<UnifiedSearchResponse>("/search/autonomous", { method: "POST", body: JSON.stringify(data) }),
};

export const locationsApi = {
  status: () => request<MapProviderStatus>("/locations/status"),
  nearby: (propertyId: number, category: string, radiusKm = 3, travelMode = "WALK") => request<LiveNearbyResponse>(`/locations/properties/${propertyId}/nearby?category=${encodeURIComponent(category)}&radius_km=${radiusKm}&travel_mode=${travelMode}`),
};
export const discoveryApi = {
  get: (discoveryId: string) =>
    request<WebDiscoveryDetail>(`/search/discoveries/${encodeURIComponent(discoveryId)}`),
  save: (discoveryId: string) =>
    request<{ discovery_id: string; saved: boolean; message: string }>(
      `/search/discoveries/${encodeURIComponent(discoveryId)}/save`,
      { method: "POST" }
    ),
  unsave: (discoveryId: string) =>
    request<{ discovery_id: string; saved: boolean; message: string }>(
      `/search/discoveries/${encodeURIComponent(discoveryId)}/save`,
      { method: "DELETE" }
    ),
};

export const financeApi = {
  emi: (data: { principal: number; annual_interest_rate: number; tenure_years: number }) =>
    request<EmiResult>("/finance/emi", { method: "POST", body: JSON.stringify(data) }),
  affordability: (data: {
    monthly_income: number;
    existing_obligations?: number;
    down_payment?: number;
    property_price?: number;
    annual_interest_rate?: number;
    tenure_years?: number;
  }) => request<AffordabilityResult>("/finance/affordability", { method: "POST", body: JSON.stringify(data) }),
  rentalYield: (data: { property_price: number; monthly_rent: number; annual_expenses_pct?: number }) =>
    request<RentalYield>("/finance/rental-yield", { method: "POST", body: JSON.stringify(data) }),
  roi: (data: { purchase_price: number; annual_rent: number; annual_expenses?: number; appreciation_pct?: number; years?: number }) =>
    request<Roi>("/finance/roi", { method: "POST", body: JSON.stringify(data) }),
  estimate: (propertyId: number) => request<PriceEstimate>(`/finance/properties/${propertyId}/estimate`),
  fairness: (propertyId: number) => request<PriceFairness>(`/finance/properties/${propertyId}/fairness`),
};

// â”€â”€â”€ Admin â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const adminApi = {
  getStats: () => request<AdminStats>("/admin/stats"),
  listUsers: (page = 1, pageSize = 50) =>
    request<{ users: AdminUser[]; total: number }>(`/admin/users?page=${page}&page_size=${pageSize}`),
  updateUser: (userId: number, updates: { role?: string; is_active?: boolean }) => {
    const params = new URLSearchParams();
    if (updates.role) params.append("role", updates.role);
    if (updates.is_active !== undefined) params.append("is_active", String(updates.is_active));
    return request<AdminUser>(`/admin/users/${userId}?${params.toString()}`, { method: "PATCH" });
  },
  listProperties: (page = 1, pageSize = 50, includeInactive = false) =>
    request<{ properties: Property[]; total: number; page: number; page_size: number; total_pages: number }>(
      `/admin/properties?page=${page}&page_size=${pageSize}&include_inactive=${includeInactive}`
    ),
  auditLogs: (limit = 100, offset = 0) =>
    request<AuditLog[]>(`/admin/audit-logs?limit=${limit}&offset=${offset}`),
  aiUsage: () => request<AdminAiUsage>("/admin/ai-usage"),
  verifyProperty: (propertyId: number, status: string) =>
    request<{ message: string }>(`/admin/properties/${propertyId}/verify?status=${encodeURIComponent(status)}`, { method: "PUT" }),
};

// â”€â”€â”€ Health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const healthApi = {
  check: () => request<{ status: string }>("/health"),
};

// â”€â”€â”€ Worker scheduler / monitoring â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export const workersApi = {
  // No secrets are exposed to the browser; triggering runs requires an admin JWT.
  status: () => request<WorkerStatus>("/workers/status"),
  runs: (workerName: string, limit = 10) =>
    request<{ runs: WorkerRun[]; total: number }>(
      `/workers/runs?worker_name=${encodeURIComponent(workerName)}&limit=${limit}`
    ),
  trigger: (workerName: string) =>
    request<Record<string, unknown>>(`/workers/run/${workerName}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }),
};
