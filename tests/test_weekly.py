from custom_components.omniroute.monitoring import parse_monitoring

def test_weekly_remaining_without_session():
    result=parse_monitoring({}, {'caches':{'a':{'quotas':{'weekly':{'used':7,'remaining':93,'total':100,'windowSeconds':604800,'resetAt':'2026-10-10T07:00:00Z'}},'fetchedAt':'now'}}}, {'a':{'provider':'codex'}})
    assert result['codex_weekly']['a']['remaining_percent']==93
    assert result['codex_weekly']['a']['window_seconds']==604800
    assert not result['codex_5h']

def test_missing_weekly_is_not_full_credit():
    result=parse_monitoring({}, {}, {'a':{'provider':'codex'}})
    assert result['codex_weekly']['a']['remaining_percent'] is None
