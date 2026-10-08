import { Suspense } from "react";
import MarketIntelligenceRedirectClient from "./redirect-client";

export default function MarketIntelligencePage() {
  return (
    <Suspense fallback={null}>
      <MarketIntelligenceRedirectClient />
    </Suspense>
  );
}