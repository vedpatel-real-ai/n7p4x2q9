# WindScope — UK day-ahead wind forecast decision pilot

**A transparent, historical January 2026 pilot.** Built for the Gridbricks full-stack take-home assessment. React + Vite frontend, Python FastAPI backend, Docker Compose, Elexon BMRS wind forecast / actual data, and Vercel-hosted frontend/backend projects. Includes Elexon source attribution..

> This template intentionally contains **no fabricated wind readings**. Run the Elexon import before presenting or deploying the dashboard. Do not claim metrics or coverage that you haven't verified against upstream data.

## Business framing

The client buys electricity in the UK day-ahead market. Wind generation is uncertain; buyers want to see the last forecast actually available **before** a procurement decision and measure how closely historical as-of forecasts matched realized generation.

This is a retrospective pilot, **not live trade execution or procurement advice**. It cannot calculate the required purchase volume without demand and existing contracted generation, which the challenge expressly excludes.

## Essential scope and modelling decisions

- **Decision dates:** January 1–31, 2026, inclusive.
- **Delivery dates:** January 2–February 1, 2026 (each decision applies to next-day delivery). January 1 decisions cover January 2; no December 2025 decision dates are considered.
- **Illustrative decision cutoff:** **09:00 GMT/UTC** on decision day. This is intentionally earlier than the GB EPEX SPOT 60-min 09:20 GMT auction and Nord Pool N2EX 09:50 GMT gate closure. There are multiple GB day-ahead markets and cutoffs, including an afternoon half-hour auction. In a real deployment, ask the client's traders to confirm their relevant auction and operational order deadline. Do **not** imply 09:00 is the market's actual legal deadline.
- **WINDFOR selection:** For each delivery `startTime`, select the row with **greatest publishTime ≤ decision-day 09:00 UTC**. A later forecast is rejected (prevents look-ahead/data leakage). Using the latest forecast published *today* to predict a decision made in January is incorrect.
- **Actual:** Filter `FUELHH` to `fuelType == "WIND"`, keep latest published outturn version for each 30-minute `startTime`, then calculate each hour's average MW from its two consecutive half-hour observations. Require both half-hours; otherwise the hour is unscored.
- **Resolution:** 24 hourly WINDFOR targets per delivery day (744 in total), compared with each hour's arithmetic mean of two FUELHH half-hourly MW observations. This avoids inventing extra forecasts. January and February 1 have no UK daylight-saving changes; both UTC and GMT apply.
- **Unit:** MW (power). The averaged hourly observation is still MW (mean power), not MWh. If energy is required for a one-hour interval, multiply mean MW by one hour.
- **Error convention:** forecast − actual. Positive bias means overforecasting (potential shortfall), negative bias underforecasting. Missing forecast or actual is **missing**, never treated as zero.
- **Metrics:** MAE, RMSE, mean signed error/bias, P90 absolute error, and matched coverage. All metrics use only matched hours. Sample-level P90 is descriptive, not a probability guarantee.
- **Dataset comparability:** `WINDFOR` forecast coverage and the `FUELHH` WIND outturn category may not match exactly in included generation assets. Differences should not be described solely as numerical prediction errors without further mapping/reconciliation; this limitation is disclosed in the UI.

Sources:

- [WINDFOR /stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
- [FUELHH /stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [Elexon Developer Portal](https://developer.data.elexon.co.uk/)
- [Elexon wind generation explainer: hourly WINDFOR cadence](https://bmrs.elexon.co.uk/wind-generation)
- [GB EPEX trading timetable](https://www.epexspot.com/sites/default/files/2025-02/EPEX%20SPOT%20Trading%20Brochure%202025%20February.pdf)
- [N2EX closure details](https://support.nordpoolgroup.com/support/solutions/articles/8000088463-about-the-n2ex-day-ahead-auction)

## Directory guide

```text
wind-decision-pilot/
├── backend/
│   ├── analysis.py                 # pure as-of selection, alignment, error metrics
│   ├── main.py                     # FastAPI JSON, day details, CSV export
│   ├── scripts/fetch_elexon.py     # Elexon downloader with retries and source checks
│   ├── tests/test_analysis.py      # unit tests incl. after-cutoff exclusion
│   ├── data/jan2026.json          # generated AFTER fetch; not bundled as fake data
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/main.jsx               # React dashboard, interactive dates/charts/table
│   ├── src/styles.css
│   ├── vite.config.js              # local API proxy
│   ├── vercel.json                 # public frontend-to-backend API rewrites
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml             # frontend and backend for local pilot
├── vercel.json                    # legacy single-project Services experiment
└── README.md
```

## Quick start — Docker (Mac, Windows or Linux)

Install Docker Desktop, start Docker Engine, then run from the repository's **root**:

```bash
# 1. Fetch real as-of WINDFOR + FUELHH records from Elexon;
#    writes backend/data/jan2026.json via Docker volume mapping.
docker compose run --rm backend python -m scripts.fetch_elexon

# 2. Check core logic tests (must pass)
docker compose run --rm backend python -m unittest discover -s tests -v

# 3. Start both React and Python services
docker compose up --build
```

Open **http://localhost:5173** in the browser. FastAPI health check is at **http://localhost:8000/api/health**; interactive Python API docs at **http://localhost:8000/docs**. Once `jan2026.json` exists, the dashboard loads real Elexon data. Use **Ctrl+C** to stop containers, then `docker compose down` to clean up.

The fetch downloads forecast publications for January 1–31 and actuals published January 2–February 4, one publication-day request at a time. Connection, response errors, or zero matched pairs **fail loudly**; a blank or synthetic snapshot is never silently exported. We don't ship measured numerical findings until the API data has been downloaded and verified.

## Optional local workflow without Docker

Two terminals, from repository root:

```bash
# Terminal 1
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.fetch_elexon
python -m unittest discover -s tests -v
uvicorn main:app --reload --port 8000
```

```bash
# Terminal 2
cd frontend
npm install
npm run dev
```

## API endpoints

- `GET /api/health`: health and data-snapshot readiness.
- `GET /api/analysis`: Elexon provenance, methodology metadata, overall metrics, daily error metrics.
- `GET /api/days/2026-01-15`: 24 hourly rows and day scores.
- `GET /api/export.csv`: auditable hourly forecast vs mean actual export.

## Public deployment — Vercel

**Live dashboard:** https://frontend-iota-seven-58.vercel.app/

**Python API:** https://backend-six-alpha-27.vercel.app/

**Repository:** https://github.com/vedpatel-real-ai/n7p4x2q9

WindScope is deployed as **two Vercel projects** connected to the same GitHub repository:

| Project | Vercel root directory | Framework | Role |
| --- | --- | --- | --- |
| `frontend` | `frontend/` | Vite | React dashboard |
| `backend` | `backend/` | FastAPI | Historical snapshot and read-only API |

The deployed frontend uses `frontend/vercel.json` to rewrite its `/api/:path*` requests to the FastAPI backend. The local Vite development server uses `frontend/vite.config.js` for an equivalent Docker-local proxy. The repository-root `vercel.json` represents an earlier single-project Services experiment, not the active two-project setup.

### Verify before submitting

In an incognito/private browser window, verify:

1. [Dashboard](https://frontend-iota-seven-58.vercel.app/) loads the historical charts and dates with actual data, not an error or loading screen.
2. [API health](https://frontend-iota-seven-58.vercel.app/api/health) reports `ok:true`, `snapshot_ready:true`, `periods:744`.
3. [Analysis](https://frontend-iota-seven-58.vercel.app/api/analysis) reports `ready:true` and `summary.paired_periods:744`.
4. [CSV](https://frontend-iota-seven-58.vercel.app/api/export.csv) downloads nonempty forecast-versus-generation rows.
5. [Public repository](https://github.com/vedpatel-real-ai/n7p4x2q9) is readable without signing in.

This is a retrospective pilot, not a continuously updating electricity-trading application. Local tests and an apparently successful Vercel build do not replace independent production checks.

## Quality evidence

- Automated tests reject all forecasts published **after** decision cutoff, resolve multiple forecast vintages, ignore non-wind actual fuel, preserve 0-MW readings, check last delivery date (February 1), and verify error metrics.
- Input date-time parsing requires timezone offsets. Errors and gaps remain visible.
- CSV download exposes the selected forecast publication time for every interval (audit trail).
- Unit tests use tiny synthetic **test fixtures only**, never displayed as real measured results.
- Performance: static JSON snapshot prevents thousands of real-time Elexon requests on every dashboard visit.

## Pilot customer story (video part 1, ~4:30)

1. **0:00–0:40**: Procurement problem: renewable forecast uncertainty ahead of day-ahead buying; product value.
2. **0:40–1:30**: January 2026 as-of retrospective; 09:00 GMT timestamp and why not to use hindsight.
3. **1:30–2:40**: Show aggregate MAE, RMSE, signed bias, P90 error and matched coverage, using actual observed values (never invented).
4. **2:40–3:40**: Click a high-error day, examine wind forecast vs actual and publication timestamp.
5. **3:40–4:30**: Explain how positive forecast bias could increase purchase shortfall risk, and that demand/prices are excluded; next pilot stage.

## Technical walkthrough (video part 2, ~4:30)

1. **0:00–0:50**: Architecture: Elexon → Python downloader → deterministic as-of scoring → JSON snapshot → FastAPI → React.
2. **0:50–2:00**: Show `analysis.py`, `publishTime` cutoff and `startTime` matching, error/coverage calculations, missing handling.
3. **2:00–2:40**: Backend endpoints, example JSON and CSV audit trail.
4. **2:40–3:30**: Frontend date selection, line chart, coverage and interpretation.
5. **3:30–4:30**: Docker command, passing tests, Vercel URL/incognito verification, limitations and production improvements.

Record with QuickTime or macOS screen recorder (Shift+Command+5), join clips if needed, upload to YouTube as **Unlisted**. In YouTube Studio check the video plays without sign-in or permission hurdles. Keep combined video **under 10 minutes**. A video is mandatory in the challenge.

## What to submit

- Public anonymous-name GitHub repository URL
- Vercel/Heroku live app URL that anyone can view
- Unlisted YouTube URL (maximum 10 minutes; both audiences addressed)
- [Microsoft submission form](https://forms.cloud.microsoft/r/FTX6K2bbnU)

Open **all three URLs in an incognito/private browser** before filling the form. **Do not submit without the video**. The assignment explicitly permits AI tools. Disclose below accurately.

## AI-assistance disclosure

AI tools (OpenAI ChatGPT) were used to assist with requirements analysis, research, design, implementation, test creation, documentation and presentation planning. The candidate must independently run, understand, validate and review the final product, data and code before submitting.

## Privacy & safety

Only the two Elexon datasets from the assignment are ingested. No API key, bank information, demand data, personal data or client confidential records are required. No executable recruiter attachments or third-party scripts are necessary. The API is read-only.

## Resolution validation note (v1.1)

The original starter showed 744 pairs out of 1,488 half-hours (50% coverage). Elexon publishes WINDFOR at **hourly** delivery timestamps; FUELHH is **half-hourly**. The original denominator was wrong for scoring the native forecast. v1.1 now scores **744 forecasted hours** (24 x 31 days) using **two FUELHH readings averaged per hour**. Coverage may not reach 100% if some actuals/forecasts are genuinely missing. Metrics must be regenerated and reviewed with a new import, and historical selection still forbids forecasts published after the stated cutoff.

## Elexon data attribution and licence

Contains BMRS data © Elexon Limited copyright and database right 2026. The public Elexon open-data licence permits redistribution and commercial or non-commercial adaptation with attribution. See [the BMRS open-data licence](https://www.elexon.co.uk/bsc/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/). The product does not imply endorsement by Elexon. The source is acknowledged in the customer-facing dashboard footer.

Deployment preflight: confirm `backend/data/jan2026.json` exists and is committed to the deployment repository (the starter excludes no `backend/data/` files via `.gitignore`); this includes processed generation readings obtained from Elexon. Check the deployed `/api/health` and `/api/analysis` routes after publishing, because local Docker's volume data does not automatically move to Vercel.

Production routing configuration is in `frontend/vercel.json`. The root `vercel.json` is from an earlier Services experiment and is not used by the active two-project deployment.
