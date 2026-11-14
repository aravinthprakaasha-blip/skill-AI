"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ChevronDown, FileCheck2, FlaskConical, Github, MessageSquareQuote, UserRound } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { QuizModal } from "@/components/QuizModal";
import { Badge, Button, Card, ErrorState, PageHeader, PageSkeleton, TierBadge, TierBar } from "@/components/ui";
import { useData } from "@/lib/useData";
import { cn, fmtDate, TIER_DESC, TIER_NAMES } from "@/lib/utils";

const KIND_ICON: Record<string, any> = { claim: UserRound, github: Github, quiz: FileCheck2, tests: FlaskConical, viva: MessageSquareQuote };

function Inner() {
  const params = useSearchParams();
  const { data, error, loading, reload } = useData("/api/skills");
  const missions = useData<any[]>("/api/missions");
  const [quiz, setQuiz] = useState<number | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "required" | "verified" | "claimed">("all");

  useEffect(() => {
    const q = params.get("quiz");
    if (q) setQuiz(Number(q));
  }, [params]);

  const grouped = useMemo(() => {
    const rows = (data?.skills ?? []).filter((s: any) =>
      filter === "all" ? true : filter === "required" ? s.required_tier : filter === "verified" ? s.tier > 0 : s.claimed && s.tier === 0);
    const g: Record<string, any[]> = {};
    rows.forEach((s: any) => (g[s.category] ??= []).push(s));
    return g;
  }, [data, filter]);

  if (loading) return <PageSkeleton />;
  if (error) return <ErrorState message={error} onRetry={reload} />;

  return (
    <>
      <PageHeader title="Skill DNA" subtitle="Every tier is derived from recorded evidence. Claims alone never raise a tier." />
      <div className="mb-6 grid gap-3 sm:grid-cols-4">
        {[0, 1, 2, 3].map((t) => (
          <Card key={t} className="p-4">
            <div className="flex items-center justify-between"><TierBadge tier={t} /><span className="text-2xl font-semibold tabular-nums">{data.skills.filter((s: any) => s.tracked && s.tier === t).length}</span></div>
            <p className="mt-2 text-xs text-muted">{TIER_DESC[t]}</p>
          </Card>
        ))}
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        {(["all", "required", "verified", "claimed"] as const).map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={cn("rounded-full border px-3 py-1 text-sm capitalize", filter === f ? "border-accent text-accent" : "border-line text-muted")}>
            {f === "claimed" ? "Claimed, unverified" : f === "required" ? "Required for my role" : f}
          </button>
        ))}
      </div>

      {Object.entries(grouped).map(([cat, rows]) => (
        <section key={cat} className="mb-6">
          <h2 className="mb-3 text-xs font-medium uppercase tracking-widest text-muted">{cat}</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {rows.map((s: any) => {
              const mission = (missions.data ?? []).find((m) => m.skill.id === s.skill_id && (s.tier < 2 ? m.kind === "coding" : m.kind === "applied"));
              return (
                <Card key={s.skill_id} className={cn("p-4", s.required_tier && s.tier < s.required_tier && "border-warn/30")}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{s.name}</span>
                        {s.critical && <Badge tone="bad">critical</Badge>}
                        {s.claimed && s.tier === 0 && <Badge>claimed</Badge>}
                      </div>
                      <p className="mt-0.5 text-xs text-muted">SFIA {s.sfia_code}{s.required_tier ? ` · role requires T${s.required_tier}` : ""}</p>
                    </div>
                    <TierBadge tier={s.tier} />
                  </div>
                  <div className="mt-3"><TierBar tier={s.tier} required={s.required_tier} /></div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    {s.tier < 1 && <Button size="sm" variant="secondary" onClick={() => setQuiz(s.skill_id)}>Concept check</Button>}
                    {s.tier >= 1 && s.tier < 3 && mission && (
                      <Link href={`/missions/${mission.id}`}><Button size="sm" variant="secondary">{mission.kind === "applied" ? "Applied project" : "Coding mission"}</Button></Link>
                    )}
                    {s.evidence.length > 0 && (
                      <button onClick={() => setOpen(open === s.skill_id ? null : s.skill_id)} className="ml-auto flex items-center gap-1 text-xs text-muted hover:text-fg">
                        {s.evidence.length} evidence <ChevronDown className={cn("h-3 w-3 transition-transform", open === s.skill_id && "rotate-180")} />
                      </button>
                    )}
                  </div>
                  {open === s.skill_id && (
                    <ol className="mt-3 space-y-2 border-t border-line pt-3">
                      {[...s.evidence].reverse().map((e: any) => {
                        const Icon = KIND_ICON[e.kind] ?? FileCheck2;
                        return (
                          <li key={e.id} className="flex gap-2 text-sm">
                            <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", e.verifying ? "text-ok" : "text-tier0")} />
                            <div>
                              <div>{e.summary}</div>
                              <div className="text-xs text-muted">{e.verifying ? `Grants up to Tier ${e.tier} (${TIER_NAMES[e.tier]})` : "Signal only, not verification"} · {fmtDate(e.created_at)}</div>
                            </div>
                          </li>
                        );
                      })}
                    </ol>
                  )}
                </Card>
              );
            })}
          </div>
        </section>
      ))}
      <QuizModal skillId={quiz} onClose={() => setQuiz(null)} onDone={reload} />
    </>
  );
}

export default function SkillsPage() {
  return <AppShell><Suspense><Inner /></Suspense></AppShell>;
}
