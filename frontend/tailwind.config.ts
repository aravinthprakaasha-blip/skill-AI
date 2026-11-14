import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "hsl(var(--bg))",
        panel: "hsl(var(--panel))",
        "panel-2": "hsl(var(--panel-2))",
        line: "hsl(var(--line))",
        fg: "hsl(var(--fg))",
        muted: "hsl(var(--muted))",
        accent: "hsl(var(--accent))",
        "accent-2": "hsl(var(--accent-2))",
        ok: "hsl(var(--ok))",
        warn: "hsl(var(--warn))",
        bad: "hsl(var(--bad))",
        tier0: "hsl(var(--tier0))",
        tier1: "hsl(var(--tier1))",
        tier2: "hsl(var(--tier2))",
        tier3: "hsl(var(--tier3))",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: { glow: "0 0 0 1px hsl(var(--accent) / 0.25), 0 8px 30px -8px hsl(var(--accent) / 0.35)" },
      keyframes: { pulseDot: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.3" } } },
      animation: { pulseDot: "pulseDot 1.2s ease-in-out infinite" },
    },
  },
  plugins: [],
};
export default config;
