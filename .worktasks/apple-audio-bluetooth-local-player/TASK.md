# 任务记忆

## 基本信息

- 任务名：apple-audio-bluetooth-local-player
- 模块锁：apple_audio
- 分支：codex/mac-apple-audio-bluetooth-local-player-20260604
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/apple-audio-bluetooth-local-player
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-04 12:04:14
- 预计结束：

## 目标

```text
支持中控音乐播放器调用 node-120 本机音频链路：NAS 音乐库路径、本机输出诊断、后置绿色 3.5mm 模拟口播放模式和显式蓝牙音箱连接接口。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
apple_audio_core.py, api/apple_audio.py, static/js/views/apple-audio.js, config.py
scripts/remote/setup_node120_apple_audio_bluetooth_20260604.sh
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 清理旧 worktree 到脚本上限以下，并备份两个带未跟踪内容的旧目录。
- 确认 node-120 有 BARROT USB Bluetooth 6.0 Adapter，BlueZ 正常。
- 确认 /vol2/1000/Audio 当前未挂载到 node-120，NAS 6902 music-tag 服务未开放。
- 确认 node-120 到 NAS 网络通，SMB/NFS 端口开放；node-120 已有 cifs-utils、PipeWire、libspa bluetooth、ffplay。
- 增加本机播放器状态、蓝牙连接接口、ffplay 播放层和前端本机模式保护。
- 确认 node-120 后置绿色口识别为 `Line Out Front Jack=on`，ALSA 设备为 `plughw:CARD=PCH,DEV=0`，测试音可听。
- 通过 sshfs 只读挂载 NAS `/vol2/1000/Audio` 到 node-120 `/mnt/fnnas-audio`。
- 导入播放器素材库，扫描到 3413 首，搜索和 stream 接口验证通过。
- 增加 `node120_analog`/`ffmpeg_aplay` 本机播放路径，用 `ffmpeg | aplay -D plughw:CARD=PCH,DEV=0` 输出到 120 后置绿色口。
- 增加音乐播放器播放模式：顺序播放、随机播放、循环播放、单曲循环。
- 播放模式写入 `apple_audio.playback_mode` 配置并从 `/api/apple-audio/status` 返回；前端播放结束和 120 本机播放进程退出都会按模式续播或停止。
- 更新查询知识库，标注音乐播放器状态查询走 `/api/apple-audio/status`，播放/模式变更属于 `/api/apple-audio/transport` 控制边界。

## 已验证

- 
- `python3 -m unittest tests.test_apple_audio_local_player -v`
- `python3 -m compileall apple_audio_core.py api/apple_audio.py config.py tests/test_apple_audio_local_player.py`
- `node --check static/js/views/apple-audio.js`
- `git diff --check`
- 本轮播放模式验证只使用 mock 本机播放器进程，不触发真实音频输出。
- 120 生产音频口测试：`Line Out Front Jack=on`，`plughw:CARD=PCH,DEV=0` 播放可听。
- 120 素材库：`library_size=3413`，`/api/apple-audio/search?q=舒伯特` 正常，stream 返回 `206 audio/mpeg`。

## 未验证

- 
- `sshfs` NAS 音频挂载当前为运行时挂载，发布后应固化为 systemd mount，避免 node-120 重启后丢失。
- 生产切到 `node120_analog` 后需用真实音乐短播验证后置绿色口。
- 播放模式尚未发布生产；发布后需验证 `/api/apple-audio/status` 返回 `playback_mode`，并在用户明确允许时再做真实续播听音测试。

## 风险点

- 
- 蓝牙连接和播放属于真实音频输出动作，接口必须要求显式调用，不自动连接/播放。
- node-120 后置绿色口播放会真实出声，验证时只播放用户明确要求的音乐/测试音。
- NAS 音乐目录必须先以 Linux 路径挂载到 node-120 后才能由后端扫描和播放。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 
