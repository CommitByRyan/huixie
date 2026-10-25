#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""徽写 V1.0 · 主引擎

    init      立作品（建目录树 + 六件档案 + 空状态）
    status    一览：进度 / 预算 / 未收伏笔 / 下一步
    state     查看或更新动态状态（草稿制：--set 先落 drafts/ 再 --apply）
    beats     节拍表校验与落盘
    assemble  装配单章上下文（硬预算 12k）
    lint      全书体检：章号 / 状态 / 伏笔 / 发布件校验和
    export    整本导出 txt / md

正文与发布件分别由 gate.py 与 publish.py 负责，写回由 writeback.py 负责。
所有命令退出码：0 成功，1 体检有问题，2 用法或环境错误。
"""

from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path

import budget
import hxlib as H

HERE = Path(__file__).resolve().parent
ROLE_SET = {"breath", "setup", "escalate", "payoff", "aftermath"}
HOOK_TYPES = {"异常细节", "悬念提问", "压力逼近", "关系反转", "信息揭露", "时间压迫"}
MIN_WORDS, MAX_WORDS = 1800, 9000

DIRS = ["canon", "beats", "events", "memory", "ctx", "dist", "drafts", "exports", "_archive"]


# ---------------------------------------------------------------- 模板

def blank_novel(slug: str, title: str, genre: str, target: int, premise: str) -> dict:
    return {
        "schema_version": H.SCHEMA_VERSION,
        "slug": slug,
        "title": title,
        "genre": genre,
        "description": "",
        "premise": premise,
        "target_words": target,
        "world": [],
        "power_system": {"intro": "", "stages": [], "hard_rules": []},
        "ban_terms": [],
        "name_facts": {},
        "realm_guard": False,
    }


def blank_state() -> dict:
    return {
        "schema_version": H.SCHEMA_VERSION,
        "chapter": 0,
        "updated_at": H.now_iso(),
        "timeline": {"now": "开篇", "time_of_day": "", "weather": ""},
        "protagonist": {"name": "", "condition": "", "power": "", "location": "",
                        "known": [], "goals": [], "updated": 0},
        "inventory": [],
        "npcs": [],
        "threads": [],
        "must_not": [],
        "open_questions": [],
        "_applied": [],
    }


def blank_bible() -> dict:
    return {"schema_version": H.SCHEMA_VERSION, "characters": [], "relationships": [],
            "locations": [], "items": [], "events": [], "storylines": []}


# ---------------------------------------------------------------- init

def cmd_init(a):
    root = H.root_path(a.root)
    slug = a.slug or re.sub(r"[^\w\u4e00-\u9fff-]+", "-", a.title).strip("-") or "untitled"
    p = root / slug
    if (p / "novel.json").exists() and not a.force:
        H.die(f"作品已存在：{p}（要重建加 --force）")
    for d in DIRS:
        (p / d).mkdir(parents=True, exist_ok=True)
    H.jsave(p / "novel.json", blank_novel(slug, a.title, a.genre, a.target, a.premise))
    H.jsave(p / "bible.json", blank_bible())
    H.jsave(p / "state.json", blank_state())
    H.jsave(p / "outline.json", {"volumes": []})
    H.jsave(p / "seasons.json", {"seasons": []})
    H.jsave(p / "chapters.json", {"chapters": []})
    H.wtext(p / "state.md", "# 动态状态（人读视图）\n\n尚未初始化，运行 `status` 生成。\n")
    out = {"ok": True, "slug": slug, "path": str(p)}
    if a.json:
        H.emit_json(out)
    else:
        print(f"已建立作品：{p}")
        print("下一步：填 novel.json 的世界观 → 写 outline.json 卷纲 → 用 beats 建节拍表")


# ---------------------------------------------------------------- beats

def validate_beats(bt: dict, n: int) -> tuple[list, list]:
    fails, warns = [], []
    if int(bt.get("chapter") or 0) != n:
        fails.append(f"chapter 字段 {bt.get('chapter')} 与参数 {n} 不一致")
    if not (bt.get("title") or "").strip():
        fails.append("缺 title")
    target = bt.get("target_words")
    if not isinstance(target, int) or not MIN_WORDS <= target <= MAX_WORDS:
        fails.append(f"target_words 须为 {MIN_WORDS}–{MAX_WORDS} 的整数")
        target = target if isinstance(target, int) else 0
    if bt.get("role") not in ROLE_SET:
        fails.append(f"role 须属于 {sorted(ROLE_SET)}")
    beats = bt.get("beats") or []
    if not 3 <= len(beats) <= 4:
        fails.append(f"节拍须 3–4 个冲突节点，当前 {len(beats)} 个")
    seen = []
    for i, b in enumerate(beats, 1):
        if int(b.get("no") or 0) != i:
            fails.append(f"第 {i} 个节拍的 no 应为 {i}")
        if not (b.get("function") or "").strip():
            fails.append(f"节拍 {i} 缺 function（承接/加压/反转/收束）")
        if not (b.get("event") or "").strip():
            fails.append(f"节拍 {i} 缺 event")
        w = b.get("words")
        if not isinstance(w, int) or w <= 0:
            fails.append(f"节拍 {i} 的 words 须为正整数")
        else:
            seen.append(w)
        if not (b.get("exit") or "").strip():
            warns.append(f"节拍 {i} 无 exit（出点），场景容易粘连")
    total = sum(seen)
    if target and seen:
        dev = abs(total - target) / target
        if dev > 0.12:
            fails.append(f"节拍字数合计 {total}，与目标 {target} 偏差 {dev:.0%}（须 ≤12%）")
        biggest = max(seen)
        if biggest > target * 0.45:
            fails.append(f"单个节拍 {biggest} 字占比超过 45%，会一段吃完整章")
    hook = bt.get("hook") or {}
    if not (hook.get("text") or "").strip():
        fails.append("缺 hook.text（章末钩子原文）")
    if hook.get("type") and hook["type"] not in HOOK_TYPES:
        warns.append(f"hook.type「{hook['type']}」不在预设枚举内（{sorted(HOOK_TYPES)}）")
    if not bt.get("continuity_from_prev"):
        warns.append("缺 continuity_from_prev（上一章停在哪）")
    return fails, warns


def cmd_beats(a):
    p = H.project(a.root, a.slug)
    if a.file:
        bt = H.jload(Path(a.file), {}) or {}
    else:
        bt = H.jload(H.beats_file(p, a.number), {}) or {}
        if not bt:
            H.die(f"没有节拍表：{H.beats_file(p, a.number)}（用 --file 指定）")
    fails, warns = validate_beats(bt, a.number)
    payload = {"ok": not fails, "chapter": a.number, "fail": fails, "warn": warns}
    if fails:
        if a.json:
            H.emit_json(payload)
        else:
            print(f"❌ 节拍表不合规（{len(fails)} 项）")
            for f in fails:
                print(f"  ❌ {f}")
            for w in warns:
                print(f"  ⚠ {w}")
        raise SystemExit(1)
    if a.check:
        payload["saved"] = False
    else:
        H.jsave(H.beats_file(p, a.number), bt)
        payload["saved"] = True
        chapters = H.jload(p / "chapters.json", {"chapters": []}) or {"chapters": []}
        rows = chapters.get("chapters", [])
        rec = next((c for c in rows if int(c.get("number", -1)) == a.number), None)
        if rec is None:
            rows.append({"number": a.number, "title": bt.get("title"),
                         "role": bt.get("role"), "summary": "",
                         "publish": {"status": "none"}})
        else:
            rec.setdefault("title", bt.get("title"))
            rec.setdefault("role", bt.get("role"))
        rows.sort(key=lambda c: int(c.get("number", 0)))
        chapters["chapters"] = rows
        H.jsave(p / "chapters.json", chapters)
    if a.json:
        H.emit_json(payload)
    else:
        print(f"✅ 节拍表通过：{len(bt.get('beats') or [])} 个节点 / "
              f"合计 {sum(int(b.get('words') or 0) for b in bt.get('beats') or [])} 字"
              + ("（已落盘）" if payload["saved"] else "（仅校验）"))
        for w in warns:
            print(f"  ⚠ {w}")


# ---------------------------------------------------------------- state

def cmd_state(a):
    p = H.project(a.root, a.slug)
    state = H.jload(p / "state.json", blank_state()) or blank_state()
    if a.set:
        new = H.jload(Path(a.set), {}) or {}
        merged = copy.deepcopy(state)
        for k, v in new.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            elif isinstance(v, list) and k in ("threads", "npcs", "inventory"):
                ids = {x.get("id") for x in merged.get(k, []) if isinstance(x, dict)}
                names = {x.get("name") for x in merged.get(k, []) if isinstance(x, dict)}
                for item in v:
                    if isinstance(item, dict) and (item.get("id") in ids or item.get("name") in names):
                        continue
                    merged.setdefault(k, []).append(item)
            else:
                merged[k] = v
        merged["updated_at"] = H.now_iso()
        H.backup(p / "state.json", "bak")
        H.jsave(p / "state.json", merged)
        state = merged
        if not a.json:
            print(f"状态已合并写入（{Path(a.set).name}）")
    if a.json:
        H.emit_json(state)
        return

    tl = state.get("timeline") or {}
    pt = state.get("protagonist") or {}
    threads = state.get("threads") or []
    by = {}
    for t in threads:
        by[t.get("status", "open")] = by.get(t.get("status", "open"), 0) + 1
    print(f"【{a.slug}】写到第 {state.get('chapter') or 0} 章 · {state.get('updated_at') or '—'}")
    print(f"时间线：{tl.get('now') or '—'} {tl.get('time_of_day') or ''}")
    print(f"主角：{pt.get('name') or '—'}｜{pt.get('condition') or '—'}｜{pt.get('power') or '—'}")
    print(f"物品 {len(state.get('inventory') or [])} 件 · NPC {len(state.get('npcs') or [])} 人")
    print("伏笔：" + " / ".join(f"{k} {v}" for k, v in sorted(by.items())) or "伏笔：无")
    due = [t for t in threads if isinstance(t.get("due"), int)
           and t["due"] <= int(state.get("chapter") or 0)
           and t.get("status") not in ("resolved", "abandoned")]
    if due:
        print("已到期未兑现：")
        for t in due[:8]:
            print(f"  ⭐ #{t['id']} {t['name']}（第{t['due']}章该兑）")


# ---------------------------------------------------------------- assemble

def cmd_assemble(a):
    p = H.project(a.root, a.slug)
    novel = H.jload(p / "novel.json", {}) or {}
    bible = H.jload(p / "bible.json", {}) or {}
    state = H.jload(p / "state.json", blank_state()) or blank_state()
    outline = H.jload(p / "outline.json", {}) or {}
    seasons = H.jload(p / "seasons.json", {}) or {}
    chapters = H.jload(p / "chapters.json", {"chapters": []}) or {"chapters": []}
    beats = H.jload(H.beats_file(p, a.number), {}) or {}

    if not beats and not a.allow_no_beats:
        H.die(f"第{a.number}章没有节拍表：先跑 beats（避免无细纲直接生成正文）")
    text, rep = budget.build(p, a.number, novel, bible, state, outline, seasons, chapters,
                             beats, cap=a.cap)
    if a.out:
        H.wtext(Path(a.out), text)
    else:
        H.wtext(H.ctx_file(p, a.number), text)
    rep["path"] = str(Path(a.out) if a.out else H.ctx_file(p, a.number))
    if a.json:
        H.emit_json(rep)
    else:
        print(f"上下文已装配：{rep['path']}")
        print(f"  总量 {rep['total']} / {rep['cap']} 字符 · 降级档位 {rep['tier_label']}")
        for k, v in rep["sections"].items():
            cap = rep["budget"][k]
            flag = "⚠" if v > cap else " "
            print(f"  {flag} {k:<7}{v:>6} / {cap}")
        if rep["over_cap"]:
            print("  ⚠ 已用尽全部降级档位仍超预算，建议拆分本章")
        if a.print_ctx:
            print("\n" + text)


# ---------------------------------------------------------------- lint

def cmd_lint(a):
    p = H.project(a.root, a.slug)
    novel = H.jload(p / "novel.json", {}) or {}
    state = H.jload(p / "state.json", blank_state()) or blank_state()
    chapters = H.jload(p / "chapters.json", {"chapters": []}) or {"chapters": []}
    rows = sorted(chapters.get("chapters", []), key=lambda c: int(c.get("number", 0)))
    errs, warns, infos = [], [], []

    nums = [int(c.get("number", 0)) for c in rows]
    if nums and nums != list(range(1, len(nums) + 1)):
        miss = sorted(set(range(1, max(nums) + 1)) - set(nums))
        errs.append(f"章号不连续，缺 {miss[:10]}" + ("…" if len(miss) > 10 else ""))

    written = sorted(int(re.search(r"(\d+)", f.stem).group(1))
                     for f in (p / "canon").glob("chapter-*.txt"))
    if written and written != list(range(1, len(written) + 1)):
        miss = sorted(set(range(1, max(written) + 1)) - set(written))
        errs.append(f"正文缺章 {miss[:10]}")
    if written and state.get("chapter") and int(state["chapter"]) != max(written):
        warns.append(f"state.chapter={state['chapter']} 与最大正文章 {max(written)} 不一致")

    no_beats = [n for n in written if not H.beats_file(p, n).exists()]
    if no_beats:
        warns.append(f"{len(no_beats)} 章缺节拍表：{no_beats[:8]}")

    no_sum = [int(c["number"]) for c in rows
              if int(c.get("number", 0)) in written and not (c.get("summary") or "").strip()]
    if no_sum:
        errs.append(f"{len(no_sum)} 章缺摘要：{no_sum[:8]}")

    threads = state.get("threads") or []
    ids = [t.get("id") for t in threads]
    if len(ids) != len(set(ids)):
        errs.append("伏笔 id 有重复")
    bad = [t.get("id") for t in threads
           if t.get("status") not in ("open", "dormant", "resolved", "abandoned")]
    if bad:
        errs.append(f"伏笔状态非法：{bad[:8]}")
    open_n = sum(1 for t in threads if t.get("status") in ("open", "dormant"))
    if open_n > 30:
        warns.append(f"未收伏笔 {open_n} 条（>30），建议收线或标 dormant/abandoned")
    no_ev = [t["id"] for t in threads
             if t.get("status") == "resolved" and not t.get("resolved_at")]
    if no_ev:
        warns.append(f"{len(no_ev)} 条已兑现伏笔缺 resolved_at：{no_ev[:6]}")

    dist_bad = []
    for f in sorted((p / "dist").glob("chapter-*.md")):
        n = int(re.search(r"(\d+)", f.stem).group(1))
        canon = H.chapter_file(p, n)
        if not canon.exists():
            dist_bad.append(f"第{n}章 dist 无对应正文")
            continue
        body = H.rtext(canon).strip()
        if H.sha256_text(body)[:16] not in H.rtext(f):
            dist_bad.append(f"第{n}章 dist 校验和与 canon 不符（正文改过但未重建）")
    if dist_bad:
        warns.extend(dist_bad[:6])

    ctx_over = []
    for f in sorted((p / "ctx").glob("ctx-*.md")):
        if H.read_len(H.rtext(f)) > budget.CAP * 1.15:
            ctx_over.append(f.name)
    if ctx_over:
        warns.append(f"上下文包超预算：{ctx_over[:5]}")

    if not novel.get("world"):
        warns.append("novel.world 为空（世界观未填，正文会缺少舞台约束）")
    if not (novel.get("description") or "").strip():
        warns.append("novel.description 为空")

    payload = {"ok": not errs, "slug": a.slug, "chapters": len(rows),
               "written": len(written), "open_threads": open_n,
               "err": errs, "warn": warns, "info": infos}
    if a.json:
        H.emit_json(payload)
    else:
        print(f"【体检】{a.slug}：{len(rows)} 章目 / {len(written)} 章正文 / 未收伏笔 {open_n}")
        for e in errs:
            print(f"  ❌ {e}")
        for w in warns:
            print(f"  ⚠ {w}")
        print("✅ 通过" if not errs else f"❌ {len(errs)} 个错误")
    raise SystemExit(0 if not errs else 1)


# ---------------------------------------------------------------- export

def cmd_export(a):
    p = H.project(a.root, a.slug)
    novel = H.jload(p / "novel.json", {}) or {}
    chapters = H.jload(p / "chapters.json", {"chapters": []}) or {"chapters": []}
    title_of = {int(c["number"]): c.get("title") or "" for c in chapters.get("chapters", [])}
    files = sorted((p / "canon").glob("chapter-*.txt"),
                   key=lambda f: int(re.search(r"(\d+)", f.stem).group(1)))
    if not files:
        H.die("没有正文可导出")
    out_dir = p / "exports"
    out_dir.mkdir(exist_ok=True)
    stem = f"{novel.get('title') or a.slug}-全本"

    if a.format in ("txt", "both"):
        parts = []
        for f in files:
            n = int(re.search(r"(\d+)", f.stem).group(1))
            parts.append(f"第{n}章 {title_of.get(n) or ''}".strip())
            parts.append("")
            parts.append(f.read_text(encoding="utf-8").strip())
            parts.append("")
        H.wtext(out_dir / f"{stem}.txt", "\n".join(parts).rstrip() + "\n")
        print(f"txt → {out_dir / f'{stem}.txt'}（{len(files)} 章）")

    if a.format in ("md", "both"):
        md = [f"# {novel.get('title') or a.slug}", "",
              (novel.get("description") or "").strip(), ""]
        for f in files:
            n = int(re.search(r"(\d+)", f.stem).group(1))
            md += [f"## 第{n}章 {title_of.get(n) or ''}".strip(), "",
                   f.read_text(encoding="utf-8").strip(), ""]
        H.wtext(out_dir / f"{stem}.md", "\n".join(md).rstrip() + "\n")
        print(f"md  → {out_dir / f'{stem}.md'}（{len(files)} 章）")


# ---------------------------------------------------------------- status

def cmd_status(a):
    p = H.project(a.root, a.slug)
    novel = H.jload(p / "novel.json", {}) or {}
    state = H.jload(p / "state.json", blank_state()) or blank_state()
    chapters = H.jload(p / "chapters.json", {"chapters": []}) or {"chapters": []}
    rows = chapters.get("chapters", [])
    written = len(list((p / "canon").glob("chapter-*.txt")))
    dist_n = len(list((p / "dist").glob("chapter-*.md")))
    cur = int(state.get("chapter") or 0)
    nxt = cur + 1
    has_beats = H.beats_file(p, nxt).exists()
    beats_ok = False
    if has_beats:
        f, _ = validate_beats(H.jload(H.beats_file(p, nxt), {}) or {}, nxt)
        beats_ok = not f
    threads = state.get("threads") or []
    open_n = sum(1 for t in threads if t.get("status") in ("open", "dormant"))

    print(f"【{novel.get('title') or a.slug}】{novel.get('genre') or '—'}｜目标 {novel.get('target_words')} 字/章")
    print(f"  章目 {len(rows)} · 正文 {written} · 发布件 {dist_n} · 状态停在第 {cur} 章")
    print(f"  未收伏笔 {open_n} · 物品 {len(state.get('inventory') or [])} · "
          f"NPC {len(state.get('npcs') or [])}")
    if not has_beats:
        print(f"  下一步：为第 {nxt} 章写节拍表 → templates/beats.json")
    elif not beats_ok:
        print(f"  下一步：第 {nxt} 章节拍表不合规，先修")
    else:
        print(f"  下一步：assemble {a.slug} {nxt} → 写正文 → gate → writeback → publish")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="huixie", description="徽写 V1.0 长篇小说引擎")
    ap.add_argument("--root", default=None, help=f"作品根目录，默认 {H.DEFAULT_ROOT}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_root(s):
        # 允许 --root 写在子命令之后；不提供时保留全局值
        s.add_argument("--root", default=argparse.SUPPRESS, help="作品根目录（同全局）")

    s = sub.add_parser("init", help="立作品")
    s.add_argument("title")
    s.add_argument("--slug", default="")
    s.add_argument("--genre", default="")
    s.add_argument("--target", type=int, default=H.DEFAULT_TARGET)
    s.add_argument("--premise", default="")
    s.add_argument("--force", action="store_true")
    s.add_argument("--json", action="store_true")
    add_root(s)
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("status", help="一览与下一步")
    s.add_argument("slug")
    add_root(s)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("state", help="查看/更新动态状态")
    s.add_argument("slug")
    s.add_argument("--set", default="", help="合并写入的 JSON 文件")
    s.add_argument("--json", action="store_true")
    add_root(s)
    s.set_defaults(func=cmd_state)

    s = sub.add_parser("beats", help="节拍表校验与落盘")
    s.add_argument("slug")
    s.add_argument("number", type=int)
    s.add_argument("--file", default="")
    s.add_argument("--check", action="store_true", help="只校验不落盘")
    s.add_argument("--json", action="store_true")
    add_root(s)
    s.set_defaults(func=cmd_beats)

    s = sub.add_parser("assemble", help="装配单章上下文")
    s.add_argument("slug")
    s.add_argument("number", type=int)
    s.add_argument("--out", default="")
    s.add_argument("--cap", type=int, default=None,
                   help=f"上下文预算字符上限，默认 {budget.CAP}（小窗口模型可调低）")
    s.add_argument("--allow-no-beats", action="store_true")
    s.add_argument("--print", dest="print_ctx", action="store_true")
    s.add_argument("--json", action="store_true")
    add_root(s)
    s.set_defaults(func=cmd_assemble)

    s = sub.add_parser("lint", help="全书体检")
    s.add_argument("slug")
    s.add_argument("--json", action="store_true")
    add_root(s)
    s.set_defaults(func=cmd_lint)

    s = sub.add_parser("export", help="整本导出")
    s.add_argument("slug")
    s.add_argument("--format", default="both", choices=["txt", "md", "both"])
    add_root(s)
    s.set_defaults(func=cmd_export)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
