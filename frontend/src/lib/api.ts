// Types + the SSE parser for POST /api/ask. Mirrors satquery/api/app.py and
// satquery/agent/state.py's TraceEntry — keep in sync if either changes.

export type NodeStatus = "ok" | "warn" | "fatal" | "skipped";

export interface ImagePreview {
  index: number;
  modality: string;
  png: string; // data:image/png;base64,...
}

export interface TraceEntryData {
  previews?: ImagePreview[];
  mask_overlay_png?: string;
  [key: string]: unknown;
}

export interface TraceEntry {
  node: string;
  status: NodeStatus;
  message: string;
  data: TraceEntryData;
  duration_ms: number;
}

export interface ConfidenceComponent {
  score: number;
  explanation: string;
}

export interface Confidence {
  components: Record<string, ConfidenceComponent>;
  overall: number;
}

export interface FinalPayload {
  outcome: "answered" | "rejected" | "clarify" | "degraded" | "pending";
  task: string | null;
  answer: string | null;
  confidence: Confidence | null;
  plan: { chosen: string | null } | null;
}

export type AskStreamEvent =
  | { event: "trace"; data: TraceEntry }
  | { event: "final"; data: FinalPayload }
  | { event: "error"; data: { message: string } }
  | { event: "end"; data: Record<string, never> };

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

/** POST the question + images and yield one AskStreamEvent per SSE message
 * as it arrives. Hand-rolled rather than EventSource because EventSource
 * can't do POST/multipart — this reads the fetch response body stream
 * directly and splits it on the SSE blank-line frame boundary.
 */
export async function* askStream(
  question: string,
  images: File[],
  signal?: AbortSignal,
): AsyncGenerator<AskStreamEvent> {
  const form = new FormData();
  form.append("question", question);
  for (const image of images) form.append("images", image);

  const res = await fetch(`${API_BASE}/api/ask`, { method: "POST", body: form, signal });
  if (!res.ok || !res.body) {
    throw new Error(`request failed: ${res.status} ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) {
        yield { event, data: JSON.parse(data) } as AskStreamEvent;
      }
      boundary = buffer.indexOf("\n\n");
    }
  }
}
