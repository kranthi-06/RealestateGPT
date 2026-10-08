"use client";

import { cn } from "@/lib/utils";

type ScoreVariant = "primary" | "success" | "warning" | "danger" | "neutral";

interface ScoreCardProps {
  label: string;
  value: number;
  variant?: ScoreVariant;
  footnote?: string;
  className?: string;
  prefix?: string;
  hideBar?: boolean;
  showBar?: boolean;
  max?: number;
  icon?: React.ReactNode;
}

const variantStyles: Record<ScoreVariant, { bar: string; text: string }> = {
  primary: { bar: "bg-primary", text: "text-foreground" },
  success: { bar: "bg-green-600", text: "text-foreground" },
  warning: { bar: "bg-amber-500", text: "text-foreground" },
  danger: { bar: "bg-red-600", text: "text-foreground" },
  neutral: { bar: "bg-slate-500", text: "text-foreground" },
};

function getAutoVariant(value: number): ScoreVariant {
  if (value >= 80) return "success";
  if (value >= 60) return "primary";
  if (value >= 40) return "warning";
  return "danger";
}

export function ScoreCard({ label, value, variant, footnote, className, prefix, hideBar, showBar = true, max = 100, icon }: ScoreCardProps) {
  const clamped = Math.max(0, Math.min(max, Math.round(value)));
  const percentage = max > 0 ? Math.round((clamped / max) * 100) : 0;
  const v = variant ?? getAutoVariant(percentage);
  const styles = variantStyles[v];
  const shouldShowBar = showBar && !hideBar;

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card p-3.5 transition-shadow hover:shadow-sm",
        className
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        {icon && <span className="text-muted-foreground">{icon}</span>}
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        <span className={cn("text-base font-bold tabular-nums", styles.text)}>
          {prefix ?? clamped}
        </span>
      </div>
      {shouldShowBar && (
        <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={cn("h-full rounded-full transition-all duration-500", styles.bar)}
            style={{ width: `${percentage}%` }}
            role="progressbar"
            aria-valuenow={percentage}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
      )}
      {footnote && (
        <p className="mt-2 line-clamp-1 text-[11px] text-muted-foreground">{footnote}</p>
      )}
    </div>
  );
}

export default ScoreCard;
