"use client";
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import { cn, TIER_DESC, TIER_NAMES } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap",
  {
    variants: {
      variant: {
        primary: "bg-accent text-bg hover:bg-accent/90 shadow-glow",
        secondary: "bg-panel-2 text-fg border border-line hover:border-accent/50",
        ghost: "text-muted hover:text-fg hover:bg-panel-2",
        danger: "bg-bad/15 text-bad border border-bad/30 hover:bg-bad/25",
        ok: "bg-ok/15 text-ok border border-ok/30 hover:bg-ok/25",
      },
      size: { sm: "h-8 px-3 text-xs", md: "h-10 px-4", lg: "h-12 px-6 text-base" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} disabled={disabled || loading} {...props}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  ),
);
Button.displayName = "Button";

export function Card({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-line bg-panel/80 backdrop-blur-sm", className)} {...p} />;
}
export function CardHeader({ title, subtitle, action, className }: { title: React.ReactNode; subtitle?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 border-b border-line px-5 py-4", className)}>
      <div className="min-w-0">
        <h3 className="font-semibold">{title}</h3>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
export function CardBody({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...p} />;
}

export function Badge({ className, tone = "default", ...p }: React.HTMLAttributes<HTMLSpanElement> & { tone?: "default" | "accent" | "ok" | "warn" | "bad" }) {
  const tones = {
    default: "border-line bg-panel-2 text-muted",
    accent: "border-accent/30 bg-accent/10 text-accent",
    ok: "border-ok/30 bg-ok/10 text-ok",
    warn: "border-warn/30 bg-warn/10 text-warn",
    bad: "border-bad/30 bg-bad/10 text-bad",
  };
  return <span className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium", tones[tone], className)} {...p} />;
}

const tierStyles = [
  "border-tier0/40 bg-tier0/10 text-tier0",
  "border-tier1/40 bg-tier1/10 text-tier1",
  "border-tier2/40 bg-tier2/10 text-tier2",
  "border-tier3/40 bg-tier3/10 text-tier3",
];
export function TierBadge({ tier, short = false }: { tier: number; short?: boolean }) {
  return (
    <span title={TIER_DESC[tier]} className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold", tierStyles[tier])}>
      T{tier}
      {!short && <span className="font-normal opacity-90">{TIER_NAMES[tier]}</span>}
    </span>
  );
}

export function TierBar({ tier, required }: { tier: number; required?: number | null }) {
  return (
    <div className="flex gap-1" aria-label={`Tier ${tier} of 3`}>
      {[1, 2, 3].map((t) => (
        <div
          key={t}
          className={cn(
            "h-1.5 flex-1 rounded-full",
            t <= tier ? ["", "bg-tier1", "bg-tier2", "bg-tier3"][tier] : "bg-line",
            required && t <= required && t > tier && "bg-warn/40",
          )}
        />
      ))}
    </div>
  );
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn("h-10 w-full rounded-lg border border-line bg-bg/60 px-3 text-sm placeholder:text-muted/60 focus:border-accent/60 focus:outline-none", className)} {...p} />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...p }, ref) => (
  <textarea ref={ref} className={cn("w-full rounded-lg border border-line bg-bg/60 p-3 text-sm placeholder:text-muted/60 focus:border-accent/60 focus:outline-none", className)} {...p} />
));
Textarea.displayName = "Textarea";

export function Label({ className, ...p }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1.5 block text-xs font-medium uppercase tracking-wide text-muted", className)} {...p} />;
}

export function Select({ className, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("h-10 w-full rounded-lg border border-line bg-bg/60 px-3 text-sm focus:border-accent/60 focus:outline-none", className)} {...p} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-panel-2", className)} />;
}

export function PageSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-64" />
      <div className="grid gap-4 md:grid-cols-3">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      <Skeleton className="h-72" />
    </div>
  );
}

export function EmptyState({ title, body, action, icon }: { title: string; body?: React.ReactNode; action?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line p-10 text-center">
      <div className="mb-3 text-muted">{icon ?? <Inbox className="h-8 w-8" />}</div>
      <p className="font-medium">{title}</p>
      {body && <p className="mt-1 max-w-md text-sm text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-bad/30 bg-bad/5 p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
      <div className="flex-1">
        <p className="text-bad">{message}</p>
        {onRetry && (
          <button onClick={onRetry} className="mt-2 text-xs text-muted underline hover:text-fg">
            Try again
          </button>
        )}
      </div>
    </div>
  );
}

export function Progress({ value, className, tone = "accent" }: { value: number; className?: string; tone?: "accent" | "ok" | "warn" }) {
  const bg = { accent: "bg-accent", ok: "bg-ok", warn: "bg-warn" }[tone];
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-line", className)}>
      <div className={cn("h-full rounded-full transition-all duration-700", bg)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function Stat({ label, value, hint, icon }: { label: string; value: React.ReactNode; hint?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-muted">
        {label}
        {icon}
      </div>
      <div className="mt-2 text-3xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; wide?: boolean }) {
  React.useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    if (open) window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 p-4 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} className={cn("max-h-[90vh] w-full overflow-y-auto rounded-xl border border-line bg-panel shadow-2xl", wide ? "max-w-3xl" : "max-w-xl")} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h3 className="font-semibold">{title}</h3>
          <button onClick={onClose} className="text-muted hover:text-fg" aria-label="Close">✕</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
