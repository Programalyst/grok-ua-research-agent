import { useState } from "react";
import type { PostRef, ResearchRun } from "../api/types";
import {
  useResearchEstimate,
  useResearchRun,
  useResearchRuns,
  useRunResearch,
} from "../hooks/queries";

const usd = (n: number) => `$${n.toFixed(n < 1 ? 3 : 2)}`;
const compact = (n: number) =>
  new Intl.NumberFormat("en", { notation: "compact" }).format(n);

function PostLinks({
  ids,
  posts,
}: {
  ids: string[];
  posts: ResearchRun["posts"];
}) {
  const refs = ids.map((id) => posts[id]).filter((p): p is PostRef => !!p);
  if (!refs.length) return null;
  return (
    <span className="muted">
      {" "}
      {refs.map((p, i) => (
        <a
          key={p.id}
          href={p.url}
          target="_blank"
          rel="noreferrer"
          title={p.text}
        >
          [{i + 1}]
        </a>
      ))}
    </span>
  );
}

/** Research comparables on X and show the Grok-written UA brief. */
export function UABriefPanel({ gameId }: { gameId: string }) {
  const [perComparable, setPerComparable] = useState(25);
  const [total, setTotal] = useState(200);
  const [searches, setSearches] = useState(5);
  const caps = {
    max_searches: searches,
    max_posts_per_comparable: perComparable,
    max_posts_total: total,
  };
  const estimate = useResearchEstimate(gameId, caps);
  const runs = useResearchRuns(gameId);
  const runResearch = useRunResearch(gameId);
  const [picked, setSelected] = useState<string>();
  const selected = picked ?? runs.data?.[0]?.id;
  const run = useResearchRun(selected);
  const r = run.data;
  const b = r?.brief;
  const est = estimate.data;

  return (
    <section className="card">
      <div className="row spread">
        <h2>UA brief</h2>
        <div className="row">
          <label>
            Per comparable{" "}
            <input
              type="number"
              min={10}
              max={100}
              value={perComparable}
              onChange={(e) => setPerComparable(Number(e.target.value))}
              style={{ width: 70 }}
            />
          </label>
          <label title="Grok x_search calls (each ~$0.20–0.25)">
            Searches{" "}
            <input
              type="number"
              min={1}
              max={30}
              value={searches}
              onChange={(e) => setSearches(Number(e.target.value))}
              style={{ width: 60 }}
            />
          </label>
          <label>
            Total{" "}
            <input
              type="number"
              min={10}
              max={1000}
              value={total}
              onChange={(e) => setTotal(Number(e.target.value))}
              style={{ width: 80 }}
            />
          </label>
          <button
            disabled={runResearch.isPending || !est?.can_run}
            onClick={() =>
              runResearch.mutate(caps, { onSuccess: (x) => setSelected(x.id) })
            }
          >
            {runResearch.isPending
              ? "Researching… (can take a few minutes)"
              : `Run research (max ${est ? usd(est.max_total_cost_usd) : "…"})`}
          </button>
        </div>
      </div>
      {est && (
        <p className="muted">
          Up to {est.max_posts_total} posts from {est.comparables.length}{" "}
          comparables ({est.planned_queries} queries via {est.collector}
          {est.collector === "grok_x_search"
            ? ` (≤${est.max_searches} searches × ~${usd(est.cost_per_search_usd)})`
            : ""}
          , {est.provider}) · max X {usd(est.max_x_cost_usd)} + LLM reserve{" "}
          {usd(est.llm_reserve_usd)} · budget left today{" "}
          {usd(est.budget_remaining_usd)} of {usd(est.budget_limit_usd)}
        </p>
      )}
      {runResearch.error && (
        <p className="error">{runResearch.error.message}</p>
      )}

      {!!runs.data?.length && (
        <label>
          Run{" "}
          <select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            {runs.data.map((x) => (
              <option key={x.id} value={x.id}>
                {new Date(x.started_at).toLocaleString()} · {x.status} ·{" "}
                {x.post_count} posts · {usd(x.total_cost_usd)}
              </option>
            ))}
          </select>
        </label>
      )}

      {r && (
        <p className="muted">
          {r.status} · {r.post_count} posts, {r.author_count} authors · cost X{" "}
          {usd(r.x_cost_usd)} + LLM {usd(r.llm_cost_usd)} ={" "}
          {usd(r.total_cost_usd)}
          {r.error && <span className="error"> · {r.error}</span>}
        </p>
      )}

      {b && r && (
        <>
          <h3>Summary</h3>
          <p style={{ whiteSpace: "pre-wrap" }}>{b.summary}</p>

          <h3>How players talk</h3>
          <ul>
            {b.player_phrasing.map((p, i) => (
              <li key={i}>
                <strong>“{p.phrase}”</strong>{" "}
                <span className="chip">{p.language}</span> — {p.meaning}
                <PostLinks ids={p.example_post_ids} posts={r.posts} />
              </li>
            ))}
          </ul>

          <h3>Creative hooks</h3>
          <ul>
            {b.creative_hooks.map((h, i) => (
              <li key={i}>
                <strong>{h.title}</strong>: {h.angle}{" "}
                <span className="muted">
                  (differentiator: {h.differentiator})
                </span>
                <PostLinks ids={h.evidence_post_ids} posts={r.posts} />
              </li>
            ))}
          </ul>

          <h3>Competitor complaints & unmet wants</h3>
          {b.competitor_insights.map((c) => (
            <div key={c.comparable}>
              <h4>
                {c.comparable}
                <PostLinks ids={c.example_post_ids} posts={r.posts} />
              </h4>
              <ul>
                {c.complaints.map((x, i) => (
                  <li key={`c${i}`}>😤 {x}</li>
                ))}
                {c.unmet_wants.map((x, i) => (
                  <li key={`w${i}`}>💡 {x}</li>
                ))}
              </ul>
            </div>
          ))}

          <h3>Creator shortlist</h3>
          <table>
            <thead>
              <tr>
                <th>Creator</th>
                <th>Followers</th>
                <th>Why</th>
                <th>Sample post</th>
              </tr>
            </thead>
            <tbody>
              {b.creators.map((c) => (
                <tr key={c.handle}>
                  <td>
                    <a href={c.profile_url} target="_blank" rel="noreferrer">
                      @{c.handle}
                    </a>
                  </td>
                  <td>
                    {c.followers_source === "unknown" ? (
                      <span className="muted">unknown</span>
                    ) : (
                      compact(c.followers)
                    )}
                    {c.followers_source === "grok_reported" && (
                      <div className="muted" style={{ fontSize: "0.8em" }}>
                        reported by Grok (unverified)
                      </div>
                    )}
                  </td>
                  <td>{c.why}</td>
                  <td>
                    {r.posts[c.sample_post_id] ? (
                      <a
                        href={r.posts[c.sample_post_id].url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {c.sample_text.slice(0, 120)}
                      </a>
                    ) : (
                      c.sample_text.slice(0, 120)
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">Model: {b.model}</p>
        </>
      )}
    </section>
  );
}
