# Mosaiva

Mosaiva is a private wellness record for one person with a complicated, uncertain health picture. It keeps working hypotheses (not diagnoses), the interventions you are actually using, freely available journal PDFs, a voice-only coach, and a weekly Mosaic review that suggests at most one change.

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

Open http://127.0.0.1:5173. The web app proxies `/api` to the local API. Locally there is no sign-in unless `GOOGLE_CLIENT_ID` is set.

## Deploy to Vercel

The deployment runs the FastAPI app as one Python function (`index.py`) and serves the built web app from Vercel's CDN. Data lives in Neon Postgres; saved PDFs live in a private Vercel Blob store. Every `/api` route except sign-in and `/api/health` requires a Google account on the allowlist.

1. **Import the repo** in Vercel (Add New → Project). Leave the framework preset on FastAPI; `vercel.json` already sets the build command.
2. **Database.** In the project, open Storage → Create → Neon (Postgres) and connect it to the project. That sets `DATABASE_URL`. Tables and the starter hypotheses, interventions, and papers are created on the first request.
3. **PDF storage.** Storage → Create → Blob, choose **Private**, and connect it to the project.
4. **Google OAuth client.** In Google Cloud Console → APIs & Services:
   - Configure the OAuth consent screen (External, scopes `openid` and `email`). While the app is in Testing, add both Google accounts as test users.
   - Credentials → Create credentials → OAuth client ID → Web application.
   - Authorized redirect URI: `https://<your-production-domain>/api/auth/callback`.
5. **Environment variables** (Settings → Environment Variables, Production):

   | Name | Value |
   | --- | --- |
   | `GOOGLE_CLIENT_ID` | From the OAuth client. |
   | `GOOGLE_CLIENT_SECRET` | From the OAuth client. |
   | `MOSAIVA_ALLOWED_EMAILS` | The two Gmail addresses, comma-separated. |
   | `MOSAIVA_SESSION_SECRET` | 32+ random characters, e.g. `openssl rand -base64 48`. Changing it signs everyone out. |
   | `MOSAIVA_PUBLIC_URL` | `https://<your-production-domain>`. Keeps the OAuth redirect on the domain Google knows. |
   | `OPENAI_API_KEY` | Server-side only. |

6. **Redeploy** so the variables take effect, open the production URL, and sign in.

A deployment with a missing or short secret, client ID, or allowlist refuses every request (503) instead of opening up. Preview deployments use other domains, so Google sign-in only works there if you add that preview's callback URL to the OAuth client and set `MOSAIVA_PUBLIC_URL` for the Preview environment.

Function duration is capped at 300 seconds (`vercel.json`). A Mosaic review or a coach question plan that runs longer than the plan allows will fail rather than finish in the background.

## Environment

| Name | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Stays on the server. The browser never receives it. |
| `OPENAI_LIVE_MODEL` | Voice model. Default `gpt-live-1`. |
| `OPENAI_REASONING_MODEL` | Mosaic, research notes, and the GPT-Live tool backend. Default `gpt-5.6-terra`. |
| `MOSAIVA_DATABASE_URL` / `DATABASE_URL` | Postgres URL. Empty means `data/mosaiva.db` (SQLite). |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in. |
| `MOSAIVA_ALLOWED_EMAILS` | Comma-separated Google accounts that can open the record. Checked on every request. |
| `MOSAIVA_SESSION_SECRET` | Signs the 30-day session cookie. At least 32 characters. |
| `MOSAIVA_PUBLIC_URL` | Optional base URL for the OAuth redirect. |
| `BLOB_READ_WRITE_TOKEN` | Vercel Blob. Without it, PDFs are written to `data/papers/`. |

Without an OpenAI key, Coach shows an error and does not offer typing. Mosaic returns an error instead of inventing a review.

## What each section does

- **Hypotheses.** A differential of working theories: description, why it might fit, a qualitative confidence label, and a likely role. Those labels are not diagnoses. Mosaic keeps a separate internal estimate and can move it later.
- **Interventions.** Medicines, diet, lifestyle, supplements, and therapy, with benefit and side-effect burden. A potential list is seeded on startup when those names are missing. Medicines in that list are questions for a clinician and cannot store a dose. Diet, supplements, and routines are marked potential rather than already in use.
- **Research.** Web search, then a filter: the file must download as a PDF, the host cannot be a paywall bypass, and the journal domain must be on `api/app/data/reputable_journals.json`. A starter set of open-access PDFs ships with the app and is added on startup when those titles are missing. The notes are background for a working idea or a clinician question. They are not doses and not instructions to start a medicine.
- **Coach.** Voice only, via GPT-Live. It opens by asking how you are today, and asks how you have been since last time when that check-in was more than a day ago. While you answer, the backend drafts a few clinical questions. The visit ends after 5 to 7 replies, with a goodbye that it has what it needs for today. Tool calls stay pending until you confirm them.
- **Mosaic.** One review per local week, in the timezone from the sidebar. It updates working estimates and suggests add, remove, or hold. A second run in the same week returns the same review.

## Tests

```bash
source .venv/bin/activate
pytest api
```

To run the same tests against Postgres, point them at an empty database you can drop tables in:

```bash
MOSAIVA_TEST_DATABASE_URL=postgres://user:pass@127.0.0.1:5432/mosaiva_test pytest api
```
