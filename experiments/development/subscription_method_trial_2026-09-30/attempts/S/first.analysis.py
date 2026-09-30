import csv, datetime as dt, hashlib, json, math, pathlib, sys

def main():
    root = pathlib.Path(sys.argv[1])
    sample = root / 'sample_first_complete_week.csv'
    manifest_path = root / 'source_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    raw = sample.read_bytes()
    expected_hash = manifest['selection']['sample_sha256']
    actual_hash = hashlib.sha256(raw).hexdigest()
    expected_rows = int(manifest['selection']['rows'])
    interval = int(manifest['selection']['interval_minutes'])
    with sample.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        required = ('date', 'Appliances', 'lights')
        if any(c not in headers for c in required):
            raise ValueError('missing required CSV columns')
        records = list(reader)
    times = [dt.datetime.strptime(r['date'], '%Y-%m-%d %H:%M:%S') for r in records]
    appliances = [float(r['Appliances']) for r in records]
    lights = [float(r['lights']) for r in records]
    if not all(math.isfinite(x) for x in appliances + lights):
        raise ValueError('non-finite energy value')
    deltas = [(b-a).total_seconds() for a, b in zip(times, times[1:])]
    continuous = (len(times) == expected_rows and bool(times) and
                  all(x == interval * 60 for x in deltas))
    daily_wh = {}
    for t, v in zip(times, appliances):
        key = t.strftime('%Y-%m-%d')
        daily_wh[key] = daily_wh.get(key, 0.0) + v
    daily_kwh = {k: v / 1000.0 for k, v in sorted(daily_wh.items())}
    result = {
        'rows': len(records),
        'first_timestamp': times[0].strftime('%Y-%m-%d %H:%M:%S') if times else '',
        'last_timestamp': times[-1].strftime('%Y-%m-%d %H:%M:%S') if times else '',
        'interval_minutes': interval,
        'continuous': continuous,
        'appliances_total_kwh': sum(appliances) / 1000.0,
        'daily_appliances_kwh': daily_kwh,
        'lights_total_kwh': sum(lights) / 1000.0,
        'units': {'appliances_total_kwh': 'kWh', 'daily_appliances_kwh': 'kWh', 'lights_total_kwh': 'kWh'},
        'sample_sha256': actual_hash,
        'sample_hash_matches_manifest': actual_hash == expected_hash,
        'rows_match_manifest': len(records) == expected_rows,
        'timestamp_timezone': manifest['selection']['timestamp_timezone']
    }
    print(json.dumps(result, allow_nan=False, separators=(',', ':')))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, allow_nan=False, separators=(',', ':')))
