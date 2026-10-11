"use client";

/**
 * Toast helper — one call site for success/error feedback.
 *
 * Save and unsave actions previously failed silently (the cards
 * swallowed their errors), so the user had no idea whether an action worked.
 */

import { toast } from "@/components/ui/toast";

export type ToastType = "success" | "error" | "warning" | "info";

export function notify(title: string, options?: { description?: string; type?: ToastType }) {
  toast.add({
    title,
    description: options?.description,
    type: options?.type ?? "info",
  });
}

export const notifySaved = (title?: string) =>
  notify(title ? `Saved: ${title}` : "Property saved", {
    description: "It is now on your Saved Properties page.",
    type: "success",
  });

export const notifyUnsaved = (title?: string) =>
  notify(title ? `Removed: ${title}` : "Property removed from saved", { type: "info" });

export const notifySaveFailed = () =>
  notify("Could not update your saved list", {
    description: "Your saved properties have not been changed. Please try again.",
    type: "error",
  });
