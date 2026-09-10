/* RealEstateGPT - API Client */

import type {
  TokenResponse,
  Property,
  PropertyListResponse,
  SavedPropertyItem,
  SavedSearch,
  Comparison,
  SearchFilters,
  AdminStats,
  User,
  AssistantResponse,
  MapProviderStatus,
  LiveNearbyResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_V1 = `${API_BASE}/api/v1`;

class ApiError extends Error {
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
      message = data.detail || data.message || message;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(message, res.status);
  }

  return res.json();
}

// ─── Auth ──────────────────────────────────

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

// ─── Properties ────────────────────────────

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

  getFeatured: () => request<Property[]>("/properties/featured"),

  getSimilar: (id: number) => request<Property[]>(`/properties/${id}/similar`),

  getCities: () => request<string[]>("/properties/cities"),

  getLocalities: (city: string) =>
    request<string[]>(`/properties/localities?city=${encodeURIComponent(city)}`),
};

// ─── Saved ─────────────────────────────────

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

// ─── Comparisons ───────────────────────────

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

// ─── Grounded AI ───────────────────────────

export const aiApi = {
  assistant: (data: { message: string; conversation_id?: number; property_id?: number; compare_ids?: number[] }) =>
    request<AssistantResponse>("/ai/assistant", { method: "POST", body: JSON.stringify(data) }),
};

export const locationsApi = {
  status: () => request<MapProviderStatus>("/locations/status"),
  nearby: (propertyId: number, category: string, radiusKm = 3) => request<LiveNearbyResponse>(`/locations/properties/${propertyId}/nearby?category=${encodeURIComponent(category)}&radius_km=${radiusKm}`),
};

// ─── Admin ─────────────────────────────────

export const adminApi = {
  getStats: () => request<AdminStats>("/admin/stats"),
};

// ─── Health ────────────────────────────────

export const healthApi = {
  check: () => request<{ status: string }>("/health"),
};

export { ApiError };
