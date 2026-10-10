import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { SavedProvider } from "@/lib/saved-context";
import { CompareProvider } from "@/lib/compare-context";
import { SearchProvider } from "@/lib/search-context";
import { Toaster } from "@/components/ui/toast";
import Navbar from "@/components/navbar";
import CompareBar from "@/components/compare-bar";

export const metadata: Metadata = {
  title: {
    default: "RealEstateGPT — AI-Powered Property Discovery",
    template: "%s | RealEstateGPT",
  },
  description:
    "Find your perfect property with AI-powered search, intelligent recommendations, and comprehensive analysis. Discover, compare, and decide with confidence.",
  applicationName: "RealEstateGPT",
  openGraph: {
    type: "website",
    siteName: "RealEstateGPT",
    title: "RealEstateGPT — AI-Powered Property Discovery",
    description:
      "Property search reimagined. Natural language search, verified inventory, location intelligence, and AI reasoning — all in one decision engine.",
  },
  twitter: {
    card: "summary_large_image",
    title: "RealEstateGPT — AI-Powered Property Discovery",
    description:
      "Property search reimagined. Natural language search, verified inventory, location intelligence, and AI reasoning.",
  },
  robots: {
    index: true,
    follow: true,
  },
  // Resolved from the deployment itself so canonical/OG URLs never point at a
  // placeholder or a developer machine.
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL?.trim() || "https://realestate-gpt-inky.vercel.app"
  ),
  alternates: {
    canonical: "/",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <AuthProvider>
          <SavedProvider>
            <CompareProvider>
              <SearchProvider>
                <Navbar />
                <main className="min-h-[calc(100vh-4rem)]">{children}</main>
                <div className="fixed inset-x-0 bottom-0 z-30 pointer-events-none [&>*]:pointer-events-auto">
                  <CompareBar />
                </div>
                <Toaster />
              </SearchProvider>
            </CompareProvider>
          </SavedProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
