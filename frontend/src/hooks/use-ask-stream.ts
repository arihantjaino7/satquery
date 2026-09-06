import { useCallback, useRef, useState } from "react";
import { askStream, type FinalPayload, type ImagePreview, type TraceEntry } from "@/lib/api";

export type RunStatus = "idle" | "streaming" | "done" | "error";

interface AskStreamState {
  status: RunStatus;
  trace: TraceEntry[];
  previews: ImagePreview[];
  maskOverlayPng: string | null;
  final: FinalPayload | null;
  error: string | null;
}

const initialState: AskStreamState = {
  status: "idle",
  trace: [],
  previews: [],
  maskOverlayPng: null,
  final: null,
  error: null,
};

export function useAskStream() {
  const [state, setState] = useState<AskStreamState>(initialState);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async (question: string, images: File[]) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setState({ ...initialState, status: "streaming" });

    try {
      for await (const evt of askStream(question, images, controller.signal)) {
        if (evt.event === "trace") {
          const entry = evt.data;
          setState((s) => ({
            ...s,
            trace: [...s.trace, entry],
            previews: entry.data.previews ?? s.previews,
            maskOverlayPng: entry.data.mask_overlay_png ?? s.maskOverlayPng,
          }));
        } else if (evt.event === "final") {
          setState((s) => ({ ...s, final: evt.data }));
        } else if (evt.event === "error") {
          setState((s) => ({ ...s, status: "error", error: evt.data.message }));
        } else if (evt.event === "end") {
          setState((s) => (s.status === "error" ? s : { ...s, status: "done" }));
        }
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setState((s) => ({ ...s, status: "error", error: (err as Error).message }));
    }
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(initialState);
  }, []);

  return { ...state, run, reset };
}
