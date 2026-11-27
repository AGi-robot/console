"""Console retains only automatic activity lights and yields to capabilities."""
import fcntl
from unittest.mock import Mock

from fastapi.testclient import TestClient
from telepathic_management.telepathic_console import server
from telepathic_management.telepathic_console.openrgb import OpenRgb


def test_console_has_no_agentic_lighting_routes():
    client = TestClient(server.app)
    assert client.get('/api/lighting').status_code == 404
    assert client.put('/api/lighting', json={'preset': 'disco'}).status_code == 404
    assert client.get('/api/lighting/catalog').status_code == 404


def test_activity_yields_and_restores_unchanged_colour(tmp_path, monkeypatch):
    path = tmp_path / 'device.lock'
    monkeypatch.setenv('AGI_OPENRGB_LOCK_PATH', str(path))
    rgb = OpenRgb()
    rgb.client = Mock()
    rgb.device = Mock()
    rgb._color_class = lambda *c: c
    rgb.state = 'resting'
    color = rgb.color_for_state('resting')
    rgb._apply_color(color)
    rgb.device.set_color.reset_mock()
    with path.open('a') as capability:
        fcntl.flock(capability, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rgb._apply_color(color)
        rgb.device.set_color.assert_not_called()
        rgb.set_state('thinking')
        assert rgb.state == 'thinking'
        rgb.device.set_color.assert_not_called()
    rgb._apply_color(rgb.color_for_state('thinking'))
    rgb.device.set_color.assert_called_once()


def test_resting_animation_resumes_after_capability_release(tmp_path, monkeypatch):
    monkeypatch.setenv('AGI_OPENRGB_LOCK_PATH', str(tmp_path / 'device.lock'))
    rgb = OpenRgb()
    rgb.state = 'resting'
    rgb._apply_color = Mock()
    rgb._animation_stop = Mock()
    rgb._animation_stop.wait.side_effect = [False, True]
    rgb._animate()
    rgb._apply_color.assert_called_once_with(rgb.color_for_state('resting'))
