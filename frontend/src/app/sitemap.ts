import type { MetadataRoute } from "next";

/**
 * Static public routes only. Property/discovery URLs are intentionally absent:
 * they are dynamic, expire, and must be discovered from real inventory rather
 * than a build-time list.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const base = (
    process.env.NEXT_PUBLIC_SITE_URL?.trim() || "https://realestate-gpt-inky.vercel.app"
  ).replace(/\/+$/, "");
  const now = new Date();

  return [
    { url: `${base}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${base}/search`, lastModified: now, changeFrequency: "daily", priority: 0.8 },
    { url: `${base}/near-me`, lastModified: now, changeFrequency: "weekly", priority: 0.6 },
    { url: `${base}/finance`, lastModified: now, changeFrequency: "monthly", priority: 0.5 },
  ];
}
