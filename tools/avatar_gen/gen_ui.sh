#!/bin/sh
# 用 Codex 画界面素材：./gen_ui.sh <名字>，读 ui/<名字>.txt 里的完整描述，存到 raw/ui_<名字>.png
set -e
cd "$(dirname "$0")"
mkdir -p raw
name="$1"
codex exec -m "${CODEX_MODEL:-gpt-6.1-terra}" --skip-git-repo-check -s workspace-write -C "$(pwd)" \
  "Use your image generation tool to create exactly one image, then save it as raw/ui_$name.png in the current directory (copy the generated PNG file there). If the prompt asks for a transparent background, request a transparent background from the image tool. Do not write any other files and do not edit anything else.

Image prompt:
$(cat "ui/$name.txt")" > "raw/ui_$name.log" 2>&1
ls -la "raw/ui_$name.png"
