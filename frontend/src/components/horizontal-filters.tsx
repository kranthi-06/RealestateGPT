"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import {
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  SlidersHorizontal,
  ChevronDown,
  IndianRupee,
  BedDouble,
  Building2,
  Maximize2,
  KeyRound,
  Home,
  RotateCcw,
  Check,
} from "lucide-react";
import type { SearchFilters } from "@/lib/types";
import { cn } from "@/lib/utils";

const PROPERTY_TYPES = [
  "apartment",
  "house",
  "villa",
  "plot",
  "pg",
  "commercial",
  "studio",
  "penthouse",
];

const BHK_OPTIONS = [1, 2, 3, 4, 5];

const FURNISHING_OPTIONS = ["unfurnished", "semi_furnished", "fully_furnished"];

const LISTING_TYPES = [
  { value: "sale", label: "Buy", icon: Home },
  { value: "rent", label: "Rent", icon: KeyRound },
];

interface HorizontalFiltersProps {
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
  onReset?: () => void;
  className?: string;
}

function FilterDropdown({
  label,
  icon: Icon,
  children,
  activeCount = 0,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  activeCount?: number;
}) {
  // Popover, not Menu: these panels contain inputs, and Base UI Menu
  // popups own the keyboard (arrow keys + typeahead), which swallows character
  // keystrokes and makes text/number inputs inside them untypeable.
  return (
    <Popover>
      <PopoverTrigger>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            "h-9 gap-1.5 rounded-lg border-border/70 bg-card text-sm font-medium shadow-sm hover:bg-accent",
            activeCount > 0 && "border-primary/40 bg-primary/5 text-primary"
          )}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
          {activeCount > 0 && (
            <Badge
              variant="default"
              className="ml-0.5 h-4 rounded-full px-1 text-[10px] tabular-nums"
            >
              {activeCount}
            </Badge>
          )}
          <ChevronDown className="h-3 w-3 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64">
        {children}
      </PopoverContent>
    </Popover>
  );
}

function PriceFilter({
  filters,
  onChange,
}: {
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
}) {
  const [minPrice, setMinPrice] = useState(filters.min_price?.toString() ?? "");
  const [maxPrice, setMaxPrice] = useState(filters.max_price?.toString() ?? "");
  // Adjust draft state during render when the filter changes elsewhere
  // (e.g. Reset) — the React-recommended alternative to a sync effect.
  const [prevRange, setPrevRange] = useState([filters.min_price, filters.max_price]);
  if (filters.min_price !== prevRange[0] || filters.max_price !== prevRange[1]) {
    setPrevRange([filters.min_price, filters.max_price]);
    setMinPrice(filters.min_price?.toString() ?? "");
    setMaxPrice(filters.max_price?.toString() ?? "");
  }

  const applyPrice = () => {
    const min = minPrice ? Number(minPrice) : undefined;
    const max = maxPrice ? Number(maxPrice) : undefined;
    onChange({ ...filters, min_price: min, max_price: max });
  };

  const presets = [
    { label: "Under ₹25L", min: 0, max: 2500000 },
    { label: "₹25L – ₹50L", min: 2500000, max: 5000000 },
    { label: "₹50L – ₹1Cr", min: 5000000, max: 10000000 },
    { label: "₹1Cr – ₹2Cr", min: 10000000, max: 20000000 },
    { label: "₹2Cr+", min: 20000000, max: undefined },
  ];

  return (
    <>
      <DropdownMenuLabel className="flex items-center gap-1.5 text-xs">
        <IndianRupee className="h-3 w-3" />
        Price Range
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      <div className="space-y-3 p-3">
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="mb-1 block text-[11px] text-muted-foreground">Min (₹)</label>
            <Input
              type="text"
              inputMode="numeric"
              autoComplete="off"
              placeholder="0"
              className="h-8 text-xs tabular-nums"
              value={minPrice}
              onChange={(e) => setMinPrice(e.target.value.replace(/[^0-9]/g, ""))}
              onBlur={applyPrice}
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-muted-foreground">Max (₹)</label>
            <Input
              type="text"
              inputMode="numeric"
              autoComplete="off"
              placeholder="Any"
              className="h-8 text-xs tabular-nums"
              value={maxPrice}
              onChange={(e) => setMaxPrice(e.target.value.replace(/[^0-9]/g, ""))}
              onBlur={applyPrice}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-1">
          {presets.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => {
                setMinPrice(p.min ? p.min.toString() : "");
                setMaxPrice(p.max ? p.max.toString() : "");
                onChange({ ...filters, min_price: p.min || undefined, max_price: p.max });
              }}
              className="rounded-full border border-border bg-background px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
            >
              {p.label}
            </button>
          ))}
        </div>
        <Button size="sm" className="h-7 w-full text-xs" onClick={applyPrice}>
          Apply
        </Button>
      </div>
    </>
  );
}

function BHKFilter({
  filters,
  onChange,
}: {
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
}) {
  const selectedBhk = new Set<number>();
  if (filters.min_bedrooms != null) {
    for (let i = filters.min_bedrooms; i <= (filters.max_bedrooms ?? 5); i++) {
      selectedBhk.add(i);
    }
  }

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

  return (
    <>
      <DropdownMenuLabel className="flex items-center gap-1.5 text-xs">
        <BedDouble className="h-3 w-3" />
        Bedrooms (BHK)
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      <div className="flex flex-wrap gap-1.5 p-3">
        {BHK_OPTIONS.map((bhk) => {
          const active = selectedBhk.has(bhk);
          return (
            <button
              key={bhk}
              type="button"
              onClick={() => toggleBhk(bhk)}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-lg border text-xs font-medium transition-all",
                active
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-foreground"
              )}
            >
              {bhk}
            </button>
          );
        })}
      </div>
    </>
  );
}

function PropertyTypeFilter({
  filters,
  onChange,
}: {
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
}) {
  const selected = filters.property_type;

  return (
    <>
      <DropdownMenuLabel className="flex items-center gap-1.5 text-xs">
        <Building2 className="h-3 w-3" />
        Property Type
      </DropdownMenuLabel>
      <div className="max-h-64 overflow-y-auto p-1">
        {PROPERTY_TYPES.map((type) => (
          <button
            key={type}
            type="button"
            onClick={() =>
              onChange({
                ...filters,
                property_type: selected === type ? undefined : type,
              })
            }
            className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-sm capitalize transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            {type.replace(/_/g, " ")}
            {selected === type && <Check className="h-3.5 w-3.5 text-primary" />}
          </button>
        ))}
      </div>
    </>
  );
}

function AreaFilter({
  filters,
  onChange,
}: {
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
}) {
  const [minArea, setMinArea] = useState(filters.min_area?.toString() ?? "");
  const [maxArea, setMaxArea] = useState(filters.max_area?.toString() ?? "");
  // Adjust draft state during render when the filter changes elsewhere
  // (e.g. Reset) — the React-recommended alternative to a sync effect.
  const [prevArea, setPrevArea] = useState([filters.min_area, filters.max_area]);
  if (filters.min_area !== prevArea[0] || filters.max_area !== prevArea[1]) {
    setPrevArea([filters.min_area, filters.max_area]);
    setMinArea(filters.min_area?.toString() ?? "");
    setMaxArea(filters.max_area?.toString() ?? "");
  }

  const applyArea = () => {
    const min = minArea ? Number(minArea) : undefined;
    const max = maxArea ? Number(maxArea) : undefined;
    onChange({ ...filters, min_area: min, max_area: max });
  };

  return (
    <>
      <DropdownMenuLabel className="flex items-center gap-1.5 text-xs">
        <Maximize2 className="h-3 w-3" />
        Area (sq.ft)
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      <div className="space-y-3 p-3">
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="mb-1 block text-[11px] text-muted-foreground">Min</label>
            <Input
              type="text"
              inputMode="numeric"
              autoComplete="off"
              placeholder="0"
              className="h-8 text-xs tabular-nums"
              value={minArea}
              onChange={(e) => setMinArea(e.target.value.replace(/[^0-9]/g, ""))}
              onBlur={applyArea}
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] text-muted-foreground">Max</label>
            <Input
              type="text"
              inputMode="numeric"
              autoComplete="off"
              placeholder="Any"
              className="h-8 text-xs tabular-nums"
              value={maxArea}
              onChange={(e) => setMaxArea(e.target.value.replace(/[^0-9]/g, ""))}
              onBlur={applyArea}
            />
          </div>
        </div>
        <Button size="sm" className="h-7 w-full text-xs" onClick={applyArea}>
          Apply
        </Button>
      </div>
    </>
  );
}

function FurnishingFilter({
  filters,
  onChange,
}: {
  filters: SearchFilters;
  onChange: (next: SearchFilters) => void;
}) {
  const selected = filters.furnishing;

  return (
    <>
      <DropdownMenuLabel>Furnishing</DropdownMenuLabel>
      <div className="p-1">
        {FURNISHING_OPTIONS.map((opt) => (
          <button
            key={opt}
            type="button"
            onClick={() =>
              onChange({
                ...filters,
                furnishing: selected === opt ? undefined : opt,
              })
            }
            className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            {opt.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            {selected === opt && <Check className="h-3.5 w-3.5 text-primary" />}
          </button>
        ))}
      </div>
    </>
  );
}

export function HorizontalFilters({
  filters,
  onChange,
  onReset,
  className,
}: HorizontalFiltersProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const activeCount = [
    filters.min_price,
    filters.max_price,
    filters.min_bedrooms,
    filters.property_type,
    filters.min_area,
    filters.max_area,
    filters.furnishing,
  ].filter(Boolean).length;

  const listingType = filters.listing_type;

  const setListingType = (type: string | undefined) => {
    onChange({ ...filters, listing_type: type });
  };

  const filterContent = (
    <div className="flex flex-wrap items-center gap-2">
      {/* Buy/Rent Toggle */}
      <div className="flex rounded-lg border border-border bg-card p-0.5 shadow-sm">
        {LISTING_TYPES.map((lt) => {
          const Icon = lt.icon;
          const active = listingType === lt.value;
          return (
            <button
              key={lt.value}
              type="button"
              onClick={() => setListingType(active ? undefined : lt.value)}
              className={cn(
                "flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-all",
                active
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {lt.label}
            </button>
          );
        })}
      </div>

      <FilterDropdown label="Price" icon={IndianRupee} activeCount={(filters.min_price ? 1 : 0) + (filters.max_price ? 1 : 0)}>
        <PriceFilter filters={filters} onChange={onChange} />
      </FilterDropdown>

      <FilterDropdown label="BHK" icon={BedDouble} activeCount={filters.min_bedrooms ? 1 : 0}>
        <BHKFilter filters={filters} onChange={onChange} />
      </FilterDropdown>

      <FilterDropdown label="Type" icon={Building2} activeCount={filters.property_type ? 1 : 0}>
        <PropertyTypeFilter filters={filters} onChange={onChange} />
      </FilterDropdown>

      <FilterDropdown label="Area" icon={Maximize2} activeCount={(filters.min_area ? 1 : 0) + (filters.max_area ? 1 : 0)}>
        <AreaFilter filters={filters} onChange={onChange} />
      </FilterDropdown>

      <FilterDropdown label="Furnishing" icon={SlidersHorizontal} activeCount={filters.furnishing ? 1 : 0}>
        <FurnishingFilter filters={filters} onChange={onChange} />
      </FilterDropdown>

      {activeCount > 0 && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onReset}
          className="h-9 gap-1 rounded-lg text-xs text-muted-foreground hover:text-foreground"
        >
          <RotateCcw className="h-3 w-3" />
          Reset
        </Button>
      )}
    </div>
  );

  return (
    <div className={cn("space-y-3", className)}>
      {/* Desktop: always visible */}
      <div className="hidden md:block">{filterContent}</div>

      {/* Mobile: toggle button + collapsible panel */}
      <div className="md:hidden">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setMobileOpen(!mobileOpen)}
          className="h-9 w-full justify-between gap-1.5 rounded-lg border-border/70 bg-card text-sm font-medium shadow-sm"
        >
          <span className="flex items-center gap-1.5">
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Filters
            {activeCount > 0 && (
              <Badge variant="default" className="h-4 rounded-full px-1 text-[10px] tabular-nums">
                {activeCount}
              </Badge>
            )}
          </span>
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", mobileOpen && "rotate-180")} />
        </Button>
        {mobileOpen && (
          <div className="mt-2 rounded-xl border border-border/60 bg-card p-3 shadow-sm">
            {filterContent}
          </div>
        )}
      </div>
    </div>
  );
}

export default HorizontalFilters;
