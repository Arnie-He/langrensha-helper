#!/bin/sh
# 并行（5 个一批）生成 roles.tsv / todo.tsv 里列出的角色头像
cd "$(dirname "$0")"
list="${1:-roles.tsv}"
while IFS='	' read -r id desc bg; do
  printf '%s\0%s\0%s\0' "$id" "$desc" "$bg"
done < "$list" | xargs -0 -n 3 -P 5 sh -c './gen.sh "$0" "$1" "$2" || echo "FAILED $0"'
