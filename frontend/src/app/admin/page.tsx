"use client";
import { useState } from "react";
import { Database, Radar } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { RunList } from "@/components/RunList";
import { Badge, Button, Card, CardBody, CardHeader, ErrorState, PageHeader, PageSkeleton, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { useData } from "@/lib/useData";
import { AGENT_LABEL, fmtDate } from "@/lib/utils";

function Inner() {
  const stats = useData("/api/admin/stats");
  const users = useData<any[]>("/api/admin/users");
  const runs = useData<any[]>("/api/admin/runs");
  const [scan, setScan] = useState<string | null>(null);

  async function stallScan() {
    try {
      const r = await api("/api/admin/stall-scan", { body: {} });
      setScan(`${r.stalled_learners} inactive learner(s); ${r.runs.length} STALLED run(s) queued.`);
      setTimeout(() => runs.reload(), 1500);
    } catch (e) {
      setScan((e as Error).message);
    }
  }

  if (stats.loading) return <PageSkeleton />;
  if (stats.error) return <ErrorState message={stats.error} onRetry={stats.reload} />;
  const s = stats.data;
  return (
    <>
      <PageHeader title="Admin" subtitle="Platform health, integrations and agent telemetry."
        action={<Button variant="secondary" onClick={stallScan}><Radar className="h-4 w-4" /> Run stall scan</Button>} />
      {scan && <Card className="mb-4 p-3 text-sm text-muted">{scan}</Card>}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Learners" value={s.users.learner ?? 0} hint={`${s.users.recruiter ?? 0} recruiter(s), ${s.users.admin ?? 0} admin(s)`} />
        <Stat label="Agent executions" value={s.agents.reduce((a: number, x: any) => a + x.executions, 0)} hint={`${s.agents.reduce((a: number, x: any) => a + x.errors, 0)} error(s)`} />
        <Stat label="Ledger entries" value={s.ledger_entries} />
        <Stat label="Catalog" value={`${s.catalog.missions} missions`} hint={`${s.catalog.skills} skills · ${s.catalog.roles} roles · ${s.catalog.resources} resources`} />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="Integrations" subtitle="Active engines and fallbacks" />
          <CardBody className="space-y-2 text-sm">
            {Object.entries(s.integrations).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between"><span className="capitalize text-muted">{k.replace("_", " ")}</span>
                <Badge tone={String(v).includes("fallback") || v === "in-process" || v === "local-runner" || v === "sqlite" ? "warn" : "ok"}>{String(v)}</Badge></div>
            ))}
            <p className="pt-2 text-xs text-muted"><Database className="mr-1 inline h-3 w-3" />Amber = development fallback in use. Configure PostgreSQL, Judge0, Redis and Gemini via environment variables for production.</p>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Agents" />
          <CardBody className="space-y-2 text-sm">
            {s.agents.map((a: any) => (
              <div key={a.agent} className="flex items-center justify-between"><span>{AGENT_LABEL[a.agent] ?? a.agent}</span><span className="tabular-nums text-muted">{a.executions}{a.errors ? <span className="text-bad"> · {a.errors} err</span> : ""}</span></div>
            ))}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Events & submissions" />
          <CardBody className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">{Object.entries(s.events).map(([k, v]) => <Badge key={k} tone="accent">{k} · {String(v)}</Badge>)}</div>
            <div className="flex flex-wrap gap-2">{Object.entries(s.submissions).map(([k, v]) => <Badge key={k}>{k} · {String(v)}</Badge>)}</div>
          </CardBody>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Users" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted"><tr><th className="px-5 py-2">Name</th><th>Email</th><th>Role</th><th>Target</th><th>Verified</th><th className="pr-5">Last active</th></tr></thead>
            <tbody className="divide-y divide-line">
              {(users.data ?? []).map((u) => (
                <tr key={u.id}><td className="px-5 py-2">{u.display_name}</td><td className="text-muted">{u.email}</td><td><Badge>{u.role}</Badge></td><td>{u.target_role ?? "-"}</td><td>{u.verified_skills}</td><td className="pr-5 text-xs text-muted">{u.last_active_at ? fmtDate(u.last_active_at) : "-"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <h2 className="mb-3 mt-8 font-semibold">Recent workflow runs</h2>
      {runs.data && <RunList runs={runs.data} />}
    </>
  );
}

export default function AdminPage() {
  return <AppShell roles={["admin"]} wide><Inner /></AppShell>;
}
