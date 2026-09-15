/* TypeScript interfaces matching backend Pydantic schemas */

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone?: string | null;
  role: string;
  is_active: boolean;
  preferred_cities?: string | null;
  budget_min?: number | null;
  budget_max?: number | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Amenity {
  id: number;
  name: string;
  category?: string | null;
  icon?: string | null;
}

export interface Property {
  id: number;
  title: string;
  description?: string | null;
  slug: string;
  price: number;
  currency?: string | null;
  price_per_sqft?: number | null;
  maintenance_charge?: number | null;
  property_type: string;
  listing_type: string;
  bedrooms?: number | null;
  bathrooms?: number | null;
  balconies?: number | null;
  area_sqft?: number | null;
  carpet_area_sqft?: number | null;
  floor?: number | null;
  total_floors?: number | null;
  property_age?: number | null;
  facing?: string | null;
  furnishing?: string | null;
  parking?: number | null;
  construction_status?: string | null;
  address?: string | null;
  locality?: string | null;
  city: string;
  state?: string | null;
  pincode?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  builder_name?: string | null;
  project_name?: string | null;
  source?: string | null;
  source_type?: string | null;
  verification_status: string;
  is_featured: boolean;
  is_synthetic: boolean;
  image_urls?: string | null;
  amenities: Amenity[];
  listed_at?: string | null;
  created_at: string;
  updated_at: string;
  is_saved?: boolean | null;
}

export interface PropertyListResponse {
  properties: Property[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SavedPropertyItem {
  id: number;
  property_id: number;
  notes?: string | null;
  created_at: string;
  property: Property;
}

export interface SavedSearch {
  id: number;
  name: string;
  city?: string | null;
  locality?: string | null;
  property_type?: string | null;
  min_price?: number | null;
  max_price?: number | null;
  bedrooms?: number | null;
  min_area?: number | null;
  max_area?: number | null;
  furnishing?: string | null;
  query_text?: string | null;
  notify_enabled: number;
  created_at: string;
}

export interface Comparison {
  id: number;
  name?: string | null;
  property_ids: string;
  created_at: string;
  properties: Property[];
}

export interface SearchFilters {
  q?: string;
  city?: string;
  locality?: string;
  property_type?: string;
  listing_type?: string;
  min_price?: number;
  max_price?: number;
  bedrooms?: number;
  bathrooms?: number;
  min_area?: number;
  max_area?: number;
  furnishing?: string;
  amenities?: string[];
  latitude?: number;
  longitude?: number;
  radius_km?: number;
  sort_by?: string;
  sort_order?: string;
  page?: number;
  page_size?: number;
}

export interface AdminStats {
  total_properties: number;
  active_properties: number;
  verified_properties: number;
  total_users: number;
  total_saved_properties: number;
  total_saved_searches: number;
  total_comparisons: number;
  total_searches: number;
  properties_by_city: Record<string, number>;
  properties_by_type: Record<string, number>;
}

export interface AiSearchResult {
  property_id: number;
  title: string;
  slug: string;
  price: number;
  locality?: string | null;
  city: string;
  property_type: string;
  bedrooms?: number | null;
  overall_score: number;
  explanation?: string | null;
  positive_factors: string[];
  negative_factors: string[];
}

export interface SearchIntent {
  raw_text: string;
  city?: string | null;
  locality?: string | null;
  property_type?: string | null;
  bedrooms?: number | null;
  min_price?: number | null;
  max_price?: number | null;
  transport_requirement?: string | null;
  nearby_requirements: { type: string; max_distance_km: number }[];
}

export interface DiscoverySearchResponse {
  query: string;
  parsed: SearchIntent;
  total: number;
  results: AiSearchResult[];
  warning?: string | null;
  metrics: Record<string, number>;
}

export interface AssistantResponse {
    conversation_id: number;
    answer: string;
    results: AiSearchResult[];
    provider: string;
    warnings: string[];
    citations: { source_type: string; source_id?: number | null; label: string; url?: string | null }[];
    tool_calls: { tool: string; input: Record<string, unknown>; output_summary: string }[];
  }

export interface MapProviderStatus { configured: boolean; provider: string; message: string; }
export interface LivePlace {
  provider: "google" | "openstreetmap";
  place_id?: string;
  name: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  rating?: number;
  rating_count?: number;
  maps_url?: string;
  photo_resource?: string;
  photo_url?: string;
  attributions: string[];
  distance_km?: number;
  travel_minutes?: number;
  travel_mode?: string;
  website_url?: string;
  phone_number?: string;
  opening_hours?: string[];
}
export interface LiveNearbyResponse { property_id: number; category: string; radius_km: number; source: string; places: LivePlace[]; }

// ─── Finance ────────────────────────────────────────────

export interface EmiResult {
  monthly_emi: number;
  total_interest: number;
  total_repayment: number;
  annual_interest_rate: number;
  tenure_years: number;
  principal: number;
  formula: string;
}

export interface AffordabilityResult {
  max_monthly_emi: number;
  max_loan_amount: number;
  max_property_price: number;
  recommended_emi: number;
  emi_to_income_ratio: number;
  assumptions: string[];
  affordable: boolean;
}

export interface RentalYield {
  gross_yield_pct: number;
  net_yield_pct: number;
  annual_rent: number;
  annual_expenses: number;
  monthly_equivalent_rent: number;
  note: string;
}

export interface Roi {
  initial_yield_pct: number;
  annual_net_rent: number;
  total_investment: number;
  final_property_value: number;
  total_return_pct: number;
  annualized_return_pct: number;
  projections: { year: number; property_value: number; cumulative_rent_net: number; total_return_pct: number }[];
  note: string;
}

export interface PriceEstimate {
  property_id: number;
  estimated_price: number;
  lower_bound: number;
  upper_bound: number;
  price_per_sqft?: number | null;
  listed_price?: number | null;
  model_version: string;
  mae?: number | null;
  rmse?: number | null;
  r2?: number | null;
  sample_size: number;
  label: string;
}

export interface PriceFairness {
  property_id: number;
  listed_price: number;
  estimated_price: number;
  lower_bound: number;
  upper_bound: number;
  verdict: string;
  verdict_label: string;
  diff_pct: number;
  reasons: string[];
  comparables_median_price?: number | null;
  listed_price_per_sqft?: number | null;
  comparables_price_per_sqft?: number | null;
}

// ─── Admin ──────────────────────────────────────────────

export interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  is_email_verified: boolean;
  created_at: string;
}

export interface AuditLog {
  id: number;
  user_id?: number | null;
  action: string;
  entity?: string | null;
  entity_id?: number | null;
  detail?: Record<string, unknown> | null;
  ip_address?: string | null;
  created_at: string;
}

export interface AdminAiUsage {
  total_messages: number;
  total_conversations: number;
  tool_calls: number;
  offline_mode: boolean;
  provider: string;
  by_action: Record<string, number>;
}
