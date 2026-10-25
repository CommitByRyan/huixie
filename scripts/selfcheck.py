#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""徽写 · 技能包自检

查六件事：
  1. 必需文件齐全（SKILL.md / references / prompts / templates / scripts）
  2. SKILL.md frontmatter 合法，命令与提示词一一对应
  3. SKILL.md 里引用的文件真实存在
  4. 全部 JSON 可解析、模板字段齐全
  5. 全部脚本可编译、可执行 --help
  6. **品牌门禁**：仓库内不得残留旧项目名（见 FORBIDDEN，按字符拼装，自身不触发）

退出码：0 全绿；1 有缺口。
"""

from __future__ import annotations

import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# 旧项目标识按片段拼装，避免自检脚本自身命中
FORBIDDEN = ["灵" + "枢", "ling" + "shu", "子夜" + "屏", "陆" + "昭", "沈素" + "琴"]

REQUIRED = [
    "SKILL.md",
    "README.md",
    "LICENSE",
    "references/schema.md",
    "references/state-model.md",
    "references/budget.md",
    "references/publishing.md",
    "references/ai_flavor.json",
    "prompts/01_outline.md",
    "prompts/02_season.md",
    "prompts/03_beats.md",
    "prompts/04_write.md",
    "prompts/05_critic.md",
    "prompts/06_writeback.md",
    "templates/beats.json",
    "templates/events.json",
    "templates/state.json",
    "templates/chapter.md",
    "scripts/hxlib.py",
    "scripts/budget.py",
    "scripts/huixie.py",
    "scripts/gate.py",
    "scripts/writeback.py",
    "scripts/publish.py",
    "scripts/selfcheck.py",
    "scripts/e2e_check.py",
]

COMMANDS = ["init", "status", "state", "beats", "assemble", "lint", "export"]


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def check_files() -> list:
    return [f"缺文件：{r}" for r in REQUIRED if not (ROOT / r).exists()]


def check_frontmatter() -> list:
    f = ROOT / "SKILL.md"
    if not f.exists():
        return ["缺 SKILL.md"]
    m = re.match(r"^---\n(.*?)\n---", read(f), re.S)
    if not m:
        return ["SKILL.md 缺 frontmatter"]
    fm = m.group(1)
    errs = []
    for key in ("name", "description", "version"):
        if not re.search(rf"^{key}:\s*\S", fm, re.M):
            errs.append(f"frontmatter 缺 {key}")
    nm = re.search(r"^name:\s*(.+)$", fm, re.M)
    if nm and nm.group(1).strip().strip('"') != "huixie":
        errs.append(f"name 应为 huixie，实际 {nm.group(1).strip()}")
    ds = re.search(r"^description:\s*(.+)$", fm, re.M)
    if ds and len(ds.group(1)) < 40:
        errs.append("description 过短（<40 字），触发词可能不足")
    return errs


def check_refs() -> list:
    text = read(ROOT / "SKILL.md")
    errs = []
    for m in re.finditer(r"`((?:references|prompts|templates|scripts)/[A-Za-z0-9_\-./]+)`", text):
        rel = m.group(1)
        if rel.endswith("/"):
            continue
        if not (ROOT / rel).exists():
            errs.append(f"SKILL.md 引用了不存在的文件：{rel}")
    for cmd in COMMANDS:
        if cmd not in text:
            errs.append(f"SKILL.md 未提及命令 {cmd}")
    for i in range(1, 7):
        if not list((ROOT / "prompts").glob(f"0{i}_*.md")):
            errs.append(f"缺第 {i} 阶段提示词")
    return errs


def check_json() -> list:
    errs = []
    for f in sorted(ROOT.rglob("*.json")):
        if "_tmp" in f.parts:
            continue
        try:
            json.loads(read(f))
        except json.JSONDecodeError as e:
            errs.append(f"JSON 解析失败 {f.relative_to(ROOT)}：{e}")
    st = ROOT / "templates" / "state.json"
    if st.exists():
        d = json.loads(read(st))
        for k in ("timeline", "protagonist", "inventory", "npcs", "threads",
                  "must_not", "open_questions"):
            if k not in d:
                errs.append(f"templates/state.json 缺字段 {k}")
    bt = ROOT / "templates" / "beats.json"
    if bt.exists():
        d = json.loads(read(bt))
        for k in ("chapter", "title", "role", "target_words", "beats", "hook"):
            if k not in d:
                errs.append(f"templates/beats.json 缺字段 {k}")
        if not 3 <= len(d.get("beats") or []) <= 4:
            errs.append("templates/beats.json 的示例节拍应为 3–4 个")
    af = ROOT / "references" / "ai_flavor.json"
    if af.exists():
        d = json.loads(read(af))
        if len(d.get("tiers") or []) < 3:
            errs.append("ai_flavor.json 应至少三层")
        for t in d.get("tiers") or []:
            if not t.get("words") or not isinstance(t.get("threshold"), int):
                errs.append(f"ai_flavor 层 {t.get('id')} 缺 words 或 threshold")
    return errs


def check_scripts() -> list:
    errs = []
    for p in sorted(SCRIPTS.glob("*.py")):
        try:
            py_compile.compile(str(p), cfile=str(p.with_suffix(".pyc.tmp")), doraise=True)
            p.with_suffix(".pyc.tmp").unlink(missing_ok=True)
        except py_compile.PyCompileError as e:
            errs.append(f"{p.name} 编译失败：{str(e).splitlines()[-1]}")
    entry = SCRIPTS / "huixie.py"
    if entry.exists():
        r = subprocess.run([sys.executable, str(entry), "--help"],
                           capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if r.returncode != 0:
            errs.append("huixie.py --help 执行失败：" + (r.stderr or "")[-200:])
    return errs


def check_branding() -> list:
    errs = []
    self_path = Path(__file__).resolve()
    exts = {".md", ".py", ".json", ".txt", ".yml", ".yaml", ".cfg", ".toml"}
    for f in sorted(ROOT.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in exts:
            continue
        if "_tmp" in f.parts or ".git" in f.parts:
            continue
        text = read(f)
        for tok in FORBIDDEN:
            if tok in text:
                errs.append(f"旧项目名残留：{f.relative_to(ROOT)} 含「{tok}」")
    _ = self_path
    return errs


def main() -> int:
    groups = [
        ("文件齐全", check_files()),
        ("技能声明", check_frontmatter()),
        ("命令与提示词", check_refs()),
        ("JSON 与模板", check_json()),
        ("脚本可运行", check_scripts()),
        ("品牌门禁", check_branding()),
    ]
    print(f"徽写 V1.0 自检 · {ROOT}")
    total = 0
    for label, errs in groups:
        total += len(errs)
        print(f"  {label:<8}{'✅' if not errs else '❌ ' + str(len(errs)) + ' 项'}")
        for e in errs:
            print(f"    ❌ {e}")
    print(f"\n{'✅ 全部通过' if total == 0 else f'❌ {total} 个缺口'}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
