# 飞牛NAS Music Tag Web服务说明

## 目标
在现有中控系统中启用 `NAS 音源`，通过 `apple_audio` 接口提供：
- 音乐目录扫描与索引
- 曲目检索
- 播放队列与播放状态
- 音频文件 HTTP 流（支持 `Range`）

## 已提供的接口
服务路径都挂在当前 Flask：

- `GET /api/apple-audio/status`
- `POST /api/apple-audio/config`
- `GET /api/apple-audio/library?q=&limit=300`
- `POST /api/apple-audio/rescan`
- `GET /api/apple-audio/stream/<track_id>`
- `POST /api/apple-audio/queue`
- `POST /api/apple-audio/queue/promote`
- `POST /api/apple-audio/queue/clear`
- `POST /api/apple-audio/transport`

## 配置方式（关键）
通过 `POST /api/apple-audio/config` 设置 NAS 音乐目录：

```json
{
  "provider": "nas_music_tag",
  "player_mode": "nas_http",
  "auth_state": "NAS music tag ready",
  "nas_music_roots": [
    "/volume1/music",
    "/volume2/public/music"
  ],
  "nas_music_exclude_dirs": [
    "@eaDir",
    "tmp",
    "cache"
  ],
  "nas_auto_scan_on_start": true
}
```

说明：
- `nas_music_roots` 必须是 NAS 上可读目录。
- 支持扩展名：`mp3/flac/m4a/aac/wav/ogg/wma/aiff/ape`。
- 标签目前读取 `ID3v1`，其余格式先用文件名回退。

## 首次上线流程
1. 配置 `nas_music_roots`。
2. 调用 `POST /api/apple-audio/rescan` 扫描媒体库。
3. 打开 `GET /api/apple-audio/status` 确认：
   - `state.scan.count > 0`
   - `state.library_size > 0`
4. 用任意曲目 `id` 访问：
   - `GET /api/apple-audio/stream/<track_id>`
5. 前端“苹果音源”页会自动读取状态与队列。

## 缓存文件
扫描结果会写入：

- `DATA_DIR/music_tag_library.json`

`DATA_DIR` 由 `paths.py` 决定，默认是项目数据目录。

## 权限要求
接口沿用现有鉴权：

- 查看类：`meter.view`
- 配置与重扫：`meter.config`

## 注意事项
- `stream` 接口目前统一返回 `audio/mpeg`，若需严格按扩展名返回，可后续加 `mimetype` 映射。
- 大规模音乐库首次扫描耗时取决于磁盘性能。
- 扫描结果中的错误项会保留在 `state.scan.errors`（最多 50 条）。
