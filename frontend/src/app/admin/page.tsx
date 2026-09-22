"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { workersApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { WorkerStatus } from "@/lib/types";
import { timeAgo } from "@/lib/format";
import {
  RefreshCw, Database, MapPin, TrendingUp, ShieldAlert, PlayCircle, Clock3, Server,
} from "lucide-react";

const WORKER_LABELS: Record<string, { label: string; icon: typeof Server }> = {
  property_ingestion: { label: "Property ingestion", icon: Database },
  property_refresh: { label: "Property refresh", icon: RefreshCw },
  geocoding_worker: { label: "Geocoding", icon: MapPin },
  stale_listing_worker: { label: "Stale listing check", icon: Clock3 },
  price_history_worker: { label: "Price history", icon: TrendingUp },
};

const STATUS_TONE: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
  running: "bg-blue-100 text-blue-700",
  skipped: "bg-amber-100 text-amber-700",
};

export default function AdminPage() {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const [status, setStatus] = useState<WorkerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<Record<string, unknown> | null>(null);

  const isAdmin = isAuthenticated && user?.role === "admin";

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      setStatus(await workersApi.status());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    const timer: ReturnType<typeof setTimeout> = setTimeout(() => loadStatus(), 0);
    return () => clearTimeout(timer);
  }, [isAdmin, loadStatus]);

  const trigger = async (name: string) => {
    setRunning(name);
    setRunResult(null);
    try {
      const result = await workersApi.trigger(name);
      setRunResult(result);
      await loadStatus();
    } catch {
      setRunResult({ status: "failed", message: "Worker trigger failed." });
    } finally {
      setRunning(null);
    }
  };

  if (authLoading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-6 h-40 w-full" />
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center px-4 py-24 text-center">
        <ShieldAlert className="h-14 w-14 text-muted-foreground/40" />
        <h1 className="mt-5 text-2xl font-bold text-foreground">Admin access required</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Worker monitoring is reserved for administrators. Worker endpoints are protected
          server-side; this page just follows the same rules.
        </p>
        <Link href="/auth/login" className="mt-6">
          <Button>Sign in</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">Workers &amp; data ops</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Scheduled jobs run via cron hitting the secret-protected worker endpoints. Every run is
            recorded in the worker runs collection.
          </p>
        </div>
        <Button variant="outline" onClick={loadStatus} disabled={loading}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {runResult && (
        <div className="mt-6 rounded-xl border border-border/60 bg-card p-4 text-sm">
          <p className="font-medium text-foreground">Last manual run result</p>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
            {JSON.stringify(runResult, null, 2)}
          </pre>
        </div>
      )}

      {/* Provider availability */}
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <Card className="rounded-2xl border-border/60 p-5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Property provider</p>
          <div className="mt-2">
            {status?.property_provider_configured ? (
              <Badge className="rounded-md">{status.property_provider}</Badge>
            ) : (
              <Badge variant="secondary" className="rounded-md">Not configured</Badge>
            )}
          </div>
          <p className="mt-3 text-sm text-muted-foreground">
            {status?.provider_message ||
              "Licensed provider is active. New inventory comes from the configured adapter."}
          </p>
        </Card>
        <Card className="rounded-2xl border-border/60 p-5">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Location provider</p>
          <p className="mt-2 text-lg font-semibold">{status?.location_provider ?? "—"}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            OpenStreetMap (OSM) by default — no billing required.
          </p>
        </Card>
      </div>

      {/* Workers */}
      <div className="mt-8 space-y-4">
        {Object.entries(WORKER_LABELS).map(([workerName, { label, icon: Icon }]) => {
          const runInfo = status?.last_runs?.[workerName];
          return (
            <Card key={workerName} className="rounded-2xl border-border/60 p-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="font-semibold text-foreground">{label}</p>
                    <p className="text-xs text-muted-foreground">{workerName}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`rounded-md px-2 py-0.5 text-xs font-medium ${
                      STATUS_TONE[runInfo?.status ?? "no_run"] || "bg-slate-100 text-slate-700"
                    }`}
                  >
                    {runInfo?.status ?? "no run yet"}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={running === workerName}
                    onClick={() => trigger(workerName)}
                  >
                    {running === workerName ? (
                      <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <PlayCircle className="mr-2 h-3.5 w-3.5" />
                    )}
                    Run now
                  </Button>
                </div>
              </div>
              {runInfo && (
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
                  <div>
                    <p className="text-xs text-muted-foreground">Last run</p>
                    <p className="mt-0.5 font-medium">
                      {runInfo.started_at ? timeAgo(runInfo.started_at) : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Processed</p>
                    <p className="mt-0.5 font-medium">{runInfo.processed_count ?? 0}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Success</p>
                    <p className="mt-0.5 font-medium text-emerald-600">{runInfo.success_count ?? 0}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Failures</p>
                    <p className="mt-0.5 font-medium text-red-600">{runInfo.failure_count ?? 0}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Skipped</p>
                    <p className="mt-0.5 font-medium">{runInfo.skipped_count ?? 0}</p>
                  </div>
                </div>
              )}
              {runInfo?.error_summary && (
                <p className="mt-3 text-xs text-red-600">{runInfo.error_summary}</p>
              )}
            </Card>
          );
        })}
      </div>

      {error && !status && (
        <div className="mt-8 rounded-2xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          Could not reach the workers status endpoint. Verify the backend and database are reachable.
        </div>
      )}
    </div>
  );
}