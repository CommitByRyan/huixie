# 徽写 · 数据schema

全部档案都是 UTF-8 JSON。`schema_version` 目前恒为 `1`。

## 目录

```
徽写作品/<slug>/
├─ novel.json      静态·基本不变
├─ bible.json      静态·慢变
├─ state.json      动态·每章变
├─ outline.json    卷纲
├─ seasons.json    季纲
├─ chapters.json   章目
├─ canon/          chapter-NNN.txt    权威正文（纯净，无标题）
├─ beats/          beats-NNN.json     节拍表
├─ events/         events-NNN.json    写回输入
├─ memory/         summary-NNN.md     摘要归档
├─ ctx/            ctx-NNN.md         装配后的上下文（可随时重建）
├─ dist/           chapter-NNN.md/.txt + manifest.json
├─ drafts/         草稿
├─ exports/        整本导出
└─ _archive/       归档（旧上下文、备份）
```

## novel.json — 静态设定

| 字段 | 类型 | 说明 |
|---|---|---|
| `slug` | str | 目录名 |
| `title` / `genre` / `description` | str | 书名 / 类型（多个用「·」）/ 简介 |
| `premise` | str | 作者原话，全书剧情唯一来源，**禁止改写** |
| `target_words` | int | 单章目标字数，默认 3400 |
| `world` | `[{label, body}]` | 世界观分段，按题材自由增减 |
| `power_system` | `{intro, stages[], hard_rules[]}` | 无力量体系时留空数组，不要编 |
| `ban_terms` | `[str]` | 本书禁词，正文出现即判失败 |
| `name_facts` | `{名字: 字数}` | 人名字数红线，如 `{"林汎": 2}` |
| `realm_guard` | bool | 是否启用境界越界检查（默认 false，避免误伤非仙侠题材） |

## state.json — 动态状态

见 `state-model.md`。核心字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `chapter` | int | 已写到的章号 |
| `timeline` | `{now, time_of_day, weather, chapter}` | 故事内当前时间 |
| `protagonist` | `{name, condition, power, location, known[], goals[], updated}` | 主角面板 |
| `inventory` | `[{name, qty, held, note, updated}]` | 物品栏，`qty<=0` 自动 `held=false` |
| `npcs` | `[{name, relation, warmth, alive, note, last_seen, updated}]` | 活跃 NPC |
| `threads` | `[{id, name, status, planted, due, note, updated, resolved_at, abandoned_at}]` | 伏笔池 |
| `must_not` | `[str]` | 作者拍板的禁区，会进每章上下文 |
| `open_questions` | `[str]` | 尚未决定怎么收的线 |
| `_applied` | `[int]` | 已写回章号，用于幂等 |

## chapters.json — 章目

```json
{"chapters": [{
  "number": 1, "title": "场面短名", "role": "escalate",
  "summary": "80–150 字", "summary_source": "writeback",
  "volume": 1, "plot_brief": "本章要点（可选，写章前填）",
  "publish": {"status": "none|draft|ready|published", "words": 3400,
              "checksum": "16位", "platform_id": null, "pushed_at": null}
}]}
```

## beats/NNN.json — 节拍表

| 字段 | 类型 | 约束 |
|---|---|---|
| `chapter` | int | 必须等于文件名章号 |
| `title` | str | 四到六字，不用「第X章」 |
| `role` | enum | `breath` / `setup` / `escalate` / `payoff` / `aftermath` |
| `target_words` | int | 1800–9000 |
| `continuity_from_prev` | str | 上一章停在哪 |
| `beats` | `[{no, function, event, words, exit}]` | **3–4 个**；字数合计偏差 ≤12%；单拍 ≤45% |
| `hook` | `{type, text}` | `text` 必须是章末原文 |
| `forbidden` | `[str]` | 本章禁止发生的事 |

`function` 建议用：承接 / 加压 / 反转 / 收束。

## events/NNN.json — 写回输入

| 字段 | 作用 |
|---|---|
| `summary` | 80–150 字，写入 chapters.json 与 memory/ |
| `timeline` | 覆盖 state.timeline |
| `protagonist` | 合并进主角面板；`known_add` 为追加 |
| `characters_new` | 新角色入库 bible.characters（同名则更新） |
| `npcs` | 按姓名 upsert |
| `items` | `delta` 增减，按名称合并 |
| `threads_new` | 新建伏笔，id 自动分配 |
| `threads_advance` | 推进，不改 status |
| `threads_resolve` | 置 `resolved`，需 `evidence` |
| `threads_abandon` | 置 `abandoned`，需作者指示 |

## dist/manifest.json — 发布清单

```json
{"book": "", "schema_version": 1, "generated_at": "", "count": 0, "total_words": 0,
 "chapters": [{"chapter": 1, "title": "", "file": "chapter-001.txt",
               "md": "chapter-001.md", "volume": 1, "season": 1, "role": "",
               "words": 3400, "cjk": 2500, "hook": "", "checksum": "16位",
               "generated": "2026-01-01", "status": "draft",
               "platform_id": null, "pushed_at": null}]}
```

`checksum` 是正文（不含标题与作者有话说）的 sha256 前 16 位。`lint` 会用它比对 `canon/` 与 `dist/`，正文改过但没重建 dist 会报出来。
