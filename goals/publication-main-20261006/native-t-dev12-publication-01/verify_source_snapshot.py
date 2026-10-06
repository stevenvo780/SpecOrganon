"""Read-only local byte verification for the dev12 published source cut. No imports of runtime, model calls or tests."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[3]
E=ROOT/'goals/method-superiority-v1/evidence/native-t-closure-dev12-01'
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert h(E/'engineering-receipt.json')=='41415fb9a014ff65d3c24a0f956c113ffa366df3be2534ab8b6ffc77c5a7aad7'
assert h(E/'SHA256SUMS')=='29676036152919247189c0585df091d434b9cf67685302dc957fffdd1c0591fe'
lines=(E/'SHA256SUMS').read_text().splitlines();assert len(lines)==211
for line in lines:
 s,f=line.split('  ',1);assert h(E/f)==s,f
pins=json.loads((E/'final-2-installed-source-pins.json').read_text());assert len(pins)==48
for f,s in pins.items():assert h(ROOT/f)==s,f
r=json.loads((E/'engineering-receipt.json').read_text())
for f,s in r['preservation']['GOAL_sha256'].items():assert h(ROOT/f)==s,f
print(json.dumps({'source_artifacts_exact':211,'installed_modules_exact':48,'GOALs_exact':True,'runtime_executions':0}))
