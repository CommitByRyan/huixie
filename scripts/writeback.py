#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""徽写 · 写回钩子（Post-Writing Hook）

一章通过硬闸后，从本章抽取的四类增量写回两处：
- state.json  动态状态：时间线 / 主角面板 / 物品栏 / NPC / 伏笔池
- bible.json  静态事实：新角色入库 / 事件账镜像（供全书检索与终检）

幂等：state.json 记录 `_applied` 章号列表，重复跑同一章默认跳过（--force 可覆盖）。
所有写回都是**增量合并**，不做整体替换，不会抹掉既有条目。
"""

from __future__ import annotations

import argparse
from pathlib import Path

import hxlib as H

THREAD_STATUS = ("open", "resolved", "dormant", "abandoned")


def _next_thread_id(threads: list) -> int:
    return max([int(t.get("id") or 0) for t in threads] + [0]) + 1


def _upsert_npc(npcs: list, item: dict, chapter: int) -> str:
    name = (item.get("name") or "").strip()
    if not name:
        return "skip"
    hit = next((x for x in npcs if x.get("name") == name), None)
    if hit:
        for k in ("relation", "warmth", "alive", "note"):
            if item.get(k) not in (None, ""):
                hit[k] = item[k]
        hit["last_seen"] = int(item.get("last_seen") or chapter)
        hit["updated"] = chapter
        return "update"
    npcs.append({
        "name": name,
        "relation": item.get("relation") or "—",
        "warmth": item.get("warmth") or "",
        "alive": item.get("alive", True),
        "note": item.get("note") or "",
        "last_seen": int(item.get("last_seen") or chapter),
        "updated": chapter,
    })
    return "add"


def _merge_inventory(inv: list, item: dict, chapter: int) -> str:
    name = (item.get("name") or "").strip()
    if not name:
        return "skip"
    delta = item.get("delta")
    hit = next((x for x in inv if x.get("name") == name), None)
    if hit:
        if isinstance(delta, int) and not isinstance(delta, bool):
            hit["qty"] = int(hit.get("qty", 1)) + delta
            hit["held"] = hit["qty"] > 0
        if item.get("note"):
            hit["note"] = item["note"]
        hit["updated"] = chapter
        return "update"
    qty = delta if isinstance(delta, int) and not isinstance(delta, bool) else 1
    inv.append({"name": name, "qty": qty, "held": qty > 0,
                "note": item.get("note") or "", "updated": chapter})
    return "add"


def apply_events(state: dict, bible: dict, chapters: dict, ev: dict, chapter: int) -> dict:
    rep = {"chapter": chapter, "added": [], "updated": [], "resolved": [],
           "abandoned": [], "warn": []}

    tl = ev.get("timeline") or {}
    if tl:
        state.setdefault("timeline", {}).update({k: v for k, v in tl.items() if v})
        state["timeline"]["chapter"] = chapter

    pt = state.setdefault("protagonist", {})
    for k, v in (ev.get("protagonist") or {}).items():
        if k == "known_add":
            known = pt.setdefault("known", [])
            for item in (v or []):
                if item and item not in known:
                    known.append(item)
        elif v not in (None, ""):
            pt[k] = v
    pt["updated"] = chapter

    for item in ev.get("items") or []:
        act = _merge_inventory(state.setdefault("inventory", []), item, chapter)
        (rep["added"] if act == "add" else rep["updated"]).append(f"物品·{item.get('name')}")

    npcs = state.setdefault("npcs", [])
    for item in ev.get("npcs") or []:
        act = _upsert_npc(npcs, item, chapter)
        if act == "add":
            rep["added"].append(f"NPC·{item.get('name')}")
        elif act == "update":
            rep["updated"].append(f"NPC·{item.get('name')}")

    for c in ev.get("characters_new") or []:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        chars = bible.setdefault("characters", [])
        hit = next((x for x in chars if x.get("name") == name), None)
        if hit:
            for k in ("role", "identity", "personality", "speech_style", "status"):
                if c.get(k):
                    hit[k] = c[k]
            hit["updated"] = chapter
            rep["updated"].append(f"角色·{name}")
        else:
            chars.append({
                "name": name,
                "role": c.get("role") or "配角",
                "identity": c.get("identity") or "",
                "personality": c.get("personality") or "",
                "speech_style": c.get("speech_style") or "",
                "status": c.get("status") or "",
                "first_chapter": chapter,
                "updated": chapter,
            })
            rep["added"].append(f"角色·{name}")
        if not any(x.get("name") == name for x in npcs):
            _upsert_npc(npcs, {"name": name, "relation": c.get("role") or "配角",
                               "note": c.get("identity") or ""}, chapter)

    threads = state.setdefault("threads", [])
    bible_events = bible.setdefault("events", [])

    for t in ev.get("threads_new") or []:
        name = (t.get("name") or "").strip()
        if not name:
            continue
        dup = next((x for x in threads if x.get("name") == name
                    and x.get("status") in ("open", "dormant")), None)
        if dup:
            rep["warn"].append(f"伏笔重复埋设：{name}（已存在 #{dup.get('id')}，本次记为推进）")
            dup.setdefault("note", "")
            dup["note"] = (dup["note"] + f"｜第{chapter}章再提：" + (t.get("note") or "")).strip("｜")
            dup["updated"] = chapter
            continue
        tid = _next_thread_id(threads)
        threads.append({
            "id": tid,
            "name": name,
            "status": "open",
            "planted": chapter,
            "due": int(t["due"]) if isinstance(t.get("due"), int) else None,
            "note": t.get("note") or "",
            "updated": chapter,
        })
        bible_events.append({"id": tid, "name": name, "planted": chapter,
                             "resolved": False, "note": t.get("note") or ""})
        rep["added"].append(f"伏笔#{tid}·{name}")

    def _find(tid):
        return next((x for x in threads if int(x.get("id") or -1) == int(tid)), None)

    for a in ev.get("threads_advance") or []:
        t = _find(a.get("id"))
        if not t:
            rep["warn"].append(f"推进失败：伏笔 #{a.get('id')} 不存在")
            continue
        if t.get("status") in ("resolved", "abandoned"):
            rep["warn"].append(f"推进跳过：伏笔 #{t['id']} 已收束（{t['status']}）")
            continue
        t["note"] = (t.get("note") or "") + f"｜第{chapter}章推进：" + (a.get("note") or "")
        t["updated"] = chapter
        rep["updated"].append(f"伏笔#{t['id']}·推进")

    for r in ev.get("threads_resolve") or []:
        t = _find(r.get("id"))
        if not t:
            rep["warn"].append(f"兑现失败：伏笔 #{r.get('id')} 不存在")
            continue
        t["status"] = "resolved"
        t["resolved_at"] = chapter
        t["note"] = (t.get("note") or "") + "｜" + (r.get("evidence") or f"第{chapter}章兑现")
        t["updated"] = chapter
        mirror = next((e for e in bible_events if int(e.get("id") or -1) == int(t["id"])), None)
        if mirror:
            mirror["resolved"] = True
            mirror["resolved_at"] = chapter
        rep["resolved"].append(f"伏笔#{t['id']}·{t.get('name')}")

    for b in ev.get("threads_abandon") or []:
        t = _find(b.get("id"))
        if not t:
            rep["warn"].append(f"放弃失败：伏笔 #{b.get('id')} 不存在")
            continue
        t["status"] = "abandoned"
        t["note"] = (t.get("note") or "") + "｜作者拍板放弃：" + (b.get("reason") or "")
        t["abandoned_at"] = chapter
        t["updated"] = chapter
        rep["abandoned"].append(f"伏笔#{t['id']}·{t.get('name')}")

    summary = (ev.get("summary") or "").strip()
    if summary:
        n_sum = H.read_len(summary)
        if not 60 <= n_sum <= 200:
            rep["warn"].append(f"摘要 {n_sum} 字，建议 80–150")
        rows = chapters.get("chapters", [])
        rec = next((c for c in rows if int(c.get("number", -1)) == chapter), None)
        if rec is not None:
            rec["summary"] = summary
            rec["summary_source"] = "writeback"
        else:
            rep["warn"].append(f"chapters.json 缺少第 {chapter} 章，摘要未落")

    state["chapter"] = chapter
    state["updated_at"] = H.now_iso()
    applied = state.setdefault("_applied", [])
    if chapter not in applied:
        applied.append(chapter)
        applied.sort()
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="徽写写回钩子")
    ap.add_argument("slug")
    ap.add_argument("number", type=int)
    ap.add_argument("--root", default=None)
    ap.add_argument("--file", default="")
    ap.add_argument("--force", action="store_true", help="重复写回同一章")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    p = H.project(a.root, a.slug)
    src = Path(a.file) if a.file else H.events_file(p, a.number)
    if not Path(src).exists():
        H.die(f"找不到事件文件：{src}")

    ev = H.jload(src, {}) or {}
    if int(ev.get("chapter") or a.number) != a.number:
        H.die(f"事件文件章号 {ev.get('chapter')} 与参数 {a.number} 不一致")

    state = H.jload(p / "state.json", {}) or {}
    bible = H.jload(p / "bible.json", {}) or {}
    chapters = H.jload(p / "chapters.json", {"chapters": []}) or {"chapters": []}

    if a.number in (state.get("_applied") or []) and not a.force:
        msg = {"ok": True, "skipped": True,
               "reason": f"第 {a.number} 章已写回过（幂等跳过）", "chapter": a.number}
        H.emit_json(msg) if a.json else print(msg["reason"])
        return

    rep = apply_events(state, bible, chapters, ev, a.number)
    rep["ok"] = True
    rep["dry_run"] = bool(a.dry_run)

    if not a.dry_run:
        H.backup(p / "state.json", "bak")
        H.backup(p / "bible.json", "bak")
        H.jsave(p / "state.json", state)
        H.jsave(p / "bible.json", bible)
        H.jsave(p / "chapters.json", chapters)
        sm = ev.get("summary")
        if sm:
            H.wtext(H.memory_file(p, a.number),
                    f"# 第{a.number}章 摘要\n\n{sm.strip()}\n")

    if a.json:
        H.emit_json(rep)
    else:
        print(f"第{a.number}章写回" + ("（试运行）" if a.dry_run else "") + "：")
        for k, label in (("added", "新增"), ("updated", "更新"),
                         ("resolved", "兑现"), ("abandoned", "放弃")):
            if rep[k]:
                print(f"  {label}：{'、'.join(rep[k])}")
        for w in rep["warn"]:
            print(f"  ⚠ {w}")
        if not any(rep[k] for k in ("added", "updated", "resolved", "abandoned")):
            print("  （本章无状态变化）")


if __name__ == "__main__":
    main()
