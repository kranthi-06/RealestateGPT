/* RealEstateGPT - Formatting utilities */

export function formatPrice(price: number): string {
  if (price >= 10000000) {
    const crore = price / 10000000;
    return `₹${crore % 1 === 0 ? crore.toFixed(0) : crore.toFixed(2)} Cr`;
  }
  if (price >= 100000) {
    const lakh = price / 100000;
    return `₹${lakh % 1 === 0 ? lakh.toFixed(0) : lakh.toFixed(1)} L`;
  }
  return `₹${price.toLocaleString("en-IN")}`;
}

export function formatArea(sqft: number): string {
  return `${sqft.toLocaleString("en-IN")} sq.ft`;
}

export function formatPricePerSqft(price: number): string {
  return `₹${Math.round(price).toLocaleString("en-IN")}/sq.ft`;
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
