#!/bin/bash
# 清理 macOS 在 ExFAT 外置盘上留下的元数据垃圾
#   ._xxx        AppleDouble 资源叉：每个只有 4KB，但 ExFAT 按 128KB 簇分配 → 每个实占 128KB
#   __pycache__  Python 字节码缓存，删了会自动重建
#   .DS_Store    Finder 窗口状态
#
# 用法：./clean_junk.sh
# 扫描范围：/Volumes/TOSHIBA/炒股（含 回测 / 每日行情 / 分钟级行情）

set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || { echo "无法进入 $ROOT"; exit 1; }

before=$(df -k "$ROOT" | tail -1 | awk '{print $4}')

n_ad=$(find . -name "._*" -type f 2>/dev/null | wc -l | tr -d ' ')
find . -name "._*" -type f -exec rm -f {} + 2>/dev/null

n_pc=$(find . -name "__pycache__" -type d 2>/dev/null | wc -l | tr -d ' ')
find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null

n_ds=$(find . -name ".DS_Store" -type f 2>/dev/null | wc -l | tr -d ' ')
find . -name ".DS_Store" -type f -exec rm -f {} + 2>/dev/null

after=$(df -k "$ROOT" | tail -1 | awk '{print $4}')
freed=$(( (after - before) / 1024 ))
[ "$freed" -lt 0 ] && freed=0        # ExFAT 的 df 有抖动，避免出现负数

echo "清理完成："
echo "  AppleDouble 元数据  $n_ad 个"
echo "  __pycache__ 目录    $n_pc 个"
echo "  .DS_Store          $n_ds 个"
echo "  释放空间            ${freed} MB"
echo ""
df -h "$ROOT" | tail -1
