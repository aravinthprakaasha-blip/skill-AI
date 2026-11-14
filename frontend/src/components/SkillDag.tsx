"use client";
import { useMemo } from "react";
import ReactFlow, { Background, Controls, MarkerType, type Edge, type Node } from "reactflow";
import "reactflow/dist/style.css";

type DagNode = { id: number; name: string; tier: number; target_tier: number; level: number; status: string; in_role: boolean; critical: boolean };

const STATUS = {
  met: { border: "hsl(152 66% 48%)", bg: "hsl(152 66% 48% / 0.10)" },
  ready: { border: "hsl(189 95% 52%)", bg: "hsl(189 95% 52% / 0.10)" },
  blocked: { border: "hsl(220 32% 30%)", bg: "hsl(222 38% 12%)" },
} as const;

export function SkillDag({ nodes, edges }: { nodes: DagNode[]; edges: { source: number; target: number }[] }) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const byLevel: Record<number, DagNode[]> = {};
    nodes.forEach((n) => (byLevel[n.level] ??= []).push(n));
    const rfNodes: Node[] = [];
    Object.entries(byLevel).forEach(([lvl, list]) =>
      list.forEach((n, i) => {
        const s = STATUS[n.status as keyof typeof STATUS] ?? STATUS.blocked;
        rfNodes.push({
          id: String(n.id),
          position: { x: Number(lvl) * 240, y: i * 92 },
          data: {
            label: (
              <div className="text-left">
                <div className="text-xs font-semibold text-fg">{n.name}{n.critical ? " *" : ""}</div>
                <div className="mt-0.5 text-[10px] text-muted">T{n.tier} → T{n.target_tier} · {n.in_role ? "required" : "prerequisite"}</div>
              </div>
            ),
          },
          style: { border: `1px solid ${s.border}`, background: s.bg, borderRadius: 10, width: 190, padding: 8, color: "inherit" },
          sourcePosition: "right" as any,
          targetPosition: "left" as any,
        });
      }),
    );
    const rfEdges: Edge[] = edges.map((e) => ({
      id: `${e.source}-${e.target}`, source: String(e.source), target: String(e.target), animated: true,
      style: { stroke: "hsl(214 98% 62% / 0.6)" }, markerEnd: { type: MarkerType.ArrowClosed, color: "hsl(214 98% 62%)" },
    }));
    return { rfNodes, rfEdges };
  }, [nodes, edges]);

  return (
    <div className="h-[420px] w-full overflow-hidden rounded-lg border border-line bg-bg/40">
      <ReactFlow nodes={rfNodes} edges={rfEdges} fitView nodesDraggable={false} nodesConnectable={false} proOptions={{ hideAttribution: true }}>
        <Background color="hsl(220 32% 19%)" gap={24} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
