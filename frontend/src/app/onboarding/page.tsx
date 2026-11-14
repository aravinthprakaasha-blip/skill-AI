"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { Logo } from "@/components/Logo";
import { RunSteps } from "@/components/AgentFeed";
import { Badge, Button, Card, ErrorState, Input, Label, PageSkeleton, Textarea } from "@/components/ui";
import { api, waitForRun } from "@/lib/api";
import { useAuth, useRequireRole } from "@/lib/auth";
import { cn } from "@/lib/utils";

type Role = { slug: string; title: string; description: string; onet_code: string; sfia_level: number };
type SkillRow = { skill_id: number; slug: string; name: string; category: string };

const STEPS = ["Profile", "Career goal", "Claimed skills", "Agents at work"];

export default function Onboarding() {
  const { ready } = useRequireRole(["learner"]);
  const { refresh } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [roles, setRoles] = useState<Role[]>([]);
  const [skills, setSkills] = useState<SkillRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ headline: "", education: "", timeline_weeks: 12, weekly_hours: 8, github: "", projects: "", certs: "" });
  const [role, setRole] = useState("");
  const [claims, setClaims] = useState<string[]>([]);
  const [run, setRun] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!ready) return;
    Promise.all([api("/api/careers/roles"), api("/api/skills"), api("/api/profile")])
      .then(([r, s, p]) => {
        setRoles(r);
        setSkills(s.skills);
        setForm((f) => ({ ...f, headline: p.headline, education: p.education, timeline_weeks: p.timeline_weeks, weekly_hours: p.weekly_hours, github: (p.github_repos || []).join("\n") }));
        if (p.target_role) setRole(p.target_role.slug);
      })
      .catch((e) => setError(e.message));
  }, [ready]);

  async function launch() {
    setBusy(true);
    setError(null);
    try {
      await api("/api/profile", {
        method: "PUT",
        body: {
          headline: form.headline, education: form.education, timeline_weeks: Number(form.timeline_weeks), weekly_hours: Number(form.weekly_hours),
          github_repos: form.github.split(/\s+/).filter(Boolean), target_role_slug: role,
          projects: form.projects.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
            const [name, url = ""] = l.split("|").map((x) => x.trim());
            return { name, url, description: "" };
          }),
          certifications: form.certs.split("\n").map((l) => l.trim()).filter(Boolean).map((name) => ({ name })),
        },
      });
      setStep(3);
      const q = await api("/api/profile/onboard", { body: { claimed_skills: claims } });
      const final = await waitForRun(q.run_id, setRun);
      setRun(final);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!ready) return <div className="p-8"><PageSkeleton /></div>;
  const categories = Array.from(new Set(skills.map((s) => s.category)));

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-8">
      <div className="mb-8 flex items-center justify-between"><Logo /><span className="text-sm text-muted">Onboarding</span></div>
      <ol className="mb-8 grid grid-cols-4 gap-2">
        {STEPS.map((s, i) => (
          <li key={s} className={cn("rounded-lg border px-3 py-2 text-xs", i === step ? "border-accent text-accent" : i < step ? "border-ok/40 text-ok" : "border-line text-muted")}>
            <span className="font-semibold">{i + 1}.</span> {s}
          </li>
        ))}
      </ol>
      {error && <div className="mb-4"><ErrorState message={error} /></div>}

      {step === 0 && (
        <Card className="space-y-4 p-6">
          <div><Label>Headline</Label><Input maxLength={200} placeholder="e.g. Final-year CS student aiming for backend roles" value={form.headline} onChange={(e) => setForm({ ...form, headline: e.target.value })} /></div>
          <div><Label>Education</Label><Input maxLength={300} placeholder="Degree, institution, year" value={form.education} onChange={(e) => setForm({ ...form, education: e.target.value })} /></div>
          <div className="grid grid-cols-2 gap-4">
            <div><Label>Timeline (weeks)</Label><Input type="number" min={1} max={104} value={form.timeline_weeks} onChange={(e) => setForm({ ...form, timeline_weeks: Number(e.target.value) })} /></div>
            <div><Label>Hours per week</Label><Input type="number" min={1} max={80} value={form.weekly_hours} onChange={(e) => setForm({ ...form, weekly_hours: Number(e.target.value) })} /></div>
          </div>
          <div><Label>GitHub repositories (one per line)</Label><Textarea rows={2} placeholder="https://github.com/you/project" value={form.github} onChange={(e) => setForm({ ...form, github: e.target.value })} /></div>
          <div><Label>Projects (one per line, optional “| url”)</Label><Textarea rows={2} placeholder="Campus inventory API | https://github.com/you/inventory" value={form.projects} onChange={(e) => setForm({ ...form, projects: e.target.value })} /></div>
          <div><Label>Certifications (one per line)</Label><Textarea rows={2} value={form.certs} onChange={(e) => setForm({ ...form, certs: e.target.value })} /></div>
          <div className="flex justify-end"><Button onClick={() => setStep(1)}>Continue <ArrowRight className="h-4 w-4" /></Button></div>
        </Card>
      )}

      {step === 1 && (
        <div className="space-y-3">
          {roles.map((r) => (
            <button key={r.slug} onClick={() => setRole(r.slug)} className={cn("w-full rounded-xl border bg-panel/70 p-5 text-left transition-colors", role === r.slug ? "border-accent shadow-glow" : "border-line hover:border-accent/40")}>
              <div className="flex items-center justify-between">
                <span className="font-semibold">{r.title}</span>
                <span className="flex gap-2"><Badge>O*NET {r.onet_code}</Badge><Badge>SFIA L{r.sfia_level}</Badge></span>
              </div>
              <p className="mt-1 text-sm text-muted">{r.description}</p>
            </button>
          ))}
          <div className="flex justify-between pt-2">
            <Button variant="ghost" onClick={() => setStep(0)}><ArrowLeft className="h-4 w-4" /> Back</Button>
            <Button disabled={!role} onClick={() => setStep(2)}>Continue <ArrowRight className="h-4 w-4" /></Button>
          </div>
        </div>
      )}

      {step === 2 && (
        <Card className="p-6">
          <p className="text-sm text-muted">Which skills do you believe you have? These start as <span className="text-tier0">Tier 0 (unverified)</span> and count for nothing until you prove them.</p>
          <div className="mt-5 space-y-4">
            {categories.map((c) => (
              <div key={c}>
                <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">{c}</div>
                <div className="flex flex-wrap gap-2">
                  {skills.filter((s) => s.category === c).map((s) => {
                    const on = claims.includes(s.name);
                    return (
                      <button key={s.slug} onClick={() => setClaims(on ? claims.filter((x) => x !== s.name) : [...claims, s.name])}
                        className={cn("flex items-center gap-1 rounded-full border px-3 py-1 text-sm", on ? "border-accent bg-accent/10 text-accent" : "border-line text-muted hover:text-fg")}>
                        {on && <Check className="h-3 w-3" />}{s.name}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-6 flex justify-between">
            <Button variant="ghost" onClick={() => setStep(1)}><ArrowLeft className="h-4 w-4" /> Back</Button>
            <Button loading={busy} onClick={launch}>Launch my agents <ArrowRight className="h-4 w-4" /></Button>
          </div>
        </Card>
      )}

      {step === 3 && (
        <Card className="p-6">
          <h2 className="font-semibold">ONBOARD workflow</h2>
          <p className="mb-4 text-sm text-muted">The orchestrator is routing your profile through the agent graph.</p>
          <RunSteps steps={run?.steps ?? []} running={!run || run.status === "running" || run.status === "queued"} />
          {run?.status === "completed" && (
            <div className="mt-6 flex justify-end"><Button onClick={() => router.push("/dashboard")}>Go to dashboard <ArrowRight className="h-4 w-4" /></Button></div>
          )}
          {run?.status === "failed" && <div className="mt-4"><ErrorState message={run.error || "Workflow failed"} onRetry={launch} /></div>}
        </Card>
      )}
    </div>
  );
}
