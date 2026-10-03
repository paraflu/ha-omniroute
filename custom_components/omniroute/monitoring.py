"""Parse version and cached upstream windows without guessing missing data."""
import math

def parse_monitoring(version, limits, accounts):
    latest = version.get('latest')
    known = isinstance(latest, str) and latest not in ('', 'unavailable', 'unknown')
    result = {'version':version.get('current'), 'latest_version':latest if known else None,
              'update_available':version.get('updateAvailable') if known and isinstance(version.get('updateAvailable'), bool) else None,
              'codex_5h':{}}
    caches = limits.get('caches', {})
    for key, account in accounts.items():
        if account.get('provider') != 'codex':
            continue
        cache=caches.get(key) or {}
        windows=cache.get('quotas') or {}
        window=next((w for w in windows.values() if isinstance(w,dict) and w.get('windowSeconds')==18000), None)
        if window is None:
            continue
        used, total=window.get('used'), window.get('total')
        value = None
        if isinstance(used,(int,float)) and not isinstance(used,bool) and isinstance(total,(int,float)) and total>0:
            calculated=100*used/total
            if math.isfinite(calculated): value=round(calculated,2)
        result['codex_5h'][key]={'used_percent':value,'reset_at':window.get('resetAt'),
                               'fetched_at':cache.get('fetchedAt'),'window_seconds':18000}
    return result
