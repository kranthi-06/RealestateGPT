"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function MarketIntelligenceRedirectClient() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    router.replace(`/area-intelligence?${params.toString()}`);
  }, [router, searchParams]);

  return null;
}