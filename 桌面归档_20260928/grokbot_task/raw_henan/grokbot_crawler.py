# -*- coding: utf-8 -*-
"""Henan 58.com county job crawler for GrokBot."""
from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.parse
from datetime import datetime

import pandas as pd
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEDS_PATH = os.path.join(SCRIPT_DIR, "henan_58_seed_urls.json")
RAW_HENAN_DIR = os.path.join(SCRIPT_DIR, "raw_henan")
RESOLVE_PATH = os.path.join(SCRIPT_DIR, "url_resolve_35.json")
os.makedirs(RAW_HENAN_DIR, exist_ok=True)

PREF_M = {
    "郑州市": "zz", "开封市": "kf", "洛阳市": "luoyang", "平顶山市": "pds",
    "安阳市": "ay", "鹤壁市": "hb", "新乡市": "xx", "焦作市": "jz",
    "濮阳市": "py", "许昌市": "xc", "漯河市": "lh", "三门峡市": "smx",
    "南阳市": "ny", "商丘市": "sq", "信阳市": "xy", "周口市": "zk", "驻马店市": "zmd",
}

# Bare city slugs that this PC IP (ipCity=tj) remaps to 天津 — do NOT prefer as channels.
GEO_BROKEN_SLUGS = {"gongyi", "dengfeng", "luanchuan"}

SLUG_OVERRIDE = {
    # User-verified; ly* works on this network. gongyi/dengfeng/luanchuan geo-hijack here.
    "410181": ["gongyi"],
    "410185": ["dengfeng"],
    "410323": ["lyxinan", "xinan"],
    "410324": ["luanchuan"],
    "410327": ["lyyiyang", "yiyang"],
    "410221": ["qixianqu", "kaifengqixian"],
    "410222": ["tongxuxian"],
    "410225": ["lankaoxian"],
    "410184": ["xinzheng"],
    "410308": ["mengjinqu"],
    "410307": ["luoyangyanshi"],
    "410326": ["ruyang"],
    "410329": ["yichuan"],
    "410421": ["baofeng"],
    "410481": ["wugang"],
    "410482": ["ruzhou"],
    "410522": ["anyangxian"],
    "410526": ["huaxian"],
    "410724": ["huojia"],
    "410725": ["yuanyang"],
    "410721": ["xinxiangxian", "xinxiang"],
    "411525": ["gushixian"],
}

ZZ_CODES = {"410122", "410181", "410182", "410183", "410184", "410185"}
BAN_GLOBAL = ["天津", "北京", "上海", "晋中", "重庆"]


def load_seeds():
    with open(SEEDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def short_name(name: str) -> str:
    for suf in ("市", "县", "区"):
        if name.endswith(suf) and len(name) > 2:
            return name[:-1]
    return name


def must_tokens(c):
    name = c["county_name"]
    if name == "杞县":
        return ["杞县"]
    if name == "淇县":
        return ["淇县"]
    return [name, short_name(name)]


def ban_tokens(c):
    bans = list(BAN_GLOBAL)
    if c["county_name"] == "杞县":
        bans += ["祁县", "晋中"]
    if c["county_name"] == "淇县":
        bans += ["杞县", "祁县"]
    return bans


def normalize_edu(text):
    if not text:
        return "未注明"
    t = str(text).strip()
    mapping = [
        (["博士"], "博士"), (["硕士", "研究生"], "硕士"), (["本科", "大学"], "本科"),
        (["大专", "专科"], "大专"), (["中专", "中技", "技校", "职高"], "中专/中技"),
        (["高中"], "高中"), (["初中", "小学"], "初中及以下"), (["不限"], "学历不限"),
    ]
    for keys, val in mapping:
        if any(k in t for k in keys):
            return val
    return "未注明"


def parse_salary(text):
    if not text:
        return pd.NA, pd.NA
    t = str(text)
    if "面议" in t:
        return pd.NA, pd.NA
    wan = re.search(r"(\d+(?:\.\d+)?)\s*[-~～到至]\s*(\d+(?:\.\d+)?)\s*万", t)
    if wan:
        return float(wan.group(1)) * 1000, float(wan.group(2)) * 1000
    m = re.findall(r"(\d+(?:\.\d+)?)", t)
    if len(m) >= 2:
        return float(m[0]), float(m[1])
    if len(m) == 1:
        return float(m[0]), float(m[0])
    return pd.NA, pd.NA


def parse_headcount(tag):
    t = str(tag).strip()
    if not t or t in {"若干", "若干人", "不限", "-", "—"}:
        return pd.NA
    m = re.search(r"招\s*(\d+)\s*人", t)
    return int(m.group(1)) if m else pd.NA


def _clean_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()


def _field(block: str, cls: str) -> str:
    m = re.search(
        rf'(?:class="[^"]*{re.escape(cls)}[^"]*"|class=\'[^\']*{re.escape(cls)}[^\']*\')[^>]*>([\s\S]*?)</(?:div|span|a|p)>',
        block,
        re.I,
    )
    if m:
        return _clean_text(m.group(1))
    m = re.search(rf'{re.escape(cls)}[^>]*>([^<]+)', block)
    return _clean_text(m.group(1)) if m else ""


def iter_blocks(html: str):
    cards = re.findall(r'<a[^>]*class="[^"]*list-item-a[^"]*"[^>]*>([\s\S]*?)</a>', html)
    if cards:
        for c in cards:
            yield c
        return
    for tm in re.finditer(r'info-title[^>]*>', html):
        yield html[max(0, tm.start() - 120): min(len(html), tm.end() + 900)]


def parse_html(html, c_item, strict_must=True, page_title=""):
    c_name = c_item["county_name"]
    c_code = str(c_item["county_code"])
    pref = c_item["prefecture"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    must = must_tokens(c_item)
    ban = ban_tokens(c_item)
    page_is_county = any(t in page_title for t in must)

    rows = []
    for item in iter_blocks(html):
        title = _field(item, "info-title")
        if not title:
            continue
        sal = _field(item, "info-salary")
        comp = _field(item, "company") or _field(item, "employer")
        region = _field(item, "local_quXianName")
        blob = f"{title} {region} {comp}"
        if any(b in blob for b in ban):
            continue
        if strict_must:
            if not any(m in blob for m in must):
                continue
        else:
            if not page_is_county and not any(m in blob for m in must):
                continue

        tags = re.findall(r'info-tag[^>]*>([^<]+)', item)
        tags = [_clean_text(t) for t in tags if _clean_text(t)]
        edu = "未注明"
        headcount = pd.NA
        for tag in tags:
            if any(k in tag for k in ["博士", "硕士", "本科", "大专", "专科", "高中", "中专", "初中", "学历", "不限"]):
                edu = normalize_edu(tag)
            hc = parse_headcount(tag)
            if pd.notna(hc):
                headcount = hc

        s_min, s_max = parse_salary(sal)
        desc = f"岗位：{title}"
        if tags:
            desc += "；标签：" + " / ".join(tags)
        if sal:
            desc += f"；薪资：{sal}"

        rows.append({
            "企业名称": comp,
            "招聘岗位": title,
            "工作城市": pref,
            "工作区域": region or c_name,
            "最低月薪": s_min,
            "最高月薪": s_max,
            "职位描述": desc,
            "学历要求": edu,
            "招聘人数": headcount,
            "来源平台": "58同城",
            "抓取时间": now,
            "county_code": c_code,
            "county_name": c_name,
            "prefecture": pref,
            "crawl_period": "2024-2026",
            "source_file": f"58_{c_name}_2024_2026.csv",
        })
    return rows


def channel_slugs(c, resolve_map=None):
    code = str(c["county_code"])
    py = c.get("county_pinyin", "")
    slugs = []
    if code in SLUG_OVERRIDE:
        slugs.extend(SLUG_OVERRIDE[code])
    if resolve_map and code in resolve_map and resolve_map[code].get("best"):
        s = resolve_map[code]["best"]["slug"]
        if s not in slugs:
            slugs.append(s)
    if code not in ZZ_CODES:
        for s in [py, f"{py}xian", f"{py}shi", f"{py}qu"]:
            if s and s not in slugs:
                slugs.append(s)
    # Drop slugs known to geo-hijack on this egress IP
    slugs = [s for s in slugs if s not in GEO_BROKEN_SLUGS]
    return slugs


def build_url_plan(c, resolve_map=None, max_pages=5):
    code = str(c["county_code"])
    pref_m = PREF_M.get(c["prefecture"], "zz")
    key = urllib.parse.quote(short_name(c["county_name"]))
    plan = []

    def add_kw():
        paths = ["job", "yewu", "siji", "zpwuliucangchu", "tech", "shengchankaifa", "meirongjianshen", "canyin"]
        for path in paths:
            for pn in range(1, max_pages + 1):
                if pn == 1:
                    plan.append(("kw", f"https://m.58.com/{pref_m}/{path}/?key={key}", None))
                else:
                    plan.append(("kw", f"https://m.58.com/{pref_m}/{path}/pn{pn}/?key={key}", None))

    def add_channels():
        for slug in channel_slugs(c, resolve_map):
            for pn in range(1, max_pages + 1):
                if pn == 1:
                    plan.append(("ch", f"https://m.58.com/{slug}/zhaopin/", slug))
                else:
                    plan.append(("ch", f"https://m.58.com/{slug}/zhaopin/pn{pn}/", slug))

    # Prefer working channel slugs when available; otherwise keyword search.
    chans = channel_slugs(c, resolve_map)
    if code in ZZ_CODES:
        if chans:
            add_channels()
            add_kw()
        else:
            add_kw()
        py = c.get("county_pinyin", "")
        if py:
            plan.append(("zzpath", f"https://m.58.com/zz/{py}/zhaopin/", py))
    else:
        add_channels()
        add_kw()
    return plan


def fetch_page(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass
    page.wait_for_timeout(700)
    for _ in range(2):
        page.mouse.wheel(0, 2600)
        page.wait_for_timeout(350)
    for _ in range(3):
        try:
            return page.content(), page.title(), page.url
        except Exception:
            page.wait_for_timeout(600)
    return page.content(), page.title(), page.url


def warm_prefecture(page, c_item):
    pref_m = PREF_M.get(c_item["prefecture"], "zz")
    url = f"https://m.58.com/{pref_m}/"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(600)
    except Exception as e:
        print(f"  warm-err {url}: {type(e).__name__}", flush=True)


def crawl_county(page, c_item, resolve_map=None, max_pages=5, target_rows=80):
    warm_prefecture(page, c_item)
    plan = build_url_plan(c_item, resolve_map=resolve_map, max_pages=max_pages)
    all_rows = []
    seen = set()
    dead_slugs = set()

    for kind, url, slug in plan:
        if len(all_rows) >= target_rows:
            break
        if slug and slug in dead_slugs:
            continue
        try:
            html, title, final = fetch_page(page, url)
        except Exception as e:
            print(f"  fetch-err {url}: {type(e).__name__}: {e}", flush=True)
            if slug:
                dead_slugs.add(slug)
            continue

        if "验证码" in title or "verifycode" in final:
            print(f"  skip(antibot) {url}", flush=True)
            if slug:
                dead_slugs.add(slug)
            continue
        if "404" in title:
            print(f"  skip(404) {url}", flush=True)
            if slug and kind in {"ch", "zzpath"}:
                dead_slugs.add(slug)
            continue
        if any(b in title for b in ban_tokens(c_item)):
            print(f"  skip(geo) {title[:40]}", flush=True)
            if slug:
                dead_slugs.add(slug)
            continue

        strict = True
        if kind == "ch" and any(t in title for t in must_tokens(c_item)):
            strict = False
        if kind == "kw":
            strict = True

        rows = parse_html(html, c_item, strict_must=strict, page_title=title)
        kept = 0
        for r in rows:
            k = (r["招聘岗位"], r["企业名称"], r["工作区域"])
            if k in seen:
                continue
            seen.add(k)
            all_rows.append(r)
            kept += 1
        print(f"  +{kept} total={len(all_rows)} {kind} {url}", flush=True)
        time.sleep(random.uniform(0.35, 0.8))

    return pd.DataFrame(all_rows)


def save_df(df, c_item):
    code = c_item["county_code"]
    name = c_item["county_name"]
    out = os.path.join(RAW_HENAN_DIR, f"{code}_{name}.csv")
    if len(df) == 0:
        return out, 0
    preferred = [
        "企业名称", "招聘岗位", "工作城市", "工作区域", "最低月薪", "最高月薪",
        "职位描述", "学历要求", "招聘人数", "来源平台", "抓取时间",
    ]
    cols = preferred + [c for c in df.columns if c not in preferred]
    df[cols].to_csv(out, index=False, encoding="utf-8-sig")
    return out, len(df)


def run_batch(limit=None, county_codes=None, start=None, end=None, max_pages=5, target_rows=80, skip_existing=False):
    seeds = load_seeds()
    if county_codes:
        want = {str(x) for x in county_codes}
        seeds = [c for c in seeds if str(c["county_code"]) in want]
    elif start is not None or end is not None:
        # 1-based inclusive indices into the seed list
        s = (start or 1) - 1
        e = end if end is not None else len(seeds)
        seeds = seeds[s:e]
    elif limit:
        seeds = seeds[:limit]

    resolve_map = {}
    if os.path.exists(RESOLVE_PATH):
        with open(RESOLVE_PATH, encoding="utf-8") as f:
            resolve_map = json.load(f)

    print(f"[GrokBot] counties={len(seeds)} pages<={max_pages} target~{target_rows}", flush=True)
    summary = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
                "Mobile/15E148 Safari/604.1"
            ),
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
        )
        page = ctx.new_page()

        for idx, c in enumerate(seeds):
            code = c["county_code"]
            name = c["county_name"]
            out = os.path.join(RAW_HENAN_DIR, f"{code}_{name}.csv")
            print(f"[{idx+1}/{len(seeds)}] {code} {name} ({c['prefecture']})", flush=True)
            if skip_existing and os.path.exists(out) and os.path.getsize(out) > 1500:
                try:
                    n = len(pd.read_csv(out, encoding="utf-8-sig"))
                except Exception:
                    n = -1
                print(f"  skip existing rows={n}", flush=True)
                summary.append((code, name, n, "skipped"))
                continue

            df = crawl_county(page, c, resolve_map=resolve_map, max_pages=max_pages, target_rows=target_rows)
            path, n = save_df(df, c)
            null_hc = int(df["招聘人数"].isna().sum()) if n else 0
            print(f"  DONE rows={n} null_hc={null_hc}/{n if n else 0} -> {path}", flush=True)
            summary.append((code, name, n, "ok" if n else "empty"))
            time.sleep(random.uniform(0.7, 1.4))

        browser.close()

    print("[GrokBot] Batch completed!", flush=True)
    for code, name, n, st in summary:
        print(f"  {code} {name}: {n} ({st})", flush=True)
    tag = "batch"
    if county_codes:
        tag = "codes_" + "_".join(str(x) for x in county_codes[:5])
        if len(county_codes) > 5:
            tag += f"_n{len(county_codes)}"
    elif start is not None or end is not None:
        tag = f"slice_{start or 1}_{end or 'end'}"
    elif limit:
        tag = f"limit_{limit}"
    summary_path = os.path.join(SCRIPT_DIR, f"{tag}_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump([{"code": a, "name": b, "rows": c, "status": d} for a, b, c, d in summary], f, ensure_ascii=False, indent=2)
    print(f"summary -> {summary_path}", flush=True)
    return summary


if __name__ == "__main__":
    args = sys.argv[1:]
    limit = None
    codes = None
    start = None
    end = None
    pages = 5
    target = 80
    skip = False
    for a in args:
        if a.startswith("--limit="):
            limit = int(a.split("=", 1)[1])
        elif a.startswith("--codes="):
            codes = [x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()]
        elif a.startswith("--start="):
            start = int(a.split("=", 1)[1])
        elif a.startswith("--end="):
            end = int(a.split("=", 1)[1])
        elif a.startswith("--pages="):
            pages = int(a.split("=", 1)[1])
        elif a.startswith("--target="):
            target = int(a.split("=", 1)[1])
        elif a == "--skip-existing":
            skip = True
        elif a == "--all":
            limit = None
            codes = None
            start = None
            end = None
    if codes is None and limit is None and start is None and end is None and "--all" not in args:
        print("Usage: python grokbot_crawler.py --limit=35 | --start=36 --end=70 | --codes=a,b | --all")
        sys.exit(1)
    run_batch(limit=limit, county_codes=codes, start=start, end=end, max_pages=pages, target_rows=target, skip_existing=skip)
