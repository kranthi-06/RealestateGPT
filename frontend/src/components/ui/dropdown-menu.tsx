"use client";

import * as React from "react";
import { Menu } from "@base-ui/react/menu";
import { cn } from "@/lib/utils";

/* Radix-compatible DropdownMenu API implemented on Base UI Menu primitives. */

function DropdownMenu({
  children,
  open,
  onOpenChange,
}: {
  children: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  return (
    <Menu.Root open={open} onOpenChange={onOpenChange}>
      {children}
    </Menu.Root>
  );
}

function DropdownMenuTrigger({
  asChild = false,
  children,
  ...props
}: React.ComponentPropsWithoutRef<"button"> & { asChild?: boolean }) {
  if (asChild && React.isValidElement(children)) {
    return <Menu.Trigger render={children as React.ReactElement} />;
  }
  return <Menu.Trigger {...props}>{children}</Menu.Trigger>;
}

function DropdownMenuContent({
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
    <Menu.Portal>
      <Menu.Positioner side={side} align={align} sideOffset={sideOffset} className="z-50">
        <Menu.Popup
          className={cn(
            "z-50 min-w-[10rem] overflow-hidden rounded-xl border border-border bg-popover p-1.5 text-popover-foreground shadow-lg",
            "transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0",
            className
          )}
          {...props}
        >
          {children}
        </Menu.Popup>
      </Menu.Positioner>
    </Menu.Portal>
  );
}

function DropdownMenuItem({
  asChild = false,
  className,
  children,
  onClick,
  ...props
}: React.ComponentPropsWithoutRef<"div"> & { asChild?: boolean }) {
  const itemClass = cn(
    "relative flex w-full cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm outline-none transition-colors",
    "hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent data-highlighted:bg-accent",
    className
  );
  if (asChild && React.isValidElement(children)) {
    const child = children as React.ReactElement<Record<string, unknown>>;
    return (
      <Menu.Item
        render={child}
        className={cn(itemClass, child.props.className as string | undefined)}
        onClick={onClick}
        {...props}
      />
    );
  }
  return (
    <Menu.Item className={itemClass} onClick={onClick} {...props}>
      {children}
    </Menu.Item>
  );
}

function DropdownMenuSeparator({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="separator"
      className={cn("-mx-1 my-1 h-px bg-border", className)}
      {...props}
    />
  );
}

function DropdownMenuLabel({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("px-2.5 py-1.5 text-xs font-medium text-muted-foreground", className)}
      {...props}
    />
  );
}

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
};
