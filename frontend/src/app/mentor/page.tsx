"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Bot, ChevronRight, MessageSquareQuote } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { VivaPanel } from "@/components/VivaPanel";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Input, PageHeader, PageSkeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useData } from "@/lib/useData";
import { cn, fmtDate, timeAgo } from "@/lib/utils";

function Inner() {
  const msgs = useData<any[]>("/api/mentor/messages");
  const vivas = useData<any[]>("/api/viva");
  const [chat, setChat] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [openViva, setOpenViva] = useState<number | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { if (msgs.data) setChat(msgs.data); }, [msgs.data]);
  useEffect(() => { end.current?.scrollIntoView(); }, [chat]);
  useEffect(() => {
    const pending = vivas.data?.find((v) => v.status === "pending");
    if (pending && openViva === null) setOpenViva(pending.id);
  }, [vivas.data, openViva]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    const t = text;
    setText("");
    setBusy(true);
    setChat((c) => [...c, { id: `l${Date.now()}`, role: "learner", content: t, created_at: new Date().toISOString() }]);
    try {
      const r = await api("/api/mentor/chat", { body: { message: t } });
      setChat((c) => [...c, { id: `m${Date.now()}`, role: "mentor", content: `${r.reply}\n\n${r.guiding_question}`, meta: { engine: r.engine }, created_at: new Date().toISOString() }]);
    } catch (err) {
      setChat((c) => [...c, { id: `e${Date.now()}`, role: "mentor", content: `⚠ ${(err as Error).message}`, created_at: new Date().toISOString() }]);
    } finally {
      setBusy(false);
    }
  }

  if (msgs.loading || vivas.loading) return <PageSkeleton />;
  if (msgs.error) return <ErrorState message={msgs.error} onRetry={msgs.reload} />;

  return (
    <>
      <PageHeader title="AI Mentor & Micro-Viva" subtitle="Socratic guidance, remediation notes from the agents, and your viva sessions." />
      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="flex h-[70vh] flex-col lg:col-span-3">
          <CardHeader title="Conversation" subtitle="Includes messages the agents posted after your assessments" />
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {chat.length === 0 && <EmptyState title="No messages yet" body="Ask a question about a concept, or open a mission and ask for a hint." />}
            {chat.map((m) => (
              <div key={m.id} className={cn("max-w-[85%] whitespace-pre-wrap rounded-lg p-3 text-sm", m.role === "mentor" ? "border border-line bg-bg/40" : "ml-auto bg-accent/10")}>
                {m.role === "mentor" && <div className="mb-1 flex items-center gap-1.5 text-xs text-muted"><Bot className="h-3.5 w-3.5 text-accent" />Mentor{m.meta?.task ? ` · ${m.meta.task}` : ""}{m.meta?.engine ? ` · ${m.meta.engine}` : ""} · {timeAgo(m.created_at)}</div>}
                {m.content}
              </div>
            ))}
            {busy && <div className="text-xs text-muted">Mentor is thinking...</div>}
            <div ref={end} />
          </div>
          <form onSubmit={send} className="flex gap-2 border-t border-line p-3">
            <Input value={text} maxLength={4000} onChange={(e) => setText(e.target.value)} placeholder="e.g. Why is a hash map lookup O(1) on average?" />
            <Button type="submit" disabled={busy || !text.trim()} aria-label="Send"><ChevronRight className="h-4 w-4" /></Button>
          </form>
        </Card>

        <div className="space-y-4 lg:col-span-2">
          <Card>
            <CardHeader title="Micro-Viva sessions" subtitle="Generated from your submitted code and its AST" />
            <div className="divide-y divide-line">
              {(vivas.data ?? []).length === 0 && <div className="p-5 text-sm text-muted">Pass the hidden tests of an applied project to unlock a viva.</div>}
              {(vivas.data ?? []).map((v) => (
                <div key={v.id} className="p-4">
                  <button className="flex w-full items-center gap-2 text-left text-sm" onClick={() => setOpenViva(openViva === v.id ? null : v.id)}>
                    <MessageSquareQuote className="h-4 w-4 text-accent" />
                    <span className="font-medium">{v.mission}</span>
                    <Badge tone={v.status === "passed" ? "ok" : v.status === "failed" ? "bad" : "accent"}>{v.status}</Badge>
                    <span className="ml-auto text-xs text-muted">{fmtDate(v.created_at)}</span>
                  </button>
                  {openViva === v.id && (
                    <div className="mt-4">
                      <VivaPanel viva={v} onDone={() => { vivas.reload(); msgs.reload(); }} />
                      {v.status === "failed" && <Link href={`/missions/${v.mission_id}`} className="mt-3 inline-block text-sm text-accent">Resubmit mission for a new viva →</Link>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

export default function MentorPage() {
  return <AppShell wide><Inner /></AppShell>;
}
