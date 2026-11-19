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
