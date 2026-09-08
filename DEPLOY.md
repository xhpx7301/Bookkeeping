# Bookkeeping 部署说明

## 1. 放置位置

建议把项目固定安装到：

```bash
/opt/bookkeeping
```

仓库地址：

```bash
https://github.com/xhpx7301/Bookkeeping
```

## 2. 一键安装

在 Debian 上运行：

```bash
bash install.sh
```

脚本会：

1. 检测 `python3`、`git`、`curl`、`rsync`、`docker`、`docker compose`
2. 缺少时询问是否安装，回车默认 `y`
3. 同步项目到 `/opt/bookkeeping`
4. 首次写入管理员账号
5. 构建并启动服务

## 3. 反向代理

Nginx Proxy Manager 新建 Proxy Host：

- Scheme: `http`
- Forward Hostname/IP: 宿主机内网 IP
- Forward Port: `37037`
- Websockets Support: 可选
- SSL: 建议开启并强制 HTTPS

如果 NPM 和服务在同一个 Docker 网络，也可以直接转发到容器名 `bookkeeping`，端口 `8080`。

## 4. 管理命令

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

其中：

- `bk settings`：设置或重置管理员登录
- `bk users`：查看用户
- `bk register`：创建普通用户
- `bk user-add`：创建管理员或普通用户
- `bk user-toggle`：启用/停用用户
- `bk user-password`：重置密码

## 5. 数据与备份

SQLite 数据默认保存在：

```bash
/opt/bookkeeping/data/bookkeeping.db
```

建议定期备份：

```bash
cp /opt/bookkeeping/data/bookkeeping.db "/opt/bookkeeping/backups/bookkeeping-$(date +%F).db"
```

升级镜像不会删除 `data/`。

## 6. 登录与用户

应用使用多用户登录。管理员可在网页里的“用户管理”面板新建、停用、重置和删除用户，也可以直接用 `bk` 菜单维护用户。

首次安装时需要先生成管理员账号；如果数据库里已经存在管理员，则服务会直接使用现有账号。
