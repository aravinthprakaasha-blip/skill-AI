"use client";
import { Award, Flame, Gauge, Target } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { AppShell } from "@/components/AppShell";
import { Badge, Card, CardBody, CardHeader, EmptyState, ErrorState, PageHeader, PageSkeleton, Stat } from "@/components/ui";
import { useData } from "@/lib/useData";
import { fmtDate } from "@/lib/utils";

const C = { accent: "hsl(189 95% 52%)", accent2: "hsl(214 98% 62%)", ok: "hsl(152 66% 48%)", bad: "hsl(352 85% 62%)", warn: "hsl(38 95% 58%)", grid: "hsl(220 32% 19%)", muted: "hsl(216 18% 62%)" };
const tooltip = { contentStyle: { background: "hsl(223 42% 9%)", border: "1px solid hsl(220 32% 19%)", borderRadius: 8, fontSize: 12 }, labelStyle: { color: "hsl(210 40% 96%)" } };

function Inner() {
  const { data: a, error, loading, reload } = useData("/api/analytics");
  if (loading) return <PageSkeleton />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  const hist = a.readiness_history.map((r: any, i: number) => ({ i: i + 1, score: r.score, role: r.role, at: fmtDate(r.at) }));
  const quiz = a.assessments.map((q: any) => ({ name: `${q.skill.split(" ")[0]} #${q.attempt}`, score: q.score, passed: q.passed }));
  const tiers = [0, 1, 2, 3].map((t) => ({ tier: `T${t}`, count: a.tier_counts[t] ?? 0 }));

  return (
    <>
      <PageHeader title="Progress Analytics" subtitle={a.role ? `Readiness tracked against ${a.role}` : undefined} />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Career readiness" value={a.readiness != null ? `${a.readiness}%` : "-"} icon={<Gauge className="h-4 w-4" />} />
        <Stat label="Missions verified" value={`${a.missions.verified}/${a.missions.total}`} hint={`${a.missions.submissions} submission(s), ${a.missions.attempted} attempted`} icon={<Target className="h-4 w-4" />} />
        <Stat label="First-attempt success"
          value={a.first_attempt.missions_rate != null ? `${a.first_attempt.missions_rate}%` : "-"}
          hint={`Missions (n=${a.first_attempt.missions_n}) · quizzes ${a.first_attempt.quizzes_rate ?? "-"}% (n=${a.first_attempt.quizzes_n})`} icon={<Award className="h-4 w-4" />} />
        <Stat label="Streak" value={`${a.streak.current}d`} hint={`Best ${a.streak.best}d · ${a.streak.active_days} active day(s)`} icon={<Flame className="h-4 w-4" />} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Skill DNA radar" subtitle="Average verified tier per category vs. your role's requirement" />
          <CardBody className="h-80">
            <ResponsiveContainer>
              <RadarChart data={a.radar} outerRadius="72%">
                <PolarGrid stroke={C.grid} />
                <PolarAngleAxis dataKey="category" tick={{ fill: C.muted, fontSize: 11 }} />
                <PolarRadiusAxis domain={[0, 3]} tickCount={4} tick={{ fill: C.muted, fontSize: 10 }} axisLine={false} />
                <Radar name="Required" dataKey="required" stroke={C.warn} fill={C.warn} fillOpacity={0.08} strokeDasharray="4 4" />
                <Radar name="Verified" dataKey="verified" stroke={C.accent} fill={C.accent} fillOpacity={0.3} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Tooltip {...tooltip} />
              </RadarChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Career readiness over time" subtitle="Recorded by the Career Architect after each workflow" />
          <CardBody className="h-80">
            {hist.length === 0 ? <EmptyState title="No readiness history yet" /> : (
              <ResponsiveContainer>
                <LineChart data={hist}>
                  <CartesianGrid stroke={C.grid} strokeDasharray="3 3" />
                  <XAxis dataKey="i" tick={{ fill: C.muted, fontSize: 11 }} label={{ value: "workflow #", fill: C.muted, fontSize: 11, position: "insideBottom", offset: -2 }} />
                  <YAxis domain={[0, 100]} tick={{ fill: C.muted, fontSize: 11 }} />
                  <Tooltip {...tooltip} labelFormatter={(_, p) => (p?.[0] ? `${p[0].payload.role} · ${p[0].payload.at}` : "")} />
                  <Line type="stepAfter" dataKey="score" stroke={C.accent} strokeWidth={2} dot={{ r: 3, fill: C.accent }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Assessment scores" subtitle="Concept quizzes; 75% required to pass" />
          <CardBody className="h-72">
            {quiz.length === 0 ? <EmptyState title="No quizzes taken yet" /> : (
              <ResponsiveContainer>
                <BarChart data={quiz}>
                  <CartesianGrid stroke={C.grid} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: C.muted, fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={50} />
                  <YAxis domain={[0, 100]} tick={{ fill: C.muted, fontSize: 11 }} />
                  <Tooltip {...tooltip} cursor={{ fill: "hsl(222 38% 12%)" }} />
                  <Bar dataKey="score" radius={[4, 4, 0, 0]}>{quiz.map((q: any, i: number) => <Cell key={i} fill={q.passed ? C.ok : C.bad} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Tier distribution" subtitle="Tracked skills by verification tier" />
          <CardBody className="h-72">
            <ResponsiveContainer>
              <BarChart data={tiers}>
                <CartesianGrid stroke={C.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="tier" tick={{ fill: C.muted, fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fill: C.muted, fontSize: 11 }} />
                <Tooltip {...tooltip} cursor={{ fill: "hsl(222 38% 12%)" }} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>{tiers.map((_, i) => <Cell key={i} fill={["hsl(216 14% 50%)", C.accent2, C.accent, C.ok][i]} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Submission history" subtitle="Every attempt is kept; first-attempt success counts attempt #1 only" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted"><tr><th className="px-5 py-2">Mission</th><th>Attempt</th><th>Language</th><th>Hidden</th><th>Status</th><th className="pr-5">When</th></tr></thead>
            <tbody className="divide-y divide-line">
              {a.submissions.slice().reverse().map((s: any, i: number) => (
                <tr key={i}><td className="px-5 py-2">{s.mission}</td><td>#{s.attempt}</td><td>{s.language}</td><td className="font-mono">{s.hidden}</td>
                  <td><Badge tone={s.status === "verified" ? "ok" : s.status.startsWith("failed") || s.status === "viva_failed" ? "bad" : "accent"}>{s.status}</Badge></td><td className="pr-5 text-xs text-muted">{fmtDate(s.at)}</td></tr>
              ))}
            </tbody>
          </table>
          {a.submissions.length === 0 && <div className="p-5 text-sm text-muted">No submissions yet.</div>}
        </div>
      </Card>
    </>
  );
}

export default function AnalyticsPage() {
  return <AppShell><Inner /></AppShell>;
}
