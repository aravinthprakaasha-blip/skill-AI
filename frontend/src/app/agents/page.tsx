"use client";
import { AppShell } from "@/components/AppShell";
import { LiveAgentFeed } from "@/components/AgentFeed";
import { RunList } from "@/components/RunList";
import { ErrorState, PageHeader, PageSkeleton } from "@/components/ui";
import { useData } from "@/lib/useData";

function Inner() {
  const { data, error, loading, reload } = useData<any[]>("/api/runs");
  if (loading) return <PageSkeleton />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  return (
    <>
      <PageHeader title="Agent Runs" subtitle="Every LangGraph workflow: the event, the orchestrator's routing, and each agent's structured output." />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2"><RunList runs={data!} /></div>
        <LiveAgentFeed />
      </div>
    </>
  );
}

export default function AgentsPage() {
  return <AppShell><Inner /></AppShell>;
}
