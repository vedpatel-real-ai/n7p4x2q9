"""Download Jan 2026 as-published Elexon data and create a real historical snapshot.

Run inside backend working directory: python -m scripts.fetch_elexon
Requires internet access. No mock data is written into the product snapshot.
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from analysis import process

ROOT = 'https://data.elexon.co.uk/bmrs/api/v1'
OUTPUT = Path(__file__).resolve().parents[1] / 'data' / 'jan2026.json'


def request_window(dataset: str, day: date) -> list[dict]:
    following = day + timedelta(days=1)
    params = urlencode({
        'publishDateTimeFrom': day.isoformat() + 'T00:00:00Z',
        'publishDateTimeTo': following.isoformat() + 'T00:00:00Z',
    })
    url = f'{ROOT}/datasets/{dataset}/stream?{params}'
    for attempt in range(5):
        try:
            req = Request(url, headers={'User-Agent': 'WindDecisionPilot/1.0 educational technical challenge', 'Accept': 'application/json'})
            with urlopen(req, timeout=35) as response:
                payload = json.load(response)
            if isinstance(payload, dict):
                payload = payload.get('data', [])
            if not isinstance(payload, list):
                raise RuntimeError(f'{dataset} {day}: unexpected response type')
            return payload
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as ex:
            if isinstance(ex, HTTPError) and ex.code in (400, 401, 403, 404):
                raise RuntimeError(f'{dataset} {day}: API HTTP {ex.code}; verify endpoint and parameters: {url}') from ex
            if attempt == 4:
                raise RuntimeError(f'{dataset} {day}: API unavailable after retries: {ex}') from ex
            print(f'  Retrying {dataset} {day} ({ex})...')
            time.sleep(min(2 ** attempt, 10))
    raise AssertionError('unreachable')


def fetch_days(dataset: str, start: date, end_exclusive: date) -> list[dict]:
    output = []
    current = start
    while current < end_exclusive:
        batch = request_window(dataset, current)
        output.extend(batch)
        print(f'  {dataset} {current}  +{len(batch)} records', flush=True)
        current += timedelta(days=1)
        time.sleep(0.12)
    return output


def main() -> None:
    print('Downloading historical Elexon BMRS records (may take a few minutes).')
    print('Decision dates Jan 1–31; deliveries Jan 2–Feb 1. Forecast cutoff 09:00 UTC.')
    forecasts = fetch_days('WINDFOR', date(2026, 1, 1), date(2026, 2, 1))
    # Actual outturn may be published after delivery; allow through Feb 4 inclusive.
    actuals = fetch_days('FUELHH', date(2026, 1, 2), date(2026, 2, 5))
    print('Normalizing, selecting historical forecast vintages, and scoring...')
    snapshot = process(forecasts, actuals)
    snapshot['metadata']['source_counts'] = {
        'raw_windfor_rows': len(forecasts),
        'raw_fuelhh_rows_all_fuels': len(actuals),
        'raw_fuelhh_wind_rows': sum(str(r.get('fuelType', '')).upper() == 'WIND' for r in actuals),
    }
    print(json.dumps({'counts': snapshot['metadata']['source_counts'], 'summary': snapshot['summary']}, indent=2))
    if snapshot['summary']['paired_periods'] == 0:
        print('ERROR: no valid forecast/actual pairs; NOT saving a blank snapshot. Inspect API data windows and fields.', file=sys.stderr)
        sys.exit(2)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(snapshot, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
    print(f'Saved REAL Elexon snapshot to {OUTPUT}, {OUTPUT.stat().st_size:,} bytes')
    if snapshot['summary']['coverage_pct'] < 60:
        print('WARNING: coverage under 60%. Inspect data before using for business decisions.')


if __name__ == '__main__':
    main()
