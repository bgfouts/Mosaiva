import { useEffect, useState } from "react";
import { api } from "./api";
import { Coach } from "./sections/Coach";
import { Hypotheses } from "./sections/Hypotheses";
import { Interventions } from "./sections/Interventions";
import { Mosaic } from "./sections/Mosaic";
import { Research } from "./sections/Research";
import { Settings, TIMEZONES } from "./types";

const TABS = [
  ["hypotheses", "Hypotheses"],
  ["interventions", "Interventions"],
  ["research", "Research"],
  ["coach", "Coach"],
  ["mosaic", "Mosaic"],
] as const;

type Tab = (typeof TABS)[number][0];

export function App() {
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

  return (
    <div className="app">
      <aside>
        <p className="mark">Mosaiva</p>
        <p className="aside-copy">One local record for a complicated picture.</p>
        <nav>
          {TABS.map(([id, label]) => (
            <button key={id} type="button" className={tab === id ? "nav on" : "nav"} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
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
