"use client";
import Link from "next/link";
import { ArrowRight, Bot, Flame, Gauge, ListChecks, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { LiveAgentFeed } from "@/components/AgentFeed";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorState, PageHeader, PageSkeleton, Progress, Stat, TierBadge } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useData } from "@/lib/useData";
import { timeAgo } from "@/lib/utils";

function Inner() {
  const { me } = useAuth();
  const a = useData("/api/analytics");
  const gap = useData("/api/careers/gap");
  const rm = useData("/api/roadmap");
  const msgs = useData<any[]>("/api/mentor/messages");

  if (a.loading || gap.loading || rm.loading) return <PageSkeleton />;
  if (a.error || gap.error) return <ErrorState message={a.error || gap.error || ""} onRetry={() => { a.reload(); gap.reload(); }} />;
  const next = rm.data?.items?.find((i: any) => i.status === "pending");
  const verified = (a.data.tier_counts[1] ?? 0) + (a.data.tier_counts[2] ?? 0) + (a.data.tier_counts[3] ?? 0);

  return (
    <>
      <PageHeader title={`Welcome back, ${me?.display_name.split(" ")[0]}`} subtitle={`Target role: ${gap.data.role.title}`} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Career readiness" value={`${gap.data.match_score}%`} hint={`${gap.data.met_count}/${gap.data.core_count} core requirements met`} icon={<Gauge className="h-4 w-4" />} />
        <Stat label="Verified skills" value={verified} hint={`${a.data.tier_counts[3] ?? 0} at Tier 3 (applied)`} icon={<ShieldCheck className="h-4 w-4" />} />
        <Stat label="Roadmap" value={rm.data ? `${rm.data.progress.done}/${rm.data.progress.total}` : "-"} hint={rm.data ? `${rm.data.summary.total_hours}h remaining` : "No roadmap yet"} icon={<ListChecks className="h-4 w-4" />} />
        <Stat label="Learning streak" value={`${a.data.streak.current}d`} hint={`Best ${a.data.streak.best}d · ${a.data.streak.active_days} active day(s)`} icon={<Flame className="h-4 w-4" />} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader title="Next best action" subtitle="Chosen by the Learning Strategist from your prerequisite graph" />
            <CardBody>
              {next ? (
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{next.skill}</span>
                      <Badge tone="accent">{next.step}</Badge>
                      <span className="text-xs text-muted">→ Tier {next.target_tier}</span>
                    </div>
                    <p className="mt-1 text-sm text-muted">{next.rationale}</p>
                  </div>
                  {next.mission ? (
                    <Link href={`/missions/${next.mission.id}`}><Button>Open mission <ArrowRight className="h-4 w-4" /></Button></Link>
                  ) : (
                    <Link href={`/skills?quiz=${next.skill_id}`}><Button>Take concept check <ArrowRight className="h-4 w-4" /></Button></Link>
                  )}
                </div>
              ) : (
                <EmptyState title="Roadmap complete" body="Every required tier for your target role is verified." />
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Critical gaps" subtitle="Weighted requirements still below their target tier" action={<Link href="/career" className="text-sm text-accent">Open simulator</Link>} />
            <CardBody className="space-y-3">
              {gap.data.gaps.length === 0 && <p className="text-sm text-muted">No gaps. You meet every core requirement.</p>}
              {gap.data.gaps.slice(0, 6).map((g: any) => (
                <div key={g.skill_id} className="flex items-center gap-3">
                  <div className="w-44 truncate text-sm">{g.name}{g.critical && <span className="ml-1 text-bad">*</span>}</div>
                  <Progress className="flex-1" value={(g.verified_tier / g.required_tier) * 100} tone={g.verified_tier ? "warn" : "accent"} />
                  <div className="flex w-28 justify-end gap-1"><TierBadge tier={g.verified_tier} short /><span className="text-xs text-muted">/ T{g.required_tier}</span></div>
                </div>
              ))}
            </CardBody>
          </Card>
        </div>

        <div className="space-y-6">
          <LiveAgentFeed />
          <Card>
            <CardHeader title="AI Mentor" action={<Link href="/mentor" className="text-sm text-accent">Open</Link>} />
            <CardBody className="space-y-3">
              {(msgs.data ?? []).filter((m) => m.role === "mentor").slice(-3).reverse().map((m) => (
                <div key={m.id} className="rounded-lg border border-line bg-bg/40 p-3 text-sm">
                  <div className="mb-1 flex items-center gap-2 text-xs text-muted"><Bot className="h-3.5 w-3.5 text-accent" />{timeAgo(m.created_at)}</div>
                  {m.content}
                </div>
              ))}
              {!msgs.data?.length && <p className="text-sm text-muted">No messages yet.</p>}
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  );
}

export default function Dashboard() {
  return <AppShell><Inner /></AppShell>;
}
