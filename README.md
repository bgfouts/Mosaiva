# Mosaiva

Mosaiva is a local wellness record for one person with a complicated, uncertain health picture. It keeps working hypotheses (not diagnoses), the interventions you are actually using, freely available journal PDFs, a voice-only coach, and a weekly Mosaic review that suggests at most one change.

Mosaiva does not diagnose, prescribe, or invent doses. A medicine it names is something to ask a clinician about. Stopping a prescribed medicine is a conversation with that clinician.

## Run locally

The API binds to `127.0.0.1` only. The SQLite database and downloaded PDFs stay in `data/` on this machine.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r api/requirements.txt
cp .env.example .env
# Put your OpenAI key in .env for live voice and Mosaic reviews.
uvicorn app.main:app --app-dir api --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd web
npm install
npm run dev
```

Open http://127.0.0.1:5173. The web app proxies `/api` to the local API.

## Environment

| Name | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Stays on this machine. The browser never receives it. |
| `OPENAI_LIVE_MODEL` | Voice model. Default `gpt-live-1`. |
| `OPENAI_REASONING_MODEL` | Mosaic, research notes, and the GPT-Live tool backend. Default `gpt-5.6-terra`. |

Without a key, Coach shows an error and does not offer typing. Mosaic returns an error instead of inventing a review.

## What each section does

- **Hypotheses.** A differential of working theories: description, why it might fit, a qualitative confidence label, and a likely role. Those labels are not diagnoses. Mosaic keeps a separate internal estimate and can move it later.
- **Interventions.** Medicines, diet, lifestyle, supplements, and therapy, with benefit and side-effect burden. Items you are not taking can be marked “ask a clinician” and cannot store a dose.
- **Research.** Web search, then a filter: the file must download as a PDF, the host cannot be a paywall bypass, and the journal domain must be on `api/app/data/reputable_journals.json`.
- **Coach.** Voice only, via GPT-Live. The browser sends its WebRTC offer to this API, which opens the Live session. Tool calls stay pending until you confirm them on screen or with a spoken yes.
- **Mosaic.** One review per local week, in the timezone from the sidebar. It updates working estimates and suggests add, remove, or hold. A second run in the same week returns the same review.

## Tests

```bash
source .venv/bin/activate
pytest api
```
