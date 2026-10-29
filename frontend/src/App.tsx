import { useState } from "react";
import { GameBriefForm } from "./components/GameBriefForm";
import { MonitorPanel } from "./components/MonitorPanel";
import { UABriefPanel } from "./components/UABriefPanel";
import { ProfilePanel } from "./components/ProfileEditor";
import { useGame, useGames } from "./hooks/queries";

type Mode =
  { kind: "new" } | { kind: "view"; id: string } | { kind: "edit"; id: string };

function GameView({ id, onEdit }: { id: string; onEdit: () => void }) {
  const game = useGame(id);
  if (game.isLoading) return <p>Loading…</p>;
  if (!game.data)
    return <p className="error">{game.error?.message ?? "Not found"}</p>;
  const g = game.data;
  return (
    <>
      <section className="card">
        <div className="row spread">
          <div>
            <h2>{g.name}</h2>
            {g.pitch && <p className="pitch">{g.pitch}</p>}
          </div>
          <button onClick={onEdit}>Edit brief</button>
        </div>
        <p className="muted">
          {[
            g.genres.join(", "),
            g.platforms.join(", ").toUpperCase(),
            g.languages.join(" / "),
            g.regions.join(", "),
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
        {g.comparable_games.length > 0 && (
          <p>Comparable: {g.comparable_games.join(", ")}</p>
        )}
        {g.images.length > 0 && (
          <div className="thumbs">
            {g.images.map((s) => (
              <figure
                key={s.id}
                className={`thumb ${s.kind}`}
                title={s.kind === "key_art" ? "Key art" : "Screenshot"}
              >
                <img src={s.url} alt={s.filename} />
              </figure>
            ))}
          </div>
        )}
      </section>
      <ProfilePanel gameId={g.id} />
      <UABriefPanel gameId={g.id} />
      <MonitorPanel gameId={g.id} />
    </>
  );
}

function EditGame({ id, onDone }: { id: string; onDone: () => void }) {
  const game = useGame(id);
  if (!game.data) return <p>Loading…</p>;
  return <GameBriefForm key={game.data.id} game={game.data} onSaved={onDone} />;
}

export default function App() {
  const games = useGames();
  const [mode, setMode] = useState<Mode | null>(null);
  const effective: Mode =
    mode ??
    (games.data?.[0]
      ? { kind: "view", id: games.data[0].id }
      : { kind: "new" });
  const activeId = effective.kind === "new" ? undefined : effective.id;

  return (
    <main>
      <header className="row spread">
        <h1>UA Research Agent</h1>
        <span className="muted">Game Launch Monitor</span>
      </header>
      <div className="layout">
        <aside>
          <button
            className="primary full"
            onClick={() => setMode({ kind: "new" })}
          >
            + New game
          </button>
          <h3>Your games</h3>
          {games.isLoading && <p>Loading…</p>}
          {games.error && <p className="error">{games.error.message}</p>}
          <ul className="games">
            {games.data?.map((g) => (
              <li key={g.id}>
                <button
                  className={g.id === activeId ? "active" : ""}
                  onClick={() => setMode({ kind: "view", id: g.id })}
                >
                  {g.name}
                  {g.has_profile && (
                    <span className="badge accepted">profile</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <div>
          {effective.kind === "new" && (
            <GameBriefForm
              onSaved={(g) => setMode({ kind: "view", id: g.id })}
            />
          )}
          {effective.kind === "edit" && (
            <EditGame
              id={effective.id}
              onDone={() => setMode({ kind: "view", id: effective.id })}
            />
          )}
          {effective.kind === "view" && (
            <GameView
              id={effective.id}
              onEdit={() => setMode({ kind: "edit", id: effective.id })}
            />
          )}
        </div>
      </div>
    </main>
  );
}
