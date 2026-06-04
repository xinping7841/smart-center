# AI_MODULE: apple_audio_local_player_tests
# AI_PURPOSE: 验证音乐播放器本机播放模式的命令路由，不触发真实蓝牙连接或真实音频输出。
# AI_BOUNDARY: 只 mock 播放进程；不访问 NAS、不连接蓝牙音箱、不播放真实音乐。
# AI_SEARCH_KEYWORDS: apple audio, local player, node120 bluetooth, node120 analog, ffplay, ffmpeg, aplay.

import os
import pwd
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


_TEST_DATA_DIR = tempfile.mkdtemp(prefix="smart-center-apple-audio-test-")
os.environ.setdefault("SMART_CENTER_DATA_DIR", _TEST_DATA_DIR)
os.environ.setdefault("SMART_CENTER_CONFIG_FILE", str(Path(_TEST_DATA_DIR) / "config.json"))

from apple_audio_core import AppleAudioService  # noqa: E402
from config import CONFIG  # noqa: E402


class FakeProcess:
    pid = 4242

    def poll(self):
        return None

    def terminate(self):
        return None

    def wait(self, timeout=None):
        return 0


class ExitedProcess:
    pid = 4343

    def __init__(self, code=0):
        self.code = code

    def poll(self):
        return self.code

    def terminate(self):
        return None

    def wait(self, timeout=None):
        return self.code


class AppleAudioLocalPlayerTest(unittest.TestCase):
    def setUp(self):
        CONFIG["apple_audio"] = {
            "enabled": True,
            "provider": "nas_music_tag",
            "player_mode": "nas_http",
            "nas_music_roots": [],
            "nas_auto_scan_on_start": False,
        }

    def _service_with_tracks(self, count=3):
        with patch.object(AppleAudioService, "scan_library", return_value={}):
            service = AppleAudioService()
        service.library = [
            {
                "id": f"track-{index}",
                "title": f"Track {index}",
                "path": f"/tmp/track-{index}.mp3",
                "playable": True,
            }
            for index in range(1, count + 1)
        ]
        service.library_by_id = {item["id"]: item for item in service.library}
        return service

    def test_play_now_starts_local_ffplay_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "track.mp3"
            audio_path.write_bytes(b"fake")
            CONFIG["apple_audio"] = {
                "enabled": True,
                "provider": "nas_music_tag",
                "player_mode": "node120_bluetooth",
                "local_player_enabled": True,
                "local_player_command": "ffplay",
                "nas_music_roots": [],
                "nas_auto_scan_on_start": False,
            }
            with patch.object(AppleAudioService, "scan_library", return_value={}):
                service = AppleAudioService()
            service.library = [{
                "id": "track-1",
                "title": "Test Track",
                "path": str(audio_path),
                "playable": True,
            }]
            service.library_by_id = {"track-1": service.library[0]}

            with patch("apple_audio_core.shutil.which", return_value="/usr/bin/ffplay"), \
                    patch("apple_audio_core.subprocess.Popen", return_value=FakeProcess()) as popen:
                state = service.queue_track("track-1", play_now=True)

        self.assertTrue(state["is_playing"])
        self.assertEqual(state["local_player"]["state"], "playing")
        self.assertEqual(state["local_player"]["pid"], 4242)
        self.assertIn(str(audio_path), popen.call_args.args[0])

    def test_node120_analog_uses_ffmpeg_aplay_alsa_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "track.mp3"
            audio_path.write_bytes(b"fake")
            CONFIG["apple_audio"] = {
                "enabled": True,
                "provider": "nas_music_tag",
                "player_mode": "node120_analog",
                "local_player_enabled": True,
                "local_player_command": "ffmpeg_aplay",
                "local_player_alsa_device": "plughw:CARD=PCH,DEV=0",
                "volume_percent": 65,
                "nas_music_roots": [],
                "nas_auto_scan_on_start": False,
            }
            with patch.object(AppleAudioService, "scan_library", return_value={}):
                service = AppleAudioService()
            service.library = [{
                "id": "track-1",
                "title": "Test Track",
                "path": str(audio_path),
                "playable": True,
            }]
            service.library_by_id = {"track-1": service.library[0]}

            with patch("apple_audio_core.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
                    patch("apple_audio_core.subprocess.Popen", return_value=FakeProcess()) as popen:
                state = service.queue_track("track-1", play_now=True)

        cmd = popen.call_args.args[0]
        self.assertTrue(state["is_playing"])
        self.assertEqual(state["local_player"]["command"], "ffmpeg_aplay")
        self.assertEqual(cmd[0:2], ["/bin/bash", "-c"])
        self.assertIn("set -o pipefail", cmd[2])
        self.assertIn('volume=$5', cmd[2])
        self.assertIn("-f wav -", cmd[2])
        self.assertIn('"$3" -D "$4"', cmd[2])
        self.assertIn(str(audio_path), cmd)
        self.assertIn("/usr/bin/ffmpeg", cmd)
        self.assertIn("/usr/bin/aplay", cmd)
        self.assertIn("plughw:CARD=PCH,DEV=0", cmd)
        self.assertIn("0.650", cmd)

    def test_audio_user_wraps_command_with_runtime_dir(self):
        CONFIG["apple_audio"] = {
            "enabled": True,
            "player_mode": "node120_bluetooth",
            "local_player_enabled": True,
            "local_player_audio_user": "audio_user",
            "nas_auto_scan_on_start": False,
        }
        with patch.object(AppleAudioService, "scan_library", return_value={}):
            service = AppleAudioService()
        fake_user = pwd.struct_passwd(("audio_user", "x", 1234, 1234, "", "/home/audio_user", "/bin/bash"))

        with patch("apple_audio_core.pwd.getpwnam", return_value=fake_user):
            cmd, env = service._audio_user_command(["/usr/bin/ffplay", "track.mp3"])

        self.assertEqual(cmd[:6], ["sudo", "-n", "-u", "audio_user", "env", "XDG_RUNTIME_DIR=/run/user/1234"])
        self.assertIn("/usr/bin/ffplay", cmd)
        self.assertEqual(env["XDG_RUNTIME_DIR"], "/run/user/1234")

    def test_playback_mode_repeat_one_restarts_current_track(self):
        service = self._service_with_tracks(2)
        service.state["current_track_id"] = "track-1"
        service.state["playback_mode"] = "repeat_one"

        state = service.transport("next")

        self.assertEqual(state["current_track"]["id"], "track-1")
        self.assertTrue(state["is_playing"])

    def test_playback_mode_repeat_all_wraps_library_when_queue_empty(self):
        service = self._service_with_tracks(2)
        service.state["current_track_id"] = "track-2"
        service.state["playback_mode"] = "repeat_all"

        state = service.transport("next")

        self.assertEqual(state["current_track"]["id"], "track-1")
        self.assertTrue(state["is_playing"])

    def test_playback_mode_shuffle_avoids_current_when_possible(self):
        service = self._service_with_tracks(3)
        service.state["current_track_id"] = "track-1"
        service.state["playback_mode"] = "shuffle"

        with patch("apple_audio_core.random.choice", return_value="track-3"):
            state = service.transport("next")

        self.assertEqual(state["current_track"]["id"], "track-3")
        self.assertTrue(state["is_playing"])

    def test_volume_transport_clamps_and_reports_percent(self):
        service = self._service_with_tracks(1)

        state = service.transport("volume", mode=135)

        self.assertEqual(state["volume_percent"], 100)
        self.assertEqual(service.state["volume_percent"], 100)

    def test_browser_ended_stops_in_normal_mode_when_queue_empty(self):
        service = self._service_with_tracks(1)
        service.state["current_track_id"] = "track-1"
        service.state["is_playing"] = True
        service.state["playback_mode"] = "normal"

        state = service.transport("ended")

        self.assertEqual(state["current_track"]["id"], "track-1")
        self.assertFalse(state["is_playing"])
        self.assertEqual(state["last_action"], "Playback ended")

    def test_local_player_exit_auto_advances_repeat_all_without_real_audio(self):
        service = self._service_with_tracks(2)
        service.state["current_track_id"] = "track-1"
        service.state["is_playing"] = True
        service.state["playback_mode"] = "repeat_all"
        service.local_player_proc = ExitedProcess(0)

        with patch.object(service, "_local_player_enabled", return_value=True), \
                patch.object(service, "_start_local_player_for_track") as start_track:
            state = service.snapshot()

        self.assertEqual(state["current_track"]["id"], "track-2")
        self.assertTrue(state["is_playing"])
        start_track.assert_called_once_with("track-2")


if __name__ == "__main__":
    unittest.main()
