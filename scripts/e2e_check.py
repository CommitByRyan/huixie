#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""徽写 · 端到端测试

在 tests/_tmp/ 下建临时作品，按真实顺序跑一遍：
    init → beats → assemble → gate(好/坏/缺文件) → writeback → publish → lint → export
再验三件容易坏的事：
    A. 预算降级：塞 60 条未收伏笔，装配后总量仍 ≤ 12000，且档位确实降了
    B. 已收伏笔不进上下文
    C. 写回幂等：同一章重复跑不重复记账

退出码：0 全过；1 有失败。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
TMP = ROOT / "tests" / "_tmp"
PY = sys.executable

SLUG = "trial"
CAP = 12000

PATTERNS = [
    "他沿着湿透的青石板往里走了{i}步，才在铺子门口停下，把伞收拢靠在墙边。",
    "柜台上的灯泡忽明忽暗，照见玻璃罐里那排暗红色蜡块，标签还是第{i}年换的。",
    "雨声压住巷子里的动静，只剩檐角的水一下一下砸在铁皮上，第{i}次响得最重。",
    "他把手伸进口袋摸了摸，指尖碰到那把冰凉的钥匙，停到第{i}秒才慢慢退出来。",
    "靠墙的木架上码着第{i}摞纸元宝，边角被潮气泡得发软，一碰就塌下去一块。",
    "巷口传来三轮车碾过水洼的声音，他默数到第{i}声，车轮忽然在半条巷外停住。",
    "他抬头看门楣，木头的颜色比旁边深，像是被什么浸过，第{i}道裂纹从中间劈开。",
    "玻璃后面的女人没有抬头，手里的红纸折到第{i}折，才把剪子轻轻放下。",
    "桌上的茶早就凉透，杯壁挂着一圈褐色的痕，位置比昨天低了第{i}指宽。",
    "他把钥匙放回口袋，指甲在掌心压出第{i}道白印，过了很久才慢慢退下去。",
    "门外的水漫过门槛，顺着砖缝往里渗，在地上洇出第{i}片深色的形状。",
    "她说话的时候眼睛没看他，视线落在柜台后面那面墙上，像在数第{i}块砖。",
    "他数到第{i}声钟响就停了，后面的声音太轻，被雨盖住，分不清从哪里来。",
    "电表的玻璃罩里落了一层灰，指针停在第{i}格的位置，一动不动。",
    "他把伞靠在门边，水顺着伞骨往下滴，在门口积成第{i}小片，绕着砖缝流走。",
    "巷子对面那户人家的灯灭了第{i}次又亮起来，窗帘后面始终没有人影。",
    "她把东西往抽屉里一放，抽屉合上时没有声音，像是垫了第{i}层布。",
    "他退了半步，后腰撞到柜台边缘，疼到第{i}下的时候，人却站住没有再动。",
    "墙上的日历翻到第{i}页，边缘卷起，墨色比前几页淡，像被反复摸过。",
    "雨小了一点，屋里的味道反而更重，混着蜡、潮气，还有第{i}种说不清的腥。",
]


def good_text(min_chars: int = 3400) -> str:
    """生成一篇能过闸门的正文：每句都带序号，避免回声句；段落控制长度。"""
    sents, i = [], 1
    while sum(len(s) for s in sents) < min_chars + 200:
        sents.append(PATTERNS[i % len(PATTERNS)].format(i=i))
        i += 1
    paras = ["".join(sents[j:j + 4]) for j in range(0, len(sents), 4)]
    return "\n\n".join(paras).rstrip()


def bad_text() -> str:
    return ("他嘴角勾起弧度，眼神闪过一丝冷意，注定是个不眠之夜。"
            "空气仿佛凝固，他不禁微微皱眉，宛如神降。"
            "心中一动，一抹杀意涌上来，他淡淡道：")


def run(script: str, *args, expect: int | None = 0) -> subprocess.CompletedProcess:
    cmd = [PY, str(SCRIPTS / script)] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if expect is not None and r.returncode != expect:
        raise AssertionError(
            f"{script} {' '.join(map(str, args))} 退出码 {r.returncode}，期望 {expect}\n"
            f"STDOUT={r.stdout[-800:]}\nSTDERR={r.stderr[-800:]}")
    return r


class Step:
    def __init__(self):
        self.n = 0
        self.fails = []

    def ok(self, msg: str):
        self.n += 1
        print(f"  ✓ {msg}")

    def check(self, cond: bool, msg: str):
        if cond:
            self.ok(msg)
        else:
            self.n += 1
            self.fails.append(msg)
            print(f"  ✗ {msg}")


def main() -> int:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    root = TMP / "works"
    p = root / SLUG
    s = Step()

    print("徽写 V1.0 端到端测试")
    print(f"临时目录：{TMP}")

    print("[1] init")
    run("huixie.py", "init", "雨巷", "--slug", SLUG, "--root", str(root),
        "--genre", "悬疑·都市", "--target", "3400", "--premise", "一盏不熄的灯")
    for d in ("canon", "beats", "events", "dist", "memory", "ctx"):
        s.check((p / d).is_dir(), f"目录 {d}/ 已建")

    novel = json.loads((p / "novel.json").read_text(encoding="utf-8"))
    novel["world"] = [{"label": "时代背景", "body": "梅雨季的江南老巷，湿气常年不散。"},
                      {"label": "地理势力", "body": "丁字巷两端高中间低，一到雨天就积水。"}]
    novel["ban_terms"] = ["系统面板", "穿越"]
    novel["name_facts"] = {"陆鸣": 2}
    (p / "novel.json").write_text(json.dumps(novel, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    s.ok("注入世界观 / 禁词 / 姓名字数")

    print("[2] beats 校验与落盘")
    beats = json.loads((ROOT / "templates" / "beats.json").read_text(encoding="utf-8"))
    beats.update({"chapter": 1, "title": "雨里的灯", "role": "setup",
                  "target_words": 3400, "continuity_from_prev": "开篇"})
    beats["hook"]["text"] = "灯还亮着，电表却停在原地。"
    (p / "drafts").mkdir(exist_ok=True)
    bf = p / "drafts" / "_b1.json"
    bf.write_text(json.dumps(beats, ensure_ascii=False), encoding="utf-8")
    run("huixie.py", "beats", SLUG, "1", "--file", str(bf), "--root", str(root))
    s.check((p / "beats" / "beats-001.json").exists(), "节拍表已落盘")
    chs = json.loads((p / "chapters.json").read_text(encoding="utf-8"))
    s.check(len(chs["chapters"]) == 1, "chapters.json 自动建了第 1 章")

    bad = json.loads(json.dumps(beats))
    bad["beats"] = bad["beats"][:2]
    bad["chapter"] = 2
    bf2 = p / "drafts" / "_b2.json"
    bf2.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    r = run("huixie.py", "beats", SLUG, "2", "--file", str(bf2), "--root", str(root),
            expect=1)
    s.check("3–4" in r.stdout or "节拍" in r.stdout, "两拍节拍表被拦下")

    print("[3] assemble 预算")
    r = run("huixie.py", "assemble", SLUG, "1", "--root", str(root), "--json")
    rep = json.loads(r.stdout)
    s.check(rep["total"] <= CAP, f"上下文 {rep['total']} 字符 ≤ {CAP}")
    s.check((p / "ctx" / "ctx-001.md").exists(), "ctx-001.md 已生成")
    s.check(rep["tier"] == 0, "首章无需降级")

    r = run("huixie.py", "assemble", SLUG, "2", "--root", str(root), expect=2)
    s.check("节拍表" in (r.stderr or ""), "缺节拍表时拒绝装配（防无细纲生成）")

    print("[4] gate 三种结局")
    txt = p / "drafts" / "_good.txt"
    txt.write_text(good_text(), encoding="utf-8")
    r = run("gate.py", SLUG, "1", "--file", str(txt), "--root", str(root), "--json")
    g = json.loads(r.stdout)
    s.check(g["ok"] and r.returncode == 0, f"好稿通过（{g['chapter_words']['read']} 字）")
    (p / "canon").mkdir(exist_ok=True)
    (p / "canon" / "chapter-001.txt").write_text(good_text(), encoding="utf-8")

    badf = p / "drafts" / "_bad.txt"
    badf.write_text(bad_text(), encoding="utf-8")
    r = run("gate.py", SLUG, "1", "--file", str(badf), "--root", str(root), "--json",
            expect=1)
    gb = json.loads(r.stdout)
    s.check(gb["ok"] is False and gb["fail"], "坏稿被拦（套话 + 字数不足）")
    s.check(any("ai_flavor" in f for f in gb["fail"]), "AI 味命中被判失败")

    r = run("gate.py", SLUG, "99", "--root", str(root), "--json", expect=2)
    s.check('"ok": false' in r.stdout and r.returncode == 2,
            "缺文件时退出码 2 且 ok=false（不会静默放行）")

    print("[5] writeback 增量与幂等")
    ev = json.loads((ROOT / "templates" / "events.json").read_text(encoding="utf-8"))
    ev.update({"chapter": 1, "summary":
               "雨夜，陆鸣在香烛铺守着一盏不该亮的灯。他从柜台底下摸到一把铜钥匙，"
               "试开后门竟对上了锁。电表停在原地，灯却整夜没灭。"})
    ev["threads_new"] = [{"name": "电表不走电", "due": 21, "note": "灯亮整夜，度数不动"}]
    ev["threads_advance"] = []
    ev["threads_resolve"] = []
    ev["threads_abandon"] = []
    ef = p / "drafts" / "_e1.json"
    ef.write_text(json.dumps(ev, ensure_ascii=False), encoding="utf-8")
    run("writeback.py", SLUG, "1", "--file", str(ef), "--root", str(root), "--json")
    st = json.loads((p / "state.json").read_text(encoding="utf-8"))
    s.check(st["chapter"] == 1, "state.chapter 推进到 1")
    s.check(any(t["name"] == "电表不走电" for t in st["threads"]), "新伏笔入库")
    s.check(any(i["name"] == "铜钥匙" for i in st["inventory"]), "物品入库")
    s.check(any(n["name"] == "周砚" for n in st["npcs"]), "NPC 入库")
    s.check(bool(st["protagonist"].get("known")), "主角已知信息追加")

    r = run("writeback.py", SLUG, "1", "--file", str(ef), "--root", str(root), "--json")
    again = json.loads(r.stdout)
    s.check(again.get("skipped") is True, "重复写回幂等跳过")
    s.check(len(json.loads((p / "state.json").read_text(encoding="utf-8"))["threads"]) == 1,
            "伏笔没被重复记账")

    print("[6] publish 发布件")
    run("publish.py", SLUG, "1", "--root", str(root), "--note", "求收藏。")
    dt = p / "dist" / "chapter-001.txt"
    dm = p / "dist" / "chapter-001.md"
    s.check(dt.exists() and dm.exists(), "dist txt 与 md 均已生成")
    pure = dt.read_text(encoding="utf-8")
    s.check("作者有话说" not in pure and "第1章" not in pure, "纯净 txt 不含标题与附言")
    md = dm.read_text(encoding="utf-8")
    s.check(md.startswith("---") and "作者有话说" in md, "md 含 front matter 与附言")
    s.check("checksum:" in md, "md 带 checksum")
    man = json.loads((p / "dist" / "manifest.json").read_text(encoding="utf-8"))
    s.check(man["count"] == 1 and man["chapters"][0]["words"] > 0, "manifest 记录 1 章")

    print("[7] lint 与 export")
    r = run("huixie.py", "lint", SLUG, "--root", str(root), "--json")
    li = json.loads(r.stdout)
    s.check(li["ok"] and not li["err"], f"体检通过（{li['written']} 章正文）")
    run("huixie.py", "export", SLUG, "--root", str(root), "--format", "both")
    s.check(len(list((p / "exports").glob("*.txt"))) == 1, "整本 txt 导出成功")
    s.check(len(list((p / "exports").glob("*.md"))) == 1, "整本 md 导出成功")

    print("[8] 预算降级与已收伏笔过滤")
    st = json.loads((p / "state.json").read_text(encoding="utf-8"))
    for k in range(60):
        st["threads"].append({
            "id": 100 + k, "name": f"旧线{k}号", "status": "open", "planted": 1,
            "due": 200, "note": "这是一条早期埋下的长描述，" * 6, "updated": 1})
    st["threads"].append({"id": 999, "name": "已兑现的线", "status": "resolved",
                          "planted": 1, "due": 5, "note": "不该进上下文",
                          "resolved_at": 1, "updated": 1})
    (p / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    r = run("huixie.py", "assemble", SLUG, "2", "--root", str(root), "--json",
            "--allow-no-beats", "--cap", "2000")
    rep = json.loads(r.stdout)
    s.check(rep["total"] <= 2000, f"压到 2000 上限后仍为 {rep['total']} 字符")
    s.check(rep["tier"] > 0, f"确实触发了降级（档位 {rep['tier_label']}）")
    s.check(rep["over_cap"] is False, "降级后未超上限")
    ctx = (p / "ctx" / "ctx-002.md").read_text(encoding="utf-8")
    s.check("已兑现的线" not in ctx, "已 resolved 的伏笔没进上下文")
    s.check(rep["opts"]["threads"] < 12, f"伏笔条数已降为 {rep['opts']['threads']}")

    print("[9] 大书预算（默认 12000）")
    st["threads"] = [t for t in st["threads"] if t["status"] == "open"][:200]
    novel["world"] = [{"label": f"模块{i}", "body": "湿气不散的江南老巷，" * 12}
                      for i in range(8)]
    (p / "novel.json").write_text(json.dumps(novel, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    (p / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    r = run("huixie.py", "assemble", SLUG, "2", "--root", str(root), "--json",
            "--allow-no-beats")
    rep = json.loads(r.stdout)
    s.check(rep["total"] <= CAP, f"默认上限下总量 {rep['total']} ≤ {CAP}")
    s.check(rep["sections"]["static"] <= rep["budget"]["static"], "静态层未越自己那格预算")
    s.check(rep["sections"]["state"] <= rep["budget"]["state"], "状态层未越自己那格预算")

    print(f"\n{'✅ 端到端全部通过' if not s.fails else f'❌ {len(s.fails)} 项失败'}"
          f"（{s.n} 项断言）")
    if s.fails:
        for f in s.fails:
            print(f"  ✗ {f}")
        return 1
    shutil.rmtree(TMP, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
