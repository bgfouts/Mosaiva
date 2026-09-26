import { useState } from "react";
import { api } from "../api";
import { Capture, CoachSession } from "../types";
import { connectVoice, functionResult, LiveServerEvent } from "../voice";

export function Coach() {
  const [session, setSession] = useState<CoachSession | null>(null);
  const [error, setError] = useState("");
  const [urgent, setUrgent] = useState("");
  const [live, setLive] = useState(false);
  const [handle, setHandle] = useState<{ stop: () => void; send: (event: unknown) => void } | null>(null);

  async function refresh(sessionId: number) {
    setSession(await api<CoachSession>(`/api/coach/sessions/${sessionId}`));
  }

  async function start() {
    setError("");
    setUrgent("");
    try {
      await api("/api/coach/session", { method: "POST", body: JSON.stringify({ probe: true }) });
      const bridge: { sessionId: number; send: (event: unknown) => void } = {
        sessionId: 0,
        send: () => undefined,
      };
      const connection = await connectVoice(
        (sdp) =>
          api<{ session_id: number; transport: { sdp: string } }>("/api/coach/session", {
            method: "POST",
            body: JSON.stringify({ sdp }),
          }),
        (event) => {
          void onLiveEvent(bridge.sessionId, event, bridge.send);
        },
      );
      bridge.sessionId = connection.sessionId;
      bridge.send = connection.send;
      connection.flush();
      await refresh(connection.sessionId);
      setHandle(connection);
      setLive(true);
    } catch (err) {
      setLive(false);
      setError(err instanceof Error ? err.message : "Voice coaching could not start.");
    }
  }

  async function onLiveEvent(sessionId: number, event: LiveServerEvent, send: (payload: unknown) => void) {
    if (event.type === "session.input_transcript.delta" && event.delta) {
      await api(`/api/coach/sessions/${sessionId}/events`, {
        method: "POST",
        body: JSON.stringify({ kind: "transcript", role: "patient", text: event.delta }),
      });
      await refresh(sessionId);
    }
    if (event.type === "session.output_transcript.delta" && event.delta) {
      await api(`/api/coach/sessions/${sessionId}/events`, {
        method: "POST",
        body: JSON.stringify({ kind: "transcript", role: "coach", text: event.delta }),
      });
      await refresh(sessionId);
    }
    const nested = event.type === "response.event" ? event.event : undefined;
    const item = nested?.type === "response.output_item.done" ? nested.item : undefined;
    if (item?.type === "function_call" && item.name && item.call_id) {
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(item.arguments || "{}") as Record<string, unknown>;
      } catch {
        payload = {};
      }
      const result = await api<{ urgent: boolean; urgent_message: string | null }>(
        `/api/coach/sessions/${sessionId}/events`,
        {
          method: "POST",
          body: JSON.stringify({ kind: "tool", tool_name: item.name, payload, call_id: item.call_id }),
        },
      );
      if (result.urgent && result.urgent_message) {
        setUrgent(result.urgent_message);
      }
      send(functionResult(item.call_id, JSON.stringify({ status: "recorded", urgent: result.urgent })));
      send({ type: "response.create" });
      await refresh(sessionId);
    }
  }

  function end() {
    handle?.stop();
    setHandle(null);
    setLive(false);
  }

  async function commit(capture: Capture) {
    await api(`/api/coach/captures/${capture.id}/commit`, { method: "POST" });
    if (session) await refresh(session.id);
  }

  async function discard(capture: Capture) {
    await api(`/api/coach/captures/${capture.id}/discard`, { method: "POST" });
    if (session) await refresh(session.id);
  }

  const pending = session?.captures.filter((item) => item.status === "pending") ?? [];

  return (
    <section id="coach">
      <header className="section-head">
        <h2>Voice coach</h2>
        <p>Speak with the coach. There is no typing. Confirm anything it wants to save.</p>
      </header>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {urgent && (
        <p className="alert urgent" role="alert">
          {urgent}
        </p>
      )}
      <div className="voice-panel card">
        <button type="button" className="voice" onClick={live ? end : start}>
          {live ? "End voice session" : "Start voice session"}
        </button>
        <p className="meta">{live ? "Listening and speaking." : "Voice only. A failed session stops here."}</p>
      </div>
      <div className="stack">
        <article className="card">
          <h3>Transcript</h3>
          {(session?.transcript.length ?? 0) === 0 && <p className="empty">The transcript appears after you talk.</p>}
          <ul className="transcript">
            {session?.transcript.map((line, index) => (
              <li key={index}>
                <strong>{line.role === "patient" ? "You" : "Coach"}:</strong> {line.text}
              </li>
            ))}
          </ul>
        </article>
        <article className="card">
          <h3>Waiting for confirmation</h3>
          {pending.length === 0 && <p className="empty">Nothing is waiting to be saved.</p>}
          {pending.map((capture) => (
            <div key={capture.id} className="capture">
              <p>
                <strong>{capture.tool_name}</strong>
              </p>
              <pre>{JSON.stringify(capture.payload, null, 2)}</pre>
              <div className="row-actions">
                <button type="button" onClick={() => commit(capture)}>
                  Confirm
                </button>
                <button type="button" className="ghost" onClick={() => discard(capture)}>
                  Discard
                </button>
              </div>
            </div>
          ))}
        </article>
      </div>
    </section>
  );
}
