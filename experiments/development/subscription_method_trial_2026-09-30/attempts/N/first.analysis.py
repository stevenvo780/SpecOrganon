import csv
import datetime as dt
import hashlib
import json
import math
import pathlib
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: analysis.py INPUT_DIRECTORY')
    root = pathlib.Path(sys.argv[1])
    csv_path = root / 'sample_first_complete_week.csv'
    manifest_path = root / 'source_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    raw = csv_path.read_bytes()
    selection = manifest['selection']
    digest = hashlib.sha256(raw).hexdigest()
    if digest != selection['sample_sha256']:
        raise ValueError('sample SHA-256 does not match manifest')
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        expected = selection['columns']
        if reader.fieldnames != expected:
            raise ValueError('CSV columns do not match manifest')
        records = list(reader)
    stamps = [dt.datetime.strptime(row['date'], '%Y-%m-%d %H:%M:%S') for row in records]
    interval = int(selection['interval_minutes'])
    continuous = all((b - a).total_seconds() == interval * 60 for a, b in zip(stamps, stamps[1:]))
    if not records:
        raise ValueError('CSV has no observations')
    appliances_daily = {}
    appliances_wh = 0.0
    lights_wh = 0.0
    for stamp, row in zip(stamps, records):
        appliance = float(row['Appliances'])
        lights = float(row['lights'])
        if not math.isfinite(appliance) or not math.isfinite(lights):
            raise ValueError('non-finite energy value')
        appliances_wh += appliance
        lights_wh += lights
        day = stamp.strftime('%Y-%m-%d')
        appliances_daily[day] = appliances_daily.get(day, 0.0) + appliance / 1000.0
    appliances_kwh = appliances_wh / 1000.0
    lights_kwh = lights_wh / 1000.0
    result = {
        'rows': len(records),
        'first_timestamp': stamps[0].strftime('%Y-%m-%d %H:%M:%S'),
        'last_timestamp': stamps[-1].strftime('%Y-%m-%d %H:%M:%S'),
        'interval_minutes': interval,
        'continuous': continuous,
        'appliances_total_kwh': appliances_kwh,
        'daily_appliances_kwh': appliances_daily,
        'lights_total_kwh': lights_kwh,
        'units': {
            'appliances_total_kwh': 'kWh',
            'daily_appliances_kwh': 'kWh',
            'lights_total_kwh': 'kWh'
        },
        'sample_sha256': digest,
        'manifest_rows_match': len(records) == selection['rows'],
        'selection_bounds_match': (
            stamps[0].strftime('%Y-%m-%d %H:%M:%S') == selection['start_inclusive'] and
            stamps[-1] < dt.datetime.strptime(selection['end_exclusive'], '%Y-%m-%d %H:%M:%S')
        )
    }
    print(json.dumps(result, allow_nan=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
