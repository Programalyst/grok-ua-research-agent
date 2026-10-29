import { useEffect, useMemo, useRef } from "react";

/** Server re-encodes to PNG/JPEG and downscales to 1568px; keep in sync with backend MAX_IMAGE_UPLOAD_BYTES. */
export const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const ACCEPT = ["image/png", "image/jpeg", "image/webp"];

export interface ExistingShot {
  id: string;
  url: string;
  filename: string;
}

interface Props {
  pending: File[];
  onPendingChange: (files: File[]) => void;
  existing?: ExistingShot[];
  onRemoveExisting?: (id: string) => void;
  onError: (msg: string | null) => void;
  max: number;
  addLabel?: string;
}

/** Pick up to `max` PNG/JPEG/WebP images (≤15 MB each) with thumbnail previews. */
export function ScreenshotPicker({
  pending,
  onPendingChange,
  existing = [],
  onRemoveExisting,
  onError,
  max,
  addLabel = "+ Add image",
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const previews = useMemo(
    () => pending.map((f) => URL.createObjectURL(f)),
    [pending],
  );
  useEffect(
    () => () => previews.forEach((u) => URL.revokeObjectURL(u)),
    [previews],
  );
  const total = existing.length + pending.length;

  const onFiles = (list: FileList | null) => {
    if (!list) return;
    const errors: string[] = [];
    const accepted: File[] = [];
    for (const f of Array.from(list)) {
      if (!ACCEPT.includes(f.type))
        errors.push(`${f.name}: only PNG, JPG or WebP`);
      else if (f.size > MAX_IMAGE_BYTES)
        errors.push(`${f.name}: larger than 15 MB`);
      else if (total + accepted.length >= max)
        errors.push(`${f.name}: max ${max} images`);
      else accepted.push(f);
    }
    onError(errors.length ? errors.join("; ") : null);
    if (accepted.length) onPendingChange([...pending, ...accepted]);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div>
      <div className="thumbs">
        {existing.map((s) => (
          <figure key={s.id} className="thumb">
            <img src={s.url} alt={s.filename} />
            {onRemoveExisting && (
              <button
                type="button"
                aria-label={`Remove ${s.filename}`}
                onClick={() => onRemoveExisting(s.id)}
              >
                ×
              </button>
            )}
          </figure>
        ))}
        {pending.map((f, i) => (
          <figure
            key={`${f.name}-${i}`}
            className="thumb pending"
            title="Not uploaded yet"
          >
            <img src={previews[i]} alt={f.name} />
            <button
              type="button"
              aria-label={`Remove ${f.name}`}
              onClick={() => onPendingChange(pending.filter((_, j) => j !== i))}
            >
              ×
            </button>
          </figure>
        ))}
        {total < max && (
          <button
            type="button"
            className="thumb add"
            onClick={() => inputRef.current?.click()}
          >
            {addLabel}
            <small>{max - total} left</small>
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT.join(",")}
        multiple
        hidden
        onChange={(e) => onFiles(e.target.files)}
      />
    </div>
  );
}
