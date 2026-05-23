# Smart Center Git Workflow

- `main` is the production baseline used for node-120 deployment.
- Development machines should create their own branches, for example `codex/mac-*` and `codex/12700k-*`.
- Pull before editing: `git fetch origin && git pull --rebase origin main`.
- Commit small changes frequently.
- Do not copy whole folders over `/srv/smart-center/current`; merge through Git, then deploy.
- Runtime data, backups, caches, logs, and databases are backed up outside Git.
