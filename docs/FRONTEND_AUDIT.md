# Frontend Audit Report

## Routes

| Route | Type | Auth | Description |
|-------|------|------|-------------|
| `/` | Client | No | Landing page with hero, story sections, featured properties |
| `/search` | Client | No | Unified search (verified + web discovery) |
| `/properties/[id]` | Client | Optional | Property detail with gallery, map, price intel, finance |
| `/discoveries/[id]` | Client | Optional | Web discovery detail (clearly labeled unverified) |
| `/auth/login` | Client | No | Login with JWT |
| `/auth/register` | Client | No | Registration |
| `/saved` | Client | Required | Saved properties list |
| `/compare` | Client | No | Property comparison table |
| `/assistant` | Client | Required | AI conversational search |
| `/admin` | Client | Admin | Worker management dashboard |

## Design System

- **Color system**: OKLCH-based tokens in globals.css
- **Typography**: Aptos/Segoe UI (sans), Iowan Old Style/Baskerville (display)
- **Components**: Shadcn UI primitives (Button, Card, Input, Dropdown, Skeleton, etc.)
- **Icons**: Lucide React
- **Maps**: Leaflet via react-leaflet (SSR-safe dynamic import)

## Accessibility

- Focus visibility: Global outline styles ✅
- Semantic HTML: Proper section/article/nav usage ✅
- Form labels: aria-label on inputs ✅
- Reduced motion: @media (prefers-reduced-motion) ✅
- Contrast: OKLCH palette maintains WCAG ratios ✅

## Performance

- Code splitting: Next.js App Router automatic ✅
- Leaflet lazy load: next/dynamic with ssr:false ✅
- Image optimization: next/image for property photos ✅
- GZip: Backend middleware ✅
