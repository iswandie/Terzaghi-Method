# Terzaghi Settlement Analysis System

An auditable engineering web application implementing Terzaghi's one-dimensional primary consolidation theory for normally consolidated and overconsolidated multilayer soil profiles.

## Run

Python 3.10+ is the only requirement.

```powershell
python app.py
```

Open <http://127.0.0.1:8000>.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Architecture

- `settlement_engine.py` — framework-independent calculations, SI conversion, mandatory validation, formula traces, multilayer settlement/time analysis.
- `app.py` — small standard-library static host and JSON calculation API.
- `static/` — responsive engineering UI, browser-side field feedback, charts, results, and printable report.
- `tests/` — known-result and validation unit tests.

## Engineering scope

Primary consolidation is calculated at each layer midpoint. Immediate and secondary settlement are explicitly not included. Results are for engineering analysis and require review by a qualified geotechnical engineer before design or construction use.