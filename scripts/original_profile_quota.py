"""Original-account quota admission, independent of historical study harnesses.

Unknown is explicit; observed quotas and snapshot timestamps must be <=600s.
This module never polls credentials, selects another account or resets budgets.
"""
import datetime as dt
import time
from specorganon.role_jobs import _read, _json, digest

class CampaignPause(ValueError):
    """No new call admitted; only resume same identity with current observations."""

def utc(text):
    if type(text) is not str: raise ValueError('timestamp must be text')
    try: value=dt.datetime.fromisoformat(text.replace('Z','+00:00'))
    except ValueError as exc: raise ValueError('invalid UTC timestamp') from exc
    if value.utcoffset()!=dt.timedelta(0): raise ValueError('UTC timestamp required')
    return value.timestamp()


def current_quota(path, *, now=None):
    raw=_read(path,128000); value=_json(path); now=time.time() if now is None else now
    if (type(value) is not dict or value.get('schema')!=1
            or value.get('accounts')!= {'codex':'original_lab_profile','gemini':'original_primary_profile'}):
        raise CampaignPause('current original-account quota snapshot required')
    age=now-utc(value.get('captured_at'))
    if not 0<=age<=600: raise CampaignPause('quota snapshot older than600s or future-dated')
    providers=value.get('providers')
    if type(providers) is not dict or set(providers)!={'codex','gemini'}:
        raise CampaignPause('both original provider observations required')
    for provider,row in providers.items():
        if (type(row) is not dict or row.get('status') not in {'observed','unknown'}
                or type(row.get('remaining_percent')) is not list):
            raise CampaignPause('invalid quota observation')
        numbers=row['remaining_percent']
        if row['status']=='unknown':
            if set(row)!={'status','remaining_percent','reason'} or numbers or not row.get('reason'):
                raise CampaignPause('unknown quota must remain explicit')
        else:
            if (set(row)!={'status','remaining_percent','source','observed_at'}
                    or not numbers or any(type(n) not in {int,float} or not 0<=n<=100 for n in numbers)
                    or not row.get('source') or not 0<=now-utc(row.get('observed_at'))<=600):
                raise CampaignPause('stale/malformed provider observation')
            if min(numbers)==0: raise CampaignPause(provider+' quota depleted; no native submission')
    return {'quota_snapshot_sha256':digest(raw),'captured_at':value['captured_at'],
            'capacity_guaranteed':False,'observations':providers}


