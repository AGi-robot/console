"""Exercise the actual console encoder and rosbridge message contract."""
import json
from unittest.mock import patch
from fastapi.testclient import TestClient
from cryptic_signal_core.telepathic_encoding import decode_text
from telepathic_management.telepathic_console import server


def test_console_encodes_structured_unicode_before_ros_publish():
    sent = []
    class Bridge:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def send(self, value): sent.append(json.loads(value))
    payload = json.dumps({'text': 'Hello Grace — 你好', 'web_search': True})
    with patch.object(server.websockets, 'connect', return_value=Bridge()):
        response = TestClient(server.app).post('/api/telepathic/send', content=payload)
    assert response.status_code == 200
    assert sent[0]['type'] == 'cryptic_signal_core/msg/TelepathicSignal'
    assert sent[1]['topic'] == '/telepathic/stimulus'
    msg = sent[1]['msg']
    assert msg['scheme'] == 'ternary_utf8_v1'
    assert decode_text(bytes(msg['signal']), msg['pulse']) == payload


def test_console_rejects_empty_input_and_removed_settings_editor():
    client = TestClient(server.app)
    assert client.post('/api/telepathic/send', content='  ').status_code == 400
    assert client.put('/api/settings', json={'settings': {}}).status_code == 409


def test_presence_has_no_entity_import_dependency(monkeypatch):
    monkeypatch.delenv('AGI_WEB_TELEOPS_CONSOLE_AIVA_LOCAL', raising=False)
    monkeypatch.delenv('AGI_WEB_TELEOPS_CONSOLE_AURORA_LOCAL', raising=False)
    monkeypatch.setattr(server, '_aiva_last_seen', None)
    client = TestClient(server.app)
    assert client.get('/api/presence').json()['aiva_online'] is False
    assert client.get('/api/presence').json()['aurora_online'] is False
    monkeypatch.setenv('AGI_WEB_TELEOPS_CONSOLE_AIVA_LOCAL', 'true')
    assert client.get('/api/presence').json()['aiva_online'] is True
    monkeypatch.setenv('AGI_WEB_TELEOPS_CONSOLE_AIVA_LOCAL', 'false')
    assert client.post('/api/presence/aiva').status_code == 204
    assert client.get('/api/presence').json()['aiva_online'] is True


def test_bridge_failure_is_reported_and_bad_scheme_rejected(monkeypatch):
    client = TestClient(server.app)
    monkeypatch.setenv('AGI_TELEPATHIC_SCHEME', 'unknown')
    assert client.post('/api/telepathic/send', content='hello').status_code == 400
    monkeypatch.delenv('AGI_TELEPATHIC_SCHEME')
    with patch.object(server.websockets, 'connect', side_effect=OSError('unavailable')):
        assert client.post('/api/telepathic/send', content='hello').status_code == 502


def test_shared_envelope_uses_configured_channel_and_source(monkeypatch):
    monkeypatch.setenv('AGI_SOURCE_ID', 'console-test')
    monkeypatch.setenv('AGI_TELEPATHIC_CHANNEL', 'aiva')
    msg = server._encode_stimulus('hello', 'request-1')
    assert (msg['source'], msg['channel'], msg['identifier']) == ('console-test', 'aiva', 'request-1')
    assert decode_text(bytes(msg['signal']), msg['pulse']) == 'hello'
