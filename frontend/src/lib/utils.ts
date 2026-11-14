import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const TIER_NAMES = ["Unverified", "Conceptual", "Coding", "Applied"] as const;
export const TIER_DESC = [
  "Self-claimed. Counts as zero toward any role.",
  "Passed a verified concept quiz.",
  "Passed hidden automated tests and a static audit.",
  "Applied project: hidden tests, AST audit and Micro-Viva.",
];

export const AGENT_LABEL: Record<string, string> = {
  orchestrator: "Orchestrator",
  skill_detective: "Skill Detective",
  career_architect: "Career Architect",
  learning_strategist: "Learning Strategist",
  resource_scout: "Resource Scout",
  skill_validator: "Skill Validator",
  ai_mentor: "AI Mentor",
};

export function timeAgo(iso: string) {
  const t = new Date(iso.endsWith("Z") ? iso : iso + "Z").getTime();
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function fmtDate(iso: string) {
  return new Date(iso.endsWith("Z") ? iso : iso + "Z").toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}
