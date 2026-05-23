1. 把 Clash Verge 导出的完整配置保存为 config.yaml
2. 将 config.yaml 放到当前目录
3. 在飞牛 NAS 中以当前目录创建 Docker 项目
4. 使用 docker-compose.yml 启动 mihomo

说明:
- 当前编排使用 host 网络
- 配置文件中的 mixed-port 当前为 7897
- 如需 HTTP 代理给其他容器或系统使用，可指向 NAS_IP:7897
