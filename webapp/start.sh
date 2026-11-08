#!/bin/bash
# A股分析系统 一键启动
#
# 用法：
#   ./start.sh                   只绑局域网网卡（默认，手机可访问、外网/隧道进不来）
#   HOST=127.0.0.1 ./start.sh    只允许本机访问（最安全）
#   HOST=0.0.0.0 ./start.sh      所有网卡（会告警，不建议）
#   PORT=9000 ./start.sh         换端口
#
# 注意：默认不再绑 0.0.0.0。0.0.0.0 等于向包括 VPN/代理隧道在内的所有网卡开放，
#       曾出现访问日志里出现公网出口 IP 的情况。绑到具体局域网 IP 后隧道接口不再监听。
cd "$(dirname "$0")"
PY=/Users/jason_wu/.workbuddy/binaries/python/envs/default/bin/python
PORT=${PORT:-8765}

# 探测局域网 IPv4（Wi-Fi 优先，其次有线），滤掉隧道/虚拟网卡
detect_lan() {
  for ifc in en1 en0 en2 en3 en4; do
    ip=$(ipconfig getifaddr "$ifc" 2>/dev/null) || continue
    case "$ip" in
      192.168.*|10.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*) echo "$ip"; return 0 ;;
    esac
  done
  return 1
}

AUTO=0
if [ -z "${HOST}" ]; then
  if HOST=$(detect_lan); then AUTO=1; else HOST=127.0.0.1; fi
fi

if [ ! -f data_store/stock_list.pkl ]; then
  echo "首次运行：正在预构建股票数据分片（约 1-2 分钟）..."
  $PY build_store.py
fi

echo "──────────────────────────────────────────────"
if [ "$HOST" = "0.0.0.0" ]; then
  echo "⚠️  警告：绑定了 0.0.0.0，所有网卡（含 VPN/代理隧道）都可访问"
  echo "   本机：http://127.0.0.1:$PORT"
  for ip in $(ifconfig 2>/dev/null | awk '/inet /{print $2}' \
              | grep -E '^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)'); do
    echo "   内网：http://$ip:$PORT"
  done
elif [ "$HOST" = "127.0.0.1" ]; then
  echo "仅本机可访问：http://127.0.0.1:$PORT"
else
  echo "访问地址：http://$HOST:$PORT     ${AUTO:+（本机也用它，127.0.0.1 不再监听）}"
fi
echo "──────────────────────────────────────────────"
echo "Ctrl+C 退出"

exec $PY -m uvicorn app:app --host "$HOST" --port "$PORT"
