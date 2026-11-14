import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
      <div className="font-mono text-sm text-accent">404</div>
      <h1 className="text-2xl font-semibold">This page could not be found</h1>
      <Link href="/" className="text-sm text-muted underline hover:text-fg">Back to SkillForge</Link>
    </div>
  );
}
