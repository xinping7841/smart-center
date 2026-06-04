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
支持中控音乐播放器调用 node-120 本机蓝牙音频链路：NAS 音乐库路径、蓝牙输出诊断、本机 ffplay 播放模式和显式蓝牙音箱连接接口。
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

## 已验证

- 
- `python3 -m unittest tests.test_apple_audio_local_player -v`
- `python3 -m compileall apple_audio_core.py api/apple_audio.py config.py tests/test_apple_audio_local_player.py`
- `node --check static/js/views/apple-audio.js`
- `git diff --check`

## 未验证

- 
- 真实蓝牙音箱配对/连接待用户让音箱进入配对模式或提供 MAC。
- node-120 本机出声待确认 PipeWire 用户会话/蓝牙音频 sink 可用。
- NAS Audio 挂载待确认 SMB 分享名和凭据，或启用 NAS 侧 music-tag 服务。

## 风险点

- 
- 蓝牙连接和播放属于真实音频输出动作，接口必须要求显式调用，不自动连接/播放。
- NAS 音乐目录必须先以 Linux 路径挂载到 node-120 后才能由后端扫描。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 
