"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

const Monaco = dynamic(() => import("@monaco-editor/react").then((m) => m.default), { ssr: false });

/** Monaco editor with a plain-textarea fallback if the editor bundle cannot load (e.g. offline CDN). */
export function CodeEditor({ value, onChange, language }: { value: string; onChange: (v: string) => void; language: string }) {
  const [mounted, setMounted] = useState(false);
  const [fallback, setFallback] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => !mounted && setFallback(true), 10_000);
    return () => clearTimeout(t);
  }, [mounted]);

  if (fallback) {
    return (
      <div className="flex h-full flex-col">
        <div className="border-b border-line bg-warn/10 px-3 py-1 text-xs text-warn">Monaco could not load; using the basic editor.</div>
        <textarea spellCheck={false} value={value} onChange={(e) => onChange(e.target.value)} aria-label="Code editor"
          className="flex-1 resize-none bg-[#0b1020] p-4 font-mono text-sm text-fg outline-none" />
      </div>
    );
  }
  return (
    <Monaco
      height="100%"
      theme="sf-dark"
      language={language}
      value={value}
      onChange={(v) => onChange(v ?? "")}
      beforeMount={(monaco) => {
        monaco.editor.defineTheme("sf-dark", {
          base: "vs-dark",
          inherit: true,
          rules: [{ token: "comment", foreground: "64748b", fontStyle: "italic" }, { token: "keyword", foreground: "22d3ee" }, { token: "string", foreground: "34d399" }],
          colors: { "editor.background": "#0b1020", "editor.lineHighlightBackground": "#111a33", "editorLineNumber.foreground": "#334155", "editor.selectionBackground": "#1e3a5f" },
        });
        monaco.languages.typescript?.typescriptDefaults.setDiagnosticsOptions({ noSemanticValidation: true });
        monaco.languages.typescript?.javascriptDefaults.setDiagnosticsOptions({ noSemanticValidation: true });
      }}
      onMount={() => setMounted(true)}
      loading={<div className="p-4 text-sm text-muted">Loading editor...</div>}
      options={{ fontSize: 14, minimap: { enabled: false }, scrollBeyondLastLine: false, tabSize: 4, padding: { top: 12 }, fontFamily: "JetBrains Mono, Cascadia Code, Consolas, monospace" }}
    />
  );
}
