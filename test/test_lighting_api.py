from unittest.mock import patch
from fastapi.testclient import TestClient
from telepathic_management.telepathic_console import server


def test_effect_api_validation_status_and_unavailable(monkeypatch):
    client = TestClient(server.app)
    for payload in ([], {'brightness': 3}, {'unknown': 1}, {'rhythm': 'morse'}):
        assert client.put('/api/lighting', json=payload).status_code == 422
    monkeypatch.setenv('AGI_OPENRGB_ENABLED', 'false')
    assert client.put('/api/lighting', json={}).status_code == 503
    assert client.get('/api/lighting').status_code == 200
    assert client.delete('/api/lighting').json()['active'] is False


def test_api_preserves_selected_effect_fields():
    client = TestClient(server.app)
    with patch.object(server._rgb, 'set_effect', return_value={'active': True}) as apply:
        response = client.put('/api/lighting', json={
            'start_color': '#ABCDEF', 'transition_colors': ['#123456'],
            'end_color': '#FEDCBA', 'rhythm': 'heartbeat', 'brightness': .3,
        })
        assert response.status_code == 200
        effect = apply.call_args.args[0]
        assert effect.start_color == '#ABCDEF'
        assert effect.transition_colors == ['#123456']
        assert effect.rhythm == 'heartbeat'
        assert effect.brightness == .3
