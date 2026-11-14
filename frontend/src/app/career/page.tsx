"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Calculator, RotateCcw, Shuffle } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { RunSteps } from "@/components/AgentFeed";
import { SkillDag } from "@/components/SkillDag";
import { Badge, Button, Card, CardBody, CardHeader, ErrorState, Modal, PageHeader, PageSkeleton, Progress, Select, TierBadge } from "@/components/ui";
import { api, waitForRun } from "@/lib/api";
import { useData } from "@/lib/useData";
import { cn } from "@/lib/utils";

function Inner() {
  const router = useRouter();
  const roles = useData<any[]>("/api/careers/roles");
  const profile = useData("/api/profile");
  const [role, setRole] = useState<string>("");
  const [gap, setGap] = useState<any>(null);
  const [dag, setDag] = useState<any>(null);
  const [overrides, setOverrides] = useState<Record<number, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [pivot, setPivot] = useState<any>(null);
  const [pivoting, setPivoting] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (!role && profile.data?.target_role) setRole(profile.data.target_role.slug);
  }, [profile.data, role]);

  useEffect(() => {
    if (!role) return;
    setOverrides({});
    setError(null);
    Promise.all([api(`/api/careers/gap?role=${role}`), api(`/api/careers/dag?role=${role}`)])
      .then(([g, d]) => { setGap(g); setDag(d); })
      .catch((e) => setError(e.message));
  }, [role]);

  function simulate(next: Record<number, number>) {
    setOverrides(next);
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        setGap(Object.keys(next).length ? await api("/api/careers/simulate", { body: { role_slug: role, overrides: next } }) : await api(`/api/careers/gap?role=${role}`));
      } catch (e) {
        setError((e as Error).message);
      }
    }, 200);
  }

  async function doPivot() {
    setPivoting(true);
    setPivot({ status: "queued", steps: [] });
    try {
      const q = await api("/api/profile/pivot", { body: { role_slug: role } });
      const run = await waitForRun(q.run_id, setPivot);
      setPivot(run);
      profile.reload();
      roles.reload();
    } catch (e) {
      setPivot({ status: "failed", error: (e as Error).message, steps: [] });
    } finally {
      setPivoting(false);
    }
  }

  if (roles.loading || profile.loading) return <PageSkeleton />;
  if (roles.error) return <ErrorState message={roles.error} onRetry={roles.reload} />;
  const isTarget = profile.data?.target_role?.slug === role;
  const archDiff = pivot?.steps?.find((s: any) => s.agent === "learning_strategist")?.output;
  const transfer = pivot?.steps?.find((s: any) => s.agent === "skill_detective")?.output;

  return (
    <>
      <PageHeader
        title="Career Gap Simulator"
        subtitle="Deterministic, explainable role matching over SFIA- and O*NET-coded competency requirements."
        action={
          <div className="flex gap-2">
            <Select value={role} onChange={(e) => setRole(e.target.value)} className="w-60">
              {(roles.data ?? []).map((r) => <option key={r.slug} value={r.slug}>{r.title} ({r.match_score}%)</option>)}
            </Select>
            {!isTarget && role && <Button variant="secondary" onClick={doPivot} loading={pivoting}><Shuffle className="h-4 w-4" /> Pivot here</Button>}
          </div>
        }
      />
      {error && <ErrorState message={error} />}
      {gap && (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-1">
            <CardHeader title={gap.role.title} subtitle={`O*NET ${gap.role.onet_code} · SFIA level ${gap.role.sfia_level}`} action={gap.simulated ? <Badge tone="warn">what-if</Badge> : isTarget ? <Badge tone="accent">target</Badge> : null} />
            <CardBody>
              <div className="text-5xl font-semibold tabular-nums">{gap.match_score}<span className="text-2xl text-muted">%</span></div>
              <Progress className="mt-3" value={gap.match_score} tone={gap.match_score >= 80 ? "ok" : "accent"} />
              <div className="mt-4 rounded-lg border border-line bg-bg/40 p-3 text-xs text-muted">
                <div className="mb-1 flex items-center gap-1 font-medium text-fg"><Calculator className="h-3.5 w-3.5" /> How this is calculated</div>
                <code className="font-mono text-accent">{gap.formula}</code>
                <div className="mt-2">= {gap.weighted_points} / {gap.max_points} weighted points. Only verified tiers count; self-claims score zero.</div>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg border border-line p-2"><div className="text-lg font-semibold text-ok">{gap.met_count}</div>met</div>
                <div className="rounded-lg border border-line p-2"><div className="text-lg font-semibold text-warn">{gap.gaps.length}</div>gaps</div>
                <div className="rounded-lg border border-line p-2"><div className="text-lg font-semibold text-bad">{gap.critical_missing.length}</div>critical</div>
              </div>
              {Object.keys(overrides).length > 0 && (
                <Button variant="ghost" size="sm" className="mt-4" onClick={() => simulate({})}><RotateCcw className="h-3.5 w-3.5" /> Reset what-if</Button>
              )}
            </CardBody>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader title="Requirement breakdown" subtitle="Drag a slider to simulate earning a tier. Nothing is saved." />
            <div className="divide-y divide-line">
              {gap.requirements.map((r: any) => (
                <div key={r.skill_id} className={cn("grid grid-cols-12 items-center gap-3 px-5 py-3 text-sm", r.optional && "opacity-70")}>
                  <div className="col-span-12 sm:col-span-4">
                    <div className="flex items-center gap-2 font-medium">
                      {r.name}
                      {r.critical && <Badge tone="bad">critical</Badge>}
                      {r.optional && <Badge>recommended</Badge>}
                    </div>
                    <div className="text-xs text-muted">SFIA {r.sfia_code} · weight {r.weight}{r.claimed_unverified ? " · claimed, unverified" : ""}</div>
                  </div>
                  <div className="col-span-6 sm:col-span-4 flex items-center gap-2">
                    <input type="range" min={0} max={3} step={1} aria-label={`What-if tier for ${r.name}`} value={overrides[r.skill_id] ?? r.verified_tier}
                      onChange={(e) => simulate({ ...overrides, [r.skill_id]: Number(e.target.value) })} className="w-full accent-[hsl(189_95%_52%)]" />
                    <TierBadge tier={overrides[r.skill_id] ?? r.verified_tier} short />
                  </div>
                  <div className="col-span-3 sm:col-span-2 text-xs text-muted">needs T{r.required_tier}</div>
                  <div className="col-span-3 sm:col-span-2 text-right font-mono text-xs">
                    {r.optional ? <span className="text-muted">bonus</span> : <span className={r.status === "met" ? "text-ok" : "text-muted"}>+{r.contribution}/{r.max_contribution}</span>}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {dag && (
            <Card className="lg:col-span-3">
              <CardHeader title="Prerequisite dependency graph" subtitle={`Topologically sorted DAG (Kahn's algorithm) · ${dag.nodes.length} skills, ${dag.edges.length} dependencies`}
                action={<div className="flex gap-2 text-xs"><Badge tone="ok">met</Badge><Badge tone="accent">ready</Badge><Badge>blocked</Badge></div>} />
              <CardBody><SkillDag nodes={dag.nodes} edges={dag.edges} /></CardBody>
            </Card>
          )}
        </div>
      )}

      <Modal open={!!pivot} onClose={() => !pivoting && setPivot(null)} title="Autonomous career pivot" wide>
        <RunSteps steps={pivot?.steps ?? []} running={pivoting} />
        {pivot?.status === "failed" && <div className="mt-4"><ErrorState message={pivot.error ?? "Pivot failed"} /></div>}
        {pivot?.status === "completed" && archDiff && (
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-ok/30 bg-ok/5 p-3 text-sm"><div className="font-medium text-ok">Transferred</div>{(transfer?.transferable ?? []).map((t: any) => <div key={t.skill} className="text-muted">{t.skill} (T{t.tier})</div>)}</div>
            <div className="rounded-lg border border-warn/30 bg-warn/5 p-3 text-sm"><div className="font-medium text-warn">Newly missing</div>{(archDiff.newly_missing ?? []).map((s: string) => <div key={s} className="text-muted">{s}</div>)}</div>
            <div className="rounded-lg border border-line p-3 text-sm"><div className="font-medium">Archived tasks</div><div className="text-muted">{archDiff.archived?.length ?? 0} archived, {archDiff.carried?.length ?? 0} carried</div></div>
            <div className="sm:col-span-3 flex justify-end"><Button onClick={() => router.push("/roadmap")}>View new roadmap</Button></div>
          </div>
        )}
      </Modal>
    </>
  );
}

export default function CareerPage() {
  return <AppShell wide><Inner /></AppShell>;
}
