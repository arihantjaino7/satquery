import { useState } from "react";
import type { ImagePreview } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ImageCanvasProps {
  previews: ImagePreview[];
  maskOverlayPng: string | null;
}

export function ImageCanvas({ previews, maskOverlayPng }: ImageCanvasProps) {
  const [showMask, setShowMask] = useState(true);

  if (previews.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
        Display-stretched previews appear here once preprocessing runs.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className={cn("grid gap-3", previews.length === 2 ? "grid-cols-2" : "grid-cols-1")}>
        {previews.map((p, i) => {
          const isLast = i === previews.length - 1;
          return (
            <div
              key={p.index}
              className="animate-in fade-in zoom-in-95 relative overflow-hidden rounded-lg border border-border bg-black/20 duration-300"
            >
              <img src={p.png} alt={`${p.modality} preview ${p.index}`} className="block w-full" />
              {isLast && maskOverlayPng && showMask && (
                <img
                  src={maskOverlayPng}
                  alt="change mask overlay"
                  className="animate-in fade-in absolute inset-0 h-full w-full duration-500"
                />
              )}
              <span className="absolute bottom-1.5 left-1.5 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[11px] text-white">
                {p.modality}
              </span>
            </div>
          );
        })}
      </div>

      {maskOverlayPng && (
        <label className="flex w-fit items-center gap-2 text-xs text-muted-foreground select-none">
          <input type="checkbox" checked={showMask} onChange={(e) => setShowMask(e.target.checked)} />
          Show change mask overlay
        </label>
      )}
    </div>
  );
}
