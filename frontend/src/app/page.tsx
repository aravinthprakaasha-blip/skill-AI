"use client";
import Link from "next/link";
import { ArrowRight, Bot, CheckCircle2, Code2, Dna, FileCheck2, GitBranch, Link2, MessagesSquare, ShieldCheck, Shuffle } from "lucide-react";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui";
import { useAuth, homeFor } from "@/lib/auth";

const TIERS = [
  { t: 0, name: "Unverified", body: "What you claim. Counts as zero.", cls: "border-tier0/40 text-tier0" },
  { t: 1, name: "Conceptual", body: "Verified concept quiz, graded server-side.", cls: "border-tier1/40 text-tier1" },
  { t: 2, name: "Coding", body: "Hidden tests in a sandbox plus a static AST audit.", cls: "border-tier2/40 text-tier2" },
  { t: 3, name: "Applied", body: "Applied project, AST audit and a Micro-Viva on your own code.", cls: "border-tier3/40 text-tier3" },
];

const AGENTS = [
  ["Orchestrator", "Routes events and owns shared learner state."],
  ["Skill Detective", "Turns evidence into Skill DNA tiers."],
  ["Career Architect", "Deterministic, explainable role match scores."],
  ["Learning Strategist", "Prerequisite DAGs and adaptive roadmaps."],
  ["Resource Scout", "Vector search over official documentation."],
  ["Skill Validator", "Sandboxed hidden tests, AST audit, code review."],
  ["AI Mentor", "Socratic hints, remediation and Micro-Viva."],
];

const FEATURES = [
  { icon: Dna, title: "Four-tier Skill DNA", body: "Every skill carries evidence, history and a verification tier. Nothing is taken on trust." },
  { icon: GitBranch, title: "Career Gap Simulator", body: "Weighted, SFIA- and O*NET-coded requirements give a match score you can audit line by line." },
  { icon: Code2, title: "Mission IDE", body: "Monaco editor, visible tests, terminal output and an AI mentor in one workspace." },
  { icon: MessagesSquare, title: "Anti-cheating Micro-Viva", body: "Questions generated from your submitted code and its AST. Explain it or no Tier 3." },
  { icon: Shuffle, title: "Autonomous career pivot", body: "Change goals and keep every verified skill. Only genuinely missing work is planned." },
  { icon: Link2, title: "Proof-of-Skill ledger", body: "A hash-chained public page recruiters can check. No private data, no hidden tests." },
];

export default function Landing() {
  const { me } = useAuth();
  return (
    <div className="relative overflow-hidden">
      <div className="grid-bg pointer-events-none absolute inset-0 h-[700px]" />
      <header className="relative mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Logo />
        <div className="flex items-center gap-2">
          {me ? (
            <Link href={homeFor(me)}><Button>Open app <ArrowRight className="h-4 w-4" /></Button></Link>
          ) : (
            <>
              <Link href="/login"><Button variant="ghost">Sign in</Button></Link>
              <Link href="/register"><Button>Get started</Button></Link>
            </>
          )}
        </div>
      </header>

      <section className="relative mx-auto max-w-6xl px-6 pb-20 pt-16 text-center sm:pt-24">
        <div className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/5 px-3 py-1 text-xs text-accent">
          <ShieldCheck className="h-3.5 w-3.5" /> Evidence-based competency verification
        </div>
        <h1 className="mx-auto max-w-4xl text-4xl font-semibold tracking-tight sm:text-6xl">
          Don&apos;t just learn skills. <span className="text-gradient">Prove them.</span>
          <br />
          Become job-ready.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-muted">
          SkillForge AI is a multi-agent career platform that verifies what you can actually do, maps it against real job
          roles, and adapts your learning path every time you submit code.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link href="/register"><Button size="lg">Start verifying <ArrowRight className="h-4 w-4" /></Button></Link>
          <Link href="/login?demo=1"><Button size="lg" variant="secondary">Explore the demo learner</Button></Link>
        </div>
      </section>

      <section className="relative mx-auto max-w-6xl px-6 pb-20">
        <h2 className="mb-2 text-center text-sm font-medium uppercase tracking-widest text-accent">Skill DNA</h2>
        <p className="mb-8 text-center text-2xl font-semibold">Four tiers. Each one earned with evidence.</p>
        <div className="grid gap-4 md:grid-cols-4">
          {TIERS.map((t) => (
            <div key={t.t} className={`rounded-xl border bg-panel/70 p-5 ${t.cls}`}>
              <div className="text-xs font-semibold">TIER {t.t}</div>
              <div className="mt-1 text-lg font-semibold text-fg">{t.name}</div>
              <p className="mt-2 text-sm text-muted">{t.body}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 text-center text-xs text-muted">Tier 3 is never granted on LLM judgement alone: tests, AST audit and a code-grounded viva must all pass.</p>
      </section>

      <section className="relative mx-auto max-w-6xl px-6 pb-20">
        <div className="grid gap-4 md:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-xl border border-line bg-panel/70 p-6">
              <f.icon className="h-6 w-6 text-accent" />
              <h3 className="mt-4 font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-muted">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="relative mx-auto max-w-6xl px-6 pb-24">
        <div className="rounded-2xl border border-line bg-panel/70 p-8">
          <div className="flex items-center gap-3">
            <Bot className="h-6 w-6 text-accent" />
            <h2 className="text-xl font-semibold">Seven agents, one shared learner state</h2>
          </div>
          <p className="mt-2 max-w-3xl text-sm text-muted">
            A LangGraph state machine routes ONBOARD, SUBMIT_CODE, ASSESSMENT_PASSED, ASSESSMENT_FAILED, PIVOT_GOAL and STALLED
            events through specialised agents that exchange structured JSON. Every step is logged and streamed live.
          </p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {AGENTS.map(([n, d]) => (
              <div key={n} className="rounded-lg border border-line bg-bg/40 p-4">
                <div className="flex items-center gap-2 text-sm font-medium"><CheckCircle2 className="h-4 w-4 text-ok" />{n}</div>
                <p className="mt-1 text-xs text-muted">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-line py-8 text-center text-xs text-muted">
        <FileCheck2 className="mx-auto mb-2 h-4 w-4" />
        SkillForge AI. Verified skills, not self-reported ones.
      </footer>
    </div>
  );
}
