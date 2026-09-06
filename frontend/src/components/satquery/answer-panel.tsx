import type { FinalPayload } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const OUTCOME_VARIANT: Record<FinalPayload["outcome"], "default" | "secondary" | "destructive"> = {
  answered: "default",
  degraded: "secondary",
  clarify: "secondary",
  rejected: "destructive",
  pending: "secondary",
};

function ComponentBar({ label, score, explanation }: { label: string; score: number; explanation: string }) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-xs">
        <span className="capitalize text-foreground/90">{label.replace(/_/g, " ")}</span>
        <span className="font-mono text-muted-foreground">{score.toFixed(2)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary/70 transition-[width] duration-500 ease-out"
          style={{ width: `${Math.round(score * 100)}%` }}
        />
      </div>
      <p className="text-[11px] text-muted-foreground">{explanation}</p>
    </div>
  );
}

export function AnswerPanel({ final }: { final: FinalPayload | null }) {
  if (!final) {
    return (
      <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-border p-6 text-sm text-muted-foreground">
        The final answer and confidence breakdown appear here once the trace completes.
      </div>
    );
  }

  return (
    <div className="animate-in fade-in slide-in-from-bottom-2 space-y-4 rounded-lg border border-border bg-card p-4 duration-300">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={OUTCOME_VARIANT[final.outcome]} className="uppercase">
          {final.outcome}
        </Badge>
        {final.task && <Badge variant="outline">{final.task.replace(/_/g, " ")}</Badge>}
        {final.plan?.chosen && <Badge variant="outline">tool: {final.plan.chosen}</Badge>}
      </div>

      <p className={cn("text-sm leading-relaxed", final.outcome === "rejected" && "text-destructive")}>
        {final.answer}
      </p>

      {final.confidence && (
        <div className="space-y-3 border-t border-border pt-3">
          <div className="flex items-baseline justify-between">
            <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Confidence</span>
            <span className="font-mono text-sm">{final.confidence.overall.toFixed(2)}</span>
          </div>
          <div className="space-y-2.5">
            {Object.entries(final.confidence.components).map(([key, c]) => (
              <ComponentBar key={key} label={key} score={c.score} explanation={c.explanation} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
