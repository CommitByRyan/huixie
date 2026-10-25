#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""徽写 · 单章硬闸（结构化输出）

与旧版最大的区别：**判定只认结构与退出码，不认人类可读文本**。
- 正常：输出 JSON（--json）或表格，退出码 0；
- 有硬伤：输出同结构 + 退出码 1；
- 自身异常：输出 {"ok": false, "error": "..."} + 退出码 2。
上层流水线必须把 1 和 2 都当作「未通过」，不允许出现「解析不到就算过」。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import hxlib as H

HERE = Path(__file__).resolve().parent
FLAVOR = HERE.parent / "references" / "ai_flavor.json"


def _ch_ref_pattern():
    return re.compile(r"第\s*[0-9零〇一二三四五六七八九十百千万两]+\s*[章回]")


def _season_ref_pattern():
    return re.compile(r"(?:第\s*[0-9零〇一二三四五六七八九十百千万两]+\s*季)"
                      r"|(?<![这叫那本是])季\s*[0-9零〇一二三四五六七八九十百千万两]+")


def load_flavor() -> dict:
    if FLAVOR.exists():
        return json.loads(FLAVOR.read_text(encoding="utf-8"))
    return {"tiers": [], "echo": {"max_len": 12, "max_repeat": 2},
            "layout": {"para_max": 200, "para_long_ratio": 0.3},
            "ending": {"allowed_tail": ["。", "！", "？", "…"],
                       "forbidden_tail": ["，", "、", "：", "；", "—"]}}


def check(text: str, target: int, novel: dict, min_pct: int, flavor: dict) -> dict:
    text = (text or "").replace("\r\n", "\n").strip()
    fails, warns, checks = [], [], []

    def rec(cid: str, ok: bool, detail: str = "", level: str | None = None):
        lv = level or ("pass" if ok else "fail")
        checks.append({"id": cid, "level": lv, "detail": detail})
        if lv == "fail":
            fails.append(f"{cid}: {detail}")
        elif lv == "warn":
            warns.append(f"{cid}: {detail}")

    if not text:
        rec("empty", False, "正文为空")
        return {"ok": False, "fail": fails, "warn": warns, "checks": checks,
                "words": {"read": 0, "cjk": 0, "target": target, "pct": 0}}

    read_n, cjk_n = H.read_len(text), H.cjk_count(text)
    pct = round(read_n * 100 / target) if target else 100

    if read_n < target * 0.60:
        rec("word_count", False, f"{read_n} 字，仅目标 {target} 的 {pct}%（<60%）")
    elif pct < min_pct:
        rec("word_count", False, f"{read_n} 字，目标 {target}，占 {pct}%（<{min_pct}%）")
    elif pct > 135:
        rec("word_count", True, f"{read_n} 字，占 {pct}%，偏长可能注水", "warn")
    else:
        rec("word_count", True, f"{read_n} 字 / 目标 {target}（{pct}%）")

    m = _ch_ref_pattern().findall(text)
    rec("chapter_ref", not m, "正文出现章节号：" + "、".join(m[:5]) if m else "")

    m = _season_ref_pattern().findall(text)
    rec("season_ref", not m, "正文出现季号：" + "、".join(m[:5]) if m else "")

    bans = [w for w in (novel.get("ban_terms") or []) if w and w in text]
    rec("ban_terms", not bans, "命中本书禁词：" + "、".join(bans) if bans else "")

    total_flavor = 0
    for tier in flavor.get("tiers", []):
        hits = {w: text.count(w) for w in tier.get("words", []) if w in text}
        n_hit = sum(hits.values())
        total_flavor += n_hit
        if not n_hit:
            continue
        thr = int(tier.get("threshold") or 3)
        detail = f"{tier['id']} {tier['name']} {n_hit} 处：" + "、".join(
            f"{k}×{v}" for k, v in list(hits.items())[:6])
        if n_hit >= thr:
            rec(f"ai_flavor_{tier['id']}", False, detail)
        else:
            rec(f"ai_flavor_{tier['id']}", True, detail, "warn")

    echo_cfg = flavor.get("echo") or {}
    max_len = int(echo_cfg.get("max_len") or 12)
    max_rep = int(echo_cfg.get("max_repeat") or 2)
    norm = Counter()
    for s in H.sentences(text):
        k = H.normalize_sentence(s)
        if 0 < len(k) <= max_len:
            norm[k] += 1
    echoes = {k: v for k, v in norm.items() if v > max_rep}
    rec("echo_sentence", not echoes,
        "回声句超限：" + "、".join(f"「{k}」×{v}" for k, v in list(echoes.items())[:4])
        if echoes else "")

    lq, rq = text.count("“"), text.count("”")
    rec("quote_pair", lq == rq, f"中文引号不配对：{lq} 开 / {rq} 闭" if lq != rq else "")

    ascii_q = text.count('"')
    if ascii_q:
        rec("ascii_quote", True, f"残留英文双引号 {ascii_q} 个（应改中文引号）", "warn")

    paras = [b.strip() for b in text.split("\n\n") if b.strip()]
    dup = [k[:18] for k, v in Counter(paras).items() if v > 1]
    rec("dup_block", not dup, "重复段落：" + "；".join(dup[:3]) if dup else "")

    lay = flavor.get("layout") or {}
    para_max = int(lay.get("para_max") or 200)
    ratio_cap = float(lay.get("para_long_ratio") or 0.3)
    longs = [p for p in paras if len(p) > para_max]
    ratio = len(longs) / len(paras) if paras else 0
    if ratio > ratio_cap:
        rec("layout_para", True,
            f"{len(longs)}/{len(paras)} 段超过 {para_max} 字（{ratio:.0%}），移动端偏挤", "warn")

    end = flavor.get("ending") or {}
    tail = text.rstrip()[-1:] if text.rstrip() else ""
    allowed = set(end.get("allowed_tail") or ["。", "！", "？", "…"])
    forbidden = set(end.get("forbidden_tail") or ["，", "、", "：", "；", "—"])
    if tail in forbidden and tail not in allowed:
        rec("ending", False, f"正文末尾停在「{tail}」，句子未完成")
    elif tail not in allowed:
        rec("ending", True, f"正文末尾是「{tail}」，不是常规收尾标点", "warn")

    if re.search(r"^#{1,6}\s", text, re.M):
        rec("markdown_leak", True, "正文含 Markdown 标题符号", "warn")

    if text.count("——\n\n——") or text.rstrip().endswith("——"):
        rec("separator", True, "结尾或中部残留分隔线", "warn")

    return {
        "ok": not fails,
        "chapter_words": {"read": read_n, "cjk": cjk_n, "target": target, "pct": pct},
        "fail": fails,
        "warn": warns,
        "checks": checks,
        "flavor_hits": total_flavor,
    }


def render(res: dict) -> str:
    w = res.get("chapter_words") or res.get("words") or {}
    lines = [f"第{res.get('chapter', '?')}章｜{w.get('read', 0)} 字 / 目标 {w.get('target', 0)}"
             f"（{w.get('pct', 0)}%）"]
    for c in res.get("checks", []):
        if c["level"] == "pass" and not c["detail"]:
            continue
        mark = {"pass": "✅", "warn": "⚠", "fail": "❌"}[c["level"]]
        lines.append(f"  {mark} {c['id']}" + (f"  {c['detail']}" if c["detail"] else ""))
    lines.append("✅ 可交付" if res.get("ok") else f"❌ 不可交付：{len(res.get('fail', []))} 个硬伤")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="徽写单章硬闸")
    ap.add_argument("slug")
    ap.add_argument("number", type=int)
    ap.add_argument("--root", default=None)
    ap.add_argument("--file", default="")
    ap.add_argument("--min-pct", type=int, default=90)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        p = H.project(a.root, a.slug)
        novel = H.jload(p / "novel.json", {}) or {}
        target = int(novel.get("target_words") or H.DEFAULT_TARGET)
        src = Path(a.file) if a.file else H.chapter_file(p, a.number)
        if not Path(src).exists():
            raise FileNotFoundError(f"找不到正文：{src}")
        text = Path(src).read_text(encoding="utf-8", errors="replace")
        res = check(text, target, novel, a.min_pct, load_flavor())
        res["chapter"] = a.number
        res["source"] = str(src)
    except SystemExit:
        raise
    except Exception as e:  # 任何自身异常都必须显式失败，绝不静默放行
        payload = {"ok": False, "error": f"{type(e).__name__}: {e}", "chapter": a.number}
        if a.json:
            H.emit_json(payload)
        else:
            print(f"❌ 闸门异常：{payload['error']}", file=sys.stderr)
        raise SystemExit(2)

    if a.json:
        H.emit_json(res)
    else:
        print(render(res))
    raise SystemExit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
