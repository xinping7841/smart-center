# 任务记忆

- 任务：apple-audio-full-scrape
- 模块锁：apple_audio
- 分支：codex/mac-apple-audio-full-scrape-20260604
- 目标：为音乐播放器增加明确的“全部刮削”入口，强制重建本地音乐库元数据、封面和歌词索引，方便后续读取。
- 修改范围：apple_audio_core.py、api/apple_audio.py、static/js/views/apple-audio.js、static/css/generated/apple_audio.css、templates/index.html、static/js/app-runtime.js、tests/test_apple_audio_local_player.py
- 验证：单元/语法/资源只读检查；不自动触发生产全量刮削。
