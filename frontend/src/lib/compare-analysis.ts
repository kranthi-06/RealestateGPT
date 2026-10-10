/**
 * Property comparison analysis.
 *
 * Everything here is derived from the actual property records that the API
 * returned. Nothing is estimated: a missing field is reported as missing, and
 * the "which is better" verdicts are simple, explainable comparisons over the
 * values that exist.
 */

import type { Property } from "@/lib/types";

export type Better = "lower" | "higher" | "none";

export interface CompareRow {
  key: string;
  label: string;
  /** Raw comparable value per property id; null means "not available". */
  values: Record<number, number | null>;
  better: Better;
  unit?: "price" | "area" | "sqft" | "count" | "rating";
  hint?: string;
}

export interface PropertyInsight {
  propertyId: number;
  title: string;
  advantages: string[];
  disadvantages: string[];
}

export interface ComparisonSummary {
  rows: CompareRow[];
  insights: PropertyInsight[];
  highlights: string[];
  /** Properties that could not be fully compared (missing price or area). */
  incomplete: number[];
}

function value(property: Property, key: keyof Property): number | null {
  const raw = property[key];
  return typeof raw === "number" && Number.isFinite(raw) && raw > 0 ? raw : null;
}

function pricePerSqft(property: Property): number | null {
  const direct = value(property, "price_per_sqft");
  if (direct != null) return direct;
  // Derive from the asking price and a real area measurement only. Never infer
  // an area to manufacture a figure.
  const area = value(property, "area_sqft");
  const price = value(property, "price");
  if (area != null && price != null) return price / area;
  return null;
}

function amenityNames(property: Property): string[] {
  return (property.amenities ?? []).map((a) => a.name).filter(Boolean);
}

/** Rows the comparison table renders, with the direction "better" points. */
export function buildRows(properties: Property[]): CompareRow[] {
  const byId = (fn: (p: Property) => number | null) =>
    Object.fromEntries(properties.map((p) => [p.id, fn(p)])) as Record<number, number | null>;

  return [
    {
      key: "price",
      label: "Asking price",
      values: byId((p) => value(p, "price")),
      better: "lower",
      unit: "price",
      hint: "What the seller is asking. Not a completed transaction price.",
    },
    {
      key: "price_per_sqft",
      label: "Price per sq ft",
      values: byId((p) => pricePerSqft(p)),
      better: "lower",
      unit: "sqft",
      hint: "Asking price divided by the listed carpet/super area.",
    },
    {
      key: "area_sqft",
      label: "Area",
      values: byId((p) => value(p, "area_sqft")),
      better: "higher",
      unit: "area",
    },
    {
      key: "bedrooms",
      label: "Bedrooms",
      values: byId((p) => value(p, "bedrooms")),
      better: "higher",
      unit: "count",
    },
    {
      key: "bathrooms",
      label: "Bathrooms",
      values: byId((p) => value(p, "bathrooms")),
      better: "higher",
      unit: "count",
    },
    {
      key: "parking",
      label: "Parking",
      values: byId((p) => value(p, "parking")),
      better: "higher",
      unit: "count",
    },
    {
      key: "property_age",
      label: "Property age",
      values: byId((p) => value(p, "property_age")),
      better: "lower",
      unit: "count",
      hint: "Years since construction, as stated in the listing.",
    },
    {
      key: "floor",
      label: "Floor",
      values: byId((p) => value(p, "floor")),
      better: "higher",
      unit: "count",
    },
    {
      key: "total_floors",
      label: "Total floors",
      values: byId((p) => value(p, "total_floors")),
      better: "higher",
      unit: "count",
    },
  ];
}

/**
 * Best and worst index for a row, or -1 when the row cannot be ranked
 * (no better direction, fewer than two comparable values, or a tie).
 */
export function rankRow(
  row: CompareRow,
  propertyIds: number[]
): { best: number; worst: number } {
  if (row.better === "none") return { best: -1, worst: -1 };
  const entries = propertyIds
    .map((id, index) => ({ index, value: row.values[id] }))
    .filter((entry): entry is { index: number; value: number } => entry.value != null);
  if (entries.length < 2) return { best: -1, worst: -1 };

  const values = entries.map((e) => e.value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  if (max === min) return { best: -1, worst: -1 };

  if (row.better === "lower") {
    const bestIndex = entries.find((e) => e.value === min)!.index;
    const worstIndex = entries.find((e) => e.value === max)!.index;
    return { best: bestIndex, worst: worstIndex };
  }
  const bestIndex = entries.find((e) => e.value === max)!.index;
  const worstIndex = entries.find((e) => e.value === min)!.index;
  return { best: bestIndex, worst: worstIndex };
}

/** Per-property advantages and disadvantages, strictly from the data. */
export function buildInsights(properties: Property[]): PropertyInsight[] {
  if (properties.length < 2) return [];
  const rows = buildRows(properties);
  const ids = properties.map((p) => p.id);
  const amenitySets = new Map(properties.map((p) => [p.id, new Set(amenityNames(p))]));
  const allAmenities = new Set<string>();
  amenitySets.forEach((set) => set.forEach((name) => allAmenities.add(name)));

  return properties.map((property) => {
    const advantages: string[] = [];
    const disadvantages: string[] = [];
    const title = property.title;

    for (const row of rows) {
      const mine = row.values[property.id];
      if (mine == null) {
        // Absence is never spun as an advantage or a disadvantage beyond
        // stating the data is unavailable.
        continue;
      }
      const { best, worst } = rankRow(row, ids);
      const index = ids.indexOf(property.id);
      if (index === best && row.better !== "none") {
        const other = ids
          .filter((id) => id !== property.id)
          .map((id) => row.values[id])
          .filter((v): v is number => v != null);
        const delta =
          row.better === "lower" ? Math.max(...other) - mine : mine - Math.min(...other);
        advantages.push(`Best ${row.label.toLowerCase()} of the group${delta > 0 ? ` (by ${formatDelta(delta, row)})` : ""}.`);
      }
      if (index === worst && row.better !== "none") {
        disadvantages.push(`Highest ${row.label.toLowerCase()} of the group.`);
      }
    }

    // Amenity coverage: count of shared amenities this listing has.
    const sharedCount = [...allAmenities].filter((name) => amenitySets.get(property.id)!.has(name)).length;
    const otherShared = properties
      .filter((p) => p.id !== property.id)
      .map((p) => [...allAmenities].filter((name) => amenitySets.get(p.id)!.has(name)).length);
    const maxShared = Math.max(...otherShared, 0);
    if (sharedCount > maxShared) {
      advantages.push(`Most listed amenities (${sharedCount}).`);
    } else if (sharedCount < maxShared) {
      disadvantages.push(`Fewer listed amenities (${sharedCount} vs ${maxShared}).`);
    }

    // Verification is a trust signal, not a quality claim.
    if (property.verification_status === "verified") {
      advantages.push("Listing is marked verified.");
    } else if (property.verification_status === "unverified") {
      disadvantages.push("Listing is not verified — confirm details with the seller.");
    }
    if (property.is_synthetic) {
      disadvantages.push("Demonstration record, not a live market listing.");
    }

    return { propertyId: property.id, title, advantages, disadvantages };
  });
}

function formatDelta(delta: number, row: CompareRow): string {
  if (row.unit === "price") return `₹${Math.round(delta).toLocaleString("en-IN")}`;
  return `${Number(delta.toFixed(2))}`;
}

/** Plain-language summary of what the comparison shows. */
export function buildHighlights(properties: Property[]): string[] {
  if (properties.length < 2) return [];
  const rows = buildRows(properties);
  const ids = properties.map((p) => p.id);
  const highlights: string[] = [];
  const nameOf = (id: number) => properties.find((p) => p.id === id)?.title ?? `#${id}`;

  for (const row of rows) {
    if (row.better === "none") continue;
    const { best } = rankRow(row, ids);
    if (best === -1) continue;
    const winner = properties[best];
    highlights.push(`${row.label}: ${nameOf(winner.id)} is the strongest on this measure.`);
  }
  return highlights;
}

export function summarize(properties: Property[]): ComparisonSummary {
  const incomplete = properties
    .filter((p) => value(p, "price") == null)
    .map((p) => p.id);
  return {
    rows: buildRows(properties),
    insights: buildInsights(properties),
    highlights: buildHighlights(properties),
    incomplete,
  };
}
