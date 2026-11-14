"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { api } from "@/lib/api";
import { homeFor, useAuth, type Me } from "@/lib/auth";
import { Logo } from "./Logo";
import { Button, Card, ErrorState, Input, Label } from "./ui";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const supabase = SUPABASE_URL && SUPABASE_ANON ? createClient(SUPABASE_URL, SUPABASE_ANON) : null;

// Local development demo accounts created by the backend seeder (see README).
const DEMO = [
  { label: "Demo learner (Maya)", email: "maya@demo.skillforge.dev" },
  { label: "Pivoted learner (Leo)", email: "leo@demo.skillforge.dev" },
  { label: "Recruiter", email: "recruiter@demo.skillforge.dev" },
  { label: "Admin", email: "admin@demo.skillforge.dev" },
];
const DEMO_PASSWORD = "skillforge-demo";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const params = useSearchParams();
  const { me, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<"learner" | "recruiter">("learner");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (me) router.replace(homeFor(me));
  }, [me, router]);

  async function finish(res: { token: string; user: Me }) {
    signIn(res.token, res.user);
    router.push(homeFor(res.user));
  }

  async function submit(e: React.FormEvent, override?: { email: string; password: string }) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const creds = override ?? { email, password };
      if (supabase && !override) {
        const fn = mode === "login"
          ? supabase.auth.signInWithPassword(creds)
          : supabase.auth.signUp({ ...creds, options: { data: { full_name: name, role } } });
        const { data, error: sbErr } = await fn;
        if (sbErr) throw new Error(sbErr.message);
        const token = data.session?.access_token;
        if (!token) throw new Error("Check your inbox to confirm your email, then sign in.");
        const res = await fetch(`${(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")}/api/auth/supabase`, {
          method: "POST", headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error("Could not link your Supabase account");
        await finish(await res.json());
        return;
      }
      const res = mode === "login" && !override
        ? await api("/api/auth/login", { body: creds, auth: false })
        : override
          ? await api("/api/auth/login", { body: override, auth: false })
          : await api("/api/auth/register", { body: { ...creds, display_name: name, role }, auth: false });
      await finish(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 flex justify-center"><Logo /></div>
        <Card className="p-6">
          <h1 className="text-xl font-semibold">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
          <p className="mt-1 text-sm text-muted">
            {mode === "login" ? "Sign in to continue proving your skills." : "Start building verified evidence of what you can do."}
            {supabase && <span className="block text-xs text-accent">Secured by Supabase Auth</span>}
          </p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            {mode === "register" && (
              <>
                <div>
                  <Label htmlFor="name">Display name</Label>
                  <Input id="name" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
                </div>
                <div>
                  <Label>I am a</Label>
                  <div className="grid grid-cols-2 gap-2">
                    {(["learner", "recruiter"] as const).map((r) => (
                      <button type="button" key={r} onClick={() => setRole(r)}
                        className={`rounded-lg border px-3 py-2 text-sm capitalize ${role === r ? "border-accent bg-accent/10 text-accent" : "border-line text-muted"}`}>
                        {r}
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            {error && <ErrorState message={error} />}
            <Button type="submit" className="w-full" loading={busy}>{mode === "login" ? "Sign in" : "Create account"}</Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted">
            {mode === "login" ? <>New here? <Link className="text-accent" href="/register">Create an account</Link></> : <>Have an account? <Link className="text-accent" href="/login">Sign in</Link></>}
          </p>
        </Card>
        {mode === "login" && (
          <Card className={`mt-4 p-4 ${params.get("demo") ? "border-accent/50 shadow-glow" : ""}`}>
            <p className="text-xs font-medium uppercase tracking-wide text-muted">Local demo accounts</p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {DEMO.map((d) => (
                <Button key={d.email} variant="secondary" size="sm" disabled={busy} onClick={(e) => submit(e, { email: d.email, password: DEMO_PASSWORD })}>
                  {d.label}
                </Button>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted">Demo journeys were generated by running the real agent pipeline, sandbox and viva.</p>
          </Card>
        )}
      </div>
    </div>
  );
}
