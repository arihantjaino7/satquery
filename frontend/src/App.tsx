import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Hero } from "@/components/satquery/hero";
import { UploadZone } from "@/components/satquery/upload-zone";
import { ThemeToggle } from "@/components/satquery/theme-toggle";
import { ImageCanvas } from "@/components/satquery/image-canvas";
import { TracePanel } from "@/components/satquery/trace-panel";
import { AnswerPanel } from "@/components/satquery/answer-panel";
import { useAskStream } from "@/hooks/use-ask-stream";

function App() {
  const [files, setFiles] = useState<File[]>([]);
  const [question, setQuestion] = useState("");
  const { status, trace, previews, maskOverlayPng, final, error, run } = useAskStream();

  const isStreaming = status === "streaming";
  const canSubmit = files.length > 0 && question.trim().length > 0 && !isStreaming;
  const hasRun = trace.length > 0 || previews.length > 0 || final !== null;

  const handleSubmit = () => {
    if (!canSubmit) return;
    run(question.trim(), files);
  };

  return (
    <div className="o-ground min-h-svh bg-background text-foreground">
      <Hero />

      <main id="query" className="o-console px-6 py-20">
        <div className="mx-auto max-w-3xl">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <p className="font-mono text-[11px] tracking-[0.2em] text-muted-foreground">01 · DOWNLINK</p>
              <h2 className="mt-2 text-2xl font-light tracking-tight sm:text-3xl">
                Drop the imagery. Ask in plain English.
              </h2>
            </div>
            <ThemeToggle />
          </div>

          <div className="o-console-panel space-y-3 p-5 sm:p-6">
            <UploadZone files={files} onFilesChange={setFiles} disabled={isStreaming} />
            <Textarea
              placeholder="What changed between these two images?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={isStreaming}
              rows={3}
            />
            <Button onClick={handleSubmit} disabled={!canSubmit} className="w-full">
              {isStreaming ? (
                <>
                  <Loader2 className="size-4 animate-spin" /> Running pipeline…
                </>
              ) : (
                "Ask"
              )}
            </Button>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
        </div>
      </main>

      {hasRun && (
        <section className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-6 pb-16 lg:grid-cols-2">
          <div className="space-y-6">
            <ImageCanvas previews={previews} maskOverlayPng={maskOverlayPng} />
            <AnswerPanel final={final} />
          </div>
          <div className="lg:sticky lg:top-6 lg:h-[calc(100svh-3rem)]">
            <TracePanel trace={trace} isStreaming={isStreaming} />
          </div>
        </section>
      )}
    </div>
  );
}

export default App;
