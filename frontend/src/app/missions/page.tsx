"use client";
import Link from "next/link";
import { Clock, Code2, Layers } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Badge, Card, ErrorState, PageHeader, PageSkeleton, TierBadge } from "@/components/ui";
import { useData } from "@/lib/useData";

const STATUS: Record<string, { label: string; tone: "ok" | "warn" | "bad" | "accent" }> = {
  verified: { label: "verified", tone: "ok" },
  awaiting_viva: { label: "viva pending", tone: "accent" },
  passed_tests: { label: "tests passed", tone: "accent" },
  viva_failed: { label: "viva failed", tone: "warn" },
  failed_audit: { label: "audit failed", tone: "bad" },
  failed_tests: { label: "tests failed", tone: "bad" },
};

function Inner() {
  const { data, error, loading, reload } = useData<any[]>("/api/missions");
  if (loading) return <PageSkeleton />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  const groups = [
    { kind: "coding", title: "Coding missions", sub: "Hidden tests + static audit grant Tier 2" },
    { kind: "applied", title: "Applied projects", sub: "Hidden tests + AST audit + Micro-Viva grant Tier 3" },
  ];
  return (
    <>
      <PageHeader title="Missions" subtitle="Practical assessments executed in an isolated sandbox with hidden tests." />
      {groups.map((g) => (
        <section key={g.kind} className="mb-8">
          <div className="mb-3 flex items-baseline gap-3"><h2 className="font-semibold">{g.title}</h2><span className="text-sm text-muted">{g.sub}</span></div>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {data!.filter((m) => m.kind === g.kind).map((m) => (
              <Link key={m.id} href={`/missions/${m.id}`}>
                <Card className="h-full p-5 transition-colors hover:border-accent/50">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 text-xs text-muted">{g.kind === "applied" ? <Layers className="h-4 w-4" /> : <Code2 className="h-4 w-4" />}{m.skill.name}</div>
                    <TierBadge tier={m.grants_tier} short />
                  </div>
                  <h3 className="mt-3 font-semibold">{m.title}</h3>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Badge>{m.difficulty}</Badge>
                    {m.languages.map((l: string) => <Badge key={l}>{l}</Badge>)}
                    <span className="flex items-center gap-1 text-xs text-muted"><Clock className="h-3 w-3" />{m.est_hours}h</span>
                  </div>
                  {m.best_status && <div className="mt-3"><Badge tone={STATUS[m.best_status]?.tone ?? "accent"}>{STATUS[m.best_status]?.label ?? m.best_status}</Badge></div>}
                </Card>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

export default function MissionsPage() {
  return <AppShell><Inner /></AppShell>;
}
