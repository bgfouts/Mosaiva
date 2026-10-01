import { useEffect, useState } from "react";
import { api } from "../api";
import { Review } from "../types";

type MosaicState = {
  week_start: string;
  timezone: string;
  review: Review | null;
};

export function Mosaic() {
  const [state, setState] = useState<MosaicState | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [editedName, setEditedName] = useState("");
  const [editedSafety, setEditedSafety] = useState("");

  async function load() {
    const next = await api<MosaicState>("/api/mosaic");
    setState(next);
    setEditedName(next.review?.recommendation.name ?? "");
    setEditedSafety(next.review?.recommendation.safety_note ?? "");
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  async function run() {
    setBusy(true);
    setError("");
    const before = state?.review?.id;
    try {
      const review = await api<Review>("/api/mosaic/run", { method: "POST" });
      if (before && review.id === before) {
        setNote("Same review for this week. No second change was created.");
      } else {
        setNote("");
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mosaic could not run.");
    } finally {
      setBusy(false);
    }
  }

  async function decide(decision: "accept" | "dismiss") {
    if (!state?.review) return;
    setError("");
    try {
      await api(`/api/mosaic/${state.review.id}/decision`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          name: editedName.trim() || undefined,
          safety_note: editedSafety,
        }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that decision.");
    }
  }

  const review = state?.review;
  const action = review?.recommendation.action;

  return (
    <section>
      <header className="section-head">
        <h2>Mosaic</h2>
        <p>
          One look at the whole record each week, and at most one change. Week of {state?.week_start ?? "…"} (
          {state?.timezone ?? "UTC"}).
        </p>
      </header>
      {error && <p className="alert">{error}</p>}
      {note && <p className="note">{note}</p>}
      {review && <p className="note">This week already has a review. Running again returns the same suggestion.</p>}
      <button type="button" onClick={run} disabled={busy}>
        {busy ? "Reading the record…" : "Run this week's review"}
      </button>
      {review && (
        <article className="card mosaic">
          <div className="card-top">
            <h3>
              {action === "add" && "Add one thing"}
              {action === "remove" && "Remove one thing"}
              {action === "hold" && "Hold"}
            </h3>
            <span className="pill">{review.status}</span>
          </div>
          {review.status === "proposed" && action !== "hold" && (
            <label>
              Suggestion
              <input value={editedName} onChange={(event) => setEditedName(event.target.value)} />
            </label>
          )}
          {review.status !== "proposed" && review.recommendation.name && (
            <p className="estimate">{review.recommendation.name}</p>
          )}
          {review.recommendation.category === "medication" && (
            <p className="note">Ask your clinician. Do not start this on your own. No dose is included.</p>
          )}
          <p>{review.recommendation.rationale}</p>
          {review.status === "proposed" ? (
            <label>
              Safety note
              <textarea rows={2} value={editedSafety} onChange={(event) => setEditedSafety(event.target.value)} />
            </label>
          ) : (
            review.recommendation.safety_note && <p className="note">{review.recommendation.safety_note}</p>
          )}
          {review.recommendation.what_to_watch && <p>Watch: {review.recommendation.what_to_watch}</p>}
          <h4>Working estimates</h4>
          <ul>
            {review.hypothesis_updates.map((update) => (
              <li key={update.hypothesis_id}>
                {update.title || `Hypothesis ${update.hypothesis_id}`}:{" "}
                {update.previous_probability !== undefined
                  ? `${Math.round(update.previous_probability * 100)}% → ${Math.round(update.probability * 100)}%`
                  : `${Math.round(update.probability * 100)}%`}
                . {update.rationale}
              </li>
            ))}
          </ul>
          {review.status === "proposed" && action !== "hold" && (
            <div className="row-actions">
              <button type="button" onClick={() => decide("accept")}>
                Accept
              </button>
              <button type="button" className="ghost" onClick={() => decide("dismiss")}>
                Dismiss
              </button>
            </div>
          )}
          {review.status === "proposed" && action === "hold" && (
            <div className="row-actions">
              <button type="button" onClick={() => decide("accept")}>
                Keep the hold
              </button>
              <button type="button" className="ghost" onClick={() => decide("dismiss")}>
                Dismiss
              </button>
            </div>
          )}
        </article>
      )}
    </section>
  );
}
