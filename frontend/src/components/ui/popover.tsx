"use client";

import * as React from "react";
import { Popover as PopoverPrimitive } from "@base-ui/react/popover";
import { cn } from "@/lib/utils";

/*
 * Radix-compatible Popover API implemented on Base UI Popover primitives.
 *
 * Why this exists beside DropdownMenu: Base UI's *Menu* popup owns the keyboard
 * (arrow navigation + typeahead), so it swallows character keystrokes — which
 * makes it impossible to type into a text or number input rendered inside a
 * menu. Popover is the generic container for arbitrary content and does not
 * intercept typing, so filter panels that contain inputs use this instead.
 * DropdownMenu remains correct for pure menus of actions/links.
 */

function Popover({
  children,
  open,
  onOpenChange,
}: {
  children: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  return (
    <PopoverPrimitive.Root open={open} onOpenChange={onOpenChange}>
      {children}
    </PopoverPrimitive.Root>
  );
}

function PopoverTrigger({
  asChild,
  children,
  ...props
}: React.ComponentPropsWithoutRef<"button"> & { asChild?: boolean }) {
  // Base UI's Trigger renders its own <button>. When the child is already an
  // element (our Button), merge into it via `render` so we never emit invalid
  // nested <button><button> HTML. This matches Radix's `asChild` contract, so
  // callers can pass children directly without opting in.
  if (React.isValidElement(children) && asChild !== false) {
    return <PopoverPrimitive.Trigger render={children as React.ReactElement} {...props} />;
  }
  return <PopoverPrimitive.Trigger {...props}>{children}</PopoverPrimitive.Trigger>;
}

function PopoverContent({
  className,
  align = "center",
  side = "bottom",
  sideOffset = 6,
  children,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  align?: "start" | "center" | "end";
  side?: "top" | "bottom" | "left" | "right";
  sideOffset?: number;
}) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Positioner
        side={side}
        align={align}
        sideOffset={sideOffset}
        className="z-50"
      >
        <PopoverPrimitive.Popup
          className={cn(
            "z-50 min-w-[10rem] overflow-hidden rounded-xl border border-border bg-popover p-1.5 text-popover-foreground shadow-lg outline-none",
            "transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0",
            className
          )}
          {...props}
        >
          {children}
        </PopoverPrimitive.Popup>
      </PopoverPrimitive.Positioner>
    </PopoverPrimitive.Portal>
  );
}

export { Popover, PopoverTrigger, PopoverContent };
