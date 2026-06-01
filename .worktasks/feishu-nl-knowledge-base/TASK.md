# 任务记忆

## 基本信息

- 任务名：feishu-nl-knowledge-base
- 模块锁：backend_api
- 分支：codex/mac-feishu-nl-knowledge-base-20260601
- Worktree 路径：/Users/wanghongyu/Documents/New project/smart-center-worktrees/feishu-nl-knowledge-base
- 执行机器：mac
- 任务类型：heavy
- 开始时间：2026-06-01 21:36:26
- 预计结束：

## 目标

```text
检查飞书自然语言、本地模型和中控控制链路现状；备份当前生产代码；建立可重复生成的模型学习知识库；记录设计问题和优化方向。
```

## 当前阶段

```text
验证完成，准备提交并释放锁
```

## 修改范围

```text
.gitignore
api/local_model.py
docs/LOCAL_MODEL_LEARNING.md
docs/FEISHU_NATURAL_LANGUAGE_DESIGN_REVIEW.md
scripts/export_code_knowledge.py
scripts/export_local_model_training.py
scripts/remote/backup_current_production_code_20260601.sh
services/control_intent_router.py
```

## 已完成

- 创建任务 worktree
- 获取模块工作锁
- 备份生产 current 代码到 /srv/smart-center/backups/pre-feishu-nl-knowledge-20260601_213944-fbb70b6/current-code.tar.gz
- 梳理飞书自然语言现状和目标架构
- 新增代码知识库导出脚本 scripts/export_code_knowledge.py
- 将命令行和本地模型页面训练导出接入代码知识库
- 生成本地知识库快照到 training/local_model（Git 忽略，不提交）
- 收紧自然语言控制路由：裸回路拒绝猜测；时序电源不被电源词误归强电；服务器语义不被电柜通道别名抢走；空调语义优先 HVAC

## 已验证

- python3 -m py_compile api/local_model.py scripts/export_code_knowledge.py scripts/export_local_model_training.py services/control_intent_router.py
- python3 scripts/export_code_knowledge.py
- /Users/wanghongyu/Documents/New project/smart-center-clean/.venv/bin/python3 scripts/export_local_model_training.py --skip-code-knowledge
- python3 scripts/test_feishu_control_dryrun.py --fail-on-unsafe
- 生产备份脚本返回 service_state=active，sha256=3159d05c954a376766cebf386ea33d909b1cf0418ee183fae0b42e30f2e14233

## 未验证

- 未在生产服务上执行训练导出；本地导出使用 worktree 数据，server_machines/logs 为 0，不代表生产实时知识。
- 未启用/测试真实飞书消息回调；未点击或执行真实设备控制。

## 风险点

- 当前飞书低风险控制仍会直接执行，例如庭院灯/大门；设计文档建议首期全部飞书控制先确认。
- Feishu 与 Smart Center HTTP 权限身份需要后续显式服务身份或内部 token。
- 本地导出会触发 config.py 对 config.json 的归一化写入，本任务已恢复该副作用，后续生产导出应使用运行数据路径并避免提交配置漂移。

## 依赖和冲突

```text
如需修改 templates/index.html、config.py、background.py 等高风险文件，需要额外获取对应锁。
```

## 下一步

- 提交、推送并释放 backend_api worklock。
