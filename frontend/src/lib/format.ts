/* RealEstateGPT - Formatting utilities */

const CURRENCY_SYMBOLS: Record<string, string> = {
  INR: "₹",
  USD: "$",
  EUR: "€",
  GBP: "£",
  AED: "AED ",
};

const MIN_REALISTIC_PRICE: Record<string, number> = {
  INR: 1000,
  USD: 100,
  EUR: 100,
  GBP: 90,
  AED: 500,
};

export function getCurrencySymbol(currency?: string | null): string {
  if (!currency) return "";
  return CURRENCY_SYMBOLS[currency.toUpperCase()] ?? `${currency} `;
}

function isRealisticPrice(price: number, currency?: string | null): boolean {
  if (!Number.isFinite(price) || price <= 0) return false;
  if (!currency) return price >= 1000;
  const min = MIN_REALISTIC_PRICE[currency.toUpperCase()];
  return min === undefined ? price >= 100 : price >= min;
}

export function formatPrice(price: number | null | undefined, currency?: string | null): string {
  if (price == null) return "Price not available";
  if (!currency || !isRealisticPrice(price, currency)) return "Price not available";
  const sym = getCurrencySymbol(currency);
  const isINR = currency.toUpperCase() === "INR";

  if (isINR) {
    if (price >= 10000000) {
      const crore = price / 10000000;
      return `${sym}${crore % 1 === 0 ? crore.toFixed(0) : crore.toFixed(2)} Cr`;
    }
    if (price >= 100000) {
      const lakh = price / 100000;
      return `${sym}${lakh % 1 === 0 ? lakh.toFixed(0) : lakh.toFixed(1)} L`;
    }
    return `${sym}${price.toLocaleString("en-IN")}`;
  }

  if (price >= 1_000_000) {
    const m = price / 1_000_000;
    return `${sym}${m % 1 === 0 ? m.toFixed(0) : m.toFixed(2)}M`;
  }
  return `${sym}${price.toLocaleString("en-US")}`;
}

export function formatArea(sqft: number): string {
  return `${sqft.toLocaleString("en-IN")} sq.ft`;
}

export function formatPricePerSqft(price: number | null | undefined, currency?: string | null): string {
  if (price == null || !currency || price <= 0) return "";
  const sym = getCurrencySymbol(currency);
  const isINR = currency.toUpperCase() === "INR";
  return `${sym}${Math.round(price).toLocaleString(isINR ? "en-IN" : "en-US")}/sq.ft`;
}

export function capitalize(str: string): string {
  return str
    .split(/[_-]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function getPropertyTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    apartment: "Apartment",
    villa: "Villa",
    plot: "Plot",
    house: "House",
    penthouse: "Penthouse",
    studio: "Studio",
  };
  return labels[type] || capitalize(type);
}

export function getFurnishingLabel(furnishing: string): string {
  const labels: Record<string, string> = {
    furnished: "Furnished",
    "semi-furnished": "Semi-Furnished",
    unfurnished: "Unfurnished",
  };
  return labels[furnishing] || capitalize(furnishing);
}

export function getBedroomLabel(bedrooms: number | null | undefined): string {
  if (bedrooms === null || bedrooms === undefined) return "N/A";
  return `${bedrooms} BHK`;
}

export function timeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  if (days < 30) return `${Math.floor(days / 7)} weeks ago`;
  if (days < 365) return `${Math.floor(days / 30)} months ago`;
  return `${Math.floor(days / 365)} years ago`;
}
