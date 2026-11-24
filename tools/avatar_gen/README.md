# 角色头像生成

头像由 Codex 的图像生成画出来（需要本机装好 `codex` 并登录）。

- `style.txt`：所有角色共用的画风描述（`BGCOLOR` 会换成每个角色的底色）
- `roles.tsv`：每个角色一行：`角色id<TAB>外形描述<TAB>底色`
- `gen.sh <id> "<描述>" "<底色>"`：画一个，存到 `raw/<id>.png`
- `run_all.sh [roles.tsv]`：5 个并行画完列表里的所有角色
- `process.sh`：把 `raw/*.png` 缩成 320px JPEG 放到 `public/avatars/`

界面素材（标题、卡背、月亮、太阳、三张背景）也是这样画的：

- `ui/<名字>.txt`：每个素材的完整描述
- `gen_ui.sh <名字>`：画一个，存到 `raw/ui_<名字>.png`
- `process_ui.py`：透明的存 WebP、不透明的存 JPEG，放到 `public/art/`

重画某个角色：改 `roles.tsv` 里那一行，然后

```bash
./gen.sh seer "$(grep '^seer	' roles.tsv | cut -f2)" "$(grep '^seer	' roles.tsv | cut -f3)"
./process.sh
```

默认用 `gpt-6.1-terra` 调度（ChatGPT 账号登录时 Codex 的默认模型可能不能用），可以用 `CODEX_MODEL=...` 换。
