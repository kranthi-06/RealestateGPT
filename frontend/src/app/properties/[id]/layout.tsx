import { Metadata } from 'next';
import { resolveApiBase } from '@/lib/api-base';

type Props = {
  params: Promise<{ id: string }>;
};

/**
 * Server-side API base. Uses ``NEXT_PUBLIC_API_URL`` when configured and the
 * deployment's own origin otherwise — never an implicit localhost dependency
 * in a production build.
 */
function apiBase(): string {
  const configured = (process.env.NEXT_PUBLIC_API_URL || '').trim().replace(/\/+$/, '');
  if (configured) return configured;
  const site = (process.env.NEXT_PUBLIC_SITE_URL || '').trim().replace(/\/+$/, '');
  if (site) return `${site}/api/backend`;
  return resolveApiBase();
}

export async function generateMetadata(
  { params }: Props
): Promise<Metadata> {
  try {
    const resolvedParams = await params;
    const id = resolvedParams.id;

    const base = apiBase();
    // Relative bases only make sense in the browser; a server render cannot
    // resolve them, so metadata falls back to the static page metadata.
    if (!/^https?:\/\//i.test(base)) return {};

    const res = await fetch(`${base}/api/v1/properties/${id}`, {
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(5000),
    });

    if (!res.ok) return {};
    
    const property = await res.json();
    
    if (!property || !property.title) return {};
    
    const imageUrl = property.images?.[0]?.url || (property.image_urls ? property.image_urls.split(',')[0] : null);
    
    return {
      title: property.title,
      description: property.description || `${property.bedrooms || ''}BHK ${property.property_type} in ${property.locality || ''}, ${property.city}`,
      openGraph: {
        title: property.title,
        description: property.description || `${property.bedrooms || ''}BHK ${property.property_type} in ${property.locality || ''}, ${property.city}`,
        images: imageUrl ? [imageUrl] : [],
        type: 'website',
      },
      twitter: {
        card: 'summary_large_image',
        title: property.title,
        description: property.description || `${property.bedrooms || ''}BHK ${property.property_type} in ${property.locality || ''}, ${property.city}`,
        images: imageUrl ? [imageUrl] : [],
      }
    };
  } catch {
    return {};
  }
}

export default function PropertyLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
