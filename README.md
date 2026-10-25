# 徽写 V1.0

> 把长篇小说拆成可执行管线：静态设定与动态状态分离，单章上下文设硬预算，节拍器先于正文，写完自动写回状态。

徽写是一套面向长篇连载的写作工作流，由 7 个阶段、6 个提示词、5 个脚本组成，只依赖 Python 标准库。它要解决的不是"让模型写得更华丽"，而是**让一本写到 200 章的书，仍然记得第 3 章那把钥匙在谁手里**。

## 它解决的四个问题

| 问题 | 现象 | 徽写的做法 |
|---|---|---|
| 吃书 | 状态散在摘要、设定、正文、记忆四处，每章重拼一遍 | `state.json` 作唯一动态状态，每章增量写回 |
| Token 膨胀 | 写到后期，90% 的输入与本章无关 | 装配器硬预算 12,000 字符，超限分层降级 |
| 节奏失控 | 一次生成整章，几句话跑完三章剧情 | 先出 3–4 个冲突节点的节拍表，正文按拍写 |
| 发布摩擦 | 正文混着标题与附言，无法直接上传 | `dist/` 三分：纯净正文 / 带元数据 md / manifest |

## 安装

徽写是一个 WorkBuddy 技能包，也是独立的命令行工具。**仓库根目录就是技能目录**，克隆到哪就在哪工作。

```bash
git clone https://github.com/CommitByRyan/huixie.git ~/.workbuddy/skills/huixie
cd ~/.workbuddy/skills/huixie && python scripts/selfcheck.py && python scripts/e2e_check.py
```

两项全绿才算装好。之后可以在任意目录用绝对路径调用，脚本自己解析仓库根：

```bash
python ~/.workbuddy/skills/huixie/scripts/huixie.py status 雨巷 --root ./徽写作品
```

- 依赖：**Python 3.10+**，零第三方包。版本不足会在导入时报错退出（退出码 2），不会跑出半截结果。
- 输出已强制 UTF-8，Windows cp936 控制台打印中文与 JSON 不会崩。
- 作品目录默认取当前 cwd 下的 `徽写作品/`，同一份技能可服务多个工作区，作品互不干扰。
- 仓库带 `.gitattributes` 统一 LF，避免 Windows 检出后 JSON 变成 CRLF 影响校验与 diff。

## 快速开始

```bash
python scripts/huixie.py init "雨巷" --genre "悬疑·都市" --target 3400
# 填 徽写作品/雨巷/novel.json 的世界观与禁词

python scripts/huixie.py status 雨巷          # 看停在哪、下一步缺什么
python scripts/huixie.py beats 雨巷 1 --file beats-001.json
python scripts/huixie.py assemble 雨巷 1      # → ctx/ctx-001.md
# 把 ctx-001.md 交给 prompts/04_write.md 写正文 → canon/chapter-001.txt

python scripts/gate.py 雨巷 1 --json          # 退出码 0 才继续
python scripts/writeback.py 雨巷 1            # 状态写回
python scripts/publish.py 雨巷 1 --note "求收藏"   # 发布件
python scripts/huixie.py lint 雨巷            # 0 错再交付
```

## 七段管线

```
S1 卷纲 → S2 分季 → S3 章目 → S4 节拍 → S5 正文 → S6 硬闸+审校 → S7 写回+发布
                                        ▲                              │
                                        └──────── 下一章 ──────────────┘
```

| 段 | 提示词 | 产出 |
|---|---|---|
| S1 卷纲 | `prompts/01_outline.md` | `outline.json` |
| S2 分季 | `prompts/02_season.md` | `seasons.json` |
| S3 章目 | 手工 / 助手 | `chapters.json` |
| S4 节拍 | `prompts/03_beats.md` | `beats/beats-NNN.json` |
| S5 正文 | `prompts/04_write.md` | `canon/chapter-NNN.txt` |
| S6 审校 | `prompts/05_critic.md` + `gate.py` | 问题清单 / 闸门结果 |
| S7 写回 | `prompts/06_writeback.md` + `writeback.py` | `state.json`·`dist/` |

## 关键设计

**状态双层。** `novel.json` / `bible.json` 是慢变的静态设定，`state.json` 是每章变的动态状态。写作时只信 `state.json`——它是"此刻世界长什么样"的唯一出口。

**伏笔四态。** `open` / `dormant` / `resolved` / `abandoned`。只有一个 `resolved` 布尔位时，"已放弃""长期休眠""作者拍板留白"全堆在未收里，账越滚越厚，最后每章都塞不下。四态之后，全量账留档，进入上下文的只有相关的那十几条。

**预算硬上限。** 单章上下文 ≤ 12,000 字符，分五层配给（静态 4000 / 卷季 1200 / 滑窗 3500 / 状态 2500 / 节拍 800）。超了按 T1–T7 逐级降级，**降了哪一档写进报告，不静默丢弃**。

**闸门只认结构与退出码。** `gate.py` 输出 JSON，退出码 `0` 通过 / `1` 有硬伤 / `2` 自身异常。上层必须把 1 和 2 都当未通过。靠"输出里有没有 ❌"判定，会在脚本崩溃时把坏稿当合格稿放行。

**写回幂等且增量。** 章号记在 `state._applied`，重复跑跳过；所有合并按姓名或 id 更新，不做整体替换。

## 实测

用一本 160 章规模的连载档案做只读基准（数据已脱敏：仅保留结构与量级，装配下一章，不改动原作）：

| | 旧做法 | 徽写 |
|---|---|---|
| 单章上下文字符 | 87,590 | **4,133** |
| 伏笔注入 | 400+ 条全量 | 12 条按相关度 |
| 降级档位 | — | T0（未触发） |

降幅 95.3%，且 `e2e_check.py` 的 41 项断言与 `selfcheck.py` 的 6 组检查全绿。

## 目录

```
徽写作品/<slug>/
├─ novel.json      静态设定：书名/世界观/力量体系/禁词/姓名红线
├─ bible.json      静态设定：角色/关系/地点/道具/主线
├─ state.json      动态状态：时间线/主角面板/物品栏/NPC/伏笔池
├─ outline.json    卷纲
├─ seasons.json    季纲
├─ chapters.json   章目与摘要
├─ canon/          权威正文
├─ beats/          节拍表
├─ events/         写回输入
├─ memory/         摘要归档
├─ ctx/            装配后的上下文（可随时重建）
├─ dist/           发布件 + manifest.json
└─ exports/        整本导出
```

## 命令

| 命令 | 作用 |
|---|---|
| `huixie.py init` | 立作品，建目录树与六件档案 |
| `huixie.py status` | 进度、未收伏笔、下一步 |
| `huixie.py state` | 查看或合并更新动态状态 |
| `huixie.py beats` | 节拍表校验并落盘（3–4 节点、字数偏差 ≤12%） |
| `huixie.py assemble` | 装配单章上下文 |
| `huixie.py lint` | 全书体检：章号/状态/伏笔/发布件校验和 |
| `huixie.py export` | 整本导出 txt / md |
| `gate.py` | 单章硬闸（结构化 JSON） |
| `writeback.py` | 增量写回 state + bible |
| `publish.py` | 生成 dist 发布件与 manifest |

## 文档

- `references/schema.md` — 全部 JSON 字段
- `references/state-model.md` — 动态状态、伏笔四态、相关度算法
- `references/budget.md` — 预算表与降级阶梯
- `references/publishing.md` — 发布件规范、校验和、状态机
- `references/ai_flavor.json` — AI 味词表三层（可自行增删）

## 许可

MIT，版权归 徽写（Huixie）。详见 [LICENSE](LICENSE)。
