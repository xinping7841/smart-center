# AI_MODULE: automation_apple_audio_tests
# AI_PURPOSE: 验证自动化场景可以调度音乐播放器播放列表和停止动作。
# AI_BOUNDARY: 只 mock apple_audio_service；不启动本机播放器、不访问 NAS、不触发真实音频输出。
# AI_SEARCH_KEYWORDS: automation, apple audio, music schedule, scene action, workday.

import sys
import types
from unittest.mock import patch
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


_TEST_DATA_DIR = tempfile.mkdtemp(prefix="smart-center-automation-audio-test-")
os.environ.setdefault("SMART_CENTER_DATA_DIR", _TEST_DATA_DIR)
os.environ.setdefault("SMART_CENTER_CONFIG_FILE", str(Path(_TEST_DATA_DIR) / "config.json"))

if "cv2" not in sys.modules:
    cv2_stub = types.SimpleNamespace(
        CAP_FFMPEG=0,
        CAP_PROP_BUFFERSIZE=0,
        CHAIN_APPROX_SIMPLE=0,
        COLOR_BGR2GRAY=0,
        FONT_HERSHEY_SIMPLEX=0,
        IMREAD_GRAYSCALE=0,
        IMWRITE_JPEG_QUALITY=0,
        INTER_AREA=0,
        LINE_AA=0,
        MORPH_OPEN=0,
        RETR_EXTERNAL=0,
        THRESH_BINARY=0,
    )
    sys.modules["cv2"] = cv2_stub

if "numpy" not in sys.modules:
    sys.modules["numpy"] = types.SimpleNamespace(uint8=int)


runtime_pkg = types.ModuleType("runtime")
runtime_pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "runtime")]
sys.modules["runtime"] = runtime_pkg
sys.modules["runtime.env_history"] = types.SimpleNamespace(build_env_lux_trend=lambda *args, **kwargs: {})
sys.modules["runtime.state"] = types.SimpleNamespace(LIGHT_DRIVERS={}, get_state_value=lambda *args, **kwargs: (False, None, None))

loader = importlib.machinery.SourceFileLoader(
    "runtime.automation",
    str(Path(__file__).resolve().parents[1] / "runtime" / "automation.py"),
)
spec = importlib.util.spec_from_loader(loader.name, loader)
automation_module = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = automation_module
loader.exec_module(automation_module)
_execute_scene_action = automation_module._execute_scene_action


class FakeAppleAudioService:
    def __init__(self):
        self.queue_calls = []
        self.transport_calls = []

    def queue_playlist(self, playlist_id, play_now=False, mode=None):
        self.queue_calls.append((playlist_id, play_now, mode))
        return {"playlist_scope": {"id": playlist_id, "name": "器乐+轻音乐"}}

    def transport(self, action):
        self.transport_calls.append(action)
        return {"is_playing": False}


class AutomationAppleAudioTest(unittest.TestCase):
    def test_automation_scene_can_play_apple_audio_playlist(self) -> None:
        service = FakeAppleAudioService()
        with patch("apple_audio_core.apple_audio_service", service):
            ok, message = _execute_scene_action(
                {
                    "sub_system": "apple_audio",
                    "action_type": "play_playlist",
                    "playlist_id": "folder:e38a08cca65f",
                    "playlist_name": "器乐+轻音乐",
                    "mode": "shuffle",
                }
            )

        self.assertTrue(ok)
        self.assertEqual(service.queue_calls, [("folder:e38a08cca65f", True, "shuffle")])
        self.assertIn("器乐+轻音乐", message)

    def test_automation_scene_can_stop_apple_audio(self) -> None:
        service = FakeAppleAudioService()
        with patch("apple_audio_core.apple_audio_service", service):
            ok, message = _execute_scene_action({"sub_system": "apple_audio", "action_type": "stop"})

        self.assertTrue(ok)
        self.assertEqual(service.transport_calls, ["stop"])
        self.assertIn("已停止", message)
