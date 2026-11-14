"use client";
import { useState } from "react";
import { CheckCircle2, MessageSquareQuote, ShieldCheck, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { RunSteps } from "./AgentFeed";
import { Badge, Button, ErrorState, Textarea } from "./ui";

export type Viva = {
  id: number;
  status: string;
  questions: { id: number; prompt: string; focus: string }[];
  answers?: string[];
  evaluation?: any;
};

export function VivaPanel({ viva, onDone }: { viva: Viva; onDone?: (passed: boolean) => void }) {
  const [answers, setAnswers] = useState<string[]>(viva.questions.map((_, i) => viva.answers?.[i] ?? ""));
  const [result, setResult] = useState<any>(viva.status !== "pending" ? { passed: viva.status === "passed", evaluation: viva.evaluation } : null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await api(`/api/viva/${viva.id}/answer`, { body: { answers } });
      setResult(r);
      onDone?.(r.passed);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const ev = result?.evaluation;
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3 rounded-lg border border-accent/30 bg-accent/5 p-3 text-sm">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
        <p className="text-muted">
          Explain <em>your own</em> code. Answers must reference the identifiers and logic in your submission. Tier 3 requires every answer to
          pass a deterministic code-grounding check{ev?.llm_pass !== undefined && ev?.llm_pass !== null ? " and an LLM grade" : ""}.
        </p>
      </div>
      {viva.questions.map((q, i) => {
        const a = ev?.answers?.[i];
        return (
          <div key={q.id}>
            <div className="mb-2 flex items-start gap-2 text-sm font-medium">
              <MessageSquareQuote className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
              <span>Q{i + 1}. {q.prompt}</span>
            </div>
            <Textarea rows={5} disabled={!!result} value={answers[i]} maxLength={4000} placeholder="Explain in your own words..." onChange={(e) => setAnswers(answers.map((x, j) => (j === i ? e.target.value : x)))} />
            {a && (
              <div className={cn("mt-2 rounded-lg border p-3 text-xs", a.grounding.passed ? "border-ok/30 bg-ok/5" : "border-bad/30 bg-bad/5")}>
                <div className="flex items-center gap-1.5 font-medium">
                  {a.grounding.passed ? <CheckCircle2 className="h-3.5 w-3.5 text-ok" /> : <XCircle className="h-3.5 w-3.5 text-bad" />}
                  Grounding {a.grounding.passed ? "passed" : "failed"} · {a.grounding.word_count} words
                  {a.llm_score !== null && <span className="ml-2 text-muted">LLM score {a.llm_score.toFixed(2)}</span>}
                </div>
                {a.grounding.identifiers_referenced.length > 0 && <div className="mt-1 text-muted">Referenced: {a.grounding.identifiers_referenced.map((x: string) => <code key={x} className="mr-1 font-mono text-accent">{x}</code>)}</div>}
                <div className="mt-1 text-muted">{a.feedback}</div>
              </div>
            )}
          </div>
        );
      })}
      {error && <ErrorState message={error} />}
      {!result && <Button className="w-full" loading={busy} disabled={answers.some((a) => a.trim().length < 20)} onClick={submit}>Submit viva answers</Button>}
      {result && (
        <div className={cn("rounded-xl border p-4", result.passed ? "border-ok/40 bg-ok/5" : "border-bad/40 bg-bad/5")}>
          <div className="flex items-center gap-2 font-semibold">
            {result.passed ? <CheckCircle2 className="text-ok" /> : <XCircle className="text-bad" />}
            {result.passed ? "Micro-Viva passed: Tier 3 verified" : "Micro-Viva not passed"}
            {ev?.engine && <Badge className="ml-auto">{ev.engine}</Badge>}
          </div>
          {!result.passed && <p className="mt-1 text-sm text-muted">Review the feedback, then resubmit the mission to receive a fresh viva.</p>}
          {result.run?.steps && <div className="mt-3"><RunSteps steps={result.run.steps} /></div>}
        </div>
      )}
    </div>
  );
}
