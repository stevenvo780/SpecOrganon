import csv, datetime as dt, hashlib, json, math, pathlib, sys

root = pathlib.Path(sys.argv[1])
manifest_path = root / 'source_manifest.json'
csv_path = root / 'sample_first_complete_week.csv'
manifest_bytes = manifest_path.read_bytes()
manifest = json.loads(manifest_bytes)
csv_bytes = csv_path.read_bytes()
actual_hash = hashlib.sha256(csv_bytes).hexdigest()
expected_hash = manifest['selection']['sample_sha256']
if actual_hash != expected_hash:
    raise ValueError('sample_sha256 mismatch')
interval = int(manifest['selection']['interval_minutes'])
rows = []
with csv_path.open('r', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    if not reader.fieldnames or not {'date', 'Appliances', 'lights'}.issubset(reader.fieldnames):
        raise ValueError('required columns absent')
    for row in reader:
        timestamp = dt.datetime.strptime(row['date'], '%Y-%m-%d %H:%M:%S')
        appliances = float(row['Appliances'])
        lights = float(row['lights'])
        if not math.isfinite(appliances) or not math.isfinite(lights):
            raise ValueError('non-finite energy')
        rows.append((timestamp, appliances, lights))
if len(rows) != int(manifest['selection']['rows']):
    raise ValueError('row count mismatch')
continuous = all((b[0] - a[0]).total_seconds() == interval * 60 for a, b in zip(rows, rows[1:]))
if not continuous:
    raise ValueError('timestamp interval discontinuity')
if rows[0][0].strftime('%Y-%m-%d %H:%M:%S') != manifest['selection']['start_inclusive']:
    raise ValueError('unexpected first timestamp')
if (rows[-1][0] + dt.timedelta(minutes=interval)).strftime('%Y-%m-%d %H:%M:%S') != manifest['selection']['end_exclusive']:
    raise ValueError('unexpected final timestamp')
daily = {}
for timestamp, appliances, lights in rows:
    day = timestamp.strftime('%Y-%m-%d')
    daily[day] = daily.get(day, 0.0) + appliances
appliances_kwh = sum(x[1] for x in rows) / 1000.0
lights_kwh = sum(x[2] for x in rows) / 1000.0
result = {
    'rows': len(rows),
    'first_timestamp': rows[0][0].strftime('%Y-%m-%d %H:%M:%S'),
    'last_timestamp': rows[-1][0].strftime('%Y-%m-%d %H:%M:%S'),
    'interval_minutes': interval,
    'continuous': continuous,
    'appliances_total_kwh': appliances_kwh,
    'daily_appliances_kwh': {k: v / 1000.0 for k, v in daily.items()},
    'lights_total_kwh': lights_kwh,
    'units': {'appliances_total_kwh': 'kWh', 'daily_appliances_kwh': 'kWh', 'lights_total_kwh': 'kWh'},
    'sample_sha256': actual_hash,
    'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest()
}
print(json.dumps(result, allow_nan=False, separators=(',', ':')))
