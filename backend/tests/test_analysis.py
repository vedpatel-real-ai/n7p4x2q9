import unittest
from datetime import datetime
from analysis import aggregate, parse_utc, process, percentile


def stamp(date, hour=0):
    return date + f'T{hour:02d}:00:00Z'


class ForecastAsOfTests(unittest.TestCase):
    def test_latest_pre_cutoff_wins_not_future_leakage(self):
        target = '2026-01-02T00:00:00Z'
        fs = [
            {'startTime': target, 'publishTime': '2026-01-01T06:00:00Z', 'generation': 900},
            {'startTime': target, 'publishTime': '2026-01-01T08:45:00Z', 'generation': 1100},
            {'startTime': target, 'publishTime': '2026-01-01T09:01:00Z', 'generation': 700},
        ]
        ac = [{'startTime': target, 'publishTime': '2026-01-02T01:00:00Z', 'fuelType': 'WIND', 'generation': 900},
              {'startTime': '2026-01-02T00:30:00Z', 'publishTime': '2026-01-02T01:00:00Z', 'fuelType': 'WIND', 'generation': 1100},
              {'startTime': target, 'fuelType': 'SOLAR', 'generation': 400}]
        output = process(fs, ac)
        row = output['days'][0]['rows'][0]
        self.assertEqual(row['forecast_mw'], 1100)
        self.assertEqual(row['actual_mw'], 1000)
        self.assertEqual(row['error_mw'], 100)
        self.assertEqual(row['forecast_published_at'], '2026-01-01T08:45:00Z')
        self.assertEqual(output['summary']['paired_periods'], 1)
        self.assertEqual(len(output['days']), 31)
        self.assertEqual(output['summary']['total_periods'], 31 * 24)

    def test_no_forecast_is_missing_not_zero(self):
        output = process([], [{'startTime': '2026-01-02T00:00:00Z', 'fuelType': 'WIND', 'generation': 0}, {'startTime': '2026-01-02T00:30:00Z', 'fuelType': 'WIND', 'generation': 0}])
        row = output['days'][0]['rows'][0]
        self.assertIsNone(row['forecast_mw'])
        self.assertEqual(row['actual_mw'], 0)
        self.assertIsNone(row['error_mw'])
        self.assertIsNone(output['summary']['mae_mw'])

    def test_error_metrics(self):
        rows = [{'forecast_mw': f, 'actual_mw': a} for f, a in [(120, 100), (90, 100), (None, 100)]]
        m = aggregate(rows)
        self.assertEqual(m['paired_periods'], 2)
        self.assertAlmostEqual(m['mae_mw'], 15)
        self.assertEqual(m['bias_mw'], 5)
        self.assertAlmostEqual(m['rmse_mw'], 15.8)
        self.assertAlmostEqual(m['coverage_pct'], 66.7)

    def test_last_decision_targets_february_first(self):
        x = process([{'startTime': '2026-02-01T23:00:00Z', 'publishTime': '2026-01-31T08:30:00Z', 'generation': 2500}], [])
        last = x['days'][-1]['rows'][-1]
        self.assertEqual(last['start_time'], '2026-02-01T23:00:00Z')
        self.assertEqual(last['forecast_mw'], 2500)

    def test_hourly_actual_is_mean_of_two_half_hours(self):
        f = [{'startTime': '2026-01-02T02:00:00Z', 'publishTime': '2026-01-01T08:30:00Z', 'generation': 2000}]
        a = [{'startTime': '2026-01-02T02:00:00Z', 'fuelType': 'WIND', 'generation': 1000},
             {'startTime': '2026-01-02T02:30:00Z', 'fuelType': 'WIND', 'generation': 1500}]
        row = process(f, a)['days'][0]['rows'][2]
        self.assertEqual(row['actual_mw'], 1250)
        self.assertEqual(row['error_mw'], 750)

    def test_missing_second_half_hour_is_unscored(self):
        f = [{'startTime': '2026-01-02T02:00:00Z', 'publishTime': '2026-01-01T08:30:00Z', 'generation': 2000}]
        a = [{'startTime': '2026-01-02T02:00:00Z', 'fuelType': 'WIND', 'generation': 1000}]
        result = process(f, a)
        self.assertIsNone(result['days'][0]['rows'][2]['actual_mw'])
        self.assertEqual(result['summary']['paired_periods'], 0)

    def test_non_hourly_forecast_not_used(self):
        f = [{'startTime': '2026-01-02T02:30:00Z', 'publishTime': '2026-01-01T08:30:00Z', 'generation': 2000}]
        self.assertEqual(process(f, [])['summary']['paired_periods'], 0)
        self.assertIsNone(process(f, [])['days'][0]['rows'][2]['forecast_mw'])

    def test_timestamp_requires_timezone(self):
        with self.assertRaises(ValueError):
            parse_utc('2026-01-01T08:00:00')

    def test_percentile(self):
        self.assertEqual(percentile([0, 10, 20], 0.9), 18)


if __name__ == '__main__':
    unittest.main()
