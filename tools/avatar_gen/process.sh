#!/bin/sh
# 把 raw/*.png（1254px，约 2MB）缩成 320px 的 JPEG，放到 public/avatars/
cd "$(dirname "$0")"
out=../../public/avatars
mkdir -p "$out"
for f in raw/*.png; do
  id=$(basename "$f" .png)
  sips -s format jpeg -s formatOptions 82 -Z 320 "$f" --out "$out/$id.jpg" >/dev/null
done
ls -la "$out"/*.jpg | awk '{s+=$5} END {print NR " files, " int(s/1024) " KB"}'
