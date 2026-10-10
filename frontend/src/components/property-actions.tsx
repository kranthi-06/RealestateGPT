"use client";

/**
 * Save / Compare actions for a property.
 *
 * Every property surface (search results, saved list, AI recommendations,
 * compare columns) uses this component so the behaviour, the loading state and
 * the error reporting are identical everywhere.
 */

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { Heart, GitCompare, Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { MAX_COMPARE, useCompare } from "@/lib/compare-context";
import { useSaved } from "@/lib/saved-context";
import {
  notifyCompareFull,
  notifyCompareRemoved,
  notifySaved,
  notifySaveFailed,
  notifyUnsaved,
} from "@/lib/notify";
import { cn } from "@/lib/utils";

interface PropertyActionsProps {
  propertyId: number;
  title?: string;
  /** "icon" is the overlay heart on image cards; "buttons" is the inline pair. */
  variant?: "icon" | "buttons" | "compact";
  className?: string;
}

export function PropertyActions({
  propertyId,
  title,
  variant = "icon",
  className,
}: PropertyActionsProps) {
  const { isAuthenticated } = useAuth();
  const { isSaved, toggleSaved } = useSaved();
  const compare = useCompare();
  const router = useRouter();
  const [pending, setPending] = useState<"save" | "compare" | null>(null);

  const saved = isSaved(propertyId);
  const comparing = compare.has(propertyId);

  const onSave = useCallback(
    async (event: React.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (!isAuthenticated || pending) {
        if (!isAuthenticated) router.push("/auth/login");
        return;
      }
      setPending("save");
      try {
        const outcome = await toggleSaved(propertyId);
        if (outcome === "failed") notifySaveFailed();
        else if (outcome === "saved") notifySaved(title);
        else notifyUnsaved(title);
      } finally {
        setPending(null);
      }
    },
    [isAuthenticated, pending, router, title, toggleSaved, propertyId]
  );

  const onCompare = useCallback(
    (event: React.MouseEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (comparing) {
        compare.remove(propertyId);
        notifyCompareRemoved();
        return;
      }
      if (compare.isFull) {
        notifyCompareFull(MAX_COMPARE);
        return;
      }
      compare.add(propertyId);
    },
    [compare, comparing, propertyId]
  );

  if (!isAuthenticated) {
    return (
      <Button
        variant="outline"
        size="sm"
        className={cn("h-8 gap-1.5", className)}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          router.push("/auth/login");
        }}
      >
        <Heart className="size-3.5" />
        Sign in to save
      </Button>
    );
  }

  if (variant === "icon") {
    return (
      <div className={cn("flex items-center gap-1.5", className)}>
        <button
          type="button"
          onClick={onSave}
          disabled={pending === "save"}
          aria-label={saved ? `Unsave ${title ?? "property"}` : `Save ${title ?? "property"}`}
          aria-pressed={saved}
          className="flex size-8 items-center justify-center rounded-full bg-white/90 shadow-sm backdrop-blur-sm transition-transform hover:scale-110 disabled:opacity-60 dark:bg-black/50"
        >
          {pending === "save" ? (
            <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
          ) : (
            <Heart
              className={cn(
                "size-3.5 transition-colors",
                saved ? "fill-red-500 text-red-500" : "text-muted-foreground"
              )}
            />
          )}
        </button>
        <button
          type="button"
          onClick={onCompare}
          aria-label={comparing ? "Remove from comparison" : "Add to comparison"}
          aria-pressed={comparing}
          className={cn(
            "flex size-8 items-center justify-center rounded-full bg-white/90 shadow-sm backdrop-blur-sm transition-transform hover:scale-110 dark:bg-black/50",
            comparing && "bg-primary text-primary-foreground"
          )}
        >
          {comparing ? <Check className="size-3.5" /> : <GitCompare className="size-3.5" />}
        </button>
      </div>
    );
  }

  if (variant === "compact") {
    return (
      <div className={cn("flex items-center gap-1", className)}>
        <Button
          variant="ghost"
          size="icon"
          className="size-8"
          onClick={onSave}
          disabled={pending === "save"}
          aria-label={saved ? "Unsave property" : "Save property"}
        >
          {pending === "save" ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Heart className={cn("size-4", saved && "fill-red-500 text-red-500")} />
          )}
        </Button>
        <Button
          variant={comparing ? "default" : "outline"}
          size="icon"
          className="size-8"
          onClick={onCompare}
          aria-label={comparing ? "Remove from comparison" : "Add to comparison"}
          aria-pressed={comparing}
        >
          {comparing ? <Check className="size-3.5" /> : <GitCompare className="size-3.5" />}
        </Button>
      </div>
    );
  }

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Button
        variant={saved ? "default" : "outline"}
        size="sm"
        className="h-8 gap-1.5"
        onClick={onSave}
        disabled={pending === "save"}
        aria-pressed={saved}
      >
        {pending === "save" ? (
          <Loader2 className="size-3.5 animate-spin" />
        ) : (
          <Heart className={cn("size-3.5", saved && "fill-current")} />
        )}
        {saved ? "Saved" : "Save"}
      </Button>
      <Button
        variant={comparing ? "default" : "outline"}
        size="sm"
        className="h-8 gap-1.5"
        onClick={onCompare}
        aria-pressed={comparing}
      >
        {comparing ? <Check className="size-3.5" /> : <GitCompare className="size-3.5" />}
        {comparing ? "Comparing" : "Compare"}
      </Button>
    </div>
  );
}

export default PropertyActions;
