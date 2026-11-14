"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft, Bot, CheckCircle2, ChevronRight, FileCode2, FileText, FlaskConical, Lock, Play, Send, ShieldAlert, Sparkles, XCircle,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { RunSteps } from "@/components/AgentFeed";
import { CodeEditor } from "@/components/CodeEditor";
import { VivaPanel } from "@/components/VivaPanel";
import { Badge, Button, ErrorState, Input, PageSkeleton, Select, TierBadge } from "@/components/ui";
import { api, waitForRun } from "@/lib/api";
import { cn } from "@/lib/utils";

const FILE: Record<string, string> = { python: "main.py", javascript: "main.js", typescript: "main.ts", java: "Main.java" };
type Pane = "brief" | "docs" | "tests";
type Out = "terminal" | "tests" | "audit" | "review";

function draftKey(id: string, lang: string) {
  return `sf_draft_${id}_${lang}`;
}
function loadDraft(id: string, lang: string) {
  try { return window.localStorage.getItem(draftKey(id, lang)); } catch { return null; }
}
function saveDraft(id: string, lang: string, code: string) {
  try { window.localStorage.setItem(draftKey(id, lang), code); } catch { /* ignore */ }
}

function Brief({ text }: { text: string }) {
  const html = text
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .split("\n\n")
    .map((block) => block.split("\n").every((l) => l.startsWith("- ")) ? `<ul>${block.split("\n").map((l) => `<li>${l.slice(2)}</li>`).join("")}</ul>` : `<p>${block.replace(/\n/g, "<br/>")}</p>`)
    .join("");
  return <div className="prose-brief text-sm leading-relaxed text-fg/90" dangerouslySetInnerHTML={{ __html: html }} />;
}

function TestRows({ report }: { report: any }) {
  if (!report) return <p className="text-sm text-muted">Run your code to see results.</p>;
  return (
    <div className="space-y-1.5">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone={report.passed ? "ok" : "bad"}>{report.passed_count}/{report.total} passed</Badge>
        <span>status: {report.status}</span><span>engine: {report.engine}</span>
        {report.time_ms != null && <span>{report.time_ms}ms</span>}
        {report.limits && <span>limits: {report.limits.time_s}s CPU / {Math.round(report.limits.memory_kb / 1024)}MB</span>}
      </div>
      {report.results.map((r: any, i: number) => (
        <div key={i} className="rounded-md border border-line bg-bg/40 px-3 py-2 font-mono text-xs">
          <div className="flex items-center gap-2">{r.passed ? <CheckCircle2 className="h-3.5 w-3.5 text-ok" /> : <XCircle className="h-3.5 w-3.5 text-bad" />}<span className="font-sans text-sm">{r.name}</span></div>
          {r.input && <div className="mt-1 text-muted">input: {JSON.stringify(r.input.args ?? r.input.ops)}</div>}
          {"expected" in r && <div className="text-muted">expected: <span className="text-ok">{JSON.stringify(r.expected)}</span> · got: <span className="text-bad">{JSON.stringify(r.actual)}</span></div>}
          {r.error && <div className="text-bad">{r.error}</div>}
        </div>
      ))}
    </div>
  );
}

function AuditView({ audit }: { audit: any }) {
  if (!audit) return <p className="text-sm text-muted">The static audit runs on every Run and Submit.</p>;
  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge tone={audit.passed ? "ok" : "bad"}>{audit.passed ? "audit passed" : "audit failed"}</Badge>
        <span>engine: {audit.engine}</span>
        <span>LOC {audit.metrics?.loc} · functions {audit.metrics?.functions} · max complexity {audit.metrics?.max_complexity} · nesting {audit.metrics?.max_nesting}</span>
      </div>
      {audit.violations.map((v: any, i: number) => (
        <div key={i} className="flex items-start gap-2 text-bad"><ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />{v.message}{v.line ? <span className="text-muted"> (line {v.line})</span> : null}</div>
      ))}
      {audit.required.map((r: any, i: number) => (
        <div key={i} className="flex items-center gap-2">{r.satisfied ? <CheckCircle2 className="h-4 w-4 text-ok" /> : <XCircle className="h-4 w-4 text-bad" />}Solution {r.rule}</div>
      ))}
      {audit.features?.length > 0 && <div className="text-xs text-muted">Detected patterns: {audit.features.join(", ")}</div>}
    </div>
  );
}

function ReviewView({ review }: { review: any }) {
  if (!review || review.engine === "skipped") return <p className="text-sm text-muted">The AI code review runs after a submission. It is advisory and never changes a tier.</p>;
  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center gap-2"><Badge tone="accent">{review.engine}</Badge><span className="text-muted">{review.summary}</span></div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {(["readability", "complexity", "modularity", "practices"] as const).map((k) => (
          <div key={k} className="rounded-lg border border-line p-2 text-center"><div className="text-lg font-semibold">{review[k]}/5</div><div className="text-xs capitalize text-muted">{k}</div></div>
        ))}
      </div>
      {review.strengths?.map((s: string, i: number) => <div key={i} className="text-ok">+ {s}</div>)}
      {review.improvements?.map((s: string, i: number) => <div key={i} className="text-warn">- {s}</div>)}
    </div>
  );
}

function Inner() {
  const { id } = useParams<{ id: string }>();
  const [m, setM] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useState("python");
  const [code, setCode] = useState("");
  const [pane, setPane] = useState<Pane>("brief");
  const [out, setOut] = useState<Out>("terminal");
  const [runRes, setRunRes] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [run, setRun] = useState<any>(null);
  const [sub, setSub] = useState<any>(null);
  const [chat, setChat] = useState<{ role: string; content: string }[]>([]);
  const [msg, setMsg] = useState("");
  const [asking, setAsking] = useState(false);
  const chatEnd = useRef<HTMLDivElement>(null);

  const loadMission = useCallback(async () => {
    try {
      const data = await api(`/api/missions/${id}`);
      setM(data);
      const first = data.languages[0];
      setLang((l) => (data.languages.includes(l) ? l : first));
      const latest = data.submissions[0];
      if (latest && ["awaiting_viva"].includes(latest.status)) setSub(await api(`/api/submissions/${latest.id}`));
      const msgs = await api(`/api/mentor/messages?mission_id=${id}`);
      setChat(msgs.map((x: any) => ({ role: x.role, content: x.content })));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => { loadMission(); }, [loadMission]);
  useEffect(() => {
    if (m) setCode(loadDraft(id, lang) ?? m.starters[lang]);
  }, [m, lang, id]);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [chat]);

  function edit(v: string) {
    setCode(v);
    saveDraft(id, lang, v);
  }

  async function doRun() {
    setRunning(true);
    setOut("terminal");
    try {
      const r = await api(`/api/missions/${id}/run`, { body: { language: lang, code } });
      setRunRes(r);
      setOut(r.tests.status === "ok" && !r.tests.stderr ? "tests" : "terminal");
    } catch (e) {
      setRunRes({ error: (e as Error).message });
    } finally {
      setRunning(false);
    }
  }

  async function doSubmit() {
    setSubmitting(true);
    setSub(null);
    setRun({ status: "queued", steps: [] });
    try {
      const q = await api(`/api/missions/${id}/submit`, { body: { language: lang, code } });
      const final = await waitForRun(q.run_id, setRun);
      setRun(final);
      const s = await api(`/api/submissions/${q.submission_id}`);
      setSub(s);
      setOut("tests");
      const msgs = await api(`/api/mentor/messages?mission_id=${id}`);
      setChat(msgs.map((x: any) => ({ role: x.role, content: x.content })));
    } catch (e) {
      setRun({ status: "failed", error: (e as Error).message, steps: [] });
    } finally {
      setSubmitting(false);
    }
  }

  async function ask(text: string) {
    setAsking(true);
    setChat((c) => [...c, ...(text ? [{ role: "learner", content: text }] : [])]);
    setMsg("");
    try {
      const r = await api("/api/mentor/chat", {
        body: { mission_id: Number(id), language: lang, code, message: text, test_report: runRes?.tests ?? sub?.test_report?.visible, ast_report: runRes?.audit ?? sub?.ast_report },
      });
      setChat((c) => [...c, { role: "mentor", content: `${r.reply}\n\n${r.guiding_question}` }]);
    } catch (e) {
      setChat((c) => [...c, { role: "mentor", content: `⚠ ${(e as Error).message}` }]);
    } finally {
      setAsking(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={loadMission} />;
  if (!m) return <PageSkeleton />;

  const tests = sub ? sub.test_report?.visible : runRes?.tests;
  const audit = sub ? sub.ast_report : runRes?.audit;
  const verdict = run?.steps?.find((s: any) => s.agent === "skill_validator")?.output;

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col gap-3 lg:h-[calc(100vh-4rem)]">
      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/missions" className="text-muted hover:text-fg"><ArrowLeft className="h-5 w-5" /></Link>
        <div className="min-w-0">
          <div className="flex items-center gap-2"><h1 className="truncate font-semibold">{m.title}</h1><TierBadge tier={m.grants_tier} /></div>
          <div className="text-xs text-muted">{m.skill.name} · {m.difficulty} · {m.hidden_test_count} hidden tests · {m.execution_engine}</div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Select value={lang} onChange={(e) => setLang(e.target.value)} className="h-9 w-36" aria-label="Language">
            {m.languages.map((l: string) => <option key={l} value={l}>{l}</option>)}
          </Select>
          <Button variant="secondary" onClick={doRun} loading={running} disabled={submitting}><Play className="h-4 w-4" /> Run</Button>
          <Button onClick={doSubmit} loading={submitting} disabled={running}><Send className="h-4 w-4" /> Submit</Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[260px_minmax(0,1fr)_360px]">
        {/* explorer / brief */}
        <div className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-panel/80">
          <div className="border-b border-line p-2 text-xs">
            <div className="px-2 py-1 font-medium uppercase tracking-wide text-muted">Explorer</div>
            {([["brief", "README.md", FileText], ["docs", "DOCS.md", FileText], ["tests", "tests.visible.json", FlaskConical]] as const).map(([k, name, Icon]) => (
              <button key={k} onClick={() => setPane(k)} className={cn("flex w-full items-center gap-2 rounded px-2 py-1 text-left", pane === k ? "bg-accent/10 text-accent" : "text-muted hover:text-fg")}><Icon className="h-3.5 w-3.5" />{name}</button>
            ))}
            <div className="flex items-center gap-2 rounded bg-panel-2 px-2 py-1 text-fg"><FileCode2 className="h-3.5 w-3.5 text-accent" />{FILE[lang]}</div>
            <div className="flex items-center gap-2 px-2 py-1 text-muted/60"><Lock className="h-3.5 w-3.5" />tests.hidden ({m.hidden_test_count})</div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {pane === "brief" && <Brief text={m.brief} />}
            {pane === "docs" && (
              <div className="space-y-3 text-sm">
                <Brief text={m.docs} />
                {m.rules.require && <div><div className="text-xs uppercase text-muted">Required patterns</div>{m.rules.require.join(", ")}</div>}
                {m.rules.banned_imports && <div><div className="text-xs uppercase text-muted">Banned imports</div>{m.rules.banned_imports.join(", ")}</div>}
              </div>
            )}
            {pane === "tests" && (
              <div className="space-y-2">
                {m.visible_tests.map((t: any) => (
                  <div key={t.name} className="rounded-md border border-line p-2 font-mono text-xs">
                    <div className="font-sans text-sm">{t.name}</div>
                    <div className="mt-1 break-all text-muted">{JSON.stringify(t.input)}</div>
                    <div className="break-all text-ok">→ {JSON.stringify(t.expected)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* editor + output */}
        <div className="flex min-h-[520px] flex-col overflow-hidden rounded-xl border border-line bg-[#0b1020]">
          <div className="flex items-center gap-2 border-b border-line bg-panel px-3 py-1.5 text-xs text-muted"><FileCode2 className="h-3.5 w-3.5 text-accent" />{FILE[lang]}<span className="ml-auto">draft autosaved locally</span></div>
          <div className="min-h-0 flex-[3]"><CodeEditor value={code} onChange={edit} language={lang} /></div>
          <div className="flex min-h-0 flex-[2] flex-col border-t border-line bg-panel">
            <div className="flex gap-1 border-b border-line px-2 text-xs">
              {(["terminal", "tests", "audit", "review"] as const).map((k) => (
                <button key={k} onClick={() => setOut(k)} className={cn("border-b-2 px-3 py-2 capitalize", out === k ? "border-accent text-fg" : "border-transparent text-muted")}>{k}</button>
              ))}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {out === "terminal" && (
                <pre className="whitespace-pre-wrap font-mono text-xs text-fg/90">
                  {runRes?.error ? <span className="text-bad">{runRes.error}</span> : runRes ? (
                    <>
                      <span className="text-muted">$ run {FILE[lang]} (visible tests, {runRes.tests.engine})</span>{"\n"}
                      {runRes.tests.stdout || <span className="text-muted">(no stdout)</span>}{"\n"}
                      {runRes.tests.stderr && <span className="text-bad">{runRes.tests.stderr}</span>}
                      {"\n"}<span className={runRes.tests.passed ? "text-ok" : "text-warn"}>{runRes.tests.passed_count}/{runRes.tests.total} visible tests passed · audit {runRes.audit.passed ? "clean" : "has issues"}</span>
                    </>
                  ) : <span className="text-muted">Press Run to execute the visible tests. Submit runs the hidden tests and verification pipeline.</span>}
                </pre>
              )}
              {out === "tests" && (
                <div className="space-y-4">
                  <TestRows report={tests} />
                  {sub?.test_report?.hidden && <div><div className="mb-1 text-xs font-medium uppercase text-muted">Hidden tests</div><TestRows report={sub.test_report.hidden} /></div>}
                </div>
              )}
              {out === "audit" && <AuditView audit={audit} />}
              {out === "review" && <ReviewView review={sub?.ai_review} />}
            </div>
          </div>
        </div>

        {/* verification + mentor */}
        <div className="flex min-h-0 flex-col gap-3">
          {(run || sub) && (
            <div className="max-h-[55%] overflow-y-auto rounded-xl border border-line bg-panel/80 p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-accent" />Verification pipeline
                {run?.event_chain?.length > 0 && <span className="ml-auto truncate text-xs font-normal text-muted">{run.event_chain.join(" → ")}</span>}</div>
              {run && <RunSteps steps={run.steps ?? []} running={submitting} />}
              {run?.status === "failed" && <div className="mt-3"><ErrorState message={run.error ?? "Workflow failed"} /></div>}
              {verdict && (
                <div className={cn("mt-3 rounded-lg border p-3 text-sm", verdict.verdict === "passed" ? "border-ok/40 bg-ok/5" : "border-bad/40 bg-bad/5")}>
                  {verdict.verdict === "passed"
                    ? m.kind === "applied" ? "Hidden tests and AST audit passed. Complete the Micro-Viva below to earn Tier 3." : "Verified: Tier 2 evidence recorded on your ledger."
                    : `Not verified (${verdict.verdict.replace("_", " ")}). The mentor has added targeted remediation to your roadmap.`}
                </div>
              )}
              {sub?.viva && sub.viva.status === "pending" && (
                <div className="mt-4 border-t border-line pt-4">
                  <div className="mb-3 text-sm font-semibold">Micro-Viva</div>
                  <VivaPanel viva={sub.viva} onDone={() => loadMission()} />
                </div>
              )}
            </div>
          )}
          <div className="flex min-h-[320px] flex-1 flex-col overflow-hidden rounded-xl border border-line bg-panel/80">
            <div className="flex items-center gap-2 border-b border-line px-4 py-3 text-sm font-semibold"><Bot className="h-4 w-4 text-accent" />AI Mentor<span className="ml-auto text-xs font-normal text-muted">Socratic: hints, not answers</span></div>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
              {chat.length === 0 && <p className="text-sm text-muted">Stuck? Ask for a hint. The mentor reads your current code and latest test output.</p>}
              {chat.map((c, i) => (
                <div key={i} className={cn("whitespace-pre-wrap rounded-lg p-3 text-sm", c.role === "mentor" ? "border border-line bg-bg/40" : "ml-6 bg-accent/10 text-fg")}>{c.content}</div>
              ))}
              {asking && <div className="text-xs text-muted">Mentor is thinking...</div>}
              <div ref={chatEnd} />
            </div>
            <form className="flex gap-2 border-t border-line p-3" onSubmit={(e) => { e.preventDefault(); ask(msg); }}>
              <Input value={msg} maxLength={4000} onChange={(e) => setMsg(e.target.value)} placeholder="Ask the mentor..." />
              <Button type="button" variant="secondary" onClick={() => ask("")} disabled={asking} title="Hint from current state">Hint</Button>
              <Button type="submit" disabled={asking || !msg.trim()} aria-label="Send"><ChevronRight className="h-4 w-4" /></Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function MissionIDE() {
  return <AppShell wide><Inner /></AppShell>;
}
