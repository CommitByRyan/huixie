#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""徽写 · 发布件生成（dist）

一章产出三个文件，职责分离：
    dist/chapter-NNN.txt     纯净正文（可配置分隔符版本，直接对接上传工具）
    dist/chapter-NNN.md      front matter + 正文 + 作者有话说（人读 / 归档）
    dist/manifest.json       全部元数据、字数、校验和、发布状态

正文与标题、作者有话说严格分离：进 .txt 的只有正文，标题与附言只存在元数据与 .md 里。
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import hxlib as H

HEAD_RE = re.compile(r"^\s*(?:#{1,3}\s*)?第\s*[0-9零〇一二三四五六七八九十百千万两]+\s*[章回]\s*[·_\-—\s]*(.*)$")


def strip_head(text: str) -> tuple[str, str]:
    """剥离首行章节标题，返回 (title, body)。"""
    lines = text.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        m = HEAD_RE.match(line)
        if m:
            return m.group(1).strip(), "\n".join(lines[i + 1:]).strip()
        break
    return "", text.replace("\r\n", "\n").strip()


def front_matter(meta: dict) -> str:
    keys = ["book", "chapter", "title", "volume", "season", "role", "words", "cjk",
            "hook", "checksum", "generated", "status", "platform_id", "pushed_at"]
    lines = ["---"]
    for k in keys:
        v = meta.get(k)
        if v is None:
            v = "null" if k in ("volume", "season", "platform_id", "pushed_at") else ""
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def build_one(p: Path, n: int, novel: dict, outline: dict, seasons: dict,
              chapters: dict, beats: dict, text: str,
              title: str = "", note: str = "", status: str = "draft",
              pure_sep: str = "") -> dict:
    body = text.replace("\r\n", "\n").strip()
    head_title, stripped = strip_head(body)
    body = stripped or body
    title = title or head_title or ""

    ch = next((c for c in chapters.get("chapters", []) if int(c.get("number", -1)) == n), {})
    if not title:
        title = ch.get("title") or ""
    if not title:
        H.die(f"第{n}章没有标题：请用 --title 指定，或在 chapters.json 里补 title")

    rn, cn = H.read_len(body), H.cjk_count(body)
    volume = season_no = None
    if ch.get("volume"):
        volume = ch.get("volume")
    else:
        vol = next((v for v in outline.get("volumes", [])
                    if int(v.get("start_number") or 0) <= n <= int(v.get("end_number") or 0)), None)
        volume = (vol or {}).get("volume")
    sea = next((s for s in seasons.get("seasons", [])
                if int(s.get("start_number") or 0) <= n <= int(s.get("end_number") or 0)), None)
    season_no = (sea or {}).get("number")

    meta = {
        "book": novel.get("title") or p.name,
        "chapter": n,
        "title": title,
        "volume": volume,
        "season": season_no,
        "role": ch.get("role") or (beats or {}).get("role") or "",
        "words": rn,
        "cjk": cn,
        "hook": ((beats or {}).get("hook") or {}).get("type") or "",
        "checksum": H.sha256_text(body)[:16],
        "generated": H.today(),
        "status": status,
        "platform_id": None,
        "pushed_at": None,
    }

    txt = H.dist_file(p, n).with_suffix(".txt")
    H.wtext(txt, body + "\n")

    md = [front_matter(meta), "", f"# 第{n}章 {title}", "", body, ""]
    if note.strip():
        md += ["<!-- 以下不属于正文，请勿带入平台 -->", "", "## 作者有话说", "", note.strip(), ""]
    H.wtext(H.dist_file(p, n), "\n".join(md))

    if pure_sep:
        H.wtext(p / "dist" / f"chapter-{H.num(n)}.sep.txt",
                f"{pure_sep}\n{body}\n{pure_sep}\n")

    ch["publish"] = ch.get("publish") or {}
    ch["publish"].update({"status": status, "words": rn, "checksum": meta["checksum"]})
    return meta


def rebuild_manifest(p: Path, novel: dict) -> dict:
    entries = []
    for f in sorted((p / "dist").glob("chapter-*.md")):
        m = re.match(r"chapter-(\d+)\.md$", f.name)
        if not m:
            continue
        head = H.rtext(f).split("---")
        fm = head[1] if len(head) > 2 else ""
        row = {"chapter": int(m.group(1)), "file": f"chapter-{H.num(int(m.group(1)))}.txt",
               "md": f.name}
        for line in fm.strip().splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v in ("", "null"):
                row[k] = None
            elif k in ("chapter", "volume", "season", "words", "cjk"):
                try:
                    row[k] = int(v)
                except ValueError:
                    row[k] = v
            else:
                row[k] = v
        entries.append(row)
    entries.sort(key=lambda x: x["chapter"])
    man = {
        "book": novel.get("title") or p.name,
        "schema_version": H.SCHEMA_VERSION,
        "generated_at": H.now_iso(),
        "count": len(entries),
        "total_words": sum(int(e.get("words") or 0) for e in entries),
        "chapters": entries,
    }
    H.jsave(p / "dist" / "manifest.json", man)
    return man


def main(argv=None):
    ap = argparse.ArgumentParser(description="徽写发布件生成")
    ap.add_argument("slug")
    ap.add_argument("number", type=int, nargs="?")
    ap.add_argument("--root", default=None)
    ap.add_argument("--file", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--note", default="", help="作者有话说")
    ap.add_argument("--status", default="draft", choices=["draft", "ready", "published"])
    ap.add_argument("--sep", default="", help="在纯净 txt 首尾插入的分隔线，如 ***")
    ap.add_argument("--all", action="store_true", help="按 canon 全量重建 dist")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    p = H.project(a.root, a.slug)
    novel = H.jload(p / "novel.json", {}) or {}
    outline = H.jload(p / "outline.json", {}) or {}
    seasons = H.jload(p / "seasons.json", {}) or {}
    chapters = H.jload(p / "chapters.json", {"chapters": []}) or {"chapters": []}

    built = []
    if a.all:
        for f in sorted((p / "canon").glob("chapter-*.txt")):
            n = int(re.search(r"(\d+)", f.stem).group(1))
            beats = H.jload(H.beats_file(p, n), {}) or {}
            built.append(build_one(p, n, novel, outline, seasons, chapters, beats,
                                   f.read_text(encoding="utf-8"), status=a.status,
                                   pure_sep=a.sep))
    else:
        if not a.number:
            H.die("需要章号，或使用 --all")
        src = Path(a.file) if a.file else H.chapter_file(p, a.number)
        if not Path(src).exists():
            H.die(f"找不到正文：{src}")
        beats = H.jload(H.beats_file(p, a.number), {}) or {}
        built.append(build_one(p, a.number, novel, outline, seasons, chapters, beats,
                               Path(src).read_text(encoding="utf-8"),
                               title=a.title, note=a.note, status=a.status, pure_sep=a.sep))

    H.backup(p / "chapters.json", "bak")
    H.jsave(p / "chapters.json", chapters)
    man = rebuild_manifest(p, novel)

    payload = {"ok": True, "built": built, "manifest": {"count": man["count"],
                                                        "total_words": man["total_words"]}}
    if a.json:
        H.emit_json(payload)
    else:
        for m in built:
            print(f"第{m['chapter']}章《{m['title']}》→ dist  {m['words']} 字"
                  f"  校验 {m['checksum']}")
        print(f"manifest：{man['count']} 章 / {man['total_words']} 字")


if __name__ == "__main__":
    main()
