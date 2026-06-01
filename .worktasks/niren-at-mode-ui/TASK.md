# 任务记忆

## 基本信息

- 任务名：niren-at-mode-ui
- 模块锁：frontend_assets
- 分支：codex/mac-niren-at-mode-ui-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/niren-at-mode-ui
- 执行机器：mac
- 任务类型：light
- 开始时间：2026-06-01 15:12:41
- 预计结束：

## 目标

```text
解决泥人 50.35 AT 模式后协议控制页名称显示、模式切换和控件指令同步问题；保持端口 502 不变。
```

## 当前阶段

```text
验证完成，待提交合并部署
```

## 修改范围

```text
control_center_core.py
api/control_center.py
api/light.py
static/js/views/universal.js
static/js/views/light-runtime.js
static/js/views/light-scene-view.js
templates/config.html
tests/test_niren_protocol_mode.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 协议设备卡片优先显示目标组名称，修复 50.35 用户备注/名称被设备配置名覆盖的问题
- 增加泥人 POE-KP-I101 模式切换后端接口
- 增加配置页泥人模式切换入口，支持 AT / RTU 透传 / Modbus TCP
- 切换模式时同步 DO/DI 读取和 DO 开/关控件指令
- AT 模式保留现有端口 502，不自动改为 44489

## 已验证

- node --check static/js/views/universal.js static/js/views/light-scene-view.js static/js/views/light-runtime.js
- python3 -m py_compile control_center_core.py api/control_center.py api/light.py drivers/light_niren_poe_kp.py tests/test_niren_protocol_mode.py
- git diff --check
- 直接执行 tests/test_niren_protocol_mode.py 中两个测试函数，验证 AT 切换保留 192.168.50.35:502 并同步 AT 控件

## 未验证

- 当前本地环境未安装 pytest，无法用 python3 -m pytest 运行

## 风险点

- 生产配置仍需在部署后把 50.35 目标组保存为 at_over_tcp；该操作只写配置，不发送 DO 开/关控制指令。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交分支、合并 main、部署生产并执行只读核对。
