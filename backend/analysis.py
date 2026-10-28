"""Pure as-of evaluation: hourly WINDFOR against mean of two FUELHH half-hours."""
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from math import sqrt
from statistics import mean
from typing import Any

START_DECISION = date(2026, 1, 1)
END_DECISION = date(2026, 1, 31)
CUTOFF_HOUR_UTC = 9  # illustrative morning auction planning cutoff, before GB gate closures


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError(f'Timestamp has no UTC offset: {value!r}')
    return dt.astimezone(timezone.utc)


def canonical(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def valid_power(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    from math import isfinite
    return number if isfinite(number) and number >= 0 else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def aggregate(rows: list[dict]) -> dict[str, float | int | None]:
    """Scores only paired intervals; error = forecast minus actual in MW."""
    pairs = [r for r in rows if r['forecast_mw'] is not None and r['actual_mw'] is not None]
    errors = [float(r['forecast_mw']) - float(r['actual_mw']) for r in pairs]
    return {
        'paired_periods': len(pairs),
        'total_periods': len(rows),
        'coverage_pct': round(100 * len(pairs) / len(rows), 1) if rows else 0,
        'mae_mw': round(mean(abs(e) for e in errors), 1) if errors else None,
        'rmse_mw': round(sqrt(mean(e ** 2 for e in errors)), 1) if errors else None,
        'bias_mw': round(mean(errors), 1) if errors else None,
        'p90_abs_error_mw': round(percentile([abs(e) for e in errors], 0.90), 1) if errors else None,
        'overforecast_pct': round(100 * sum(e > 0 for e in errors) / len(errors), 1) if errors else None,
    }


def process(forecasts: list[dict], actuals: list[dict]) -> dict:
    """Use exactly one latest pre-cutoff hourly WINDFOR version per 60-minute target.

    Actuals may arrive after delivery; forecasts MUST be historical as-of only.
    """
    actual_by_start: dict[str, tuple[datetime, float]] = {}
    for row in actuals:
        if str(row.get('fuelType', '')).upper() != 'WIND':
            continue
        mw = valid_power(row.get('generation'))
        if mw is None or not row.get('startTime'):
            continue
        try:
            target = parse_utc(row['startTime'])
            publication = parse_utc(row['publishTime']) if row.get('publishTime') else target
        except ValueError:
            continue
        key = canonical(target)
        if key not in actual_by_start or publication > actual_by_start[key][0]:
            actual_by_start[key] = (publication, mw)

    candidates: dict[tuple[str, str], tuple[datetime, float]] = {}
    for row in forecasts:
        mw = valid_power(row.get('generation'))
        if mw is None or not row.get('startTime') or not row.get('publishTime'):
            continue
        try:
            target = parse_utc(row['startTime'])
            published = parse_utc(row['publishTime'])
        except ValueError:
            continue
        # Elexon publishes hourly WINDFOR targets. Do not invent half-hourly forecasts.
        if target.minute != 0 or target.second != 0:
            continue
        decision_day = target.date() - timedelta(days=1)
        if not START_DECISION <= decision_day <= END_DECISION:
            continue
        cutoff = datetime.combine(decision_day, time(CUTOFF_HOUR_UTC), tzinfo=timezone.utc)
        if published > cutoff:
            continue  # prohibit lookahead and post-auction forecast data
        key = (decision_day.isoformat(), canonical(target))
        if key not in candidates or published > candidates[key][0]:
            candidates[key] = (published, mw)

    days = []
    all_rows = []
    cursor = START_DECISION
    while cursor <= END_DECISION:
        delivery_day = cursor + timedelta(days=1)
        values = []
        for i in range(24):  # 24 hourly WINDFOR targets per day; no DST transition
            target = datetime.combine(delivery_day, time(), tzinfo=timezone.utc) + timedelta(hours=i)
            start = canonical(target)
            pick = candidates.get((cursor.isoformat(), start))
            # FUELHH is 30-minute MW. Two matching observations produce
            # the same-hour average power (MW) for comparison with WINDFOR.
            # If either half-hour is absent, mark the whole hour missing.
            actual_first = actual_by_start.get(start)
            actual_second = actual_by_start.get(canonical(target + timedelta(minutes=30)))
            forecast_mw = pick[1] if pick else None
            actual_mw = round((actual_first[1] + actual_second[1]) / 2, 3) if actual_first and actual_second else None
            values.append({
                'start_time': start,
                'label_utc': target.strftime('%H:%M'),
                'forecast_mw': forecast_mw,
                'actual_mw': actual_mw,
                'forecast_published_at': canonical(pick[0]) if pick else None,
                'error_mw': round(forecast_mw - actual_mw, 3) if forecast_mw is not None and actual_mw is not None else None,
            })
        day = {
            'decision_date': cursor.isoformat(),
            'delivery_date': delivery_day.isoformat(),
            'cutoff_utc': f'{cursor.isoformat()}T09:00:00Z',
            'metrics': aggregate(values),
            'rows': values,
        }
        days.append(day)
        all_rows.extend(values)
        cursor += timedelta(days=1)
    return {
        'metadata': {
            'data_source': 'Elexon BMRS FUELHH (WIND) and WINDFOR /stream',
            'decision_window': '2026-01-01/2026-01-31 inclusive',
            'delivery_window': '2026-01-02/2026-02-01 inclusive',
            'selection_rule': 'Latest hourly WINDFOR publication <= 09:00 UTC on decision day for each hourly delivery target',
            'cutoff_note': '09:00 GMT is a deliberately conservative illustrative cutoff, not a universal GB market gate closure.',
            'error_convention': 'forecast minus actual: positive error is overforecast (shortfall risk)',
            'resolution': 'Hourly WINDFOR; FUELHH half-hourly WIND outturn aggregated to hourly mean MW',
            'aggregation_rule': 'For each hour, average the two FUELHH 30-minute wind MW readings; require both.',
            'units': 'MW',
            'status': 'historical_backtest',
        },
        'summary': aggregate(all_rows),
        'daily_metrics': [
            {'date': d['decision_date'], 'delivery_date': d['delivery_date'], **d['metrics']}
            for d in days
        ],
        'days': days,
    }
