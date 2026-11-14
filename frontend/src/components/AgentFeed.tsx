"use client";
import { CheckCircle2, Circle, XCircle } from "lucide-react";
import { useLiveEvents } from "@/lib/live";
import { AGENT_LABEL, cn } from "@/lib/utils";
import { Badge, Card, CardHeader } from "./ui";

export type Step = { seq: number; agent: string; task: string; status: string; duration_ms: number; output?: any; event?: string };

export function summarize(step: Step): string {
  const o = step.output || {};
  if (o.status === "error") return o.error;
  switch (`${step.agent}.${step.task}`) {
    case "skill_detective.profile_scan":
      return `${o.claims_recorded?.length ?? 0} claim(s) recorded as Tier 0; ${o.verified_count ?? 0} verified skill(s)`;
    case "skill_detective.record_evidence":
      return o.granted ? `${o.skill}: Tier ${o.tier_before} → ${o.tier_after}` : `No tier change: ${o.reason ?? "requirements not met"}`;
    case "skill_detective.transferable_skills":
      return `${o.transferable?.length ?? 0} verified skill(s) transfer to ${o.to_role}`;
    case "skill_detective.activity_check":
      return o.stalled ? `Inactive for ${o.days_inactive} day(s)` : "Learner is active - no intervention";
    case "career_architect.gap_analysis":
      return `${o.role_title ?? o.role}: ${o.match_score}% match, ${o.gaps?.length ?? 0} gap(s)`;
    case "learning_strategist.generate_roadmap":
      return `${o.items_created} task(s), ${o.total_hours}h, ${o.archived?.length ?? 0} archived`;
    case "learning_strategist.update_progress":
      return `${o.items_completed?.length ?? 0} item(s) completed${o.next_item ? `; next: ${o.next_item.skill}` : ""}`;
    case "learning_strategist.add_remediation":
      return o.added ? `Remediation task added with ${o.resources_attached} resource(s)` : o.reason;
    case "learning_strategist.rebalance":
      return `Rescheduled: ${o.total_hours ?? 0}h over ${o.weeks_needed ?? 0} week(s)`;
    case "resource_scout.attach_resources":
      return `Attached resources to ${o.items_enriched} task(s) via ${o.retrieval}`;
    case "resource_scout.find_remediation":
      return `${o.resources?.length ?? 0} resource(s) for "${String(o.query).slice(0, 40)}"`;
    case "skill_validator.validate":
      return `${o.verdict}: hidden ${o.tests?.hidden}, audit ${o.audit?.passed ? "clean" : "failed"} (${o.tests?.engine})`;
    case "ai_mentor.start_viva":
      return `Micro-Viva opened with ${o.questions?.length ?? 0} question(s)`;
    default:
      return o.message || o.diagnosis || o.task || "";
  }
}

export function RunSteps({ steps, running }: { steps: Step[]; running?: boolean }) {
  return (
    <ol className="space-y-2">
      {steps.map((s) => (
        <li key={s.seq} className="flex gap-3 rounded-lg border border-line bg-bg/40 p-3">
          {s.status === "ok" ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{AGENT_LABEL[s.agent] ?? s.agent}</span>
              <span className="font-mono text-xs text-muted">{s.task}</span>
              <span className="ml-auto text-xs text-muted tabular-nums">{s.duration_ms}ms</span>
            </div>
            <p className="mt-0.5 text-sm text-muted">{summarize(s)}</p>
          </div>
        </li>
      ))}
      {running && (
        <li className="flex items-center gap-3 rounded-lg border border-dashed border-accent/40 p-3 text-sm text-accent">
          <Circle className="h-3 w-3 animate-pulseDot fill-accent" /> Orchestrator routing to next agent...
        </li>
      )}
    </ol>
  );
}

/** Live stream of agent activity over WebSocket. */
export function LiveAgentFeed({ className }: { className?: string }) {
  const { events, connected } = useLiveEvents();
  const finished = events.filter((e) => e.type === "agent_finished" || e.type === "run_finished").slice(0, 12);
  return (
    <Card className={className}>
      <CardHeader
        title="Live agent activity"
        subtitle="Streamed from the orchestrator over WebSocket"
        action={<Badge tone={connected ? "ok" : "warn"}>{connected ? "connected" : "reconnecting"}</Badge>}
      />
      <div className="max-h-80 space-y-2 overflow-y-auto p-4">
        {finished.length === 0 && <p className="text-sm text-muted">Waiting for activity. Take a quiz or submit a mission to watch the agents collaborate.</p>}
        {finished.map((e, i) =>
          e.type === "run_finished" ? (
            <div key={i} className={cn("rounded-md px-3 py-1.5 text-xs", e.status === "completed" ? "bg-ok/10 text-ok" : "bg-bad/10 text-bad")}>
              Run {e.status}: {e.event_chain?.join(" → ")}
            </div>
          ) : (
            <div key={i} className="text-sm">
              <span className="font-medium text-accent">{AGENT_LABEL[e.agent!] ?? e.agent}</span>{" "}
              <span className="text-muted">{summarize(e as unknown as Step)}</span>
            </div>
          ),
        )}
      </div>
    </Card>
  );
}
