# Terzaghi Settlement Analysis System

An auditable engineering web application implementing Terzaghi's one-dimensional primary consolidation theory for normally consolidated and overconsolidated multilayer soil profiles.

## Run locally

Python 3.12+ is recommended. Install the runtime dependency first:

```powershell
python -m pip install -r requirements.txt
python -m flask --app api.app run --port 8000
```

Open <http://127.0.0.1:8000>.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Architecture

- `settlement_engine.py` — framework-independent calculations, SI conversion, mandatory validation, formula traces, multilayer settlement/time analysis.
- `api/app.py` — Flask WSGI application for local use and Vercel Functions.
- `static/` — responsive engineering UI, browser-side field feedback, charts, results, and printable report.
- `tests/` — known-result and validation unit tests.

## Deploy to Vercel

Import this repository in Vercel. `vercel.json` routes the application through
the Flask function, while `requirements.txt` installs Flask. No custom build
or start command is required.

## Engineering scope

Primary consolidation is calculated at each layer midpoint. Immediate and secondary settlement are explicitly not included. Results are for engineering analysis and require review by a qualified geotechnical engineer before design or construction use.