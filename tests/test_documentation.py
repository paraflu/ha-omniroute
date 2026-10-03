"""Keep the documented dashboard example valid and anonymous."""
from pathlib import Path
import yaml


def test_dashboard_example():
    path = Path('examples/codex-usage-card.yaml')
    text = path.read_text()
    card = yaml.safe_load(text)
    assert card['type'] == 'vertical-stack'
    gauges = card['cards'][1]['cards']
    assert len(gauges) == 2
    for gauge in gauges:
        assert gauge['type'] == 'gauge'
        assert gauge['max'] == 100
        assert gauge['entity'] in card['cards'][2]['content']
    assert '@' not in text
    assert Path('docs/images/codex-usage-example.png').is_file()
