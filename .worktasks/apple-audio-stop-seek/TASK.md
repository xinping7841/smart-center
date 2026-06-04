# 任务记忆

- 任务：apple-audio-stop-seek
- 模块锁：apple_audio
- 分支：codex/mac-apple-audio-stop-seek-20260604
- 目标：音乐播放器增加停止按钮、可拖动进度条，并修正右侧播放列表文字显示不协调。
- 修改范围：apple_audio_core.py、api/apple_audio.py、static/js/views/apple-audio.js、static/css/generated/apple_audio.css、templates/index.html、static/js/app-runtime.js、tests/test_apple_audio_local_player.py
- 验证：只做单元/语法/只读资源检查，不点击真实播放、停止或设备控制按钮。
