import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type {
  Game,
  GameCreate,
  ImageKind,
  Language,
  Platform,
} from "../api/types";
import { useCreateGame, useDeleteImage, useUpdateGame } from "../hooks/queries";
import { useQueryClient } from "@tanstack/react-query";
import { ChipInput } from "./ChipInput";
import { ScreenshotPicker } from "./ScreenshotPicker";

const PLATFORMS: { value: Platform; label: string }[] = [
  { value: "pc", label: "PC" },
  { value: "console", label: "Console" },
  { value: "ios", label: "iOS" },
  { value: "android", label: "Android" },
  { value: "mac", label: "Mac" },
  { value: "web", label: "Web" },
];
const LANGUAGES: { value: Language; label: string }[] = [
  { value: "en", label: "English" },
  { value: "zh", label: "中文" },
  { value: "ja", label: "日本語" },
  { value: "ko", label: "한국어" },
];
const REGION_SUGGESTIONS = [
  "North America",
  "Europe",
  "Japan",
  "Korea",
  "China",
  "SEA",
  "LATAM",
];
const MAX_IMAGES: Record<ImageKind, number> = { screenshot: 5, key_art: 2 }; // mirrors backend MAX_SCREENSHOTS / MAX_KEY_ART
const SEED_PLACEHOLDER: Record<Language, string> = {
  en: "e.g. tactics rpg, post-apoc",
  zh: "例如 战棋, 末日",
  ja: "例: SRPG, 終末",
  ko: "예: 전략 RPG, 아포칼립스",
};
const GENRE_SUGGESTIONS = [
  "Roguelike",
  "RPG",
  "Gacha",
  "Shooter",
  "Cozy",
  "Strategy",
];

type Errors = Partial<
  Record<
    "name" | "pitch" | "platforms" | "languages" | "comparable_games",
    string
  >
>;

function toDraft(g?: Game): Required<
  Pick<GameCreate, "name" | "pitch" | "description" | "differentiators">
> & {
  genres: string[];
  platforms: Platform[];
  regions: string[];
  languages: Language[];
  comparable_games: string[];
  seed_keywords: Partial<Record<Language, string[]>>;
} {
  return {
    name: g?.name ?? "",
    pitch: g?.pitch ?? "",
    description: g?.description ?? "",
    genres: g?.genres ?? [],
    platforms: g?.platforms ?? [],
    regions: g?.regions ?? [],
    languages: g?.languages ?? ["en", "zh", "ja", "ko"],
    differentiators: g?.differentiators ?? "",
    comparable_games: g?.comparable_games?.length
      ? g.comparable_games
      : ["", "", ""],
    seed_keywords: g?.seed_keywords ?? {},
  };
}

function validate(d: ReturnType<typeof toDraft>): Errors {
  const e: Errors = {};
  if (!d.name.trim()) e.name = "Name is required";
  if (d.pitch.length > 280) e.pitch = "Keep the pitch to 280 characters";
  if (!d.platforms.length) e.platforms = "Pick at least one platform";
  if (!d.languages.length) e.languages = "Pick at least one language";
  const comps = d.comparable_games.map((c) => c.trim()).filter(Boolean);
  if (comps.length < 3) e.comparable_games = "Add at least 3 comparable games";
  return e;
}

interface Props {
  game?: Game;
  onSaved: (game: Game) => void;
}

/** "Your game" brief: create a new game or edit an existing one, including screenshot uploads. */
export function GameBriefForm({ game, onSaved }: Props) {
  const qc = useQueryClient();
  const create = useCreateGame();
  const update = useUpdateGame(game?.id ?? "");
  const deleteImage = useDeleteImage(game?.id ?? "");
  const [d, setD] = useState(() => toDraft(game));
  const [errors, setErrors] = useState<Errors>({});
  const [pending, setPending] = useState<Record<ImageKind, File[]>>({
    screenshot: [],
    key_art: [],
  });
  const [fileError, setFileError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const set = <K extends keyof typeof d>(k: K, v: (typeof d)[K]) =>
    setD((prev) => ({ ...prev, [k]: v }));
  const toggle = <T,>(list: T[], v: T) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errs = validate(d);
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSubmitError(null);
    const seeds = Object.fromEntries(
      Object.entries(d.seed_keywords).filter(
        ([lang, words]) =>
          d.languages.includes(lang as Language) && words?.length,
      ),
    );
    const body: GameCreate = {
      ...d,
      seed_keywords: seeds,
      comparable_games: d.comparable_games.map((c) => c.trim()).filter(Boolean),
    };
    try {
      let saved = game
        ? await update.mutateAsync(body)
        : await create.mutateAsync(body);
      const queued = [
        ...pending.key_art.map((f) => [f, "key_art"] as const),
        ...pending.screenshot.map((f) => [f, "screenshot"] as const),
      ];
      if (queued.length) {
        setUploading(true);
        const failures: string[] = [];
        for (const [f, kind] of queued) {
          try {
            await api.uploadImage(saved.id, f, kind);
          } catch (err) {
            failures.push(`${f.name}: ${(err as Error).message}`);
          }
        }
        setPending({ screenshot: [], key_art: [] });
        if (failures.length) setFileError(failures.join("; "));
        saved = await api.getGame(saved.id);
        qc.setQueryData(["games", saved.id], saved);
      }
      onSaved(saved);
    } catch (err) {
      setSubmitError((err as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const busy = create.isPending || update.isPending || uploading;

  return (
    <form onSubmit={submit} className="card brief" noValidate>
      <h2>{game ? "Edit your game" : "Your game"}</h2>
      <p className="muted">
        Describe your game. We'll build a profile used to research comparable
        titles on X.
      </p>

      <label>
        Name *
        <input
          value={d.name}
          maxLength={200}
          onChange={(e) => set("name", e.target.value)}
        />
        {errors.name && <span className="error">{errors.name}</span>}
      </label>

      <label>
        One-line pitch
        <input
          value={d.pitch}
          placeholder="e.g. A cozy roguelike about rebuilding a lunar village"
          onChange={(e) => set("pitch", e.target.value)}
        />
        <small className={d.pitch.length > 280 ? "error" : "muted"}>
          {d.pitch.length}/280
        </small>
        {errors.pitch && <span className="error">{errors.pitch}</span>}
      </label>

      <label>
        Detailed description
        <textarea
          rows={8}
          maxLength={5000}
          value={d.description}
          onChange={(e) => set("description", e.target.value)}
        />
        <small className="muted">{d.description.length}/5000</small>
      </label>

      <div className="field">
        <span>Genre tags</span>
        <ChipInput
          value={d.genres}
          onChange={(v) => set("genres", v)}
          placeholder="Type and press Enter"
          suggestions={GENRE_SUGGESTIONS}
        />
      </div>

      <div className="grid-2">
        <fieldset>
          <legend>Platforms *</legend>
          {PLATFORMS.map((p) => (
            <label key={p.value} className="inline">
              <input
                type="checkbox"
                checked={d.platforms.includes(p.value)}
                onChange={() => set("platforms", toggle(d.platforms, p.value))}
              />
              {p.label}
            </label>
          ))}
          {errors.platforms && (
            <span className="error">{errors.platforms}</span>
          )}
        </fieldset>
        <fieldset>
          <legend>Languages *</legend>
          {LANGUAGES.map((l) => (
            <label key={l.value} className="inline">
              <input
                type="checkbox"
                checked={d.languages.includes(l.value)}
                onChange={() => set("languages", toggle(d.languages, l.value))}
              />
              {l.label}
            </label>
          ))}
          {errors.languages && (
            <span className="error">{errors.languages}</span>
          )}
        </fieldset>
      </div>

      <div className="field">
        <span>
          Seed keywords — how players actually talk about games like yours (per
          language, optional)
        </span>
        {LANGUAGES.filter((l) => d.languages.includes(l.value)).map((l) => (
          <div key={l.value} className="seed-row">
            <small>{l.label}</small>
            <ChipInput
              value={d.seed_keywords[l.value] ?? []}
              onChange={(v) =>
                set("seed_keywords", { ...d.seed_keywords, [l.value]: v })
              }
              placeholder={SEED_PLACEHOLDER[l.value]}
              max={30}
            />
          </div>
        ))}
      </div>

      <div className="field">
        <span>Target regions</span>
        <ChipInput
          value={d.regions}
          onChange={(v) => set("regions", v)}
          placeholder="Add a region"
          max={20}
          suggestions={REGION_SUGGESTIONS}
        />
      </div>

      <label>
        What makes it different?
        <textarea
          rows={5}
          maxLength={5000}
          value={d.differentiators}
          onChange={(e) => set("differentiators", e.target.value)}
        />
      </label>

      <div className="field">
        <span>Comparable games * (3–5)</span>
        {d.comparable_games.map((c, i) => (
          <div key={i} className="row">
            <input
              value={c}
              placeholder={`Comparable game ${i + 1}`}
              onChange={(e) =>
                set(
                  "comparable_games",
                  d.comparable_games.map((x, j) =>
                    j === i ? e.target.value : x,
                  ),
                )
              }
            />
            {d.comparable_games.length > 3 && (
              <button
                type="button"
                onClick={() =>
                  set(
                    "comparable_games",
                    d.comparable_games.filter((_, j) => j !== i),
                  )
                }
              >
                Remove
              </button>
            )}
          </div>
        ))}
        {d.comparable_games.length < 5 && (
          <button
            type="button"
            className="link"
            onClick={() => set("comparable_games", [...d.comparable_games, ""])}
          >
            + Add comparable
          </button>
        )}
        {errors.comparable_games && (
          <span className="error">{errors.comparable_games}</span>
        )}
      </div>

      {(["screenshot", "key_art"] as const).map((kind) => (
        <div className="field" key={kind}>
          <span>
            {kind === "key_art" ? "Key art" : "Gameplay screenshots"} (up to{" "}
            {MAX_IMAGES[kind]}, PNG/JPG/WebP, ≤15 MB each)
          </span>
          <ScreenshotPicker
            max={MAX_IMAGES[kind]}
            addLabel={kind === "key_art" ? "+ Add key art" : "+ Add screenshot"}
            pending={pending[kind]}
            onPendingChange={(files) =>
              setPending((p) => ({ ...p, [kind]: files }))
            }
            existing={game?.images.filter((i) => i.kind === kind)}
            onRemoveExisting={game ? (id) => deleteImage.mutate(id) : undefined}
            onError={setFileError}
          />
        </div>
      ))}
      {fileError && <span className="error">{fileError}</span>}

      {submitError && <p className="error">{submitError}</p>}
      <div className="row">
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "Saving…" : game ? "Save brief" : "Create game"}
        </button>
      </div>
    </form>
  );
}
