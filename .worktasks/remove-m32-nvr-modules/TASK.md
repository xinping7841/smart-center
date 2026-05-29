# 任务记忆

## 基本信息

- 任务名：remove-m32-nvr-modules
- 模块锁：templates_index
- 分支：codex/mac-remove-m32-nvr-modules-20260527
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/remove-m32-nvr-modules
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-27 17:37:17
- 预计结束：

## 目标

```text
移除主系统中的 M32/M32R 控台模块和海康威视 NVR 厂商接入/预览模块；保留归档备份，避免生产运行继续加载这些模块。
```

## 当前阶段

```text
代码清理完成，等待提交/推送/释放锁。
```

## 修改范围

```text
app.py、background.py、runtime/*、api/*、config.py、config.json、templates/*、static/js/views/*、static/smart-center-time-ntp.css、docs/*。
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 已归档 M32R / Hikvision NVR 模块到 NAS：/mnt/ubuntu01/smart-center-backups/module-archive/20260527_174132
- 移除 api/m32r.py、m32r_core.py、templates/m32r.html、static/js/views/m32r.js
- 移除 api/nvr.py、services/hikvision_nvr.py、static/js/views/nvr-view.js
- 移除 Flask 蓝图注册、后台轮询线程、runtime 状态缓存、driver hub M32R 驱动、dashboard NVR 汇总
- 清理首页/配置页 M32R 与海康 NVR 预览入口
- 清理 config.json 中 m32r、nvr_devices、sidebar 旧入口和 Apple Audio 的 M32 字段
- 删除根目录旧 index.html 副本，避免旧模块代码继续留在仓库主路径

## 已验证

- python3 -m compileall app.py api runtime config.py background.py
- node --check static/js/views/snmp.js
- node --check static/js/views/apple-audio.js
- node --check static/js/views/dashboard-summary.js
- rg 扫描已删除模块入口：无 from api.m32r/from api.nvr/m32r_core/hikvision_nvr//api/m32r//api/nvr 等运行引用

## 未验证

- 未在真实生产服务切换验证；本次仅完成代码分支清理。

## 风险点

- config.py 保留对旧 m32r/nvr_devices/sidebar 项的 pop/filter 迁移逻辑，用来清理旧配置，扫描时会保留这些字符串。
- api/door.py 中 camera_preview_queues 是门禁摄像头预览队列，和已删除的海康 NVR 预览无关。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交并推送分支。
- 如需上线，另行创建生产备份和 release 切换，不直接覆盖生产。
