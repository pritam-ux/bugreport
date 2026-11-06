# BugSense AI

BugSense AI finds likely duplicate bug reports by meaning, predicts each report's component, priority and severity, and recommends a developer. People make the final decision every time.

**Stack:** React, Vite, Tailwind CSS, Lucide and Recharts on the frontend. FastAPI, Pydantic and MongoDB on the backend. Sentence-BERT (`all-MiniLM-L6-v2`, run with ONNX Runtime), TF-IDF and scikit-learn for the NLP.

## Quick start (Windows)

You need Python 3.12 and Node 20 or later. Docker and admin rights aren't needed.

```powershell
.\scripts\setup.ps1    # installs packages and MongoDB, loads sample data
.\scripts\dev.ps1      # starts everything
```

Then open http://localhost:5180. API docs are at http://localhost:8100/docs.

Setup downloads about 1 GB, most of it MongoDB. The trained models and embedding model are in the repo. The Python environment and database live in `%LOCALAPPDATA%\BugSenseAI`, because this project sits in OneDrive and sync locks live database files. `frontend/node_modules` does stay in the project folder, so you may want to exclude it from OneDrive sync.

### Sample accounts

All three use the password `BugSense2026!`. These are for local use only, and the seed script refuses to run when `ENVIRONMENT=production`.

| Role | Email | Can do |
|---|---|---|
| Admin | `admin@bugsense.dev` | Everything, including approving triage, deleting reports and changing roles |
| Developer | `developer@bugsense.dev` | Edit any report, assign developers, review duplicates |
| Reporter | `reporter@bugsense.dev` | Submit reports, edit their own text, review duplicates on their own reports |

Public sign-up always creates a Reporter.

### macOS, Linux or manual setup

```bash
docker compose up -d                   # MongoDB on port 27018, or set MONGODB_URI to your own

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                   # then set JWT_SECRET
python -m scripts.seed
uvicorn app.main:app --port 8100

cd ../frontend && npm install && npm run dev
```

## Try the main workflow

1. Sign in as the admin and open **Submit a bug**.
2. Enter the title `Application crashes when I click the login button` and any description, then submit.
3. The results page shows the five closest reports, the predictions, suggested developers and what each pipeline step produced.
4. Select **Review duplicates**, then **System stops working after pressing the sign-in button**. The two reports share almost no wording, but the model links them. Hover a tinted sentence to see its partner.
5. Mark the report as a duplicate or confirm it as unique.
6. Open **AI triage** to approve or edit the suggestions. The dashboard reflects each change straight away.

## How the NLP works

All model code is in [`backend/nlp`](backend/nlp), separate from the API. Routes and services only call `NlpEngine` in [`pipeline.py`](backend/nlp/pipeline.py).

| Step | File | What it does |
|---|---|---|
| Preprocess | `preprocess.py` | Removes HTML, URLs, timestamps, addresses and file paths, reduces stack traces to exception names and messages, then combines the fields |
| TF-IDF baseline | `similarity.py` | Stems words, removes stop words, and scores word overlap using unigrams and bigrams |
| Semantic match | `embeddings.py`, `similarity.py` | Compares 384-dimension Sentence-BERT vectors with cosine similarity and ranks the top 5 |
| Duplicate chance | `similarity.py`, `evaluation.py` | A logistic regression learns from labelled pairs how raw scores map to a probability, capped at 99% |
| Explanation | `highlight.py` | Links sentences with similar meaning and marks shared words |
| Classification | `classifier.py` | Tries TF-IDF, BERT and combined features for each target, and keeps the best under cross-validation |
| Developer recommendation | `recommender.py` | Scores expertise (30%), past fixes in the component (35%), similar past bugs (20%) and availability (15%), and returns a reason built from those facts |

### If a model is unavailable

- **BERT can't load** (for example, the model files are missing): duplicate search uses the TF-IDF baseline, and the app shows a warning with the reason.
- **Classifiers aren't trained:** reports still save, marked as having no predictions, and the app tells you to run `python -m scripts.train`.

## Measured results

`python -m scripts.train` calculates these numbers and saves them to `backend/artifacts/metrics.json`. The analytics page reads that file, so no metric is hardcoded.

| Duplicate detection | BERT | TF-IDF baseline |
|---|---|---|
| Recall@1 | 94.3% | 82.9% |
| Recall@5 | 98.6% | 100% |
| Precision | 77.5% | 66.1% |
| Recall | 78.6% | 55.7% |
| F1 | 78.0% | 60.5% |

| Classifier | Accuracy | Macro F1 | Always guessing the commonest label |
|---|---|---|---|
| Component | 75.0% | 74.9% | 15.8% |
| Priority | 45.9% | 43.0% | 42.9% |
| Severity | 54.6% | 46.6% | 44.4% |

### How far to trust these numbers

- **The dataset is small and hand-written.** The 196 reports in [`seed_bugs.psv`](backend/data/seed_bugs.psv), including 35 duplicate groups, are synthetic. No public bug dataset is bundled. Expect different results on real data.
- **Priority and severity are weak.** They only modestly beat guessing, so low-confidence predictions are flagged in the UI and nothing applies without review. Component prediction is the only classifier here that is clearly useful.
- **The evaluation avoids obvious leaks.** Reports in a duplicate group stay in the same cross-validation fold, and thresholds are chosen on different groups from those they're scored on. Choosing the best feature set by cross-validation score still makes the classifier numbers slightly optimistic.
- **Duplicate chance is relative to its training pairs.** Its negative examples are the hardest near-matches, so treat it as a ranking aid rather than a true real-world rate.

To train on your own data, export it with the same `|`-separated header and run:

```powershell
python -m scripts.train --dataset path\to\bugs.psv
```

Restart the API afterwards. Reports that share a value in the `group` column are treated as duplicates of each other.

## What is real and what is sample data

- **Computed by models:** embeddings, similarity scores, duplicate chances, predictions and recommendations.
- **Computed from the database:** every dashboard number and developer statistic.
- **Simulated by the seed script:** sample dates, assignments and resolution times. Seeded records are flagged, so the "Decisions from your team" analytics count real reviews only.

## Deploy to Vercel

`vercel.json` deploys the app as one project with two services: `backend` on `/api/*` and `frontend` on everything else. The backend fits the 500 MB Python limit at about 427 MB, because it uses ONNX Runtime instead of PyTorch. Vercel's services feature is in beta.

1. Create a hosted MongoDB database, such as MongoDB Atlas, and allow connections from Vercel.
2. Load the starting data from your computer. Choose your own password, because the default one is public:

   ```powershell
   cd backend
   $env:MONGODB_URI = "<your connection string>"
   $env:SEED_PASSWORD = "<a strong password>"
   python -m scripts.seed
   ```

3. Import the repo in Vercel and set these environment variables:

   | Variable | Value |
   |---|---|
   | `MONGODB_URI` | Your connection string |
   | `JWT_SECRET` | A random value of at least 32 characters |
   | `ENVIRONMENT` | `production` |

Limits on Vercel: attachments are capped at 4 MB, login throttling is per instance, and password reset needs a mail provider first. The first request after a quiet period is slower while the model loads. Retraining means committing the new files in `backend/artifacts`.

## API

Interactive docs are at `/docs`. Everything except register, login, password reset and health needs a bearer token.

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register`, `/login`, `/forgot-password`, `/reset-password`, `GET /api/auth/me` |
| Bugs | `POST` and `GET /api/bugs`, `GET`, `PUT` and `DELETE /api/bugs/{id}`, `POST /api/bugs/{id}/attachments`, `GET /api/bugs/{id}/attachments/{attachment_id}` |
| Duplicates | `POST /api/duplicates/search`, `POST /api/duplicates/check/{id}`, `GET /api/duplicates/{id}`, `POST /api/duplicates/confirm` |
| Triage | `POST /api/triage/predict`, `GET /api/triage/{id}`, `POST /api/triage/{id}/decision` |
| Developers | `GET` and `POST /api/developers`, `GET /api/developers/{id}` |
| Analytics | `GET /api/analytics/dashboard`, `/duplicates`, `/triage` |
| Users | `GET /api/users`, `PUT /api/users/{id}/role` (Admin) |
| System | `GET /api/health`, `GET /api/system/status` |

Beyond the original specification, the app adds `/duplicates/search`, the attachment routes, the triage decision route, the password reset routes, and the user role routes.

## Project layout

```
backend/
  app/
    routers/        HTTP routes and permission checks
    services/       Business logic and MongoDB access
    integrations/   Connector interface for future trackers
  nlp/              Models, independent of the API and database
  scripts/          train.py and seed.py
  data/             Labelled sample reports
  tests/            NLP and API tests
frontend/src/
  api/              API client and data-loading hook
  components/       Layout, charts, comparison view and shared UI
  pages/            One file per screen
scripts/            Windows setup and run scripts
```

MongoDB collections: `users`, `bug_reports`, `developers`, `duplicate_matches`, plus `counters` for readable IDs. Attachments (up to 4 MB each) are stored in MongoDB in a GridFS bucket called `attachments`, so the API needs no writable disk.

## Tests

The tests need MongoDB running. They use the real models and a separate `bugsense_ai_test` database, which they delete afterwards.

```powershell
cd backend
& "$env:LOCALAPPDATA\BugSenseAI\venv\Scripts\python.exe" -m pytest tests
```

## Known limits and next steps

- **Password reset email isn't connected.** No mail service is configured, so in development the reset link appears on screen. In production the API won't return it, so connect a mail provider in `routers/auth.py` before deploying.
- **Large datasets:** each search loads all candidates into memory and refits TF-IDF, which suits thousands of reports. Beyond that, use a vector index such as MongoDB Atlas Vector Search or FAISS behind `NlpEngine.find_duplicates`.
- **Login throttling is per process.** Use a shared store such as Redis if you run several API workers.
- **Tracker integrations aren't built.** `app/integrations` defines the connector interface. `services.bugs.create_bug` already accepts `source` and `external_id`, so imported reports can use the same pipeline.
- **Embedding model:** `backend/models` holds the quantized ONNX build of `all-MiniLM-L6-v2` (Apache 2.0), from Hugging Face.
- **Model retraining is manual.** Reviewer decisions are stored but not yet fed back into training.
- **Before production:** set `ENVIRONMENT=production`, use a new `JWT_SECRET`, enable MongoDB authentication and serve over HTTPS.
