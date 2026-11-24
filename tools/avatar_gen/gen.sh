#!/bin/sh
# 用 Codex 的图像生成画一个角色头像：./gen.sh <角色id> "<角色描述>" "<底色>"
# 结果保存为 raw/<角色id>.png
set -e
cd "$(dirname "$0")"
mkdir -p raw
id="$1"; desc="$2"; bg="$3"
style=$(sed "s/BGCOLOR/$bg/" style.txt)
codex exec -m "${CODEX_MODEL:-gpt-6.1-terra}" --skip-git-repo-check -s workspace-write -C "$(pwd)" \
  "Use your image generation tool to create exactly one image, then save it as raw/$id.png in the current directory (copy the generated PNG file there). Do not write any other files and do not edit anything else.

Image prompt:
Character: $desc
$style" > "raw/$id.log" 2>&1
ls -la "raw/$id.png"
