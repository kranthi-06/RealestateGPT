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
  min_area?: number;
  max_area?: number;
  furnishing?: string;
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

export interface AssistantResponse {
  conversation_id: number;
  answer: string;
  results: AiSearchResult[];
  provider: string;
  warnings: string[];
}

export interface MapProviderStatus { configured: boolean; provider: string; message: string; }
export interface LivePlace { place_id?: string; name: string; address?: string; rating?: number; maps_url?: string; photo_resource?: string; attributions: string[]; }
export interface LiveNearbyResponse { property_id: number; category: string; radius_km: number; source: string; places: LivePlace[]; }
