import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import { DOMAINS, Hypothesis } from "../types";

const empty = {
  title: "",
  statement: "",
  domains: [] as string[],
  status: "active" as Hypothesis["status"],
  probability: 0.5,
};

export function Hypotheses() {
  const [rows, setRows] = useState<Hypothesis[]>([]);
  const [form, setForm] = useState(empty);
  const [customDomain, setCustomDomain] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setRows(await api<Hypothesis[]>("/api/hypotheses"));
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, []);

  function toggleDomain(domain: string) {
    setForm((current) => ({
      ...current,
      domains: current.domains.includes(domain)
        ? current.domains.filter((item) => item !== domain)
        : [...current.domains, domain],
    }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const payload = {
      ...form,
      domains: customDomain.trim() ? [...form.domains, customDomain.trim()] : form.domains,
    };
    try {
      if (editing) {
        await api(`/api/hypotheses/${editing}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await api("/api/hypotheses", { method: "POST", body: JSON.stringify(payload) });
      }
      setForm(empty);
      setCustomDomain("");
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
      domains: row.domains,
      status: row.status,
      probability: row.probability,
    });
  }

  return (
    <section>
      <header className="section-head">
        <h2>Working hypotheses</h2>
        <p>These are ideas about what might be going on. They are not diagnoses.</p>
      </header>
      {error && <p className="alert">{error}</p>}
      <form className="card form" onSubmit={onSubmit}>
        <label>
          Title
          <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required />
        </label>
        <label>
          What would make this worth tracking?
          <textarea
            value={form.statement}
            onChange={(event) => setForm({ ...form, statement: event.target.value })}
            rows={3}
          />
        </label>
        <div>
          <span className="label">Domains</span>
          <div className="chips">
            {DOMAINS.map((domain) => (
              <button
                key={domain}
                type="button"
                className={form.domains.includes(domain) ? "chip on" : "chip"}
                onClick={() => toggleDomain(domain)}
              >
                {domain}
              </button>
            ))}
          </div>
          <label>
            Other domain
            <input value={customDomain} onChange={(event) => setCustomDomain(event.target.value)} />
          </label>
        </div>
        <label>
          Your starting estimate ({Math.round(form.probability * 100)}%)
          <input
            type="range"
            min={5}
            max={95}
            value={Math.round(form.probability * 100)}
            onChange={(event) => setForm({ ...form, probability: Number(event.target.value) / 100 })}
          />
        </label>
        <label>
          Status
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
          <button type="submit">{editing ? "Save hypothesis" : "Add hypothesis"}</button>
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
        {rows.length === 0 && <p className="empty">No working hypotheses yet.</p>}
        {rows.map((row) => (
          <article key={row.id} className="card">
            <div className="card-top">
              <h3>{row.title}</h3>
              <span className="pill">{row.status}</span>
            </div>
            <p className="estimate">Working estimate {Math.round(row.probability * 100)}%</p>
            <div className="bar" aria-hidden="true">
              <span style={{ width: `${Math.round(row.probability * 100)}%` }} />
            </div>
            {row.statement && <p>{row.statement}</p>}
            {row.why_moved && <p className="note">Why this moved: {row.why_moved}</p>}
            <div className="chips">
              {row.domains.map((domain) => (
                <span key={domain} className="chip on">
                  {domain}
                </span>
              ))}
            </div>
            <ul className="evidence">
              {row.evidence.length === 0 && <li>Nothing captured from the coach yet.</li>}
              {row.evidence.map((item) => (
                <li key={item.id}>
                  {item.direction === "supports" ? "Supports" : "Contradicts"} · {item.strength}: {item.text}
                </li>
              ))}
            </ul>
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
