"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { BadgeCheck, ChevronDown, ExternalLink, FolderGit2, Link2, ShieldCheck, ShieldX } from "lucide-react";
import { Logo } from "@/components/Logo";
import { Badge, Card, CardBody, CardHeader, EmptyState, ErrorState, PageSkeleton, Progress, TierBadge, TierBar } from "@/components/ui";
import { useData } from "@/lib/useData";
import { cn, fmtDate } from "@/lib/utils";

const KIND: Record<string, string> = { quiz: "Concept quiz", tests: "Hidden automated tests", viva: "Applied project + Micro-Viva" };

function EvidenceDetail({ ev }: { ev: Record<string, any> }) {
  const rows = Object.entries(ev).filter(([k]) => k !== "checks");
  return (
    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      {rows.map(([k, v]) => <span key={k}>{k.replace(/_/g, " ")}: <span className="text-fg/80">{String(v)}</span></span>)}
      {ev.checks && <span>checks: {Object.entries(ev.checks).filter(([, v]) => v).length}/{Object.keys(ev.checks).length} passed</span>}
    </div>
  );
}

export default function VerifyPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading } = useData(`/api/verify/${encodeURIComponent(id)}`);
  const [open, setOpen] = useState<string | null>(null);

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-8">
      <div className="mb-8 flex items-center justify-between"><Logo /><Badge tone="accent"><ShieldCheck className="h-3.5 w-3.5" />Proof-of-Skill Ledger</Badge></div>
      {loading && <PageSkeleton />}
      {error && <ErrorState message={error} />}
      {data && (
        <>
          <Card className="overflow-hidden">
            <div className="bg-gradient-to-r from-accent/10 to-accent-2/10 p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h1 className="text-2xl font-semibold">{data.learner.display_name}</h1>
                  {data.learner.headline && <p className="text-muted">{data.learner.headline}</p>}
                  <p className="mt-1 font-mono text-xs text-muted">ledger id {data.learner.public_id}</p>
                </div>
                <div className={cn("flex items-center gap-2 rounded-lg border px-3 py-2 text-sm", data.ledger.chain_valid ? "border-ok/40 text-ok" : "border-bad/40 text-bad")}>
                  {data.ledger.chain_valid ? <BadgeCheck className="h-5 w-5" /> : <ShieldX className="h-5 w-5" />}
                  <div>
                    <div className="font-medium">{data.ledger.chain_valid ? "Ledger integrity verified" : "Ledger integrity check FAILED"}</div>
                    <div className="text-xs text-muted">{data.ledger.entries} entries · SHA-256 hash chain</div>
                  </div>
                </div>
              </div>
              {data.target_role && (
                <div className="mt-5">
                  <div className="flex items-center justify-between text-sm"><span>Verified match for <b>{data.target_role.title}</b> <span className="text-xs text-muted">(O*NET {data.target_role.onet_code})</span></span><span className="font-semibold">{data.target_role.match_score}%</span></div>
                  <Progress className="mt-2" value={data.target_role.match_score} />
                  <p className="mt-1 text-xs text-muted">{data.target_role.formula}</p>
                </div>
              )}
            </div>
          </Card>

          <h2 className="mb-3 mt-8 text-xs font-medium uppercase tracking-widest text-muted">Verified skills</h2>
          {data.skills.length === 0 && <EmptyState title="No verified skills yet" body="Only skills proven by assessments appear here." />}
          <div className="space-y-3">
            {data.skills.map((s: any) => (
              <Card key={s.slug}>
                <button className="flex w-full items-center gap-3 p-4 text-left" onClick={() => setOpen(open === s.slug ? null : s.slug)}>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2"><span className="font-medium">{s.skill}</span><span className="text-xs text-muted">SFIA {s.sfia_code} · {s.category}</span></div>
                    <div className="mt-2 max-w-xs"><TierBar tier={s.tier} /></div>
                  </div>
                  <TierBadge tier={s.tier} />
                  <ChevronDown className={cn("h-4 w-4 text-muted transition-transform", open === s.slug && "rotate-180")} />
                </button>
                {open === s.slug && (
                  <ol className="space-y-3 border-t border-line p-4">
                    {s.entries.map((e: any) => (
                      <li key={e.hash} className="text-sm">
                        <div className="flex flex-wrap items-center gap-2"><TierBadge tier={e.tier} short /><span className="font-medium">{KIND[e.kind] ?? e.kind}</span><span className="text-xs text-muted">{fmtDate(e.verified_at)}</span></div>
                        <div className="mt-1">{e.summary}</div>
                        <EvidenceDetail ev={e.evidence} />
                        <div className="mt-1 flex items-center gap-1 font-mono text-[10px] text-muted"><Link2 className="h-3 w-3" />{e.hash}</div>
                      </li>
                    ))}
                  </ol>
                )}
              </Card>
            ))}
          </div>

          {data.projects.length > 0 && (
            <Card className="mt-8">
              <CardHeader title="Projects" />
              <CardBody className="space-y-2">
                {data.projects.map((p: any) => (
                  <div key={p.name} className="flex items-start gap-2 text-sm">
                    <FolderGit2 className="mt-0.5 h-4 w-4 text-muted" />
                    <div>
                      {p.url ? <a href={p.url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-accent hover:underline">{p.name}<ExternalLink className="h-3 w-3" /></a> : p.name}
                      {p.description && <p className="text-muted">{p.description}</p>}
                    </div>
                  </div>
                ))}
                <p className="text-xs text-muted">Projects are self-listed; only the skills above are verified.</p>
              </CardBody>
            </Card>
          )}
          <p className="mt-8 text-center text-xs text-muted">{data.policy}</p>
        </>
      )}
    </div>
  );
}
