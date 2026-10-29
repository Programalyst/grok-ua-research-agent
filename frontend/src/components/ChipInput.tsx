import { useState, type KeyboardEvent } from "react";

interface Props {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  max?: number;
  suggestions?: string[];
}

/** Free-entry tag input: Enter or comma adds a chip, Backspace on empty removes the last one. */
export function ChipInput({
  value,
  onChange,
  placeholder,
  max = 15,
  suggestions = [],
}: Props) {
  const [draft, setDraft] = useState("");
  const add = (raw: string) => {
    const v = raw.trim();
    if (
      !v ||
      value.length >= max ||
      value.some((x) => x.toLowerCase() === v.toLowerCase())
    )
      return;
    onChange([...value, v]);
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(draft);
      setDraft("");
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };
  const unused = suggestions.filter(
    (s) => !value.some((v) => v.toLowerCase() === s.toLowerCase()),
  );
  return (
    <div>
      <div className="chips">
        {value.map((v) => (
          <span key={v} className="chip">
            {v}
            <button
              type="button"
              aria-label={`Remove ${v}`}
              onClick={() => onChange(value.filter((x) => x !== v))}
            >
              ×
            </button>
          </span>
        ))}
        <input
          value={draft}
          placeholder={value.length >= max ? `Max ${max}` : placeholder}
          disabled={value.length >= max}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          onBlur={() => {
            add(draft);
            setDraft("");
          }}
        />
      </div>
      {unused.length > 0 && (
        <div className="chip-suggestions">
          {unused.map((s) => (
            <button
              type="button"
              key={s}
              className="chip ghost"
              onClick={() => add(s)}
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
