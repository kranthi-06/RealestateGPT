import Link from "next/link";
import { Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export function EmptyState({
  title,
  description,
  actionHref,
  actionLabel,
}: {
  title: string;
  description: string;
  actionHref?: string;
  actionLabel?: string;
}) {
  return (
    <section className="surface-raised flex min-h-72 flex-col items-center justify-center rounded-2xl border border-dashed border-border px-6 py-12 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Building2 className="size-6" /></span>
      <h2 className="product-heading mt-5 text-2xl">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{description}</p>
      {actionHref && actionLabel ? <Link className="mt-6" href={actionHref}><Button className="rounded-xl">{actionLabel}</Button></Link> : null}
    </section>
  );
}
