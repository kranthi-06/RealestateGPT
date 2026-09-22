import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <section role="alert" className="rounded-2xl border border-destructive/25 bg-destructive/5 px-6 py-10 text-center">
    <AlertCircle className="mx-auto size-7 text-destructive" />
    <h2 className="mt-3 font-semibold">We couldn&apos;t load this right now.</h2>
    <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">{message}</p>
    {onRetry ? <Button variant="outline" onClick={onRetry} className="mt-5 rounded-xl">Try again</Button> : null}
  </section>;
}
