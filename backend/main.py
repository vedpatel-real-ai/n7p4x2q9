"""Small read-only FastAPI backend for the January 2026 historical decision pilot."""
import csv
import io
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

DATA_PATH = Path(__file__).resolve().parent / 'data' / 'jan2026.json'
app = FastAPI(title='Wind Decision Pilot API', version='1.0.0')


def load_snapshot():
    if not DATA_PATH.is_file():
        return None
    try:
        return json.loads(DATA_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


@app.get('/api/health')
def health():
    snapshot = load_snapshot()
    return {'ok': True, 'snapshot_ready': snapshot is not None, 'periods': snapshot['summary']['paired_periods'] if snapshot else 0}


@app.get('/api/analysis')
def analysis():
    snapshot = load_snapshot()
    if snapshot is None:
        return {
            'ready': False,
            'message': 'No real Elexon snapshot yet. Run python -m scripts.fetch_elexon, then refresh.',
            'metadata': {'status': 'awaiting_data'},
        }
    return {'ready': True, 'metadata': snapshot['metadata'], 'summary': snapshot['summary'], 'daily_metrics': snapshot['daily_metrics']}


@app.get('/api/days/{decision_date}')
def day_detail(decision_date: str):
    snapshot = load_snapshot()
    if snapshot is None:
        raise HTTPException(503, 'Historical Elexon data has not been loaded yet')
    days = {d['decision_date']: d for d in snapshot['days']}
    if decision_date not in days:
        raise HTTPException(404, 'Date must be a January 2026 decision date')
    return days[decision_date]


@app.get('/api/export.csv')
def export_csv():
    snapshot = load_snapshot()
    if snapshot is None:
        raise HTTPException(503, 'No historical snapshot loaded')
    output = io.StringIO()
    columns = ['decision_date', 'delivery_date', 'cutoff_utc', 'start_time', 'forecast_published_at', 'forecast_mw', 'actual_mw', 'error_mw']
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for d in snapshot['days']:
        for r in d['rows']:
            writer.writerow({**{'decision_date': d['decision_date'], 'delivery_date': d['delivery_date'], 'cutoff_utc': d['cutoff_utc']}, **{k: r.get(k) for k in columns[3:]}})
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="january-2026-wind-asof.csv"'})
