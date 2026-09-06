import { useRef, useState, type DragEvent } from "react";
import { ImagePlus, X } from "lucide-react";
import { cn } from "@/lib/utils";

const MAX_IMAGES = 2;

interface UploadZoneProps {
  files: File[];
  onFilesChange: (files: File[]) => void;
  disabled?: boolean;
}

export function UploadZone({ files, onFilesChange, disabled }: UploadZoneProps) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = (incoming: FileList | File[]) => {
    const next = [...files, ...Array.from(incoming)].slice(0, MAX_IMAGES);
    onFilesChange(next);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    if (disabled) return;
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };

  const removeAt = (index: number) => {
    onFilesChange(files.filter((_, i) => i !== index));
  };

  const canAddMore = files.length < MAX_IMAGES && !disabled;

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (canAddMore) setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => canAddMore && inputRef.current?.click()}
        className={cn(
          "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center transition-colors",
          canAddMore ? "cursor-pointer hover:bg-accent/40" : "opacity-60",
          dragActive ? "border-ring bg-accent/50" : "border-border",
        )}
      >
        <ImagePlus className="size-6 text-muted-foreground" />
        <p className="text-sm text-foreground">
          Drop {MAX_IMAGES - files.length > 0 ? "GeoTIFF/PNG images" : "images"} here, or click to browse
        </p>
        <p className="text-xs text-muted-foreground">1 image for VQA/captioning, 2 for change detection or fusion ({files.length}/{MAX_IMAGES})</p>
        <input
          ref={inputRef}
          type="file"
          accept="image/*,.tif,.tiff"
          multiple
          hidden
          disabled={!canAddMore}
          onChange={(e) => {
            if (e.target.files?.length) addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {files.length > 0 && (
        <ul className="grid grid-cols-2 gap-2">
          {files.map((file, i) => (
            <li
              key={`${file.name}-${i}`}
              className="animate-in fade-in slide-in-from-bottom-1 flex items-center justify-between gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm"
            >
              <span className="truncate" title={file.name}>
                {file.name}
              </span>
              {!disabled && (
                <button
                  type="button"
                  onClick={() => removeAt(i)}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={`Remove ${file.name}`}
                >
                  <X className="size-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
