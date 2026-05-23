# 任务记忆

## 基本信息

- 任务名：current-node-red-push
- 模块锁：current_collector
- 分支：codex/mac-current-node-red-push-20260524
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/current-node-red-push
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-05-24 02:10:19
- 预计结束：

## 目标

```text
切断 node-120 直接读取 16 路电流采集器，改为 node-121 Node-RED 读取 192.168.50.109:502 后主动推送到 node-120。
```

## 当前阶段

```text
进行中
```

## 修改范围

```text
api/current_collector.py
config.py
templates/config.html
auth/__init__.py
deploy/node_red_current_collector/
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 增加 current_collector push 模式和 /api/current-collector/push 接口
- 配置中心增加数据来源、推送超时、允许推送主机、推送 Token
- 增加 node-121 Node-RED 电流采集部署包
- 补回 clean baseline 漏掉的 auth/__init__.py，避免新 release 启动失败

## 已验证

- python3 -m compileall auth/__init__.py api/current_collector.py config.py current_collector.py deploy/node_red_current_collector/deploy_current_collector_flow.py

## 未验证

- node-120 Python 3.12 临时目录接口测试
- 生产 release 切换
- node-121 Node-RED flow 实机部署和推送验证

## 风险点

- 需要先让 120 部署支持 push 接口，再把生产配置切为 source_mode=push，最后启动 121 Node-RED flow
- Node-RED flow 会每 2 秒连接 192.168.50.109:502，确认 120 已停止直接读取后再验证真实数据

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交推送分支，120 临时测试，通过后部署生产并配置 node-121 flow
