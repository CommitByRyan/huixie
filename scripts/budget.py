#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""徽写 · 上下文装配器（预算硬约束 + 分层降级）

设计目标：单章上下文 **不超过 12,000 字符**，且关键信息一条不少。

分层预算：
    静态层  4000   世界观 / 力量体系 / 禁词 / 姓名红线 / 主角卡
    卷季层  1200   本卷主线 / 本季主线 / 季末钩子
    滑窗层  3500   近 3 章摘要 / 上一章末尾 900 字 / 本章要点
    状态层  2500   主角面板 / 物品栏 / 活跃 NPC / 相关伏笔
    节拍层   800   本章节拍表

超出总预算时按 LADDER 逐级降级（伏笔 12→8→5 / NPC 5→3 / 世界观 5→4→3 /
摘要 3→2 / 角色卡 6→3），最后才硬裁。每一步都记录在报告里，不做静默丢弃。
"""

from __future__ import annotations

import re
from pathlib import Path

import hxlib as H

CAP = 12_000

SECTION_BUDGET = {
    "static": 4000,
    "arc": 1200,
    "window": 3500,
    "state": 2500,
    "beats": 800,
}

DEFAULT_OPTS = {
    "world": 5,       # 世界观段数
    "cards": 6,       # 角色卡张数
    "threads": 12,    # 伏笔条数
    "npcs": 5,        # 活跃 NPC 数
    "summaries": 3,   # 近章摘要条数
    "thread_desc": 48,  # 单条伏笔描述上限
}

# 降级阶梯：只有在总量超出 CAP 时才逐级施加
LADDER = [
    {"threads": 8},
    {"npcs": 3},
    {"world": 4},
    {"summaries": 2},
    {"threads": 5},
    {"world": 3},
    {"cards": 3, "thread_desc": 32},
]

TIER_LABEL = ["T0 满配", "T1 伏笔8", "T2 NPC3", "T3 世界观4", "T4 摘要2",
              "T5 伏笔5", "T6 世界观3", "T7 角色3"]


# ---------------------------------------------------------------- 相关度

def thread_score(t: dict, n: int, brief: str) -> int:
    """伏笔相关度评分。返回 -1 表示不进上下文（已收线/已放弃）。"""
    if str(t.get("status", "open")) in ("resolved", "abandoned"):
        return -1
    s = 0
    due = t.get("due")
    if isinstance(due, int):
        if due <= n:
            s += 120                     # 已到期，必须处理
        elif due - n <= 3:
            s += 90
    planted = t.get("planted")
    if isinstance(planted, int) and n - planted <= 20:
        s += 25
    if str(t.get("status")) == "dormant":
        s -= 30
    name = t.get("name") or ""
    if name and name in brief:
        s += 60
    elif name and any(ch in brief for ch in name if H.CJK.match(ch)):
        s += 8
    rel = str(t.get("related_chapters") or "")
    if rel and re.search(rf"(?<!\d){n}(?!\d)", rel):
        s += 40
    return s


def pick_threads(threads: list, n: int, brief: str, k: int) -> list:
    scored = [(thread_score(t, n, brief), t) for t in threads]
    alive = [(sc, t) for sc, t in scored if sc >= 0]
    alive.sort(key=lambda x: (-x[0], -int(x[1].get("id") or 0)))
    return [t for _, t in alive[:k]]


# ---------------------------------------------------------------- 渲染片段

def _label(x, keys=("name", "stage", "level", "title", "境界", "层级")) -> str:
    """把字符串或对象都压成一行文字（力量体系 / 硬规则可能是对象数组）。"""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for k in keys:
            if x.get(k):
                return str(x[k])
        vals = [str(v) for v in x.values() if isinstance(v, (str, int, float)) and str(v).strip()]
        return vals[0] if vals else ""
    return str(x)


def _render_static(novel: dict, bible: dict, brief: str, opts: dict) -> str:
    L = [f"【作品】{novel.get('title') or '—'}｜类型：{novel.get('genre') or '—'}"]
    if novel.get("premise"):
        L.append(f"【作者原话·不可改】{novel['premise']}")
    world = novel.get("world") or []
    if world:
        L.append(f"【世界观·{min(len(world), opts['world'])}段】")
        for w in world[: opts["world"]]:
            L.append(f"- {w.get('label') or '设定'}：{H.clip(w.get('body') or '', 360)}")
    ps = novel.get("power_system") or {}
    if ps and (ps.get("intro") or ps.get("stages")):
        stages = "→".join(_label(x) for x in (ps.get("stages") or []) if _label(x))
        L.append(f"【力量体系·硬锁定】{_label(ps.get('intro')) if isinstance(ps.get('intro'), (dict, list)) else (ps.get('intro') or '')}"
                 + (f"｜层级：{stages}" if stages else ""))
        rules = ps.get("hard_rules") or []
        if rules:
            L.append("  硬规则：" + "；".join(_label(r) for r in rules[:6] if _label(r)))
    if novel.get("ban_terms"):
        L.append("【本书禁词·永不出现】" + "、".join(novel["ban_terms"]))
    if novel.get("name_facts"):
        L.append("【人名字数红线】" + "；".join(f"{k}＝{v}个字"
                                            for k, v in novel["name_facts"].items()))

    chars = bible.get("characters") or []
    prot = [c for c in chars if re.match(r"^(男主|女主|主角|主人公)", c.get("role") or "")]
    others = [c for c in chars
              if c not in prot and (c.get("name") or "") and
              ((c.get("name") in brief) or
               any(ch in brief for ch in (c.get("name") or "") if H.CJK.match(ch)))]
    picked = (prot + others)[: opts["cards"]]
    if picked:
        L.append("【角色卡｜表现用姓名优先】")
        for c in picked:
            bits = [c.get("name") or ""]
            for k, label in (("role", ""), ("identity", ""), ("personality", ""),
                             ("speech_style", "口吻"), ("status", "现状")):
                if c.get(k):
                    bits.append(f"{label}{c[k]}" if label else str(c[k]))
            L.append("- " + "｜".join(str(b) for b in bits if b))
    rels = bible.get("relationships") or []
    if rels:
        L.append("【人物关系】" + "；".join(
            f"{r.get('from')}→{r.get('to')}({r.get('relation_type') or ''})"
            for r in rels[:12]))
    return "\n".join(L)


def _render_arc(novel: dict, outline: dict, seasons: dict, chapters: dict, n: int) -> str:
    ch = next((c for c in chapters.get("chapters", []) if int(c.get("number", -1)) == n), {})
    vol_no = int(ch.get("volume") or 0)
    volume = next((v for v in outline.get("volumes", [])
                   if int(v.get("volume", 0)) == vol_no), None)
    if not volume:  # 章目未标卷号时，按章号区间兜底
        volume = next((v for v in outline.get("volumes", [])
                       if int(v.get("start_number") or 0) <= n <= int(v.get("end_number") or 0)), None)
    season = next((s for s in seasons.get("seasons", [])
                   if int(s.get("start_number") or 0) <= n <= int(s.get("end_number") or 0)), None)
    L = []
    if volume:
        L.append(f"【本卷】第{volume.get('volume')}卷 {volume.get('title') or ''}"
                 f"｜{H.clip(volume.get('summary') or '', 300)}")
    if season:
        L.append(f"【本季】第{season.get('number')}季 {season.get('theme') or ''}"
                 f"（{season.get('start_number')}–{season.get('end_number')}章）")
        if season.get("arc_summary"):
            L.append("  本季主线：" + H.clip(season["arc_summary"], 240))
        if season.get("season_hook"):
            L.append("  季末钩子：" + H.clip(season["season_hook"], 120))
    return "\n".join(L)


def _render_window(p: Path, chapters: dict, n: int, opts: dict) -> str:
    rows = sorted(chapters.get("chapters", []), key=lambda c: int(c.get("number", 0)))
    prev_rows = [c for c in rows if int(c.get("number", 0)) < n and (c.get("summary") or "")]
    L = []
    if prev_rows:
        L.append(f"【近章摘要·最近{min(len(prev_rows), opts['summaries'])}章】")
        for c in prev_rows[-opts["summaries"]:]:
            L.append(f"- 第{c['number']}章：{H.clip(c['summary'], 150)}")
    prev_text = ""
    for c in reversed(rows):
        if int(c.get("number", 0)) < n:
            txt = H.rtext(H.chapter_file(p, int(c["number"])))
            if txt.strip():
                prev_text = txt.strip()
                break
    if prev_text:
        L.append("【上一章结尾·本章开场必须接住】")
        L.append(H.clip(prev_text[-1200:], 900))
    ch = next((c for c in rows if int(c.get("number", -1)) == n), {})
    if ch.get("plot_brief"):
        L.append("【本章要点·硬约束】" + H.clip(ch["plot_brief"], 500))
    elif ch.get("summary"):
        L.append("【本章要点·硬约束】" + H.clip(ch["summary"], 500))
    return "\n".join(L)


def _render_state(state: dict, bible: dict, n: int, brief: str, opts: dict) -> str:
    L = []
    tl = state.get("timeline") or {}
    if tl:
        bits = [str(v) for v in (tl.get("now"), tl.get("time_of_day"), tl.get("weather")) if v]
        if bits:
            L.append("【当前时间线】" + "｜".join(bits))
    pt = state.get("protagonist") or {}
    if pt:
        bits = []
        if pt.get("name"):
            bits.append(f"主角 {pt['name']}")
        for k, label in (("condition", "状态"), ("power", "修为"), ("location", "所在"),
                         ("inventory_summary", "")):
            v = pt.get(k)
            if isinstance(v, str) and v:
                bits.append(f"{label}{v}" if label else v)
            elif isinstance(v, dict) and v:
                bits.append("；".join(f"{a}:{b}" for a, b in v.items()))
        known = pt.get("known") or []
        if known:
            bits.append("已知：" + "、".join(known[:8]))
        if bits:
            L.append("【主角面板】" + "｜".join(bits))
    inv = state.get("inventory") or []
    held = [i for i in inv if i.get("held", True)]
    if held:
        L.append("【物品栏】" + "、".join(
            f"{i.get('name')}×{i.get('qty', 1)}" for i in held[:10]))
    npcs = [x for x in (state.get("npcs") or []) if x.get("alive", True)]
    npcs.sort(key=lambda x: -int(x.get("last_seen") or 0))
    if npcs:
        L.append("【活跃 NPC】" + "；".join(
            f"{x.get('name')}({x.get('relation') or '—'}"
            + (f",{x['warmth']}" if x.get("warmth") else "")
            + (f",第{x['last_seen']}章" if x.get("last_seen") else "") + ")"
            for x in npcs[: opts["npcs"]]))
    threads = pick_threads(state.get("threads") or [], n, brief, opts["threads"])
    if threads:
        L.append(f"【伏笔池·相关{len(threads)}条】⭐＝本章应兑（全量账见 state.json）")
        for t in threads:
            due = t.get("due")
            star = "⭐" if isinstance(due, int) and due <= n else " "
            desc = H.clip(t.get("note") or t.get("description") or "", opts["thread_desc"])
            L.append(f"- {star}#{t.get('id')}〔第{t.get('planted', '?')}章埋"
                     + (f"/第{due}章兑" if due else "") + f"〕{t.get('name')}：{desc}")
    must_not = state.get("must_not") or []
    if must_not:
        L.append("【本章禁区·作者拍板】" + "；".join(must_not[:6]))
    return "\n".join(L)


def _render_beats(beats: dict, target: int) -> str:
    if not beats:
        return ""
    L = [f"【节拍表】第{beats.get('chapter')}章《{beats.get('title') or ''}》"
         f"｜角色定位 {beats.get('role') or '—'}｜目标 {beats.get('target_words') or target} 字"]
    for b in beats.get("beats", []):
        L.append(f"  {b.get('no')}. [{b.get('function')}] 约{b.get('words')}字｜{b.get('event')}"
                 + (f" → 出点：{b['exit']}" if b.get("exit") else ""))
    hook = beats.get("hook") or {}
    if hook:
        L.append(f"【章末钩子·{hook.get('type') or '未定'}】{hook.get('text') or ''}")
    if beats.get("forbidden"):
        L.append("【本章禁止】" + "；".join(beats["forbidden"]))
    return "\n".join(L)


# ---------------------------------------------------------------- 组装

def build(p: Path, n: int, novel: dict, bible: dict, state: dict, outline: dict,
          seasons: dict, chapters: dict, beats: dict, cap: int | None = None) -> tuple[str, dict]:
    cap = int(cap or CAP)
    ch = next((c for c in chapters.get("chapters", []) if int(c.get("number", -1)) == n), {})
    brief = str(ch.get("plot_brief") or ch.get("summary") or "")
    target = int((beats or {}).get("target_words") or novel.get("target_words") or H.DEFAULT_TARGET)

    opts = dict(DEFAULT_OPTS)
    tier = 0
    while True:
        parts = {
            "static": _render_static(novel, bible, brief, opts),
            "arc": _render_arc(novel, outline, seasons, chapters, n),
            "window": _render_window(p, chapters, n, opts),
            "state": _render_state(state, bible, n, brief, opts),
            "beats": _render_beats(beats, target),
        }
        parts = {k: H.clip(v, SECTION_BUDGET[k]) for k, v in parts.items()}
        total = sum(len(v) for v in parts.values())
        if total <= cap or tier >= len(LADDER):
            break
        opts.update(LADDER[tier])
        tier += 1

    head = [
        f"# 徽写上下文 · {novel.get('title') or ''} 第{n}章",
        f"<!-- 预算 {total}/{cap} · 降级档位 {TIER_LABEL[tier]} · 目标 {target} 字 -->",
        "",
    ]
    body = []
    for key, label in (("static", "一、静态设定"), ("arc", "二、卷季脉络"),
                       ("window", "三、滑窗（近况）"), ("state", "四、动态状态"),
                       ("beats", "五、本章节拍")):
        if parts.get(key):
            body.append(f"## {label}")
            body.append(parts[key])
            body.append("")
    text = "\n".join(head + body).rstrip() + "\n"

    report = {
        "chapter": n,
        "total": total,
        "cap": cap,
        "tier": tier,
        "tier_label": TIER_LABEL[tier],
        "budget": SECTION_BUDGET,
        "sections": {k: len(v) for k, v in parts.items()},
        "opts": {k: opts[k] for k in ("world", "cards", "threads", "npcs", "summaries")},
        "over_cap": total > cap,
    }
    return text, report
