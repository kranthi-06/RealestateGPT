"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { adminApi, workersApi, healthApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type {
  AdminStats, AdminUser, AuditLog, AdminAiUsage, WorkerStatus, Property,
} from "@/lib/types";
import { timeAgo, formatPrice } from "@/lib/format";
import {
  RefreshCw, Database, MapPin, TrendingUp, ShieldAlert, PlayCircle, Clock3,
  Server, Users, Search, Brain, HardDrive, CheckCircle2, Activity,
  HeartPulse, FileText, Building2, BarChart3, Shield,
} from "lucide-react";

/* ---------- worker labels ---------- */

const WORKER_LABELS: Record<string, { label: string; icon: typeof Server }> = {
  property_ingestion: { label: "Property ingestion", icon: Database },
  property_refresh:   { label: "Property refresh",   icon: RefreshCw },
  geocoding_worker:   { label: "Geocoding",          icon: MapPin },
  stale_listing_worker: { label: "Stale listing check", icon: Clock3 },
  price_history_worker: { label: "Price history",     icon: TrendingUp },
};

const STATUS_TONE: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-700",
  failed:    "bg-red-100 text-red-700",
  running:   "bg-blue-100 text-blue-700",
  skipped:   "bg-amber-100 text-amber-700",
};

/* ---------- KPI Card ---------- */

function KpiCard({
  label, value, icon: Icon, detail,
}: {
  label: string;
  value: string | number;
  icon: typeof Building2;
  detail?: string;
}) {
  return (
    <Card className="rounded-2xl border-border/60 p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
          {detail && <p className="mt-1 text-xs text-muted-foreground">{detail}</p>}
        </div>
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </span>
      </div>
    </Card>
  );
}

/* ---------- Main ---------- */

export default function AdminPage() {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  /* ── data state ── */
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<{ users: AdminUser[]; total: number } | null>(null);
  const [properties, setProperties] = useState<{ properties: Property[]; total: number } | null>(null);
  const [aiUsage, setAiUsage] = useState<AdminAiUsage | null>(null);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [workerStatus, setWorkerStatus] = useState<WorkerStatus | null>(null);
  const [apiHealth, setApiHealth] = useState<{ status: string } | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<Record<string, unknown> | null>(null);
  const [activeTab, setActiveTab] = useState("properties");

  const isAdmin = isAuthenticated && user?.role === "admin";

  /* ── data fetching ── */
  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [s, u, p, ai, lg, ws, h] = await Promise.allSettled([
        adminApi.getStats(),
        adminApi.listUsers(1, 50),
        adminApi.listProperties(1, 50, true),
        adminApi.aiUsage(),
        adminApi.auditLogs(100, 0),
        workersApi.status(),
        healthApi.check(),
      ]);
      if (s.status === "fulfilled")  setStats(s.value);
      if (u.status === "fulfilled")  setUsers(u.value);
      if (p.status === "fulfilled")  setProperties(p.value);
      if (ai.status === "fulfilled") setAiUsage(ai.value);
      if (lg.status === "fulfilled") setLogs(lg.value);
      if (ws.status === "fulfilled") setWorkerStatus(ws.value);
      if (h.status === "fulfilled")  setApiHealth(h.value);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAdmin) return;
    const t = setTimeout(() => loadAll(), 0);
    return () => clearTimeout(t);
  }, [isAdmin, loadAll]);

  const triggerWorker = async (name: string) => {
    setRunning(name);
    setRunResult(null);
    try {
      const result = await workersApi.trigger(name);
      setRunResult(result);
      const ws = await workersApi.status();
      setWorkerStatus(ws);
    } catch {
      setRunResult({ status: "failed", message: "Worker trigger failed." });
    } finally {
      setRunning(null);
    }
  };

  /* ── Auth guards ── */
  if (authLoading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <Skeleton className="h-8 w-64" />
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center px-4 py-24 text-center">
        <ShieldAlert className="h-14 w-14 text-muted-foreground/40" />
        <h1 className="mt-5 text-2xl font-bold text-foreground">Admin access required</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This dashboard is reserved for administrators. Endpoints are protected server-side.
        </p>
        <Link href="/auth/login" className="mt-6">
          <Button>Sign in</Button>
        </Link>
      </div>
    );
  }

  /* ── derived KPI values ── */
  const verificationRate = stats
    ? stats.active_properties > 0
      ? Math.round((stats.verified_properties / stats.active_properties) * 100)
      : 0
    : 0;

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">Admin Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Platform health, users, data ops, and AI usage at a glance.
          </p>
        </div>
        <Button variant="outline" onClick={loadAll} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* ── KPI Cards ── */}
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Total Properties"
          value={stats?.total_properties?.toLocaleString() ?? "—"}
          icon={Building2}
          detail={`${stats?.active_properties ?? 0} active`}
        />
        <KpiCard
          label="Total Users"
          value={stats?.total_users?.toLocaleString() ?? "—"}
          icon={Users}
        />
        <KpiCard
          label="Saved Searches"
          value={stats?.total_saved_searches?.toLocaleString() ?? "—"}
          icon={Search}
          detail={`${stats?.total_searches?.toLocaleString() ?? 0} total searches`}
        />
        <KpiCard
          label="AI Conversations"
          value={aiUsage?.total_conversations?.toLocaleString() ?? "—"}
          icon={Brain}
          detail={`${aiUsage?.total_messages ?? 0} messages, ${aiUsage?.tool_calls ?? 0} tool calls`}
        />
        <KpiCard
          label="Verified Properties"
          value={stats?.verified_properties?.toLocaleString() ?? "—"}
          icon={CheckCircle2}
          detail={`${verificationRate}% verification rate`}
        />
        <KpiCard
          label="Saved Properties"
          value={stats?.total_saved_properties?.toLocaleString() ?? "—"}
          icon={HardDrive}
        />
        <KpiCard
          label="Comparisons"
          value={stats?.total_comparisons?.toLocaleString() ?? "—"}
          icon={BarChart3}
        />
        <KpiCard
          label="API Health"
          value={apiHealth?.status === "ok" ? "Healthy" : apiHealth?.status ?? "—"}
          icon={HeartPulse}
          detail={apiHealth?.status === "ok" ? "All systems operational" : "Check connectivity"}
        />
      </div>

      {/* ── Tabs ── */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-10 w-full">
        <TabsList className="flex w-full flex-wrap gap-1">
          <TabsTrigger value="properties"><Building2 className="mr-1.5 h-3.5 w-3.5" />Properties</TabsTrigger>
          <TabsTrigger value="users"><Users className="mr-1.5 h-3.5 w-3.5" />Users</TabsTrigger>
          <TabsTrigger value="searches"><Search className="mr-1.5 h-3.5 w-3.5" />Searches</TabsTrigger>
          <TabsTrigger value="ai-usage"><Brain className="mr-1.5 h-3.5 w-3.5" />AI Usage</TabsTrigger>
          <TabsTrigger value="data-ingestion"><Database className="mr-1.5 h-3.5 w-3.5" />Data Ingestion</TabsTrigger>
          <TabsTrigger value="data-quality"><Shield className="mr-1.5 h-3.5 w-3.5" />Data Quality</TabsTrigger>
          <TabsTrigger value="api-health"><Activity className="mr-1.5 h-3.5 w-3.5" />API Health</TabsTrigger>
          <TabsTrigger value="system-health"><Server className="mr-1.5 h-3.5 w-3.5" />System Health</TabsTrigger>
          <TabsTrigger value="logs"><FileText className="mr-1.5 h-3.5 w-3.5" />Logs</TabsTrigger>
        </TabsList>

        {/* ─── 1. Properties ─── */}
        <TabsContent value="properties" className="mt-6">
          <Card className="rounded-2xl border-border/60 p-0 overflow-hidden">
            <div className="flex items-center justify-between border-b border-border/60 px-5 py-4">
              <h2 className="font-semibold text-foreground">Properties ({properties?.total ?? 0})</h2>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>City</TableHead>
                  <TableHead>Price</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Verified</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {properties?.properties?.slice(0, 25).map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="font-mono text-xs">{p.id}</TableCell>
                    <TableCell>
                      <Link href={`/property/${p.id}`} className="text-primary hover:underline">
                        {p.title.slice(0, 60)}{p.title.length > 60 ? "…" : ""}
                      </Link>
                    </TableCell>
                    <TableCell>{p.city}</TableCell>
                    <TableCell>{formatPrice(p.price, p.currency)}</TableCell>
                    <TableCell><Badge variant="secondary" className="capitalize">{p.property_type}</Badge></TableCell>
                    <TableCell>
                      <Badge className={p.status === "active" ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}>
                        {p.status ?? "unknown"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge className={p.verification_status === "verified" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}>
                        {p.verification_status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
                {(!properties?.properties || properties.properties.length === 0) && (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                      No properties loaded.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* ─── 2. Users ─── */}
        <TabsContent value="users" className="mt-6">
          <Card className="rounded-2xl border-border/60 p-0 overflow-hidden">
            <div className="flex items-center justify-between border-b border-border/60 px-5 py-4">
              <h2 className="font-semibold text-foreground">Users ({users?.total ?? 0})</h2>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Active</TableHead>
                  <TableHead>Joined</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users?.users?.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-mono text-xs">{u.id}</TableCell>
                    <TableCell className="font-medium">{u.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">{u.email}</TableCell>
                    <TableCell>
                      <Badge className={u.role === "admin" ? "bg-purple-100 text-purple-700" : "bg-slate-100 text-slate-600"}>
                        {u.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {u.is_active
                        ? <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                        : <span className="text-xs text-red-500">Inactive</span>}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{timeAgo(u.created_at)}</TableCell>
                  </TableRow>
                ))}
                {(!users?.users || users.users.length === 0) && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                      No users loaded.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* ─── 3. Searches ─── */}
        <TabsContent value="searches" className="mt-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <KpiCard label="Total Searches" value={stats?.total_searches?.toLocaleString() ?? "—"} icon={Search} />
            <KpiCard label="Saved Searches" value={stats?.total_saved_searches?.toLocaleString() ?? "—"} icon={HardDrive} />
            <KpiCard label="Saved Properties" value={stats?.total_saved_properties?.toLocaleString() ?? "—"} icon={Building2} />
          </div>

          {stats?.properties_by_city && Object.keys(stats.properties_by_city).length > 0 && (
            <Card className="mt-6 rounded-2xl border-border/60 p-5">
              <h3 className="font-semibold text-foreground mb-4">Properties by City</h3>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {Object.entries(stats.properties_by_city)
                  .sort(([, a], [, b]) => b - a)
                  .map(([city, count]) => (
                    <div key={city} className="flex items-center justify-between rounded-lg bg-muted/50 px-4 py-2.5">
                      <span className="text-sm font-medium">{city}</span>
                      <Badge variant="secondary">{count.toLocaleString()}</Badge>
                    </div>
                  ))}
              </div>
            </Card>
          )}

          {stats?.properties_by_type && Object.keys(stats.properties_by_type).length > 0 && (
            <Card className="mt-4 rounded-2xl border-border/60 p-5">
              <h3 className="font-semibold text-foreground mb-4">Properties by Type</h3>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {Object.entries(stats.properties_by_type)
                  .sort(([, a], [, b]) => b - a)
                  .map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between rounded-lg bg-muted/50 px-4 py-2.5">
                      <span className="text-sm font-medium capitalize">{type}</span>
                      <Badge variant="secondary">{count.toLocaleString()}</Badge>
                    </div>
                  ))}
              </div>
            </Card>
          )}
        </TabsContent>

        {/* ─── 4. AI Usage ─── */}
        <TabsContent value="ai-usage" className="mt-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard label="Messages" value={aiUsage?.total_messages?.toLocaleString() ?? "—"} icon={Brain} />
            <KpiCard label="Conversations" value={aiUsage?.total_conversations?.toLocaleString() ?? "—"} icon={FileText} />
            <KpiCard label="Tool Calls" value={aiUsage?.tool_calls?.toLocaleString() ?? "—"} icon={Activity} />
            <KpiCard
              label="Provider"
              value={aiUsage?.provider ?? "—"}
              icon={Server}
              detail={aiUsage?.offline_mode ? "Offline mode" : "Online"}
            />
          </div>

          {aiUsage?.by_action && Object.keys(aiUsage.by_action).length > 0 && (
            <Card className="mt-6 rounded-2xl border-border/60 p-5">
              <h3 className="font-semibold text-foreground mb-4">Usage by Action</h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Action</TableHead>
                    <TableHead className="text-right">Count</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(aiUsage.by_action)
                    .sort(([, a], [, b]) => b - a)
                    .map(([action, count]) => (
                      <TableRow key={action}>
                        <TableCell className="capitalize">{action.replace(/_/g, " ")}</TableCell>
                        <TableCell className="text-right font-mono">{count.toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                </TableBody>
              </Table>
            </Card>
          )}
        </TabsContent>

        {/* ─── 5. Data Ingestion (Workers) ─── */}
        <TabsContent value="data-ingestion" className="mt-6">
          {runResult && (
            <div className="mb-6 rounded-xl border border-border/60 bg-card p-4 text-sm">
              <p className="font-medium text-foreground">Last manual run result</p>
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
                {JSON.stringify(runResult, null, 2)}
              </pre>
            </div>
          )}

          {/* Provider cards */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="rounded-2xl border-border/60 p-5">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Property provider</p>
              <div className="mt-2">
                {workerStatus?.property_provider_configured ? (
                  <Badge className="rounded-md">{workerStatus.property_provider}</Badge>
                ) : (
                  <Badge variant="secondary" className="rounded-md">Not configured</Badge>
                )}
              </div>
              <p className="mt-3 text-sm text-muted-foreground">
                {workerStatus?.provider_message ?? "Provider status unknown."}
              </p>
            </Card>
            <Card className="rounded-2xl border-border/60 p-5">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Location provider</p>
              <p className="mt-2 text-lg font-semibold">{workerStatus?.location_provider ?? "—"}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                OpenStreetMap (OSM) by default — no billing required.
              </p>
            </Card>
          </div>

          {/* Worker rows */}
          <div className="mt-6 space-y-4">
            {Object.entries(WORKER_LABELS).map(([workerName, { label, icon: Icon }]) => {
              const runInfo = workerStatus?.last_runs?.[workerName];
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
                        onClick={() => triggerWorker(workerName)}
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
        </TabsContent>

        {/* ─── 6. Data Quality ─── */}
        <TabsContent value="data-quality" className="mt-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <KpiCard
              label="Verified Properties"
              value={stats?.verified_properties?.toLocaleString() ?? "—"}
              icon={CheckCircle2}
              detail={`${verificationRate}% of active`}
            />
            <KpiCard
              label="Active Properties"
              value={stats?.active_properties?.toLocaleString() ?? "—"}
              icon={Building2}
              detail={`${stats?.total_properties ?? 0} total`}
            />
            <KpiCard
              label="Inactive / Stale"
              value={
                stats
                  ? (stats.total_properties - stats.active_properties).toLocaleString()
                  : "—"
              }
              icon={Clock3}
              detail="Properties needing review"
            />
          </div>

          <Card className="mt-6 rounded-2xl border-border/60 p-5">
            <h3 className="font-semibold text-foreground mb-3">Quality Summary</h3>
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between rounded-lg bg-muted/50 px-4 py-3">
                <span>Verification rate</span>
                <div className="flex items-center gap-2">
                  <div className="h-2 w-32 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-emerald-500 transition-all"
                      style={{ width: `${verificationRate}%` }}
                    />
                  </div>
                  <span className="font-mono text-xs">{verificationRate}%</span>
                </div>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-muted/50 px-4 py-3">
                <span>Active rate</span>
                <div className="flex items-center gap-2">
                  <div className="h-2 w-32 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-blue-500 transition-all"
                      style={{
                        width: `${stats && stats.total_properties > 0
                          ? Math.round((stats.active_properties / stats.total_properties) * 100)
                          : 0}%`,
                      }}
                    />
                  </div>
                  <span className="font-mono text-xs">
                    {stats && stats.total_properties > 0
                      ? Math.round((stats.active_properties / stats.total_properties) * 100)
                      : 0}%
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-muted/50 px-4 py-3">
                <span>Geocoding worker</span>
                <Badge className={STATUS_TONE[workerStatus?.last_runs?.geocoding_worker?.status ?? ""] || "bg-slate-100 text-slate-700"}>
                  {workerStatus?.last_runs?.geocoding_worker?.status ?? "no run"}
                </Badge>
              </div>
              <div className="flex items-center justify-between rounded-lg bg-muted/50 px-4 py-3">
                <span>Stale listing check</span>
                <Badge className={STATUS_TONE[workerStatus?.last_runs?.stale_listing_worker?.status ?? ""] || "bg-slate-100 text-slate-700"}>
                  {workerStatus?.last_runs?.stale_listing_worker?.status ?? "no run"}
                </Badge>
              </div>
            </div>
          </Card>
        </TabsContent>

        {/* ─── 7. API Health ─── */}
        <TabsContent value="api-health" className="mt-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <KpiCard
              label="API Status"
              value={apiHealth?.status === "ok" ? "Healthy" : apiHealth?.status ?? "Unknown"}
              icon={HeartPulse}
              detail="Backend health endpoint"
            />
            <KpiCard
              label="Property Provider"
              value={workerStatus?.property_provider_configured ? "Configured" : "Not configured"}
              icon={Database}
              detail={workerStatus?.property_provider ?? "—"}
            />
            <KpiCard
              label="Location Provider"
              value={workerStatus?.location_provider ?? "Unknown"}
              icon={MapPin}
              detail="Geocoding service"
            />
          </div>

          {workerStatus?.web_search_provider && (
            <Card className="mt-6 rounded-2xl border-border/60 p-5">
              <h3 className="font-semibold text-foreground mb-4">Web Search Provider</h3>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-lg bg-muted/50 px-4 py-3">
                  <p className="text-xs text-muted-foreground">Provider</p>
                  <p className="mt-1 font-medium">{workerStatus.web_search_provider.provider}</p>
                </div>
                <div className="rounded-lg bg-muted/50 px-4 py-3">
                  <p className="text-xs text-muted-foreground">Status</p>
                  <Badge className={workerStatus.web_search_provider.status === "healthy"
                    ? "bg-emerald-100 text-emerald-700 mt-1"
                    : "bg-amber-100 text-amber-700 mt-1"}>
                    {workerStatus.web_search_provider.status}
                  </Badge>
                </div>
                <div className="rounded-lg bg-muted/50 px-4 py-3">
                  <p className="text-xs text-muted-foreground">Requests</p>
                  <p className="mt-1 font-medium">{workerStatus.web_search_provider.requests}</p>
                </div>
                <div className="rounded-lg bg-muted/50 px-4 py-3">
                  <p className="text-xs text-muted-foreground">Success</p>
                  <p className="mt-1 font-medium">{workerStatus.web_search_provider.success}</p>
                </div>
                <div className="rounded-lg bg-muted/50 px-4 py-3">
                  <p className="text-xs text-muted-foreground">Errors</p>
                  <p className="mt-1 font-medium text-red-600">{workerStatus.web_search_provider.errors}</p>
                </div>
                <div className="rounded-lg bg-muted/50 px-4 py-3">
                  <p className="text-xs text-muted-foreground">Avg Latency</p>
                  <p className="mt-1 font-medium">{workerStatus.web_search_provider.average_latency_ms}ms</p>
                </div>
                <div className="rounded-lg bg-muted/50 px-4 py-3">
                  <p className="text-xs text-muted-foreground">Cache Hit Rate</p>
                  <p className="mt-1 font-medium">{Math.round(workerStatus.web_search_provider.cache_hit_rate * 100)}%</p>
                </div>
                <div className="rounded-lg bg-muted/50 px-4 py-3">
                  <p className="text-xs text-muted-foreground">Rate-limited</p>
                  <p className="mt-1 font-medium">{workerStatus.web_search_provider.too_many_requests}</p>
                </div>
              </div>
              {workerStatus.web_search_provider.last_failure_reason && (
                <p className="mt-4 text-xs text-red-600">
                  Last failure: {workerStatus.web_search_provider.last_failure_reason}
                </p>
              )}
            </Card>
          )}
        </TabsContent>

        {/* ─── 8. System Health ─── */}
        <TabsContent value="system-health" className="mt-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <KpiCard
              label="Backend"
              value={apiHealth?.status === "ok" ? "Online" : "Offline"}
              icon={Server}
              detail={apiHealth?.status === "ok" ? "Responding normally" : "Connection error"}
            />
            <KpiCard
              label="Workers"
              value={
                workerStatus?.last_runs
                  ? `${Object.values(workerStatus.last_runs).filter((r) => r.status === "completed").length}/${Object.keys(workerStatus.last_runs).length} OK`
                  : "—"
              }
              icon={HardDrive}
              detail="Last run statuses"
            />
            <KpiCard
              label="AI Provider"
              value={aiUsage?.provider ?? "—"}
              icon={Brain}
              detail={aiUsage?.offline_mode ? "Offline mode active" : "Connected"}
            />
          </div>

          <Card className="mt-6 rounded-2xl border-border/60 p-5">
            <h3 className="font-semibold text-foreground mb-4">Worker Health Overview</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Worker</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Run</TableHead>
                  <TableHead>Processed</TableHead>
                  <TableHead>Failures</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(WORKER_LABELS).map(([name, { label }]) => {
                  const run = workerStatus?.last_runs?.[name];
                  return (
                    <TableRow key={name}>
                      <TableCell className="font-medium">{label}</TableCell>
                      <TableCell>
                        <Badge className={STATUS_TONE[run?.status ?? ""] || "bg-slate-100 text-slate-700"}>
                          {run?.status ?? "no run"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {run?.started_at ? timeAgo(run.started_at) : "—"}
                      </TableCell>
                      <TableCell>{run?.processed_count ?? 0}</TableCell>
                      <TableCell className={run?.failure_count ? "text-red-600" : ""}>
                        {run?.failure_count ?? 0}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>

        {/* ─── 9. Logs ─── */}
        <TabsContent value="logs" className="mt-6">
          <Card className="rounded-2xl border-border/60 p-0 overflow-hidden">
            <div className="flex items-center justify-between border-b border-border/60 px-5 py-4">
              <h2 className="font-semibold text-foreground">Audit Logs ({logs.length})</h2>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Entity</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>IP</TableHead>
                  <TableHead>Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.slice(0, 50).map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="font-mono text-xs">{log.id}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="capitalize">
                        {log.action.replace(/_/g, " ")}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm">
                      {log.entity ? `${log.entity}${log.entity_id ? ` #${log.entity_id}` : ""}` : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{log.user_id ?? "system"}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{log.ip_address ?? "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{timeAgo(log.created_at)}</TableCell>
                  </TableRow>
                ))}
                {logs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                      No audit logs available.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </Card>
        </TabsContent>
      </Tabs>

      {error && !stats && (
        <div className="mt-8 rounded-2xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          Could not reach the admin endpoints. Verify the backend and database are reachable.
        </div>
      )}
    </div>
  );
}