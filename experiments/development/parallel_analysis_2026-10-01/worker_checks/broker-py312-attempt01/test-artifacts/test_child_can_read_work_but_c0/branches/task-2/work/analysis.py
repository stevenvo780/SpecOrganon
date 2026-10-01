import json
from pathlib import Path
work = Path(__file__).parent
try:
    (work/'metrics.json').write_text('{}')
except PermissionError:
    print(json.dumps({'readonly': True, 'source_visible': (work/'analysis.py').exists()}))
else:
    raise AssertionError('unexpected child write')
