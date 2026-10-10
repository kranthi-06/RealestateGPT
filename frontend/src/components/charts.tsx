"use client";

/**
 * Dependency-free SVG charts.
 *
 * The market-intelligence view previously rendered its trend as a text list and
 * its locality comparison as a static table, so there was no way to see the
 * shape of the data. These charts draw the same numbers the API returned —
 * never a smoothed or invented series.
 */

import { useId } from "react";
import { cn } from "@/lib/utils";

interface SeriesPoint {
  label: string;
  value: number | null;
  hint?: string;
}

/* ── Bar chart ────────────────────────────────────────────────────────── */

export function BarChart({
  data,
  valueFormat,
  height = 220,
  ariaLabel,
  emptyMessage = "No data to chart.",
}: {
  data: SeriesPoint[];
  valueFormat?: (value: number) => string;
  height?: number;
  ariaLabel: string;
  emptyMessage?: string;
}) {
  const gradientId = useId();
  const points = data.filter((d) => d.value != null);
  if (points.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">{emptyMessage}</p>;
  }

  const values = points.map((p) => p.value as number);
  const max = Math.max(...values, 0);

  return (
    <div className="w-full">
      <div
        className="flex items-end gap-1.5"
        style={{ height }}
        role="img"
        aria-label={ariaLabel}
      >
        {points.map((point, index) => {
          const value = point.value as number;
          const ratio = max > 0 ? value / max : 0;
          return (
            <div
              key={`${point.label}-${index}`}
              className="group flex h-full min-w-0 flex-1 flex-col justify-end"
              title={point.hint ?? `${point.label}: ${valueFormat ? valueFormat(value) : value}`}
            >
              <span className="mb-1 truncate text-[10px] font-medium tabular-nums text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
                {valueFormat ? valueFormat(value) : value}
              </span>
              <div
                className="w-full rounded-t-md bg-primary/70 transition-all group-hover:bg-primary"
                style={{ height: `${Math.max(ratio * 100, 2)}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex gap-1.5">
        {points.map((point, index) => (
          <span
            key={`${point.label}-${index}`}
            className="min-w-0 flex-1 truncate text-center text-[10px] text-muted-foreground"
          >
            {point.label}
          </span>
        ))}
      </div>
      <svg width="0" height="0" aria-hidden="true">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.9" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0.4" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  );
}

/* ── Line chart ───────────────────────────────────────────────────────── */

export function LineChart({
  data,
  valueFormat,
  height = 220,
  ariaLabel,
  emptyMessage = "No data to chart.",
}: {
  data: SeriesPoint[];
  valueFormat?: (value: number) => string;
  height?: number;
  ariaLabel: string;
  emptyMessage?: string;
}) {
  const points = data.filter((d) => d.value != null);
  if (points.length < 2) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        {points.length === 0 ? emptyMessage : "Only one observation — a trend needs at least two."}
      </p>
    );
  }

  const values = points.map((p) => p.value as number);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 100;
  const stepX = width / (points.length - 1);
  const toY = (value: number) => 100 - ((value - min) / span) * 100;

  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${index * stepX} ${toY(point.value as number)}`)
    .join(" ");
  const areaPath = `${path} L ${width} 100 L 0 100 Z`;

  return (
    <div className="w-full">
      <div className="relative" style={{ height }} role="img" aria-label={ariaLabel}>
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="h-full w-full overflow-visible"
        >
          <path d={areaPath} fill="currentColor" className="text-primary/10" />
          <path
            d={path}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            vectorEffect="non-scaling-stroke"
            className="text-primary"
          />
          {points.map((point, index) => (
            <circle
              key={`${point.label}-${index}`}
              cx={index * stepX}
              cy={toY(point.value as number)}
              r={2.5}
              className="fill-primary"
              vectorEffect="non-scaling-stroke"
            >
              <title>
                {point.hint ?? `${point.label}: ${valueFormat ? valueFormat(point.value as number) : point.value}`}
              </title>
            </circle>
          ))}
        </svg>
        {/* First / last labels so the range is visible without hovering. */}
        <div className="pointer-events-none absolute inset-x-0 -bottom-1 flex justify-between text-[10px] text-muted-foreground">
          <span>{points[0].label}</span>
          <span>{points[points.length - 1].label}</span>
        </div>
      </div>
    </div>
  );
}

/* ── Horizontal comparison bars ───────────────────────────────────────── */

export function ComparisonBars({
  data,
  valueFormat,
  ariaLabel,
  emptyMessage = "No data to chart.",
  bestIsHighest = true,
}: {
  data: SeriesPoint[];
  valueFormat?: (value: number) => string;
  ariaLabel: string;
  emptyMessage?: string;
  bestIsHighest?: boolean;
}) {
  const points = data.filter((d) => d.value != null);
  if (points.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">{emptyMessage}</p>;
  }
  const values = points.map((p) => p.value as number);
  const max = Math.max(...values, 0);
  const target = bestIsHighest ? Math.max(...values) : Math.min(...values);

  return (
    <ul className="space-y-2" role="img" aria-label={ariaLabel}>
      {points.map((point, index) => {
        const value = point.value as number;
        const ratio = max > 0 ? value / max : 0;
        const isBest = value === target;
        return (
          <li key={`${point.label}-${index}`} className="group">
            <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
              <span className="truncate font-medium">{point.label}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {valueFormat ? valueFormat(value) : value}
                {isBest && (
                  <span className="ml-1.5 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
                    {bestIsHighest ? "Highest" : "Lowest"}
                  </span>
                )}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={cn("h-full rounded-full", isBest ? "bg-emerald-500" : "bg-primary/60")}
                style={{ width: `${Math.max(ratio * 100, 2)}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
