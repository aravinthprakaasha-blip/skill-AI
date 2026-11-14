"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { BadgeCheck, Search } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Button, Card, Input, PageHeader } from "@/components/ui";

function Inner() {
  const router = useRouter();
  const [value, setValue] = useState("");
  function go(e: React.FormEvent) {
    e.preventDefault();
    const id = value.trim().replace(/\/$/, "").split("/verify/").pop()?.split(/[/?#]/)[0];
    if (id) router.push(`/verify/${encodeURIComponent(id)}`);
  }
  return (
    <>
      <PageHeader title="Verify a candidate" subtitle="Paste a SkillForge proof-of-skill link or ledger id shared by a candidate." />
      <Card className="max-w-2xl p-6">
        <form onSubmit={go} className="flex gap-2">
          <Input value={value} onChange={(e) => setValue(e.target.value)} placeholder="https://…/verify/AbC123xyz or AbC123xyz" />
          <Button type="submit"><Search className="h-4 w-4" /> Verify</Button>
        </form>
        <ul className="mt-6 space-y-2 text-sm text-muted">
          {[
            "Only Tier 1+ skills proven by assessments are shown; self-claims never appear.",
            "Each entry is part of a SHA-256 hash chain, so edits after the fact are detectable.",
            "Tier 3 means hidden tests, an AST audit and a code-grounded Micro-Viva all passed.",
            "Candidates' code, hidden tests and private profile data are never exposed.",
          ].map((t) => <li key={t} className="flex gap-2"><BadgeCheck className="h-4 w-4 shrink-0 text-ok" />{t}</li>)}
        </ul>
      </Card>
    </>
  );
}

export default function RecruiterPage() {
  return <AppShell roles={["recruiter", "admin"]}><Inner /></AppShell>;
}
