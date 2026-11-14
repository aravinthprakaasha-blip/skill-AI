"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import {
  Activity, BarChart3, Bot, Dna, ExternalLink, GitBranch, LayoutDashboard, LogOut, Map, Menu, Search, Shield, Swords, X,
} from "lucide-react";
import { useAuth, useRequireRole, type Me } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Logo } from "./Logo";
import { PageSkeleton } from "./ui";

const LEARNER_NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/skills", label: "Skill DNA", icon: Dna },
  { href: "/career", label: "Career Gap", icon: GitBranch },
  { href: "/roadmap", label: "Roadmap", icon: Map },
  { href: "/missions", label: "Missions", icon: Swords },
  { href: "/mentor", label: "AI Mentor", icon: Bot },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/agents", label: "Agent Runs", icon: Activity },
];
const NAV: Record<Me["role"], typeof LEARNER_NAV> = {
  learner: LEARNER_NAV,
  recruiter: [{ href: "/recruiter", label: "Verify Candidates", icon: Search }],
  admin: [{ href: "/admin", label: "Admin", icon: Shield }],
};

export function AppShell({ roles = ["learner"], children, wide }: { roles?: Me["role"][]; children: React.ReactNode; wide?: boolean }) {
  const { me, ready } = useRequireRole(roles);
  const { signOut } = useAuth();
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const nav = me ? NAV[me.role] : [];

  const sidebar = (
    <nav className="flex h-full flex-col gap-1 p-4">
      <div className="mb-6 px-2">
        <Logo href={nav[0]?.href ?? "/"} />
      </div>
      {nav.map((n) => {
        const active = path === n.href || path.startsWith(n.href + "/");
        return (
          <Link
            key={n.href}
            href={n.href}
            onClick={() => setOpen(false)}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
              active ? "bg-accent/10 text-accent" : "text-muted hover:bg-panel-2 hover:text-fg",
            )}
          >
            <n.icon className="h-4 w-4" />
            {n.label}
          </Link>
        );
      })}
      {me?.role === "learner" && me.public_id && (
        <Link href={`/verify/${me.public_id}`} target="_blank" className="mt-2 flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted hover:bg-panel-2 hover:text-fg">
          <ExternalLink className="h-4 w-4" /> Public ledger
        </Link>
      )}
      <div className="mt-auto border-t border-line pt-4">
        <div className="px-3 text-sm font-medium">{me?.display_name}</div>
        <div className="truncate px-3 text-xs capitalize text-muted">{me?.role}</div>
        <button
          onClick={() => {
            signOut();
            router.push("/login");
          }}
          className="mt-3 flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted hover:bg-panel-2 hover:text-fg"
        >
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 border-r border-line bg-panel/60 backdrop-blur lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 bg-bg/80 lg:hidden" onClick={() => setOpen(false)}>
          <aside className="h-full w-64 border-r border-line bg-panel" onClick={(e) => e.stopPropagation()}>
            {sidebar}
          </aside>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-bg/80 px-4 py-3 backdrop-blur lg:hidden">
          <Logo />
          <button onClick={() => setOpen(!open)} aria-label="Menu" className="text-muted">
            {open ? <X /> : <Menu />}
          </button>
        </header>
        <main className={cn("mx-auto p-4 sm:p-6 lg:p-8", wide ? "max-w-[1600px]" : "max-w-6xl")}>{ready ? children : <PageSkeleton />}</main>
      </div>
    </div>
  );
}
