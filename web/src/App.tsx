import { useEffect, useState } from "react";
import { api, SIGNED_OUT_EVENT } from "./api";
import { Coach } from "./sections/Coach";
import { Hypotheses } from "./sections/Hypotheses";
import { Interventions } from "./sections/Interventions";
import { Mosaic } from "./sections/Mosaic";
import { Research } from "./sections/Research";
import { SignIn } from "./SignIn";
import { Settings, TIMEZONES } from "./types";

const TABS = [
  ["hypotheses", "Hypotheses"],
  ["interventions", "Interventions"],
  ["research", "Research"],
  ["coach", "Coach"],
  ["mosaic", "Mosaic"],
] as const;

type Tab = (typeof TABS)[number][0];

type Me = { auth_required: boolean; email: string | null };
type AuthState = { status: "checking" } | { status: "signed_out"; problem: string } | { status: "ready"; me: Me };

function readAuthError(): string {
  return new URLSearchParams(window.location.search).get("auth_error") ?? "";
}

export function App() {
  const [auth, setAuth] = useState<AuthState>({ status: "checking" });
  const [authError] = useState(readAuthError);

  useEffect(() => {
    if (authError) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, [authError]);

  useEffect(() => {
    let active = true;
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!active) return;
        if (response.ok) {
          setAuth({ status: "ready", me: body as Me });
        } else if (response.status === 401) {
          setAuth({ status: "signed_out", problem: "" });
        } else {
          setAuth({ status: "signed_out", problem: String(body.detail ?? "Sign-in is not available right now.") });
        }
      })
      .catch(() => active && setAuth({ status: "signed_out", problem: "The server could not be reached." }));
    const onSignedOut = () => setAuth({ status: "signed_out", problem: "" });
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => {
      active = false;
      window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
    };
  }, []);

  if (auth.status === "checking") {
    return <p className="loading">Opening Mosaiva…</p>;
  }
  if (auth.status === "signed_out") {
    return <SignIn error={authError} problem={auth.problem} />;
  }
  return <Record me={auth.me} />;
}

function Record({ me }: { me: Me }) {
  const [tab, setTab] = useState<Tab>("hypotheses");
  const [settings, setSettings] = useState<Settings | null>(null);

  useEffect(() => {
    api<Settings>("/api/settings").then(setSettings).catch(() => setSettings(null));
  }, []);

  async function changeTimezone(timezone: string) {
    const next = await api<Settings>("/api/settings", {
      method: "PATCH",
      body: JSON.stringify({ timezone }),
    });
    setSettings(next);
  }

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    window.location.assign("/");
  }

  function choose(id: Tab) {
    setTab(id);
    window.scrollTo({ top: 0 });
  }

  return (
    <div className="app">
      <aside>
        <div className="brand">
          <p className="mark">Mosaiva</p>
          <p className="aside-copy">One record for a complicated picture.</p>
        </div>
        <nav aria-label="Sections">
          {TABS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={tab === id ? "nav on" : "nav"}
              aria-current={tab === id ? "page" : undefined}
              onClick={() => choose(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="aside-foot">
          <label className="tz">
            Week timezone
            <select
              value={settings?.timezone ?? "UTC"}
              onChange={(event) => changeTimezone(event.target.value)}
            >
              {TIMEZONES.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </select>
          </label>
          {me.email && (
            <div className="account">
              <span className="meta">{me.email}</span>
              <button type="button" className="ghost small" onClick={signOut}>
                Sign out
              </button>
            </div>
          )}
        </div>
      </aside>
      <main>
        <p className="banner">
          Mosaiva tracks working hypotheses and coaching. It is not medical care, a diagnosis, or a prescription.
        </p>
        {tab === "hypotheses" && <Hypotheses />}
        {tab === "interventions" && <Interventions />}
        {tab === "research" && <Research />}
        {tab === "coach" && <Coach />}
        {tab === "mosaic" && <Mosaic />}
      </main>
    </div>
  );
}
