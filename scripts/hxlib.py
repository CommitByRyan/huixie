#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""徽写 · 公共库（路径 / 读写 / 字数 / 裁剪 / 编号）

所有脚本共用，不含业务判断。仅依赖标准库。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_ROOT = "徽写作品"
DEFAULT_TARGET = 3400

# 运行环境守卫：低于 3.10 无法解析 `X | None` 之类语法
if sys.version_info < (3, 10):
    print(f"[错误] 徽写需要 Python 3.10+，当前 {sys.version.split()[0]}", file=sys.stderr)
    raise SystemExit(2)

# 控制台编码守卫：Windows 默认 cp936 时，打印中文或 JSON 可能抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
del _stream

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
NUM_WORDS = "零〇一二三四五六七八九十百千万两"

# 版面与文本工具用的标点集合
SENT_END = "。！？…"
CLIP_MARKS = "。！？…；，、）】」』"


# ---------------------------------------------------------------- 输出

def out(msg: str = "") -> None:
    print(msg)


def die(msg: str, code: int = 2) -> "None":
    print(f"[错误] {msg}", file=sys.stderr)
    raise SystemExit(code)


def emit_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- 路径

def root_path(root: str | Path | None) -> Path:
    return Path(root or DEFAULT_ROOT).expanduser().resolve()


def project(root: str | Path | None, slug: str, must_exist: bool = True) -> Path:
    p = root_path(root) / slug
    if must_exist and not (p / "novel.json").exists():
        die(f"找不到作品：{p}（--root 须指向含 <slug> 的目录）")
    return p


def num(n: int) -> str:
    """章号 -> 三位位编号，同时用于 canon / beats / events / dist / ctx 文件名。"""
    return f"{int(n):03d}"


def chapter_file(p: Path, n: int) -> Path:
    return p / "canon" / f"chapter-{num(n)}.txt"


def beats_file(p: Path, n: int) -> Path:
    return p / "beats" / f"beats-{num(n)}.json"


def events_file(p: Path, n: int) -> Path:
    return p / "events" / f"events-{num(n)}.json"


def ctx_file(p: Path, n: int) -> Path:
    return p / "ctx" / f"ctx-{num(n)}.md"


def dist_file(p: Path, n: int) -> Path:
    return p / "dist" / f"chapter-{num(n)}.md"


def memory_file(p: Path, n: int) -> Path:
    return p / "memory" / f"summary-{num(n)}.md"


# ---------------------------------------------------------------- 读写

def jload(path: Path, default=None):
    if not Path(path).exists():
        return default
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"JSON 解析失败 {path}：{e}")


def jsave(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rtext(path: Path, default: str = "") -> str:
    path = Path(path)
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8", errors="replace")


def wtext(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def backup(path: Path, tag: str = "bak") -> Path | None:
    """写前备份，同目录 <name>.<tag>.<时间戳>，保留最近 30 份。"""
    path = Path(path)
    if not path.exists():
        return None
    stamp = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
    dst = path.with_name(f"{path.name}.{tag}-{stamp}")
    dst.write_bytes(path.read_bytes())
    olds = sorted(path.parent.glob(f"{path.name}.{tag}-*"))
    for old in olds[:-30]:
        old.unlink(missing_ok=True)
    return dst


# ---------------------------------------------------------------- 文本

def cjk_count(text: str) -> int:
    return len(CJK.findall(text or ""))


def read_len(text: str) -> int:
    """阅读页口径：去掉所有空白后的字符数。"""
    return len(re.sub(r"\s", "", text or ""))


def clip(text: str, limit: int) -> str:
    """按句读边界裁剪到 limit 字符以内，不截断句子。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    pos = max(cut.rfind(ch) for ch in CLIP_MARKS)
    if pos >= limit * 0.6:
        return cut[: pos + 1] + "…"
    return cut.rstrip() + "…"


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？…])", text or "")
    return [s.strip() for s in parts if s.strip()]


def normalize_sentence(s: str) -> str:
    return re.sub(r"[\s　\"'“”‘’「」『』（）()—…、，。！？：；]", "", s or "")


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def now_iso() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def today() -> str:
    return _dt.date.today().isoformat()


def cn_number(n: int) -> str:
    """1-9999 阿拉伯转中文（章名/季名排版用，非必需）。"""
    digits = "零一二三四五六七八九"
    if n <= 10:
        return "十" if n == 10 else digits[n]
    units = [(1000, "千"), (100, "百"), (10, "十"), (1, "")]
    res, rest = "", n
    for base, unit in units:
        d, rest = divmod(rest, base)
        if d:
            res += digits[d] + unit
        elif res and rest:
            res += "零"
    return res.rstrip("零")
