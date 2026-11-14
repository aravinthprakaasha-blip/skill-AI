"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { RunSteps } from "./AgentFeed";
import { Badge, Button, ErrorState, Modal, Skeleton } from "./ui";

export function QuizModal({ skillId, onClose, onDone }: { skillId: number | null; onClose: () => void; onDone: () => void }) {
  const [quiz, setQuiz] = useState<any>(null);
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setQuiz(null); setAnswers({}); setResult(null); setError(null);
    if (skillId) api(`/api/skills/${skillId}/quiz`).then(setQuiz).catch((e) => setError(e.message));
  }, [skillId]);

  async function submit() {
    setBusy(true);
    try {
      const r = await api(`/api/skills/${skillId}/quiz`, { body: { answers } });
      setResult(r);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={!!skillId} onClose={onClose} title={quiz ? `Concept check: ${quiz.skill.name}` : "Concept check"} wide>
      {error && <ErrorState message={error} />}
      {!quiz && !error && <Skeleton className="h-64" />}
      {quiz && !result && (
        <div className="space-y-5">
          <p className="text-sm text-muted">Score at least {quiz.pass_pct}% to earn Tier 1. Answers are graded on the server.</p>
          {quiz.questions.map((q: any, i: number) => (
            <fieldset key={q.id}>
              <legend className="mb-2 text-sm font-medium">{i + 1}. {q.prompt}</legend>
              <div className="grid gap-2">
                {q.options.map((o: string, j: number) => (
                  <label key={j} className={cn("flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm", answers[q.id] === j ? "border-accent bg-accent/10" : "border-line hover:border-accent/40")}>
                    <input type="radio" name={`q${q.id}`} className="accent-[hsl(189_95%_52%)]" checked={answers[q.id] === j} onChange={() => setAnswers({ ...answers, [q.id]: j })} />
                    {o}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          <div className="flex justify-end">
            <Button loading={busy} disabled={Object.keys(answers).length < quiz.questions.length} onClick={submit}>Submit answers</Button>
          </div>
        </div>
      )}
      {result && (
        <div className="space-y-5">
          <div className={cn("rounded-xl border p-4", result.passed ? "border-ok/40 bg-ok/5" : "border-bad/40 bg-bad/5")}>
            <div className="flex items-center gap-2 text-lg font-semibold">
              {result.passed ? <CheckCircle2 className="text-ok" /> : <XCircle className="text-bad" />}
              {result.score}% · {result.passed ? "Tier 1 verified" : "Not passed yet"}
            </div>
            <p className="mt-1 text-sm text-muted">Attempt {result.attempt}. Event chain: {result.run.event_chain.join(" → ")}</p>
          </div>
          <div className="space-y-2">
            {result.detail.questions.map((q: any) => (
              <div key={q.id} className="rounded-lg border border-line p-3 text-sm">
                <div className="flex items-start gap-2">{q.correct ? <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" /> : <XCircle className="h-4 w-4 shrink-0 text-bad" />}{q.prompt}</div>
                {!q.correct && <p className="mt-1 pl-6 text-muted">{q.explanation}</p>}
              </div>
            ))}
          </div>
          <div>
            <div className="mb-2 flex items-center gap-2 text-sm font-medium">Agent workflow <Badge>{result.run.status}</Badge></div>
            <RunSteps steps={result.run.steps} />
          </div>
        </div>
      )}
    </Modal>
  );
}
