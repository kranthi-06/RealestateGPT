"use client";

import { Brain } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface AiScoreBadgeProps {
  score: number;
  size?: "sm" | "md";
  className?: string;
  showLabel?: boolean;
}

function getVariant(score: number): "success" | "default" | "warning" | "destructive" {
  if (score >= 80) return "success";
  if (score >= 60) return "default";
  if (score >= 40) return "warning";
  return "destructive";
}

export function AiScoreBadge({ score, size = "sm", className, showLabel = true }: AiScoreBadgeProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const variant = getVariant(clamped);
  const iconSize = size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5";
  const pad = size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs";

  return (
    <Badge variant={variant} className={cn("gap-1 font-semibold", pad, className)}>
      <Brain className={iconSize} />
      {showLabel && <span>AI</span>}
      <span className="tabular-nums">{clamped}</span>
    </Badge>
  );
}

export default AiScoreBadge;
