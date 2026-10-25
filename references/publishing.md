# 徽写 · 发布件规范

## 三类产物，职责分离

| 文件 | 内容 | 用途 |
|---|---|---|
| `dist/chapter-NNN.txt` | **只有正文**，无标题、无附言 | 直接喂上传工具 / 平台导入 |
| `dist/chapter-NNN.md` | front matter + 标题 + 正文 + 作者有话说 | 人读、归档、版本对照 |
| `dist/manifest.json` | 全部元数据、字数、校验和、发布状态 | 批量上传、进度核对 |

标题、正文、作者有话说三者在文件层面就分开，不靠约定：

- `.txt` 里没有标题行，也没有 `## 作者有话说`。上传工具不可能把它们带进平台。
- `.md` 里作者有话说前面有 `<!-- 以下不属于正文，请勿带入平台 -->` 分隔注释。
- 元数据全部在 front matter 与 manifest 里，正文里不出现任何结构编号。

## front matter 字段

```yaml
---
book: 书名
chapter: 164
title: 场面短名
volume: 3
season: 12
role: escalate
words: 3412          # 阅读页口径：去空白后的字符数
cjk: 2500            # 汉字数
hook: 异常细节
checksum: a1b2c3d4e5f60718   # 正文 sha256 前 16 位
generated: 2026-10-25
status: draft        # draft | ready | published
platform_id: null    # 平台侧章节 id，回填后不再变动
pushed_at: null
---
```

## 校验和的作用

`checksum` 只对**正文**计算，不含标题与附言。`lint` 会比对 `canon/chapter-NNN.txt` 与 `dist/chapter-NNN.md` 里的 checksum：

- 一致 → 发布件与正文同步。
- 不一致 → 正文改过但没重建 dist，`lint` 报 warn。**这是防止「改了稿但发的是旧版」的唯一机械保障。**

改稿流程因此固定为：改 `canon/` → 跑 `gate` → 跑 `publish` 重建。不要手改 `dist/`。

## 发布状态机

```
none ──publish──▶ draft ──作者确认──▶ ready ──上传成功──▶ published
                    ▲                                        │
                    └────────────── 改稿重发 ─────────────────┘
```

`manifest.json` 里每章带 `status` 与 `platform_id`，让「本地写到第几章」与「平台上了第几章」不再靠记忆对齐。批量上传工具应当在成功后回写这两个字段。

## 分隔线选项

平台若要求章末加 `***` 之类分隔，用 `--sep "***"`，会额外产出 `chapter-NNN.sep.txt`，正文本身不动。不要为了加分隔线去改 `canon/`。

## 命名规范

- 章号固定三位：`chapter-001`，过 999 章自然变成四位，排序不受影响。
- 全部小写 ASCII 文件名，中文只出现在内容里。避免平台或工具在 Windows 下因编码出错。
- 每章三个文件同名同号，靠扩展名区分用途。
