"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ChevronDown,
  ChevronRight,
  IndianRupee,
  BedDouble,
  Building2,
  Maximize2,
  CalendarClock,
  Navigation,
  Sparkles,
  RotateCcw,
} from "lucide-react";
import type { SearchFilters } from "@/lib/types";
import { useState } from "react";
import { cn } from "@/lib/utils";

export const PROPERTY_TYPES = [
  "apartment",
  "house",
  "villa",
  "plot",
  "pg",
  "commercial",
  "studio",
  "penthouse",
];

export const BHK_OPTIONS = [1, 2, 3, 4, 5];
export const AMENITIES_OPTIONS = [
  "parking",
  "lift",
  "gym",
  "swimming_pool",
  "garden",
  "security",
  "power_backup",
  "water_supply",
  "club_house",
];
export const AVAILABILITY_OPTIONS = ["ready_to_move", "under_construction", "resale", "new_launch"];

interface FilterSidebarProps {
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
  onReset?: () => void;
  className?: string;
  compact?: boolean;
}

interface SectionProps {
  title: string;
  Icon: React.ComponentType<{ className?: string }>;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function Section({ title, Icon, defaultOpen = true, children }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-border last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 py-3 text-left text-xs font-semibold uppercase tracking-wide text-foreground hover:text-primary"
      >
        <span className="flex items-center gap-1.5">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
          {title}
        </span>
        {open ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground" />
        )}
      </button>
      {open && <div className="pb-4 pt-1">{children}</div>}
    </div>
  );
}

function ChipsRow<T extends string | number>({
  options,
  selected,
  onToggle,
  renderLabel,
}: {
  options: readonly T[];
  selected: Set<T>;
  onToggle: (v: T) => void;
  renderLabel?: (v: T) => string;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((v) => {
        const active = selected.has(v);
        return (
          <button
            key={String(v)}
            type="button"
            onClick={() => onToggle(v)}
            className={cn(
              "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all",
              active
                ? "border-primary bg-primary/10 text-primary"
                : "border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-foreground"
            )}
          >
            {renderLabel ? renderLabel(v) : String(v)}
          </button>
        );
      })}
    </div>
  );
}

export function FilterSidebar({ filters, onChange, onReset, className, compact = false }: FilterSidebarProps) {
  const selectedBhk = new Set<number>();
  if (filters.min_bedrooms != null) {
    for (let i = filters.min_bedrooms; i <= (filters.max_bedrooms ?? 5); i++) selectedBhk.add(i);
  }
  const selectedTypes = new Set<string>();
  if (filters.property_type) selectedTypes.add(filters.property_type);
  const selectedAmenities = new Set<string>(filters.amenities ?? []);
  const selectedAvailability = new Set<string>();
  if (filters.construction_status) selectedAvailability.add(filters.construction_status);

  const toggleBhk = (bhk: number) => {
    const next = new Set(selectedBhk);
    if (next.has(bhk)) next.delete(bhk);
    else next.add(bhk);
    if (next.size === 0) {
      const rest = { ...filters };
      delete rest.min_bedrooms;
      delete rest.max_bedrooms;
      onChange(rest);
      return;
    }
    const arr = [...next].sort((a, b) => a - b);
    onChange({
      ...filters,
      min_bedrooms: arr[0],
      max_bedrooms: arr[arr.length - 1],
    });
  };

  const toggleType = (t: string) => {
    const next = new Set(selectedTypes);
    if (next.has(t)) next.delete(t);
    else {
      next.clear();
      next.add(t);
    }
    onChange({
      ...filters,
      property_type: next.size === 1 ? [...next][0] : undefined,
    });
  };

  const toggleAmenity = (a: string) => {
    const next = new Set(selectedAmenities);
    if (next.has(a)) next.delete(a);
    else next.add(a);
    onChange({ ...filters, amenities: [...next] });
  };

  const toggleAvailability = (a: string) => {
    const next = new Set(selectedAvailability);
    if (next.has(a)) next.delete(a);
    else {
      next.clear();
      next.add(a);
    }
    onChange({
      ...filters,
      construction_status: next.size === 1 ? [...next][0] : undefined,
    });
  };

  const priceMin = filters.min_price ?? 0;
  const priceMax = filters.max_price ?? 50000000;
  const areaMin = filters.min_area ?? 0;
  const areaMax = filters.max_area ?? 5000;
  const radius = filters.radius_km ?? 5;

  const activeCount = [
    filters.min_price,
    filters.max_price,
    filters.min_bedrooms,
    filters.property_type,
    filters.min_area,
    filters.max_area,
    filters.construction_status,
    filters.radius_km,
    (filters.amenities ?? []).length > 0,
  ].filter(Boolean).length;

  return (
    <Card className={cn("h-fit w-full", className)}>
      <CardContent className={cn(compact ? "p-4" : "p-5")}>
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            <Sparkles className="h-4 w-4 text-primary" />
            Filters
            {activeCount > 0 && (
              <Badge variant="default" className="px-1.5 py-0 text-[10px]">
                {activeCount}
              </Badge>
            )}
          </div>
          {onReset && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onReset}
              className="h-7 gap-1 px-2 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <RotateCcw className="h-3 w-3" />
              Reset
            </Button>
          )}
        </div>

        <ScrollArea className="h-[calc(100vh-220px)] pr-2">
          <div>
            <Section title="Price" Icon={IndianRupee}>
              <div className="grid grid-cols-2 gap-2 pb-3">
                <Input
                  type="number"
                  inputMode="numeric"
                  placeholder="Min"
                  className="h-8 text-xs tabular-nums"
                  value={priceMin || ""}
                  onChange={(e) =>
                    onChange({
                      ...filters,
                      min_price: e.target.value === "" ? undefined : Number(e.target.value),
                    })
                  }
                />
                <Input
                  type="number"
                  inputMode="numeric"
                  placeholder="Max"
                  className="h-8 text-xs tabular-nums"
                  value={priceMax || ""}
                  onChange={(e) =>
                    onChange({
                      ...filters,
                      max_price: e.target.value === "" ? undefined : Number(e.target.value),
                    })
                  }
                />
              </div>
              <Slider
                min={0}
                max={50000000}
                step={100000}
                value={[priceMin, priceMax]}
                onValueChange={(val) => {
                  if (Array.isArray(val)) {
                    const [min, max] = val;
                    onChange({ ...filters, min_price: min, max_price: max });
                  }
                }}
              />
              <p className="mt-1.5 text-[10px] text-muted-foreground tabular-nums">
                ₹{(priceMin / 100000).toFixed(1)}L – ₹{(priceMax / 10000000).toFixed(2)}Cr
              </p>
            </Section>

            <Section title="BHK" Icon={BedDouble}>
              <ChipsRow
                options={BHK_OPTIONS}
                selected={selectedBhk}
                onToggle={toggleBhk}
                renderLabel={(v) => `${v} BHK`}
              />
            </Section>

            <Section title="Property Type" Icon={Building2}>
              <ChipsRow
                options={PROPERTY_TYPES}
                selected={selectedTypes}
                onToggle={toggleType}
                renderLabel={(v) => v.charAt(0).toUpperCase() + v.slice(1).replace(/_/g, " ")}
              />
            </Section>

            <Section title="Area (sq.ft)" Icon={Maximize2}>
              <div className="grid grid-cols-2 gap-2 pb-3">
                <Input
                  type="number"
                  inputMode="numeric"
                  placeholder="Min"
                  className="h-8 text-xs tabular-nums"
                  value={areaMin || ""}
                  onChange={(e) =>
                    onChange({
                      ...filters,
                      min_area: e.target.value === "" ? undefined : Number(e.target.value),
                    })
                  }
                />
                <Input
                  type="number"
                  inputMode="numeric"
                  placeholder="Max"
                  className="h-8 text-xs tabular-nums"
                  value={areaMax || ""}
                  onChange={(e) =>
                    onChange({
                      ...filters,
                      max_area: e.target.value === "" ? undefined : Number(e.target.value),
                    })
                  }
                />
              </div>
              <Slider
                min={0}
                max={5000}
                step={50}
                value={[areaMin, areaMax]}
                onValueChange={(val) => {
                  const [min, max] = Array.isArray(val) ? val : [val, val];
                  onChange({ ...filters, min_area: min, max_area: max });
                }}
              />
            </Section>

            <Section title="Availability" Icon={CalendarClock}>
              <ChipsRow
                options={AVAILABILITY_OPTIONS as unknown as readonly string[]}
                selected={selectedAvailability}
                onToggle={toggleAvailability}
                renderLabel={(v) =>
                  String(v)
                    .split("_")
                    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                    .join(" ")
                }
              />
            </Section>

            <Section title="Distance (radius)" Icon={Navigation}>
              <Slider
                min={1}
                max={25}
                step={1}
                value={[radius]}
                onValueChange={(val) => {
                  const [r] = Array.isArray(val) ? val : [val];
                  onChange({ ...filters, radius_km: r });
                }}
              />
              <p className="mt-1.5 text-[10px] text-muted-foreground tabular-nums">
                Within {radius} km
              </p>
            </Section>

            <Section title="Amenities" Icon={Sparkles} defaultOpen={false}>
              <ChipsRow
                options={AMENITIES_OPTIONS}
                selected={selectedAmenities}
                onToggle={toggleAmenity}
                renderLabel={(v) =>
                  String(v)
                    .split("_")
                    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
                    .join(" ")
                }
              />
            </Section>
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

export function FilterSidebarSkeleton({ className }: { className?: string }) {
  return (
    <Card className={className}>
      <CardContent className="space-y-4 p-5">
        <Skeleton className="h-4 w-20" />
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-6 w-full" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default FilterSidebar;
