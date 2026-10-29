import { useState } from "react";
import type { Category } from "../api/types";
import { useInsights, usePosts, useRunScan } from "../hooks/queries";

/** Existing scan / posts / insights view (kept from the original monitor scaffold). */
export function MonitorPanel({ gameId }: { gameId: string }) {
  const [category, setCategory] = useState<Category | "">("");
  const scan = useRunScan(gameId);
  const posts = usePosts(gameId, { category: category || undefined });
  const insights = useInsights(gameId);

  return (
    <section className="card">
      <div className="row spread">
        <h2>X monitor</h2>
        <button
          onClick={() => scan.mutate({ max_posts: 20 })}
          disabled={scan.isPending}
        >
          {scan.isPending ? "Scanning…" : "Run scan"}
        </button>
      </div>
      {scan.data && (
        <p className="muted">
          Last scan: {scan.data.status} · {scan.data.post_count} posts via{" "}
          {scan.data.provider}
        </p>
      )}
      {scan.error && <p className="error">{scan.error.message}</p>}

      {insights.data && insights.data.total_posts > 0 && (
        <div>
          <h3>Summary ({insights.data.total_posts} posts)</h3>
          <p>Sentiment: {JSON.stringify(insights.data.sentiment_totals)}</p>
          <p>Categories: {JSON.stringify(insights.data.category_totals)}</p>
          <p>Languages: {JSON.stringify(insights.data.language_totals)}</p>
          <h4>Top issues</h4>
          <ul>
            {insights.data.top_issues.map((i) => (
              <li key={i.label}>
                {i.label} ({i.count})
              </li>
            ))}
          </ul>
          <h4>Spikes</h4>
          <ul>
            {insights.data.spikes.map((s) => (
              <li key={s.post_id}>
                @{s.author} · {s.engagement} · {s.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!!posts.data?.length && (
        <>
          <div className="row">
            <h3>Posts</h3>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as Category | "")}
            >
              <option value="">All categories</option>
              {["bug", "praise", "question", "influencer", "other"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </div>
          <table>
            <thead>
              <tr>
                <th>Lang</th>
                <th>Sentiment</th>
                <th>Category</th>
                <th>Author</th>
                <th>Engagement</th>
                <th>Text</th>
              </tr>
            </thead>
            <tbody>
              {posts.data.map((p) => (
                <tr key={p.id}>
                  <td>{p.language}</td>
                  <td className={p.sentiment}>{p.sentiment}</td>
                  <td>{p.category}</td>
                  <td>@{p.author}</td>
                  <td>{p.engagement}</td>
                  <td>
                    <a href={p.url} target="_blank" rel="noreferrer">
                      {p.text}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
