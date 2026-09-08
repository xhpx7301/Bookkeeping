#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="/opt/bookkeeping"
REPO_URL="https://github.com/xhpx7301/Bookkeeping"
MISSING=()
REMOTE_BRANCH="main"
BK_LINK="/usr/local/bin/bk"

SUDO=""
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  command -v sudo >/dev/null 2>&1 || { echo "需要 sudo。请用 root 运行，或先安装 sudo。"; exit 1; }
  SUDO="sudo"
fi

have() { command -v "$1" >/dev/null 2>&1; }

ask_yes() {
  local answer
  read -r -p "$1 [Y/n] " answer
  answer="${answer:-y}"
  [[ "$answer" =~ ^[Yy]$ ]]
}

apt_install() {
  $SUDO apt-get update
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y "$@"
}

ensure_base_tools() {
  local need_base=()
  for pkg in python3 git curl ca-certificates gnupg rsync; do
    have "$pkg" || need_base+=("$pkg")
  done
  if ((${#need_base[@]})); then
    MISSING+=("${need_base[@]}")
  fi
}

install_docker() {
  if have docker && docker compose version >/dev/null 2>&1; then
    return 0
  fi

  local distro codename
  if ! have docker || ! docker compose version >/dev/null 2>&1; then
    distro="$(. /etc/os-release && printf '%s' "${ID:-debian}")"
    codename="$(. /etc/os-release && printf '%s' "${VERSION_CODENAME:-}")"
    [[ "$distro" == "debian" ]] || { echo "当前脚本仅面向 Debian。"; exit 1; }
    [[ -n "$codename" ]] || { echo "无法识别 Debian 代号。"; exit 1; }

    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $codename stable" | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
    apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    $SUDO systemctl enable --now docker
  fi
}

sync_project() {
  $SUDO mkdir -p "$TARGET_DIR"
  local source_real target_real
  source_real="$(cd "$SOURCE_DIR" && pwd -P)"
  target_real="$(cd "$TARGET_DIR" && pwd -P)"
  if [[ "$source_real" == "$target_real" ]]; then
    $SUDO chmod +x "$TARGET_DIR/bk" "$TARGET_DIR/install.sh"
    return 0
  fi
  if [[ -d "$TARGET_DIR/.git" ]]; then
    (cd "$TARGET_DIR" && git fetch origin "$REMOTE_BRANCH" && git reset --hard "origin/$REMOTE_BRANCH")
  else
    rsync -a --exclude '.git' --exclude '.env' --exclude 'data' --exclude 'backups' "$SOURCE_DIR"/ "$TARGET_DIR"/
  fi
  $SUDO chmod +x "$TARGET_DIR/bk" "$TARGET_DIR/install.sh"
  $SUDO ln -sf "$TARGET_DIR/bk" "$BK_LINK"
}

main() {
  ensure_base_tools
  if ((${#MISSING[@]})); then
    printf '检测到缺少依赖：%s\n' "${MISSING[*]}"
    if ask_yes "是否自动安装这些依赖（包含 Docker）？"; then
      apt_install "${MISSING[@]}"
    else
      echo "安装已取消。"
      exit 1
    fi
  fi

  if ! have docker || ! docker compose version >/dev/null 2>&1; then
    if ask_yes "检测到 Docker 或 Docker Compose 不可用，是否现在安装？"; then
      install_docker
    else
      echo "Docker 未安装，Bookkeeping 无法以服务方式运行。"
      exit 1
    fi
  fi

  sync_project
  cd "$TARGET_DIR"

  if [[ ! -s .env ]]; then
    echo "首次安装需要配置管理员账户。"
    ./bk settings
  fi

  ./bk upgrade
  ./bk status

  cat <<EOF

Bookkeeping 已安装到：$TARGET_DIR
GitHub：$REPO_URL
管理命令：bk
访问端口：37037
如果使用 Nginx Proxy Manager，反代到宿主机 37037 即可。
EOF
}

main "$@"
