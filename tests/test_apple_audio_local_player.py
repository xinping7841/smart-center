# AI_MODULE: apple_audio_local_player_tests
# AI_PURPOSE: 验证音乐播放器本机播放模式、首页轻量状态、全量刮削、文件夹播放列表、停止和进度跳转，不触发真实音频输出。
# AI_BOUNDARY: 只 mock 播放进程；不访问 NAS、不连接蓝牙音箱、不播放真实音乐。
# AI_SEARCH_KEYWORDS: apple audio, local player, dashboard status, full scrape, folder playlist, playlist scope, stop, seek, node120 analog, ffplay, ffmpeg, aplay.

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
                "category": "Folder A" if index < count else "Folder B",
                "relative_path": f"Folder {'A' if index < count else 'B'}/track-{index}.mp3",
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
                "duration": 120,
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
                "duration": 120,
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
        self.assertIn('volume="$5"', cmd[2])
        self.assertIn("-f wav -", cmd[2])
        self.assertIn('"$aplay_bin" -D "$device"', cmd[2])
        self.assertIn(str(audio_path), cmd)
        self.assertIn("/usr/bin/ffmpeg", cmd)
        self.assertIn("/usr/bin/aplay", cmd)
        self.assertIn("plughw:CARD=PCH,DEV=0", cmd)
        self.assertIn("0.650", cmd)
        self.assertNotIn("", cmd)

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

    def test_transport_stop_pauses_and_resets_elapsed(self):
        service = self._service_with_tracks(1)
        service.state["current_track_id"] = "track-1"
        service.state["is_playing"] = True
        service.state["elapsed_sec"] = 42

        state = service.transport("stop")

        self.assertFalse(state["is_playing"])
        self.assertEqual(state["elapsed_sec"], 0)
        self.assertEqual(state["last_action"], "Stopped")

    def test_transport_seek_clamps_to_current_duration(self):
        service = self._service_with_tracks(1)
        service.library[0]["duration"] = 120
        service.library_by_id = {item["id"]: item for item in service.library}
        service.state["current_track_id"] = "track-1"
        service.state["is_playing"] = False

        state = service.transport("seek", mode=999)

        self.assertEqual(state["elapsed_sec"], 120)
        self.assertEqual(state["last_action"], "Seek: 120s")

    def test_local_ffplay_seek_restarts_with_start_offset_without_real_audio(self):
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
                "duration": 120,
            }]
            service.library_by_id = {"track-1": service.library[0]}
            service.state["current_track_id"] = "track-1"
            service.state["is_playing"] = True

            with patch("apple_audio_core.shutil.which", return_value="/usr/bin/ffplay"), \
                    patch("apple_audio_core.subprocess.Popen", return_value=FakeProcess()) as popen:
                state = service.transport("seek", mode=37)

        cmd = popen.call_args.args[0]
        self.assertEqual(state["elapsed_sec"], 37)
        self.assertIn("-ss", cmd)
        self.assertIn("37", cmd)

    def test_local_ffmpeg_aplay_seek_uses_split_seek_args(self):
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
                "duration": 120,
            }]
            service.library_by_id = {"track-1": service.library[0]}
            service.state["current_track_id"] = "track-1"
            service.state["is_playing"] = True

            with patch("apple_audio_core.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
                    patch("apple_audio_core.subprocess.Popen", return_value=FakeProcess()) as popen:
                state = service.transport("seek", mode=37)

        cmd = popen.call_args.args[0]
        self.assertEqual(state["elapsed_sec"], 37)
        self.assertIn("-ss", cmd)
        self.assertIn("37", cmd)
        self.assertNotIn("-ss 37", cmd)
        self.assertNotIn("", cmd)

    def test_local_player_exit_reports_stderr_tail(self):
        service = self._service_with_tracks(1)
        log_path = Path(_TEST_DATA_DIR) / "runtime" / "apple-audio-test.stderr.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("ALSA lib pcm.c: device busy\naplay: main: audio open error\n", encoding="utf-8")
        service.local_player_stderr_path = log_path
        service.local_player_proc = ExitedProcess(1)
        service.state["current_track_id"] = "track-1"
        service.state["is_playing"] = True

        state = service.snapshot()

        self.assertFalse(state["is_playing"])
        self.assertIn("Local player exited: 1", state["local_player"]["message"])
        self.assertIn("audio open error", state["local_player"]["message"])

    def test_folder_and_custom_playlists_queue_tracks(self):
        service = self._service_with_tracks(3)

        playlists = service.playlists_snapshot()["playlists"]
        folder = next(item for item in playlists if item["kind"] == "folder" and item["name"] == "Folder A")
        self.assertEqual(folder["count"], 2)

        payload = service.create_custom_playlist("晚间列表")
        custom = next(item for item in payload["playlists"] if item["kind"] == "custom")
        service.add_track_to_custom_playlist(custom["id"], "track-1")
        service.add_track_to_custom_playlist(custom["id"], "track-2")

        state = service.queue_playlist(custom["id"], play_now=True)

        self.assertEqual(state["current_track"]["id"], "track-1")
        self.assertEqual([item["id"] for item in state["queue"]], ["track-2"])
        self.assertTrue(state["is_playing"])

    def test_full_scrape_force_clears_lyrics_cache_and_updates_status(self):
        service = self._service_with_tracks(2)
        service.lyrics_cache = {"track-1": {"payload": {"lyrics_type": "plain"}, "mtime": 1}}

        with patch.object(service, "_config", return_value={
            "nas_music_roots": ["/tmp/music"],
            "nas_music_exclude_dirs": [],
        }), patch.object(service, "_scan_root", return_value=(service.library, [], len(service.library))), \
                patch.object(service, "_scrape_track_lyrics_payload") as scrape:
            state = service.scan_library(full_scrape=True, force=True)

        self.assertEqual(service.lyrics_cache, {})
        self.assertEqual(scrape.call_count, 2)
        self.assertFalse(state["scan"]["running"])
        self.assertEqual(state["scan"]["stage"], "done")
        self.assertEqual(state["scan"]["progress"], 100)
        self.assertEqual(state["last_action"], "Library fully scraped")

    def test_scan_without_full_scrape_skips_eager_lyrics_scrape(self):
        service = self._service_with_tracks(2)

        with patch.object(service, "_config", return_value={
            "nas_music_roots": ["/tmp/music"],
            "nas_music_exclude_dirs": [],
        }), patch.object(service, "_scan_root", return_value=(service.library, [], len(service.library))), \
                patch.object(service, "_scrape_track_lyrics_payload") as scrape:
            state = service.scan_library(full_scrape=False, force=False)

        scrape.assert_not_called()
        self.assertFalse(state["scan"]["running"])
        self.assertEqual(state["scan"]["stage"], "done")
        self.assertEqual(state["scan"]["progress"], 100)

    def test_dashboard_snapshot_is_compact_without_library_payload(self):
        service = self._service_with_tracks(3)
        service.state["current_track_id"] = "track-2"
        service.state["is_playing"] = True
        service.state["playback_mode"] = "shuffle"
        service.state["volume_percent"] = 80

        payload = service.dashboard_snapshot()

        self.assertTrue(payload["is_playing"])
        self.assertEqual(payload["current_track"]["id"], "track-2")
        self.assertEqual(payload["playback_mode"], "shuffle")
        self.assertEqual(payload["volume_percent"], 80)
        self.assertEqual(payload["library_size"], 3)
        self.assertNotIn("library", payload)

    def test_folder_playlist_uses_directory_order(self):
        service = self._service_with_tracks(1)
        service.library = [
            {
                "id": "track-b",
                "title": "B",
                "path": "/tmp/Folder A/02-b.mp3",
                "playable": True,
                "category": "Old Category",
                "relative_path": "Folder A/02-b.mp3",
            },
            {
                "id": "track-a",
                "title": "A",
                "path": "/tmp/Folder A/01-a.mp3",
                "playable": True,
                "category": "Old Category",
                "relative_path": "Folder A/01-a.mp3",
            },
        ]
        service.library_by_id = {item["id"]: item for item in service.library}

        folder = next(item for item in service.playlists_snapshot()["playlists"] if item["kind"] == "folder")
        state = service.queue_playlist(folder["id"], play_now=True, mode="normal")

        self.assertEqual(folder["name"], "Folder A")
        self.assertEqual(folder["track_ids"], ["track-a", "track-b"])
        self.assertEqual(state["current_track"]["id"], "track-a")
        self.assertEqual([item["id"] for item in state["queue"]], ["track-b"])

    def test_playlist_repeat_all_wraps_inside_playlist_scope(self):
        service = self._service_with_tracks(3)
        folder = next(item for item in service.playlists_snapshot()["playlists"] if item["kind"] == "folder" and item["name"] == "Folder A")

        state = service.queue_playlist(folder["id"], play_now=True, mode="repeat_all")
        self.assertEqual(state["playlist_scope"]["id"], folder["id"])
        self.assertEqual(state["current_track"]["id"], "track-1")

        state = service.transport("next")
        self.assertEqual(state["current_track"]["id"], "track-2")

        state = service.transport("next")
        self.assertEqual(state["current_track"]["id"], "track-1")

    def test_playlist_shuffle_stays_inside_playlist_scope(self):
        service = self._service_with_tracks(3)
        folder = next(item for item in service.playlists_snapshot()["playlists"] if item["kind"] == "folder" and item["name"] == "Folder A")

        with patch("apple_audio_core.random.shuffle", side_effect=lambda ids: ids.reverse()):
            state = service.queue_playlist(folder["id"], play_now=True, mode="shuffle")

        self.assertEqual(state["playback_mode"], "shuffle")
        self.assertEqual(state["playlist_scope"]["track_ids"], ["track-1", "track-2"])
        self.assertEqual(state["current_track"]["id"], "track-2")
        self.assertEqual([item["id"] for item in state["queue"]], ["track-1"])

        with patch("apple_audio_core.random.choice", return_value="track-1") as choice:
            state = service.transport("next")

        self.assertEqual(state["current_track"]["id"], "track-1")
        choice.assert_not_called()

    def test_configure_keeps_runtime_shuffle_while_playing(self):
        service = self._service_with_tracks(3)
        folder = next(item for item in service.playlists_snapshot()["playlists"] if item["kind"] == "folder" and item["name"] == "Folder A")

        state = service.queue_playlist(folder["id"], play_now=True, mode="shuffle")
        self.assertEqual(state["playback_mode"], "shuffle")

        CONFIG["apple_audio"]["playback_mode"] = "normal"
        service.configure()

        self.assertTrue(service.state["is_playing"])
        self.assertEqual(service.state["playback_mode"], "shuffle")

    def test_configure_keeps_playlist_runtime_mode_after_track_exit(self):
        service = self._service_with_tracks(3)
        service.state["is_playing"] = False
        service.state["playback_mode"] = "shuffle"
        service.state["queue_ids"] = ["track-2"]
        service.state["playlist_scope_ids"] = ["track-1", "track-2"]

        CONFIG["apple_audio"]["playback_mode"] = "normal"
        service.configure()

        self.assertEqual(service.state["playback_mode"], "shuffle")

    def test_local_player_retries_when_alsa_device_is_busy(self):
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
                "duration": 120,
            }]
            service.library_by_id = {"track-1": service.library[0]}
            attempts = [ExitedProcess(1), FakeProcess()]

            with patch("apple_audio_core.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
                    patch.object(service, "_local_player_device_busy", return_value=True), \
                    patch.object(service, "_spawn_local_player_process", side_effect=lambda *args, **kwargs: attempts.pop(0)) as spawn, \
                    patch("apple_audio_core.time.sleep", return_value=None):
                service._start_local_player_for_track("track-1")

        self.assertEqual(spawn.call_count, 2)
        self.assertEqual(service.state["local_player"]["state"], "playing")
        self.assertEqual(service.state["local_player"]["pid"], 4242)

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

    def test_dashboard_snapshot_auto_advances_local_player_exit(self):
        service = self._service_with_tracks(2)
        service.state["current_track_id"] = "track-1"
        service.state["is_playing"] = True
        service.state["playback_mode"] = "repeat_all"
        service.local_player_proc = ExitedProcess(0)

        with patch.object(service, "_local_player_enabled", return_value=True), \
                patch.object(service, "_start_local_player_for_track") as start_track:
            state = service.dashboard_snapshot()

        self.assertEqual(state["current_track"]["id"], "track-2")
        self.assertTrue(state["is_playing"])
        self.assertEqual(state["last_action"], "Auto next: Track 2")
        self.assertNotIn("library", state)
        start_track.assert_called_once_with("track-2")

    def test_local_player_auto_advance_does_not_stop_after_restart_probe(self):
        service = self._service_with_tracks(2)
        service.state["current_track_id"] = "track-1"
        service.state["is_playing"] = True
        service.state["playback_mode"] = "repeat_all"
        service.local_player_proc = ExitedProcess(0)

        def mark_restarted(track_id):
            service.local_player_proc = ExitedProcess(0)

        with patch.object(service, "_local_player_enabled", return_value=True), \
                patch.object(service, "_start_local_player_for_track", side_effect=mark_restarted):
            state = service.snapshot()
            self.assertEqual(state["current_track"]["id"], "track-2")
            self.assertTrue(state["is_playing"])

            state = service.snapshot()

        self.assertEqual(state["current_track"]["id"], "track-1")
        self.assertTrue(state["is_playing"])


if __name__ == "__main__":
    unittest.main()
