import { Suspense } from "react";
import ExploreClient from "./explore-client";

export default function ExplorePage() {
  return (
    <Suspense fallback={<div className="min-h-[500px] flex items-center justify-center">Loading map…</div>}>
      <ExploreClient />
    </Suspense>
  );
}