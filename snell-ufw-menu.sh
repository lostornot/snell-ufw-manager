#!/usr/bin/env bash

# ============================================================
# Snell UFW 交互式白名单助手 v3
#
# 适用场景：
# - 落地机跑 Snell
# - Surge Proxy Chain：客户端 → 中转 → 落地 Snell
# - 只允许指定中转 IP / CIDR 访问 Snell TCP + UDP
# - 用 journalctl -k 抓被 UFW 拦截的真实中转出口 IP
#
# v3 改动：
# - 单层菜单，不再使用二级菜单
# - 全部菜单使用数字编号
# - 删除规则改为先显示 ufw status numbered，再按编号删除
# - 取消“自动清理 CIDR 覆盖单 IP”这类复杂逻辑
#
# 配置文件：
# - /root/snell-ufw-helper.conf
# ============================================================

set -uo pipefail

CONFIG_FILE="/root/snell-ufw-helper.conf"

SNELL_PORT="28261"
SSH_PORT="22"

load_config() {
  if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck source=/dev/null
    source "$CONFIG_FILE"
  fi
}

save_config() {
  cat > "$CONFIG_FILE" <<CONF
SNELL_PORT="$SNELL_PORT"
SSH_PORT="$SSH_PORT"
CONF
}

need_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "请用 root 执行："
    echo "  sudo bash $0"
    exit 1
  fi
}

pause() {
  echo
  read -rp "按 Enter 返回菜单..."
}

line() {
  echo "------------------------------------------------------------"
}

trim() {
  echo "$1" | xargs
}

show_config() {
  echo "当前配置："
  echo "  Snell 端口：$SNELL_PORT"
  echo "  SSH 端口：$SSH_PORT"
  echo "  配置文件：$CONFIG_FILE"
}

show_menu() {
  clear
  line
  echo "Snell UFW 交互式白名单助手 v3"
  line
  show_config
  line
  echo "[基础]"
  echo "  1) 初始化 UFW"
  echo "  2) 查看 UFW 状态和编号"
  echo
  echo "[白名单]"
  echo "  3) 查看 Snell 白名单"
  echo "  4) 添加 IP / CIDR 白名单"
  echo "  5) 从文件批量添加白名单"
  echo "  6) 按 UFW 编号删除规则"
  echo
  echo "[日志排查]"
  echo "  7) 实时查看 journalctl -k 来源 IP"
  echo "  8) 提取最近访问 Snell 的来源 IP"
  echo "  9) 从提取结果加入白名单"
  echo
  echo "[安全清理]"
  echo " 10) 清理 Snell 端口全网放行"
  echo " 11) 检查 Snell 端口监听"
  echo
  echo "[配置]"
  echo " 12) 修改 Snell / SSH 端口"
  echo " 13) 添加自定义端口白名单，例如 iPerf3 5201"
  echo "  0) 退出"
  line
}

setup_ufw() {
  clear
  line
  echo "1) 初始化 UFW"
  line
  show_config
  echo
  echo "这个操作会："
  echo "  1. 安装 ufw"
  echo "  2. 放行 SSH ${SSH_PORT}/tcp"
  echo "  3. 设置默认拒绝入站"
  echo "  4. 设置默认允许出站"
  echo "  5. 启用 UFW"
  echo "  6. 设置日志级别为 low"
  echo
  read -rp "确认执行？[y/N]: " confirm

  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消。"
    pause
    return
  fi

  apt update
  apt install -y ufw

  echo
  echo "==> 放行 SSH，避免失联..."
  ufw allow "${SSH_PORT}/tcp" comment 'Allow SSH management'

  echo
  echo "==> 设置默认规则：入站拒绝，出站允许..."
  ufw default deny incoming
  ufw default allow outgoing

  echo
  echo "==> 设置日志级别为 low..."
  ufw logging low

  echo
  echo "==> 启用 UFW..."
  ufw --force enable

  echo
  echo "==> 当前状态："
  ufw status verbose

  pause
}

show_ufw_status() {
  clear
  line
  echo "2) 查看 UFW 状态和编号"
  line
  show_config
  echo
  echo "==> UFW verbose 状态："
  ufw status verbose
  echo
  echo "==> UFW numbered 状态："
  ufw status numbered

  pause
}

show_snell_whitelist() {
  clear
  line
  echo "3) 查看 Snell 白名单"
  line
  show_config
  echo
  echo "==> Snell 端口相关规则："
  echo

  ufw status verbose | grep -E "^${SNELL_PORT}/(tcp|udp)" || echo "没有找到 Snell 端口规则。"

  echo
  echo "提示："
  echo "  你想要的是："
  echo "    ${SNELL_PORT}/tcp ALLOW IN 某个中转 IP 或 CIDR"
  echo "    ${SNELL_PORT}/udp ALLOW IN 某个中转 IP 或 CIDR"
  echo
  echo "  不建议长期存在："
  echo "    ${SNELL_PORT}/tcp ALLOW IN Anywhere"
  echo "    ${SNELL_PORT}/udp ALLOW IN Anywhere"

  pause
}

allow_target() {
  local target="$1"

  echo "==> 放行 $target 访问 Snell TCP ${SNELL_PORT}..."
  ufw allow from "$target" to any port "$SNELL_PORT" proto tcp comment "Allow relay ${target} to Snell TCP"

  echo "==> 放行 $target 访问 Snell UDP ${SNELL_PORT}..."
  ufw allow from "$target" to any port "$SNELL_PORT" proto udp comment "Allow relay ${target} to Snell UDP"
}

add_whitelist() {
  clear
  line
  echo "4) 添加 IP / CIDR 白名单"
  line
  echo "示例："
  echo "  单个 IP：74.211.105.75"
  echo "  整个 C 段：38.181.81.0/24"
  echo
  read -rp "请输入要放行的 IP 或 CIDR: " target
  target="$(trim "$target")"

  if [[ -z "$target" ]]; then
    echo "输入为空，已取消。"
    pause
    return
  fi

  echo
  echo "准备放行：$target"
  echo "端口：${SNELL_PORT}/tcp + ${SNELL_PORT}/udp"
  read -rp "确认添加？[y/N]: " confirm

  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消。"
    pause
    return
  fi

  allow_target "$target"

  echo
  echo "==> 当前 Snell 端口规则："
  ufw status verbose | grep -E "^${SNELL_PORT}/(tcp|udp)" || true

  pause
}

add_whitelist_file() {
  clear
  line
  echo "5) 从文件批量添加白名单"
  line
  echo "文件格式示例："
  echo
  echo "  # 自有中转"
  echo "  74.211.105.75"
  echo
  echo "  # 第三方 SS 出口池"
  echo "  38.181.81.0/24"
  echo
  read -rp "请输入文件路径，例如 /root/relay-ips.txt: " file
  file="$(trim "$file")"

  if [[ -z "$file" || ! -f "$file" ]]; then
    echo "文件不存在，已取消。"
    pause
    return
  fi

  echo
  echo "将从文件读取：$file"
  echo "会为每个 IP / CIDR 添加 TCP + UDP 两条规则。"
  read -rp "确认批量添加？[y/N]: " confirm

  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消。"
    pause
    return
  fi

  while IFS= read -r raw_line; do
    item="$(trim "$raw_line")"

    # 跳过空行和注释行
    [[ -z "$item" ]] && continue
    [[ "$item" =~ ^# ]] && continue

    echo
    allow_target "$item"
  done < "$file"

  echo
  echo "==> 当前 Snell 端口规则："
  ufw status verbose | grep -E "^${SNELL_PORT}/(tcp|udp)" || true

  pause
}

expand_rule_numbers() {
  local input="$1"

  for token in $input; do
    if [[ "$token" =~ ^[0-9]+$ ]]; then
      echo "$token"
    elif [[ "$token" =~ ^([0-9]+)-([0-9]+)$ ]]; then
      start="${BASH_REMATCH[1]}"
      end="${BASH_REMATCH[2]}"

      if (( start <= end )); then
        for ((i=start; i<=end; i++)); do
          echo "$i"
        done
      else
        for ((i=start; i>=end; i--)); do
          echo "$i"
        done
      fi
    else
      echo "WARN: 忽略无效输入：$token" >&2
    fi
  done | sort -n | uniq | sort -nr
}

delete_by_number() {
  clear
  line
  echo "6) 按 UFW 编号删除规则"
  line
  echo "当前 UFW 规则编号如下："
  echo
  ufw status numbered
  echo
  echo "用法："
  echo "  删除单条：输入 4"
  echo "  删除多条：输入 4 5 8"
  echo "  删除连续范围：输入 4-7"
  echo
  echo "注意："
  echo "  这个功能会按 UFW 编号删除规则。"
  echo "  请不要误删 SSH 规则，否则可能影响远程登录。"
  echo "  脚本会自动按编号从大到小删除，避免编号变化导致删错。"
  echo
  read -rp "请输入要删除的规则编号，直接回车取消: " input
  input="$(trim "$input")"

  if [[ -z "$input" ]]; then
    echo "已取消。"
    pause
    return
  fi

  mapfile -t nums < <(expand_rule_numbers "$input")

  if [[ "${#nums[@]}" -eq 0 ]]; then
    echo "没有有效编号，已取消。"
    pause
    return
  fi

  echo
  echo "准备删除以下编号："
  printf '  %s\n' "${nums[@]}"
  echo
  read -rp "确认删除？[y/N]: " confirm

  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消。"
    pause
    return
  fi

  echo
  for num in "${nums[@]}"; do
    echo "==> 删除规则编号 $num"
    ufw --force delete "$num" || true
  done

  echo
  echo "==> 删除后的 UFW 状态："
  ufw status numbered

  pause
}

watch_log() {
  clear
  line
  echo "7) 实时查看 journalctl -k 来源 IP"
  line
  echo "端口：$SNELL_PORT"
  echo
  echo "使用方法："
  echo "  1. 保持这个窗口运行"
  echo "  2. 去 Surge 里测试不通的中转链路"
  echo "  3. 回来看 SRC= 后面的来源 IP"
  echo
  echo "重点字段："
  echo "  SRC=来源IP"
  echo "  DPT=${SNELL_PORT}"
  echo "  PROTO=TCP / UDP"
  echo
  echo "按 Ctrl+C 退出实时查看。"
  echo
  read -rp "按 Enter 开始..."

  trap 'echo; echo "已退出实时查看。"; trap - INT; pause; return' INT
  journalctl -kf | grep --line-buffered "DPT=${SNELL_PORT}"
  trap - INT
  pause
}

extract_src() {
  clear
  line
  echo "8) 提取最近访问 Snell 的来源 IP"
  line
  echo "常用时间范围："
  echo "  10 minutes ago"
  echo "  1 hour ago"
  echo "  2 hours ago"
  echo "  today"
  echo
  read -rp "请输入时间范围，直接回车默认 1 hour ago: " since

  if [[ -z "$since" ]]; then
    since="1 hour ago"
  fi

  echo
  echo "从 ${since} 以来访问 ${SNELL_PORT} 的来源 IP："
  echo

  result="$(
    journalctl -k --since "$since" 2>/dev/null \
      | grep "DPT=${SNELL_PORT}" \
      | grep -o 'SRC=[0-9.]*' \
      | cut -d= -f2 \
      | sort -u
  )"

  if [[ -z "$result" ]]; then
    echo "没有提取到来源 IP。"
    echo
    echo "可能原因："
    echo "  1. 最近没有被 UFW 拦截的访问"
    echo "  2. 该来源已经被放行，所以不会再出现 BLOCK 日志"
    echo "  3. 时间范围太短"
  else
    echo "$result"
  fi

  pause
}

extract_and_allow() {
  clear
  line
  echo "9) 从提取结果加入白名单"
  line
  echo "常用时间范围："
  echo "  10 minutes ago"
  echo "  1 hour ago"
  echo "  2 hours ago"
  echo "  today"
  echo
  read -rp "请输入时间范围，直接回车默认 1 hour ago: " since

  if [[ -z "$since" ]]; then
    since="1 hour ago"
  fi

  mapfile -t ips < <(
    journalctl -k --since "$since" 2>/dev/null \
      | grep "DPT=${SNELL_PORT}" \
      | grep -o 'SRC=[0-9.]*' \
      | cut -d= -f2 \
      | sort -u
  )

  if [[ "${#ips[@]}" -eq 0 ]]; then
    echo
    echo "没有提取到来源 IP。"
    pause
    return
  fi

  echo
  echo "提取到以下来源 IP："
  echo

  local i=1
  for ip in "${ips[@]}"; do
    echo "  [$i] $ip"
    ((i++))
  done

  echo
  echo "可选操作："
  echo "  输入编号：添加对应单个 IP"
  echo "  输入 a：添加全部 IP"
  echo "  输入 c：手动输入 CIDR，比如 38.181.81.0/24"
  echo "  直接回车：取消"
  echo
  read -rp "请选择: " choice
  choice="$(trim "$choice")"

  if [[ -z "$choice" ]]; then
    echo "已取消。"
    pause
    return
  fi

  if [[ "$choice" == "a" || "$choice" == "A" ]]; then
    echo
    echo "准备添加全部 IP。"
    read -rp "确认？[y/N]: " confirm

    if [[ "$confirm" =~ ^[Yy]$ ]]; then
      for ip in "${ips[@]}"; do
        allow_target "$ip"
      done
    else
      echo "已取消。"
    fi

    pause
    return
  fi

  if [[ "$choice" == "c" || "$choice" == "C" ]]; then
    echo
    read -rp "请输入 CIDR，例如 38.181.81.0/24: " cidr
    cidr="$(trim "$cidr")"

    if [[ -z "$cidr" ]]; then
      echo "输入为空，已取消。"
      pause
      return
    fi

    echo
    echo "准备放行 CIDR：$cidr"
    read -rp "确认？[y/N]: " confirm

    if [[ "$confirm" =~ ^[Yy]$ ]]; then
      allow_target "$cidr"
    else
      echo "已取消。"
    fi

    pause
    return
  fi

  if [[ "$choice" =~ ^[0-9]+$ ]]; then
    index=$((choice - 1))

    if [[ "$index" -lt 0 || "$index" -ge "${#ips[@]}" ]]; then
      echo "编号无效。"
      pause
      return
    fi

    selected_ip="${ips[$index]}"

    echo
    echo "准备放行：$selected_ip"
    read -rp "确认？[y/N]: " confirm

    if [[ "$confirm" =~ ^[Yy]$ ]]; then
      allow_target "$selected_ip"
    else
      echo "已取消。"
    fi

    pause
    return
  fi

  echo "输入无效。"
  pause
}

cleanup_anywhere() {
  clear
  line
  echo "10) 清理 Snell 端口全网放行"
  line
  echo "这个操作会尝试删除："
  echo "  ${SNELL_PORT}/tcp Anywhere"
  echo "  ${SNELL_PORT}/udp Anywhere"
  echo
  echo "不会删除指定 IP / CIDR 的白名单规则。"
  echo
  read -rp "确认清理？[y/N]: " confirm

  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消。"
    pause
    return
  fi

  echo
  echo "==> 删除 TCP 全网放行..."
  ufw delete allow "${SNELL_PORT}/tcp" || true

  echo
  echo "==> 删除 UDP 全网放行..."
  ufw delete allow "${SNELL_PORT}/udp" || true

  echo
  echo "==> 当前 Snell 端口规则："
  ufw status verbose | grep -E "^${SNELL_PORT}/(tcp|udp)" || echo "没有找到 Snell 端口规则。"

  echo
  echo "请确认不要再有："
  echo "  ${SNELL_PORT}/tcp ALLOW IN Anywhere"
  echo "  ${SNELL_PORT}/udp ALLOW IN Anywhere"

  pause
}

check_listen() {
  clear
  line
  echo "11) 检查 Snell 端口监听"
  line
  echo "检查端口：$SNELL_PORT"
  echo
  ss -tulpen | grep "$SNELL_PORT" || echo "没有看到 $SNELL_PORT 的监听记录。"
  echo
  echo "提示："
  echo "  看到 0.0.0.0:${SNELL_PORT} 只代表 Snell 在监听。"
  echo "  是否能从公网访问，要看 UFW 是否只允许白名单。"
  pause
}


add_custom_port_whitelist() {
  clear
  line
  echo "13) 添加自定义端口白名单"
  line
  echo "适合临时放行 iPerf3、测试服务、临时端口。"
  echo
  echo "iPerf3 默认端口：5201"
  echo

  read -rp "请输入要放行的来源 IP 或 CIDR，例如 1.2.3.4 或 38.181.81.0/24: " source_ip
  source_ip="$(trim "$source_ip")"

  if [[ -z "$source_ip" ]]; then
    echo "来源 IP / CIDR 为空，已取消。"
    pause
    return
  fi

  read -rp "请输入端口，直接回车默认 5201: " port
  port="$(trim "$port")"

  if [[ -z "$port" ]]; then
    port="5201"
  fi

  if [[ ! "$port" =~ ^[0-9]+$ ]]; then
    echo "端口必须是数字，已取消。"
    pause
    return
  fi

  echo
  echo "请选择协议："
  echo "  1) TCP"
  echo "  2) UDP"
  echo "  3) TCP + UDP，推荐 iPerf3"
  echo
  read -rp "请选择，直接回车默认 3: " proto_choice
  proto_choice="$(trim "$proto_choice")"

  if [[ -z "$proto_choice" ]]; then
    proto_choice="3"
  fi

  echo
  echo "准备添加："
  echo "  来源：$source_ip"
  echo "  端口：$port"
  case "$proto_choice" in
    1) echo "  协议：TCP" ;;
    2) echo "  协议：UDP" ;;
    3) echo "  协议：TCP + UDP" ;;
    *) echo "协议选择无效，已取消。"; pause; return ;;
  esac

  echo
  read -rp "确认添加？[y/N]: " confirm

  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "已取消。"
    pause
    return
  fi

  case "$proto_choice" in
    1)
      ufw allow from "$source_ip" to any port "$port" proto tcp comment "TEMP allow custom TCP ${port} from ${source_ip}"
      ;;
    2)
      ufw allow from "$source_ip" to any port "$port" proto udp comment "TEMP allow custom UDP ${port} from ${source_ip}"
      ;;
    3)
      ufw allow from "$source_ip" to any port "$port" proto tcp comment "TEMP allow custom TCP ${port} from ${source_ip}"
      ufw allow from "$source_ip" to any port "$port" proto udp comment "TEMP allow custom UDP ${port} from ${source_ip}"
      ;;
  esac

  echo
  echo "==> 添加后的 UFW 编号规则："
  ufw status numbered

  echo
  echo "提示："
  echo "  测试完后，建议用菜单 6 按编号删除这些 TEMP 规则。"

  pause
}

change_config() {
  clear
  line
  echo "12) 修改 Snell / SSH 端口"
  line
  show_config
  echo

  read -rp "请输入 Snell 端口，直接回车保持 ${SNELL_PORT}: " new_snell
  read -rp "请输入 SSH 端口，直接回车保持 ${SSH_PORT}: " new_ssh

  if [[ -n "$new_snell" ]]; then
    SNELL_PORT="$new_snell"
  fi

  if [[ -n "$new_ssh" ]]; then
    SSH_PORT="$new_ssh"
  fi

  save_config

  echo
  echo "配置已保存："
  show_config

  pause
}

main() {
  need_root
  load_config
  save_config

  while true; do
    show_menu
    read -rp "请选择操作: " choice
    choice="$(trim "$choice")"

    case "$choice" in
      1) setup_ufw ;;
      2) show_ufw_status ;;
      3) show_snell_whitelist ;;
      4) add_whitelist ;;
      5) add_whitelist_file ;;
      6) delete_by_number ;;
      7) watch_log ;;
      8) extract_src ;;
      9) extract_and_allow ;;
      10) cleanup_anywhere ;;
      11) check_listen ;;
      12) change_config ;;
      13) add_custom_port_whitelist ;;
      0|q|Q) echo "退出。"; exit 0 ;;
      *) echo "无效选择。"; pause ;;
    esac
  done
}

main