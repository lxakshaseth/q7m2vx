# Wind Forecast Intelligence frontend

This Vite + React dashboard presents the existing FastAPI analysis; it does not
call Elexon or calculate forecast selection, cadence reconciliation, or metrics in
the browser.

## Run locally

Start the backend from the repository root in one PowerShell window:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

This backend command is run from the repository root. If you instead start it
while your prompt is already in `backend`, use `--app-dir ..` after the app
path so Python can resolve the top-level package.

In a second PowerShell window:

```powershell
Set-Location .\frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The Vite development server proxies `/api` to
the backend, avoiding a browser cross-origin request during local development.

## Environment configuration

`VITE_API_BASE_URL` is the browser-facing API base path or URL, including
`/api` (for example, `/api` or `https://example.utility.uk/api`). It defaults
to `/api`, which is appropriate for the Vite proxy and a production reverse
proxy. `VITE_API_PROXY_TARGET` is development-only and defaults to
`http://127.0.0.1:8000`.

Keep the API base set to `/api` for the local run above. If pointing directly
to another backend origin, that backend must permit the dashboard origin.

## Useful commands

```powershell
# Build the static production bundle
npm run build

# Serve the completed bundle locally after building
npm run preview
```

## Interface notes for the demonstration

- The delivery-date and decision-cut-off controls query
  `GET /api/intervals`; changing either refreshes the displayed day.
- `12:00 Europe/London` is deliberately labelled as a configurable demo
  assumption. It is distinct from the selected forecast publication time
  shown in the chart tooltip and detail table.
- WINDFOR is hourly while FUELHH is half-hourly. The backend matches identical
  `startTime` values only, and the dashboard leaves unmatched `:30` rows visible
  as missing forecasts rather than inventing intermediate values.
- Null API values are kept as gaps: the charts do not interpolate them, the
  table names unavailable forecasts, and the coverage/data-quality sections
  explain their effect on metrics.
- Results are from live public source data, so values can vary if Elexon
  revises its historical records.
