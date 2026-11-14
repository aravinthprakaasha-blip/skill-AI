"use client";
import Link from "next/link";
import { useState } from "react";
import { BookOpen, CheckCircle2, Circle, ExternalLink, History, LifeBuoy, Timer } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { RunSteps } from "@/components/AgentFeed";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorState, Modal, PageHeader, PageSkeleton, Progress } from "@/components/ui";
import { api } from "@/lib/api";
import { useData } from "@/lib/useData";
import { cn, fmtDate } from "@/lib/utils";

const STEP_TONE: Record<string, "accent" | "ok" | "warn" | "default"> = { concept: "default", coding: "accent", applied: "ok", remediation: "warn" };

function Inner() {
  const rm = useData("/api/roadmap");
  const hist = useData<any[]>("/api/roadmap/history");
  const [checkin, setCheckin] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  async function doCheckin() {
    setBusy(true);
    try {
      const r = await api("/api/profile/checkin", { body: {} });
      setCheckin(r);
      rm.reload();
    } catch (e) {
      setCheckin({ error: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  if (rm.loading) return <PageSkeleton />;
  if (rm.error) return <ErrorState message={rm.error} onRetry={rm.reload} />;
  if (!rm.data) return <EmptyState title="No roadmap yet" body="Complete onboarding so the Learning Strategist can plan your path." action={<Link href="/onboarding"><Button>Start onboarding</Button></Link>} />;
  const d = rm.data;
  const weeks: Record<number, any[]> = {};
  d.items.filter((i: any) => i.status === "pending").forEach((i: any) => (weeks[i.week] ??= []).push(i));
  const done = d.items.filter((i: any) => i.status === "done");

  return (
    <>
      <PageHeader title="Adaptive Learning Roadmap" subtitle={`${d.role.title} · generated ${fmtDate(d.created_at)} (${d.summary.reason})`}
        action={<Button variant="secondary" onClick={doCheckin} loading={busy}><LifeBuoy className="h-4 w-4" /> Agent check-in</Button>} />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Card className="p-5">
          <div className="text-xs uppercase tracking-wide text-muted">Progress</div>
          <div className="mt-2 text-3xl font-semibold">{d.progress.done}/{d.progress.total}</div>
          <Progress className="mt-3" value={d.progress.total ? (100 * d.progress.done) / d.progress.total : 0} tone="ok" />
        </Card>
        <Card className="p-5">
          <div className="flex items-center gap-1 text-xs uppercase tracking-wide text-muted"><Timer className="h-3.5 w-3.5" /> Remaining effort</div>
          <div className="mt-2 text-3xl font-semibold">{d.summary.total_hours}h</div>
          <div className="mt-1 text-xs text-muted">{d.summary.weeks_needed} week(s) at {d.summary.weekly_hours} h/week</div>
        </Card>
        <Card className={cn("p-5", d.summary.fits_timeline ? "" : "border-warn/40")}>
          <div className="text-xs uppercase tracking-wide text-muted">Timeline</div>
          <div className={cn("mt-2 text-3xl font-semibold", d.summary.fits_timeline ? "text-ok" : "text-warn")}>{d.summary.fits_timeline ? "On track" : "Over"}</div>
          <div className="mt-1 text-xs text-muted">Target {d.summary.timeline_weeks} week(s)</div>
        </Card>
      </div>

      {d.summary.transferable?.length > 0 && d.summary.reason === "pivot" && (
        <Card className="mb-6 border-ok/30 p-4 text-sm">
          <span className="font-medium text-ok">Pivot preserved:</span>{" "}
          <span className="text-muted">{d.summary.transferable.map((t: any) => `${t.skill} (T${t.tier})`).join(", ")}</span>
          {d.summary.archived?.length > 0 && <span className="text-muted"> · {d.summary.archived.length} irrelevant task(s) archived</span>}
        </Card>
      )}

      <div className="space-y-6">
        {Object.keys(weeks).length === 0 && <EmptyState title="All tasks complete" body="Every requirement for this role is verified." />}
        {Object.entries(weeks).map(([w, items]) => (
          <section key={w}>
            <h2 className="mb-3 text-xs font-medium uppercase tracking-widest text-muted">Week {w}</h2>
            <div className="space-y-3">
              {items.map((i: any) => (
                <Card key={i.id} className="p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex gap-3">
                      <Circle className="mt-1 h-4 w-4 shrink-0 text-muted" />
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{i.skill}</span>
                          <Badge tone={STEP_TONE[i.step]}>{i.step}</Badge>
                          <span className="text-xs text-muted">→ Tier {i.target_tier} · {i.est_hours}h</span>
                        </div>
                        <p className="mt-1 text-sm text-muted">{i.mission ? i.mission.title + " - " : ""}{i.rationale}</p>
                        {i.resources.length > 0 && (
                          <ul className="mt-2 space-y-1">
                            {i.resources.map((r: any) => (
                              <li key={r.id}>
                                <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline">
                                  <BookOpen className="h-3.5 w-3.5" />{r.title}<span className="text-xs text-muted">({r.source})</span><ExternalLink className="h-3 w-3" />
                                </a>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                    {i.mission ? (
                      <Link href={`/missions/${i.mission.id}`}><Button size="sm">Open mission</Button></Link>
                    ) : i.step !== "remediation" ? (
                      <Link href={`/skills?quiz=${i.skill_id}`}><Button size="sm" variant="secondary">Concept check</Button></Link>
                    ) : null}
                  </div>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>

      {done.length > 0 && (
        <Card className="mt-8">
          <CardHeader title="Completed" subtitle="Closed automatically when verified evidence reached the target tier" />
          <CardBody className="grid gap-2 sm:grid-cols-2">
            {done.map((i: any) => (
              <div key={i.id} className="flex items-center gap-2 text-sm"><CheckCircle2 className="h-4 w-4 text-ok" />{i.skill} <span className="text-muted">({i.step}, T{i.target_tier})</span></div>
            ))}
          </CardBody>
        </Card>
      )}

      {(hist.data?.length ?? 0) > 1 && (
        <Card className="mt-6">
          <CardHeader title="Roadmap history" subtitle="Previous plans are archived, never deleted" />
          <CardBody className="space-y-2">
            {hist.data!.map((h) => (
              <div key={h.id} className="flex items-center gap-3 text-sm">
                <History className="h-4 w-4 text-muted" /><span>{h.role}</span><Badge tone={h.status === "active" ? "accent" : "default"}>{h.status}</Badge>
                <span className="ml-auto text-xs text-muted">{fmtDate(h.created_at)}</span>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      <Modal open={!!checkin} onClose={() => setCheckin(null)} title="STALLED check-in">
        {checkin?.error ? <ErrorState message={checkin.error} /> : (
          <>
            <p className="mb-3 text-sm text-muted">Event chain: {checkin?.event_chain?.join(" → ")}</p>
            <RunSteps steps={(checkin?.trace ?? []).map((t: any) => ({ ...t, output: checkin.outputs?.[t.agent] }))} />
          </>
        )}
      </Modal>
    </>
  );
}

export default function RoadmapPage() {
  return <AppShell><Inner /></AppShell>;
}
