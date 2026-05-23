# music_tag_web (飞牛NAS)

独立音乐标签 Web 服务，适合在飞牛NAS Docker中运行。

## 功能
- 扫描音乐目录并建立索引
- 关键词检索
- 音频流直链（支持 `Range`）
- 简单 Web 状态页

## 默认端口
- `6902`

## 目录映射
`docker-compose.yml` 默认读取：
- 容器内音乐目录：`/music`
- NAS 路径变量：`MUSIC_TAG_NAS_AUDIO_PATH`

你的截图中音频目录名是 `Audio`，一般可映射为：
- `/vol1/Audio` 或你NAS实际路径

## 启动
在 `music_tag_web` 目录执行：

```bash
docker compose up -d --build
```

如果 NAS 音频路径不是 `/vol1/Audio`，先设置变量再启动：

```bash
MUSIC_TAG_NAS_AUDIO_PATH=/你的实际Audio路径 docker compose up -d --build
```

## 访问
- Web 页面：`http://NAS_IP:6902/`
- 健康检查：`http://NAS_IP:6902/api/music-tag/health`
- 曲库接口：`http://NAS_IP:6902/api/music-tag/library?limit=100`
- 重扫接口：`POST http://NAS_IP:6902/api/music-tag/rescan`

## 快速验证
1. 打开 `health`，确认 `ok=true`。
2. 若 `tracks=0`，调用一次 `rescan`。
3. 再查 `library`，拿到 `id` 后可访问：
   - `http://NAS_IP:6902/api/music-tag/stream/<track_id>`
