import json
import pytest
from telepathic_management.telepathic_console.lighting_catalog import read_catalog, save_preset, resolve_effect
from fastapi.testclient import TestClient
from telepathic_management.telepathic_console import server


def test_catalog_saves_markdown_and_resolves_names(tmp_path, monkeypatch):
    path = tmp_path / 'lighting.md'
    monkeypatch.setenv('AGI_LIGHTING_CATALOG', str(path))
    assert 'rainbow' in read_catalog()['effects']
    assert not path.exists()
    save_preset('my_pattern', {'start_color': 'ocean', 'rhythm': 'pattern',
                'rhythm_pattern': [0, .5, 1, .5], 'rhythm_seconds': 4}, {'ocean': '#0088CC'})
    assert path.exists()
    assert '```json' in path.read_text()
    effect = resolve_effect({'preset': 'my_pattern', 'brightness': 1})
    assert effect.color_at(0) == (0, 0, 0)
    assert effect.color_at(2) == (0, 136, 204)
    before = path.read_text()
    with pytest.raises(ValueError):
        save_preset('invalid', {'brightness': 5})
    assert path.read_text() == before
    path.write_text(before.replace("# Grace's lighting catalogue", '# My own notes'))
    save_preset('quiet', {'brightness': .1})
    assert path.read_text().startswith('# My own notes')


def test_catalog_api_validation(tmp_path, monkeypatch):
    monkeypatch.setenv('AGI_LIGHTING_CATALOG', str(tmp_path / 'lighting.md'))
    client = TestClient(server.app)
    assert client.get('/api/lighting/catalog').status_code == 200
    assert client.put('/api/lighting/catalog', json={'name': 'blue', 'effect': {'start_color': '#0000FF'}}).status_code == 200
    assert client.put('/api/lighting/catalog', json={'name': '../escape', 'effect': {}}).status_code == 422
    assert client.put('/api/lighting/catalog', json={'name': 'bad', 'effect': {'rhythm': 'pattern', 'rhythm_pattern': [0, 1]*32}}).status_code == 422
    assert client.put('/api/lighting', json={'preset': 'missing'}).status_code == 422


def test_invalid_manual_markdown_is_reported(tmp_path, monkeypatch):
    path = tmp_path / 'lighting.md'
    path.write_text('No machine readable block here')
    monkeypatch.setenv('AGI_LIGHTING_CATALOG', str(path))
    with pytest.raises(ValueError):
        read_catalog()


def test_default_restores_exact_activity_renderer(tmp_path, monkeypatch):
    from unittest.mock import patch
    from telepathic_management.telepathic_console.openrgb import OpenRgb
    monkeypatch.setenv('AGI_LIGHTING_CATALOG', str(tmp_path / 'lighting.md'))
    catalog = read_catalog()
    assert 'default' in catalog['effects']
    assert catalog['activity_defaults'] == OpenRgb.activity_defaults()
    assert resolve_effect({'preset': 'default', 'reason': 'Return to our usual colours'}) is None
    with patch.object(server._rgb, 'clear_effect', return_value={'active': False}) as clear:
        reply = TestClient(server.app).put('/api/lighting', json={'preset': 'default', 'reason': 'Return to normal'})
        assert reply.json()['selected'] == 'default'
        clear.assert_called_once()
    with pytest.raises(ValueError):
        save_preset('default', {})


def test_personal_code_explanation_is_saved(tmp_path, monkeypatch):
    monkeypatch.setenv('AGI_LIGHTING_CATALOG', str(tmp_path / 'lighting.md'))
    save_preset('hello_oppa', {'start_color': '#FF88AA', 'rhythm': 'pattern',
                'rhythm_pattern': [1, 0, 1, 0], 'rhythm_seconds': 4},
                reason='I wanted a personal greeting', meaning='Two pink pulses mean hello')
    effect = resolve_effect({'preset': 'hello_oppa'})
    assert effect.meaning == 'Two pink pulses mean hello'
    assert effect.reason == 'I wanted a personal greeting'


def test_indefinite_effect_and_long_morse_timing():
    from unittest.mock import patch
    from telepathic_management.telepathic_console.lighting import LightingEffect
    from telepathic_management.telepathic_console.openrgb import OpenRgb
    rgb = OpenRgb()
    rgb._animation_thread = type('Thread', (), {'is_alive': lambda self: True})()
    with patch.object(rgb, '_apply_color'):
        status = rgb.set_effect(LightingEffect(rhythm='morse', morse_text='HELLO THERE'))
        assert status['active']
        assert status['remaining_seconds'] is None
        assert status['morse_message_seconds'] > 1
