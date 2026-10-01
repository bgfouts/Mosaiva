import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { Hypothesis, Intervention, ResearchItem } from "../types";

export function Research() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<ResearchItem[]>([]);
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [interventions, setInterventions] = useState<Intervention[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const [papers, ideas, actions] = await Promise.all([
      api<ResearchItem[]>("/api/research"),
      api<Hypothesis[]>("/api/hypotheses"),
      api<Intervention[]>("/api/interventions"),
    ]);
    setItems(papers);
    setHypotheses(ideas);
    setInterventions(actions);
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api<{ items: ResearchItem[]; message: string }>("/api/research/search", {
        method: "POST",
        body: JSON.stringify({ query }),
      });
      setMessage(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  async function link(item: ResearchItem, hypothesisId: number) {
    const hypothesis_ids = item.hypothesis_ids.includes(hypothesisId)
      ? item.hypothesis_ids.filter((id) => id !== hypothesisId)
      : [...item.hypothesis_ids, hypothesisId];
    await api(`/api/research/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify({ hypothesis_ids }),
    });
    await load();
  }

  return (
    <section>
      <header className="section-head">
        <h2>Research</h2>
        <p>
          Web search keeps only freely downloadable PDFs from a list of reputable journals. A starter set of
          open-access papers is saved here when those titles are missing. The notes are background, not a dose
          and not an instruction to start a medicine.
        </p>
      </header>
      {error && <p className="alert">{error}</p>}
      <form className="card form inline" onSubmit={onSearch}>
        <label>
          Search
          <input id="research-query" value={query} onChange={(event) => setQuery(event.target.value)} required />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Searching…" : "Search journals"}
        </button>
      </form>
      {message && <p className="note">{message}</p>}
      <div className="stack">
        {items.length === 0 && <p className="empty">No papers saved yet.</p>}
        {items.map((item) => (
          <article key={item.id} className="card">
            <h3>{item.title}</h3>
            <p className="meta">
              {item.journal || "Journal"}
              {item.year ? ` · ${item.year}` : ""}
            </p>
            <p>{item.relevance_note}</p>
            {interventions.some((row) => item.intervention_ids.includes(row.id)) && (
              <p className="meta">
                Filed with:{" "}
                {interventions
                  .filter((row) => item.intervention_ids.includes(row.id))
                  .map((row) => row.name)
                  .join(" · ")}
              </p>
            )}
            <p>
              <a href={item.pdf_url} target="_blank" rel="noreferrer">
                Free PDF
              </a>
            </p>
            {item.excerpt && <p className="excerpt">{item.excerpt.slice(0, 500)}</p>}
            <div className="chips">
              {hypotheses.map((hypothesis) => (
                <button
                  type="button"
                  key={hypothesis.id}
                  className={item.hypothesis_ids.includes(hypothesis.id) ? "chip on" : "chip"}
                  onClick={() => link(item, hypothesis.id)}
                >
                  {hypothesis.title}
                </button>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
