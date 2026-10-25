---
name: huixie
description: "徽写 V1.0 长篇小说工作流（写小说/网文/连载/长篇/开书/日更）。当用户要开新书、写正文、做设定与卷纲季纲、拆分章节节拍、装配单章上下文、审查去 AI 味、回写状态、生成发布件或整本导出时使用。核心特征：静态设定与动态状态分离、单章上下文硬预算 12k 字符、节拍器先于正文、写回钩子维护伏笔四态、发布件正文与标题附言分离。"
version: 1.0.0
---

# 徽写 V1.0

一套把长篇小说拆成**可执行管线**的写作系统。要解决的问题只有四个：

1. **吃书** —— 状态散在四处，每章重新拼一遍，拼错就崩人设。
2. **Token 膨胀** —— 单章上下文越长越胖，写到后期 90% 的输入与本章无关。
3. **节奏失控** —— 一次生成整章，几句话把三章剧情跑完。
4. **AI 味与发布摩擦** —— 套话堆砌，且成品格式无法直接对接上传。

对应四个机制：**状态双层解耦 / 预算装配器 / 节拍器 / 写回钩子 + 发布件**。

---

## 0. 安装、自检与命令入口

### 0.1 拉取与安装（首次必做）

```bash
git clone https://github.com/CommitByRyan/huixie.git ~/.workbuddy/skills/huixie
cd ~/.workbuddy/skills/huixie && python scripts/selfcheck.py && python scripts/e2e_check.py
```

**两项全绿才算装好**：`selfcheck.py` 查文件齐全、声明合法、JSON 可解析、脚本可运行、无旧名残留；`e2e_check.py` 用临时目录跑完整链路并断言 41 项（含预算降级、闸门拦截、写回幂等）。

装好后的目录结构就是技能目录本身，无需再移动文件。

### 0.2 路径规则（决定能不能在任意目录调用）

- 脚本**自己解析仓库根**（`Path(__file__).resolve().parent.parent`），因此可以在任意 cwd 用绝对路径调用，不依赖 `cd`。
- 作品目录默认取**当前 cwd** 下的 `徽写作品/`，用 `--root` 可改。这意味着同一份技能可以服务多个工作区，作品不会串。
- 依赖：**Python 3.10+**，零第三方包。低于 3.10 会在导入时直接报错退出（退出码 2），不会跑出半截结果。
- 控制台已强制 UTF-8 输出，Windows 下 cp936 环境打印中文与 JSON 不会崩。

推荐写法（把技能目录固定成变量，避免相对路径歧义）：

```bash
SKILL=~/.workbuddy/skills/huixie
python "$SKILL/scripts/huixie.py" status <slug> --root ./徽写作品
```

### 0.3 命令

```bash
PY=python                                    # 用哪个解释器都行，脚本只用标准库
HX=<技能目录>/scripts/huixie.py

"$PY" "$HX" init "书名" --genre "悬疑·都市"     # 立作品，建目录树与六件档案
"$PY" "$HX" status <slug>                       # 进度 / 未收伏笔 / 下一步该做什么
"$PY" "$HX" state <slug>                        # 看动态状态（时间线·面板·伏笔四态）
"$PY" "$HX" beats <slug> 12 --file b.json       # 节拍表校验并落盘
"$PY" "$HX" assemble <slug> 12                  # 装配单章上下文 → ctx/ctx-012.md
"$PY" "$HX" lint <slug>                         # 全书体检
"$PY" "$HX" export <slug> --format txt          # 整本导出

"$PY" scripts/gate.py <slug> 12 --json           # 硬闸（退出码 0/1/2）
"$PY" scripts/writeback.py <slug> 12             # 写回 state + bible
"$PY" scripts/publish.py <slug> 12 --note "…"    # 生成 dist 发布件
```

作品默认放在 `<工作区>/徽写作品/<slug>/`，可用 `--root` 改。同一工作区可放多本。

**所有命令先跑 `status`**，它会告诉你停在哪、下一章缺什么。

---

## 1. 七段管线

```
S1 卷纲 → S2 分季 → S3 章目 → S4 节拍 → S5 正文 → S6 硬闸+审校 → S7 写回+发布
                                        ▲                              │
                                        └──────── 下一章 ──────────────┘
```

| 段 | 做什么 | 提示词 | 产出 | 通过标准 |
|---|---|---|---|---|
| S1 | 世界切成 2–4 卷 | `prompts/01_outline.md` | `outline.json` | 卷号连续、章号覆盖全书 |
| S2 | 一卷切 3–5 季 | `prompts/02_season.md` | `seasons.json` | 季号全书连续、区间接得上 |
| S3 | 每章一句要点 | 手工/助手 | `chapters.json` | 章名不重复、role 分配合理 |
| S4 | 拆 3–4 个冲突节点 | `prompts/03_beats.md` | `beats/beats-NNN.json` | `beats` 校验全绿 |
| S5 | 按节拍写正文 | `prompts/04_write.md` | `canon/chapter-NNN.txt` | `gate` 退出码 0 |
| S6 | 机器闸门 + 四维审校 | `prompts/05_critic.md` | 问题清单 | 无 blocker |
| S7 | 抽增量写回 + 出发布件 | `prompts/06_writeback.md` | `events/`·`state.json`·`dist/` | `writeback` 无 warn、`lint` 0 错 |

**不要跳段。** 没有节拍表就写正文，等于放弃节奏控制——`assemble` 会直接拒绝（要强写加 `--allow-no-beats`）。

---

## 2. 状态双层

| 层 | 文件 | 谁写 | 变化频率 |
|---|---|---|---|
| 静态设定 | `novel.json`、`bible.json` | 作者确认后手改 | 基本不变 |
| 动态状态 | `state.json` | `writeback.py` 增量写 | 每章 |

`state.json` 里的伏笔是**四态**：`open` / `dormant` / `resolved` / `abandoned`。
「推进」不等于「兑现」——`advance` 只记一笔，`resolve` 必须带正文里指认得到的 evidence。
详见 `references/state-model.md`。

---

## 3. 上下文预算（本系统最关键的一条）

`assemble` 产出的单章上下文**硬上限 12,000 字符**：

| 层 | 预算 | 内容 |
|---|---|---|
| static | 4000 | 世界观 5 段 / 力量体系 / 禁词 / 姓名红线 / 角色卡 6 张 |
| arc | 1200 | 本卷 / 本季主线 / 季钩子 |
| window | 3500 | 近 3 章摘要 + 上一章末 900 字 + 本章要点 |
| state | 2500 | 主角面板 / 物品栏 / 活跃 NPC 5 / 相关伏笔 12 |
| beats | 800 | 节拍表 |

超了就按 T1–T7 逐级降级，降了哪一档会写进报告，不静默丢弃。
伏笔**按相关度取**（到期 > 三章内到期 > 本章点名 > 近埋），已 `resolved` / `abandoned` 的一律不注入。
详见 `references/budget.md`。

实测：一本 160 章规模的档案，下一章的上下文从 87,590 字符压到 **4,133 字符（降幅 95.3%）**，未触发降级。

---

## 4. 闸门与审校

`gate.py` 是**机器闸门**，输出结构化 JSON，靠退出码判定：

- `0` 通过，`1` 有硬伤，`2` 闸门自身异常。

上层流水线**必须把 1 和 2 都当成未通过**。这是刻意设计：旧式「看输出里有没有 ❌」的判定，在脚本崩溃时会把坏稿当合格稿放行。

机器查：字数（阅读页口径与汉字数双报）/ 章节号季号泄漏 / 本书禁词 / AI 味三层阈值 /
回声句（≤12 字句子重复 >2 次）/ 引号配对 / 重复段落 / 段落长度 / 结尾完整性。

`prompts/05_critic.md` 是**人味审校**，只看节奏、信息、语言、连贯四维，输出问题清单与**最小改法**，不改全文。
分数有锚点（9 分可发布 / 7 分有可改处 / 5 分骨架有问题），任一项 ≤6 即 `fix_required`。

AI 味词表在 `references/ai_flavor.json`，可直接增删，`gate.py` 只读该文件，不在代码里写死。

---

## 5. 写回钩子

一章过闸后，跑 `writeback.py`，把 `events/events-NNN.json` 增量合并进状态：

- 新角色 → `bible.characters`，同时补 `npcs` 与 `speech_style`（对话同质化的对策就在这里）
- 物品 → 按 `delta` 增减，`qty<=0` 自动置 `held=false`
- 伏笔 → 新建 / 推进 / 兑现 / 放弃，四态分别落位
- 摘要 → `chapters.json.summary` 与 `memory/summary-NNN.md`

**幂等**：写回的章号记在 `state._applied`，重复跑会跳过，要覆盖加 `--force`。
**增量**：所有合并都是按姓名/ id 更新，不做整体替换，不会抹掉既有条目。

---

## 6. 发布件

`publish.py` 一章产出三个文件，标题、正文、附言在文件层面就分开：

| 文件 | 内容 |
|---|---|
| `dist/chapter-NNN.txt` | 只有正文，可直接喂上传工具 |
| `dist/chapter-NNN.md` | front matter + 标题 + 正文 + 作者有话说 |
| `dist/manifest.json` | 元数据、字数、checksum、发布状态、平台 id |

`checksum` 是正文 sha256 前 16 位，`lint` 用它比对 `canon/` 与 `dist/`——正文改了但没重建 dist 会被抓出来。
详见 `references/publishing.md`。

---

## 7. 每次落笔前后的固定动作

**写之前**
1. `status` 确认停在哪、下一章有没有节拍表。
2. `assemble` 生成上下文，看报告里有没有降级、有没有 `over_cap`。
3. 上下文交给 `04_write.md`，按节拍一拍一拍写。

**写之后**
4. `gate --json`：退出码不是 0 就不许进下一步。
5. `05_critic.md` 过一遍，只改 blocker 与 major。
6. `writeback`：把本章增量写回状态。
7. `publish`：出发布件。
8. `lint`：0 错再交付。

**每 10 章**：`lint` + `export` 各跑一次，核对字数与章号。

---

## 8. 参考文件

| 文件 | 内容 |
|---|---|
| `references/schema.md` | 全部 JSON 字段与文件命名 |
| `references/state-model.md` | 动态状态模型、伏笔四态、相关度算法、不变式 |
| `references/budget.md` | 预算表、降级阶梯、实测省量 |
| `references/ai_flavor.json` | AI 味词表三层 + 回声句/版面/结尾阈值 |
| `references/publishing.md` | 发布件规范、校验和、状态机 |
| `prompts/01…06` | 六个阶段的提示词母本 |
| `templates/` | beats / events / state / chapter 模板 |
| `scripts/selfcheck.py` | 技能包自检（含旧名残留门禁） |
| `scripts/e2e_check.py` | 端到端测试（含预算降级与闸门拦截） |

---

## 9. 四条纪律

1. **一次只做一段。** 当前段没通过，不进下一段。
2. **节拍表是硬约束。** 正文里发生的事必须能对上某个节拍；要改剧情先改节拍表。
3. **状态只信 `state.json`。** 摘要、正文、记忆都可能旧，`state.json` 是这一章唯一的此刻。
4. **降级要可见。** 上下文被砍了什么，必须在报告里说清，不允许悄悄丢。
