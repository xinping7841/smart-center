# 注释规范 (Comment Style Guide)

Last updated: 2026-06-12

## 文件头：AI_MODULE 标记块（必须）

每个源文件顶部必须有 AI_MODULE 标记块：
# AI_MODULE / AI_PURPOSE / AI_BOUNDARY / AI_DATA_FLOW
# AI_RUNTIME / AI_RISK / AI_COMPAT / AI_SEARCH_KEYWORDS

风险等级：高(物理设备控制) / 中(页面/缓存/兼容) / 低(展示/工具)

禁止：
- 描述代码字面意思的注释
- 大段注释掉的旧代码
- TODO 个人标记（用 .worktasks/ 任务追踪）
- 裸 except:（全部消除，必须加日志）
- CSS !important（提升特异性）
- HTML 裸 style= 属性（提取到 CSS）

## AI Agent 读取策略
1. AGENTS.md → 项目全貌
2. 目标文件 AI_MODULE 头 → 模块职责
3. docs/QUERY_KNOWLEDGE_BASE.md → NL 路由
4. 相关代码文件 → 实现

详见 docs/AI_CODE_MARKERS.md。
