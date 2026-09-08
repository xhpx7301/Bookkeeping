# Bookkeeping

一个用于分期贷款记账的轻量台账服务，支持：

- 自动计算剩余本金、利息和每月还款额
- 按月份、按还款日汇总
- 已结清贷款历史
- 逐期实际还款记录
- 多用户登录
- 管理员用户管理
- Docker 部署
- Nginx Proxy Manager 反代

## 在线运行

默认服务端口：

```bash
37037
```

建议通过 Nginx Proxy Manager 反代到宿主机 `37037`。

## 安装

在 Debian 上执行：

```bash
bash -lc 'if [ -d /opt/bookkeeping/.git ]; then cd /opt/bookkeeping && git fetch origin main && git reset --hard origin/main; else git clone https://github.com/xhpx7301/Bookkeeping.git /opt/bookkeeping; fi && cd /opt/bookkeeping && bash install.sh'
```

如果你已经把代码放到本地目录，也可以直接执行：

```bash
bash install.sh
```

安装脚本会：

1. 检测 `python3`、`git`、`curl`、`rsync`、`docker`、`docker compose`
2. 缺少时询问是否安装，回车默认 `y`
3. 同步项目到 `/opt/bookkeeping`
4. 首次设置管理员账号
5. 构建并启动服务

## 管理命令

```bash
bk
bk status
bk start
bk stop
bk restart
bk upgrade
bk logs
bk backup
bk settings
bk users
bk user-add
bk register
bk user-password
bk user-toggle
bk user-delete
```

## 用户管理

- `bk settings`：设置或重置初始管理员账号
- `bk register`：新建普通用户
- `bk user-add`：新建普通用户或管理员
- `bk users`：查看用户列表
- `bk user-password`：重置密码
- `bk user-toggle`：停用或启用用户
- `bk user-delete`：删除用户

管理员登录后，也可以在网页里的“用户管理”面板完成这些操作。

## 数据

SQLite 数据默认保存在：

```bash
/opt/bookkeeping/data/bookkeeping.db
```

升级不会清空 `data/`。

## 相关文件

- [部署说明](DEPLOY.md)
- [安装脚本](install.sh)
- [服务端](server.py)
- [前端页面](loan-ledger.html)
