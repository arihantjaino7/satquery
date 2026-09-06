import { useEffect, useRef, useState } from "react";
import type { NodeStatus, TraceEntry } from "@/lib/api";
import { cn } from "@/lib/utils";

// The one bespoke component in this UI (per the build plan — everything
// else is off-the-shelf shadcn/ui). Renders trace lines as they stream in
// over SSE, one per completed pipeline node, oldest first.

const STATUS_STYLE: Record<NodeStatus, { dot: string; label: string }> = {
  ok: { dot: "bg-emerald-500", label: "text-emerald-500" },
  warn: { dot: "bg-amber-500", label: "text-amber-500" },
  fatal: { dot: "bg-red-500", label: "text-red-500" },
  skipped: { dot: "bg-muted-foreground/50", label: "text-muted-foreground" },
};

// Large base64 payloads are rendered on the canvas, not dumped as raw text
// in the expanded trace JSON.
function summarizeData(data: TraceEntry["data"]): Record<string, unknown> {
  const { previews, mask_overlay_png, ...rest } = data;
  const summary: Record<string, unknown> = { ...rest };
  if (previews) summary.previews = `[${previews.length} preview image(s) — shown on canvas]`;
  if (mask_overlay_png) summary.mask_overlay_png = "[change mask — shown as canvas overlay]";
  return summary;
}

interface TracePanelProps {
  trace: TraceEntry[];
  isStreaming: boolean;
}

export function TracePanel({ trace, isStreaming }: TracePanelProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [trace.length]);

  const toggle = (i: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  return (
    <div className="flex h-full min-h-0 flex-col rounded-lg border border-border bg-muted/40 dark:bg-black/60">
      <div className="flex shrink-0 items-center justify-between border-b border-border px-3 py-2">
        <span className="font-mono text-xs tracking-widest text-muted-foreground">EXECUTION TRACE</span>
        <span className="flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
          <span
            className={cn(
              "size-1.5 rounded-full",
              isStreaming ? "animate-pulse bg-emerald-500" : "bg-muted-foreground/40",
            )}
          />
          {isStreaming ? "streaming" : trace.length > 0 ? "complete" : "idle"}
        </span>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2 font-mono text-[13px]">
        {trace.length === 0 && (
          <p className="p-2 text-muted-foreground">Trace lines will appear here as each node completes.</p>
        )}
        {trace.map((entry, i) => {
          const style = STATUS_STYLE[entry.status];
          const isOpen = expanded.has(i);
          return (
            <div
              key={`${entry.node}-${i}`}
              className="animate-in fade-in slide-in-from-bottom-1 rounded border border-transparent duration-300 fill-mode-both hover:border-border"
            >
              <button type="button" onClick={() => toggle(i)} className="flex w-full items-start gap-2 px-2 py-1.5 text-left">
                <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", style.dot)} />
                <span className="w-6 shrink-0 text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
                <span className={cn("w-24 shrink-0 uppercase", style.label)}>{entry.node}</span>
                <span className="flex-1 truncate text-foreground/90">{entry.message}</span>
                <span className="shrink-0 text-muted-foreground">{entry.duration_ms.toFixed(1)}ms</span>
              </button>
              {isOpen && (
                <pre className="animate-in fade-in mx-2 mb-2 max-h-64 overflow-auto rounded bg-muted/40 p-2 text-[11px] whitespace-pre-wrap text-muted-foreground">
                  {JSON.stringify(summarizeData(entry.data), null, 2)}
                </pre>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
