import Link from "next/link";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2 font-semibold tracking-tight">
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
        <defs>
          <linearGradient id="sf" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0" stopColor="hsl(189 95% 52%)" />
            <stop offset="1" stopColor="hsl(214 98% 62%)" />
          </linearGradient>
        </defs>
        <path d="M16 2 28 9v14L16 30 4 23V9Z" fill="none" stroke="url(#sf)" strokeWidth="2" />
        <path d="M11 12c0-2 2-3 5-3s5 1 5 3M21 20c0 2-2 3-5 3s-5-1-5-3M11 12c0 4 10 4 10 8" fill="none" stroke="url(#sf)" strokeWidth="2" strokeLinecap="round" />
      </svg>
      <span>
        SkillForge <span className="text-gradient">AI</span>
      </span>
    </Link>
  );
}
