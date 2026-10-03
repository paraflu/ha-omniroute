from custom_components.omniroute.monitoring import parse_monitoring


def test_version_unavailable_is_not_no_update():
    result=parse_monitoring({'current':'3.8.51','latest':'unavailable','updateAvailable':False},{}, {})
    assert result['version']=='3.8.51'
    assert result['update_available'] is None


def test_codex_five_hour_usage_is_account_specific():
    accounts={'a':{'provider':'codex'},'b':{'provider':'gemini'}}
    caches={'caches':{'a':{'quotas':{'session':{'used':3,'total':100,'windowSeconds':18000,'resetAt':'2026-10-03T12:00:00Z'}},'fetchedAt':'2026-10-03T09:00:00Z'}}}
    result=parse_monitoring({},caches,accounts)
    assert result['codex_5h']['a']['used_percent']==3
    assert result['codex_5h']['a']['fetched_at']=='2026-10-03T09:00:00Z'
    assert 'b' not in result['codex_5h']
