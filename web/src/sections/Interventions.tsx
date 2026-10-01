import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { Hypothesis, Intervention } from "../types";

type FormState = {
  name: string;
  category: Intervention["category"];
  dose: string;
  schedule: string;
  clinician_prescribed: boolean;
  status: Intervention["status"];
  benefit: string;
  side_effect_burden: string;
  side_effect_notes: string;
  hypothesis_ids: number[];
};

const empty: FormState = {
  name: "",
  category: "lifestyle",
  dose: "",
  schedule: "",
  clinician_prescribed: false,
  status: "active",
  benefit: "",
  side_effect_burden: "",
  side_effect_notes: "",
  hypothesis_ids: [],
};

export function Interventions() {
  const [rows, setRows] = useState<Intervention[]>([]);
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [form, setForm] = useState<FormState>(empty);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");

  async function load() {
    const [interventions, ideas] = await Promise.all([
      api<Intervention[]>("/api/interventions"),
      api<Hypothesis[]>("/api/hypotheses"),
    ]);
    setRows(
      [...interventions].sort((a, b) => {
        const rank = (row: Intervention) => {
          if (row.status === "active" && row.net_value !== null && row.net_value < 0) return 0;
          if (row.status === "active") return 1;
          return 2;
        };
        const byRank = rank(a) - rank(b);
        if (byRank !== 0) return byRank;
        if (rank(a) === 0) return (a.net_value ?? 0) - (b.net_value ?? 0);
        return a.position - b.position || a.id - b.id;
      }),
    );
    setHypotheses(ideas);
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  function payload() {
    return {
      name: form.name,
      category: form.category,
      dose: form.status === "ask_clinician" ? "" : form.dose,
      schedule: form.schedule,
      clinician_prescribed: form.clinician_prescribed,
      status: form.status,
      benefit: form.benefit ? Number(form.benefit) : null,
      side_effect_burden: form.side_effect_burden ? Number(form.side_effect_burden) : null,
      side_effect_notes: form.side_effect_notes,
      hypothesis_ids: form.hypothesis_ids,
    };
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      if (editing) {
        await api(`/api/interventions/${editing}`, { method: "PATCH", body: JSON.stringify(payload()) });
      } else {
        await api("/api/interventions", { method: "POST", body: JSON.stringify(payload()) });
      }
      setForm(empty);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the intervention.");
    }
  }

  async function remove(id: number) {
    await api(`/api/interventions/${id}`, { method: "DELETE" });
    if (editing === id) {
      setEditing(null);
      setForm(empty);
    }
    await load();
  }

  function beginEdit(row: Intervention) {
    setEditing(row.id);
    setForm({
      name: row.name,
      category: row.category,
      dose: row.dose,
      schedule: row.schedule,
      clinician_prescribed: row.clinician_prescribed,
      status: row.status,
      benefit: row.benefit ? String(row.benefit) : "",
      side_effect_burden: row.side_effect_burden ? String(row.side_effect_burden) : "",
      side_effect_notes: row.side_effect_notes,
      hypothesis_ids: row.hypothesis_ids,
    });
  }

  return (
    <section>
      <header className="section-head">
        <h2>Interventions</h2>
        <p>
          Potential changes, questions for a clinician, and anything you are already using. A medicine is named
          only as a question, with no dose, and is not an instruction to start or change it on your own.
        </p>
      </header>
      {error && <p className="alert">{error}</p>}
      <form className="card form" onSubmit={onSubmit}>
        <label>
          Name
          <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
        </label>
        <div className="split">
          <label>
            Category
            <select
              value={form.category}
              onChange={(event) => setForm({ ...form, category: event.target.value as Intervention["category"] })}
            >
              <option value="lifestyle">Lifestyle</option>
              <option value="diet">Diet</option>
              <option value="supplement">Supplement</option>
              <option value="medication">Medication</option>
              <option value="therapy">Therapy</option>
            </select>
          </label>
          <label>
            Status
            <select
              value={form.status}
              onChange={(event) =>
                setForm({
                  ...form,
                  status: event.target.value as Intervention["status"],
                  dose: event.target.value === "ask_clinician" ? "" : form.dose,
                })
              }
            >
              <option value="potential">Potential</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="stopped">Stopped</option>
              <option value="ask_clinician">Ask a clinician</option>
            </select>
          </label>
        </div>
        {form.status !== "ask_clinician" && (
          <div className="split">
            <label>
              Dose, if you already take it
              <input value={form.dose} onChange={(event) => setForm({ ...form, dose: event.target.value })} />
            </label>
            <label>
              Schedule
              <input value={form.schedule} onChange={(event) => setForm({ ...form, schedule: event.target.value })} />
            </label>
          </div>
        )}
        {form.status === "ask_clinician" && (
          <p className="note">
            This is a question for a clinician. It cannot include a dose, and it is not an instruction to start or
            change a medicine on your own.
          </p>
        )}
        <label className="check">
          <input
            type="checkbox"
            checked={form.clinician_prescribed}
            onChange={(event) => setForm({ ...form, clinician_prescribed: event.target.checked })}
          />
          A clinician prescribed this
        </label>
        <div className="split">
          <label>
            Benefit (1–5)
            <select value={form.benefit} onChange={(event) => setForm({ ...form, benefit: event.target.value })}>
              <option value="">Not rated</option>
              {[1, 2, 3, 4, 5].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Side-effect burden (1–5)
            <select
              value={form.side_effect_burden}
              onChange={(event) => setForm({ ...form, side_effect_burden: event.target.value })}
            >
              <option value="">Not rated</option>
              {[1, 2, 3, 4, 5].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label>
          Side effects
          <textarea
            rows={2}
            value={form.side_effect_notes}
            onChange={(event) => setForm({ ...form, side_effect_notes: event.target.value })}
          />
        </label>
        <div>
          <span className="label">Meant to test</span>
          <div className="chips">
            {hypotheses.map((item) => (
              <button
                type="button"
                key={item.id}
                className={form.hypothesis_ids.includes(item.id) ? "chip on" : "chip"}
                onClick={() =>
                  setForm((current) => ({
                    ...current,
                    hypothesis_ids: current.hypothesis_ids.includes(item.id)
                      ? current.hypothesis_ids.filter((id) => id !== item.id)
                      : [...current.hypothesis_ids, item.id],
                  }))
                }
              >
                {item.title}
              </button>
            ))}
          </div>
        </div>
        <div className="row-actions">
          <button type="submit">{editing ? "Save intervention" : "Add intervention"}</button>
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
      <div className="stack">
        {rows.length === 0 && <p className="empty">No interventions yet.</p>}
        {rows.map((row) => (
          <article key={row.id} className="card">
            <div className="card-top">
              <h3>{row.name}</h3>
              <span className="pill">
                {row.status === "ask_clinician" ? "Ask a clinician" : row.status === "potential" ? "Potential" : row.status}
              </span>
            </div>
            <p className="meta">
              {row.category}
              {row.clinician_prescribed
                ? " · prescribed"
                : row.status === "ask_clinician"
                  ? ""
                  : " · self-directed"}
              {row.dose ? ` · ${row.dose}` : ""}
              {row.schedule ? ` · ${row.schedule}` : ""}
            </p>
            <p>
              Benefit {row.benefit ?? "—"} · Side-effect burden {row.side_effect_burden ?? "—"}
              {row.net_value !== null ? ` · Net ${row.net_value}` : ""}
            </p>
            {row.status === "ask_clinician" && row.category === "medication" && (
              <p className="note">Ask your clinician before starting or changing this. Do not do it on your own.</p>
            )}
            {row.status === "ask_clinician" && row.category !== "medication" && (
              <p className="note">Ask your clinician about this. It is not a treatment to start on your own.</p>
            )}
            {row.clinician_task && <p className="note">{row.clinician_task}</p>}
            {row.side_effect_notes && <p>{row.side_effect_notes}</p>}
            {row.stop_date && <p className="meta">Stopped {row.stop_date}</p>}
            <div className="chips">
              {row.hypotheses.map((item) => (
                <span key={item.id} className="chip on">
                  {item.title}
                </span>
              ))}
            </div>
            <div className="row-actions">
              <button type="button" className="ghost" onClick={() => beginEdit(row)}>
                Edit
              </button>
              <button type="button" className="danger" onClick={() => remove(row.id)}>
                Remove
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
