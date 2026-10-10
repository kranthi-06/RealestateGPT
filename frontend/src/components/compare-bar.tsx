"use client";

/**
 * Sticky comparison bar.
 *
 * Properties are added to the comparison from anywhere — search results, saved
 * properties, AI recommendations — so the bar lives in the layout and reads
 * from the shared compare store rather than from page-local state.
 */

import { useRouter } from "next/navigation";
import { GitCompare, X, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { MAX_COMPARE, useCompare } from "@/lib/compare-context";
import { notifyCompareFull } from "@/lib/notify";

export function CompareBar() {
  const { ids, remove, clear } = useCompare();
  const router = useRouter();

  if (ids.length === 0) return null;

  const goCompare = () => {
    if (ids.length < 2) {
      notifyCompareFull(MAX_COMPARE);
      return;
    }
    router.push(`/compare?ids=${ids.join(",")}`);
  };

  return (
    <div
      className="sticky bottom-4 z-30 mx-auto w-[calc(100%-1.5rem)] max-w-3xl"
      role="region"
      aria-label="Comparison selection"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/70 bg-card/95 p-3 shadow-lg backdrop-blur-md">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <GitCompare className="size-4" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">
              <span className="tabular-nums">{ids.length}</span>{" "}
              {ids.length === 1 ? "property" : "properties"} selected
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {ids.length < 2
                ? "Add at least one more to compare"
                : `Compare up to ${MAX_COMPARE} side by side`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="h-9 gap-1.5" onClick={clear}>
            <X className="size-3.5" />
            Clear
          </Button>
          <Button size="sm" className="h-9 gap-1.5" onClick={goCompare} disabled={ids.length < 2}>
            Compare
            <ArrowRight className="size-3.5" />
          </Button>
        </div>
      </div>

      {/* Selected chips: visible, individually removable, keyboard reachable. */}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {ids.map((id) => (
          <Badge key={id} variant="secondary" className="gap-1 pr-1">
            <span className="tabular-nums">#{id}</span>
            <button
              type="button"
              onClick={() => remove(id)}
              className="ml-0.5 rounded-full p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
              aria-label={`Remove property ${id} from comparison`}
            >
              <X className="size-3" />
            </button>
          </Badge>
        ))}
        {ids.length >= MAX_COMPARE && (
          <span className="self-center text-xs text-muted-foreground">
            Limit reached — remove one to add another
          </span>
        )}
      </div>
    </div>
  );
}

export default CompareBar;
