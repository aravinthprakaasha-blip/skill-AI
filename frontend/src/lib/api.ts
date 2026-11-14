export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "sf_token";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable */
  }
}

function detailMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const d = detail[0] as { msg?: string; loc?: string[] };
    return `${d.loc?.slice(-1)[0] ?? "input"}: ${d.msg ?? "invalid"}`;
  }
  return "Request failed";
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token && opts.auth !== false) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: opts.method || (opts.body !== undefined ? "POST" : "GET"),
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the SkillForge API. Is the backend running?");
  }
  if (res.status === 401 && typeof window !== "undefined" && opts.auth !== false) {
    setToken(null);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, detailMessage((data as { detail?: unknown }).detail));
  return data as T;
}

export const wsUrl = (token: string) => `${API_URL.replace(/^http/, "ws")}/ws?token=${encodeURIComponent(token)}`;

export async function waitForRun(runId: string, onUpdate?: (run: any) => void, timeoutMs = 120_000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const run = await api(`/api/runs/${runId}`);
    onUpdate?.(run);
    if (run.status === "completed" || run.status === "failed") return run;
    await new Promise((r) => setTimeout(r, 700));
  }
  throw new ApiError(408, "The agents are taking longer than expected. Check back shortly.");
}
