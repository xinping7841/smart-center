# Smart Center 协作流程

中心仓库：`node-120:/srv/git/smart-center.git`

推荐流程：

1. 每次修改前先同步：`git fetch origin`。
2. 从 `main` 拉功能分支：`git switch -c codex/功能名 origin/main`。
3. 本地修改、测试后提交：`git add ... && git commit -m "说明"`。
4. 推送分支：`git push -u origin codex/功能名`。
5. 合并前先在测试/本机预览，确认后再合并到 `main` 并部署到 `/srv/smart-center/current`。

约定：

- `main` 保持可部署状态，不直接在 `main` 上边试边改。
- Windows 12700K 本地改动先推到 `codex/12700k-*` 分支。
- 笔记本异地改动先推到 `codex/laptop-*` 分支。
- 数据库、日志、截图、临时 `_*.js/_*.html` 不进入仓库。
- 重要改动部署前先备份 `/srv/smart-center/current`。
