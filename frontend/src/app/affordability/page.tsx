import { Suspense } from "react";
import AffordabilityRedirectClient from "./redirect-client";

export default function AffordabilityRedirect() {
  return (
    <Suspense fallback={null}>
      <AffordabilityRedirectClient />
    </Suspense>
  );
}