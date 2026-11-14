"use client";
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { RunSteps } from "./AgentFeed";
import { Badge, Card, EmptyState, ErrorState } from "./ui";
import { cn, fmtDate } from "@/lib/utils";

export function RunList({ runs }: { runs: any[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!runs.length) return <EmptyState title="No workflow runs yet" />;
  return (
    <div className="space-y-2">
      {runs.map((r) => (
        <Card key={r.id}>
          <button className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left text-sm" onClick={() => setOpen(open === r.id ? null : r.id)}>
            <Badge tone="accent">{r.event}</Badge>
            {r.event_chain.length > 1 && <span className="text-xs text-muted">→ {r.event_chain.slice(1).join(" → ")}</span>}
            <span className="text-xs text-muted">{r.steps.length} agent step(s)</span>
            <Badge tone={r.status === "completed" ? "ok" : r.status === "failed" ? "bad" : "warn"} className="ml-auto">{r.status}</Badge>
            <span className="text-xs text-muted">{fmtDate(r.created_at)}</span>
            <ChevronDown className={cn("h-4 w-4 text-muted transition-transform", open === r.id && "rotate-180")} />
          </button>
          {open === r.id && (
            <div className="space-y-3 border-t border-line p-4">
              <RunSteps steps={r.steps} />
              <details className="text-xs">
                <summary className="cursor-pointer text-muted">Structured JSON exchanged between agents</summary>
                <pre className="mt-2 max-h-96 overflow-auto rounded-lg bg-bg/60 p-3 font-mono">{JSON.stringify(r.steps.map((s: any) => ({ agent: s.agent, task: s.task, output: s.output })), null, 2)}</pre>
              </details>
              {r.error && <ErrorState message={r.error} />}
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}
