import { FormEvent, Fragment, useEffect, useState } from "react";
import { api } from "../api";
import { Hypothesis } from "../types";

const SHEET_TITLE = "Health Differential / Theories Discussed";
const CONFIDENCE_NOTE =
  "Confidence reflects how well each theory currently fits the reported pattern; it is not a diagnosis or a calculated probability.";
const SHEET_FOOTER =
  "Important: This workbook summarizes hypotheses discussed in conversation. It is intended for organizing questions and patterns, not for self-diagnosis or replacing medical evaluation.";

const CONFIDENCE_OPTIONS = [
  "High",
  "Moderate–High",
  "Moderate",
  "Moderate, provisional",
  "High for rash; Low–Moderate for sleepiness",
  "Moderate for individual episodes; Low as unifying diagnosis",
  "Low–Moderate",
  "Low–Moderate / insufficient evidence",
  "Low",
  "Low if prior thyroid testing normal; otherwise unresolved",
  "Low as unifying explanation",
  "Moderate as amplifier; Low as primary cause",
  "Very Low",
];

const empty = {
  title: "",
  statement: "",
  why_it_fits: "",
  confidence: "",
  likely_role: "",
  status: "active" as Hypothesis["status"],
};

export function Hypotheses() {
  const [rows, setRows] = useState<Hypothesis[]>([]);
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setRows(await api<Hypothesis[]>("/api/hypotheses"));
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const payload = {
      title: form.title,
      statement: form.statement,
      why_it_fits: form.why_it_fits,
      confidence: form.confidence,
      likely_role: form.likely_role,
      status: form.status,
    };
    try {
      if (editing) {
        await api(`/api/hypotheses/${editing}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await api("/api/hypotheses", { method: "POST", body: JSON.stringify(payload) });
      }
      setForm(empty);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the hypothesis.");
    }
  }

  async function remove(id: number) {
    setError("");
    await api(`/api/hypotheses/${id}`, { method: "DELETE" });
    if (editing === id) {
      setEditing(null);
      setForm(empty);
    }
    await load();
  }

  function beginEdit(row: Hypothesis) {
    setEditing(row.id);
    setForm({
      title: row.title,
      statement: row.statement,
      why_it_fits: row.why_it_fits,
      confidence: row.confidence,
      likely_role: row.likely_role,
      status: row.status,
    });
  }

  return (
    <section>
      <header className="section-head">
        <h2>{SHEET_TITLE}</h2>
        <p>{CONFIDENCE_NOTE}</p>
      </header>
      {error && <p className="alert">{error}</p>}
      <form className="card form" onSubmit={onSubmit}>
        <label>
          Theory
          <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required />
        </label>
        <label>
          Description
          <textarea
            value={form.statement}
            onChange={(event) => setForm({ ...form, statement: event.target.value })}
            rows={3}
          />
        </label>
        <label>
          Why it might fit your history
          <textarea
            value={form.why_it_fits}
            onChange={(event) => setForm({ ...form, why_it_fits: event.target.value })}
            rows={3}
          />
        </label>
        <label>
          Current confidence / fit
          <input
            value={form.confidence}
            list="confidence-options"
            onChange={(event) => setForm({ ...form, confidence: event.target.value })}
          />
          <datalist id="confidence-options">
            {CONFIDENCE_OPTIONS.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
        </label>
        <label>
          Likely role
          <input
            value={form.likely_role}
            onChange={(event) => setForm({ ...form, likely_role: event.target.value })}
          />
        </label>
        <label>
          Tracking status
          <select
            value={form.status}
            onChange={(event) => setForm({ ...form, status: event.target.value as Hypothesis["status"] })}
          >
            <option value="active">Active</option>
            <option value="parked">Parked</option>
            <option value="supported">Supported</option>
            <option value="refuted">Refuted</option>
          </select>
        </label>
        <div className="row-actions">
          <button type="submit">{editing ? "Save theory" : "Add theory"}</button>
          {editing && (
            <button
              type="button"
              className="ghost"
              onClick={() => {
                setEditing(null);
                setForm(empty);
              }}
            >
              Cancel edit
            </button>
          )}
        </div>
      </form>
      {rows.length === 0 && <p className="empty">No theories yet.</p>}
      {rows.length > 0 && (
        <div className="table-scroll">
          <table className="theories">
            <thead>
              <tr>
                <th>Theory</th>
                <th>Description</th>
                <th>Why it might fit your history</th>
                <th>Current confidence / fit</th>
                <th>Likely role</th>
                <th>
                  <span className="sr">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Fragment key={row.id}>
                  <tr className={editing === row.id ? "editing" : undefined}>
                    <td className="theory">
                      {row.title}
                      {row.status !== "active" && <span className="pill">{row.status}</span>}
                    </td>
                    <td>{row.statement}</td>
                    <td>{row.why_it_fits}</td>
                    <td>{row.confidence}</td>
                    <td>{row.likely_role}</td>
                    <td className="actions">
                      <button type="button" className="ghost" onClick={() => beginEdit(row)}>
                        Edit
                      </button>
                      <button type="button" className="danger" onClick={() => remove(row.id)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                  {(row.evidence.length > 0 || row.why_moved) && (
                    <tr className="detail">
                      <td colSpan={6}>
                        {row.why_moved && <p className="note">Why this moved: {row.why_moved}</p>}
                        {row.evidence.length > 0 && (
                          <ul className="evidence">
                            {row.evidence.map((item) => (
                              <li key={item.id}>
                                {item.direction === "supports" ? "Supports" : "Contradicts"} · {item.strength}:{" "}
                                {item.text}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="note footer-note">{SHEET_FOOTER}</p>
    </section>
  );
}
