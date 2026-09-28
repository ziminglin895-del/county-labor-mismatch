# -*- coding: utf-8 -*-
"""Playwright 抓取：纠正县域 slug，过滤异地串岗。"""
import os, sys, json, re, time, random
from datetime import datetime
import pandas as pd
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEDS_PATH = os.path.join(SCRIPT_DIR, "henan_58_seed_urls.json")
RAW_HENAN_DIR = os.path.join(SCRIPT_DIR, "raw_henan")
os.makedirs(RAW_HENAN_DIR, exist_ok=True)

URL_OVERRIDE = {
    "410181": [
        "https://m.58.com/zz/job/?key=%E5%B7%A9%E4%B9%89",
        "https://m.58.com/zz/job/?key=%E5%B7%A9%E4%B9%89%E5%B8%82",
    ],
    "410221": [
        "https://m.58.com/kaifengqixian/zhaopin/",
        "https://m.58.com/qixianqu/zhaopin/",
    ],
    "411525": [
        "https://m.58.com/gushixian/zhaopin/",
    ],
}

REGION_MUST = {
    "410181": ["巩义"],
    "410221": ["杞县"],
    "411525": ["固始"],
}

REGION_BAN = {
    "410181": ["天津", "北京", "晋中"],
    "410221": ["祁县", "晋中", "天津"],
    "411525": ["天津", "北京"],
}


def normalize_edu(text):
    if not text:
        return "未注明"
    t = str(text).strip()
    if any(k in t for k in ["博士"]):
        return "博士"
    if any(k in t for k in ["硕士", "研究生"]):
        return "硕士"
    if any(k in t for k in ["本科", "大学"]):
        return "本科"
    if any(k in t for k in ["大专", "专科"]):
        return "大专"
    if any(k in t for k in ["中专", "中技", "技校", "职高"]):
        return "中专/中技"
    if any(k in t for k in ["高中"]):
        return "高中"
    if any(k in t for k in ["初中", "小学"]):
        return "初中及以下"
    if any(k in t for k in ["不限"]):
        return "学历不限"
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
    if m:
        return int(m.group(1))
    return pd.NA


def parse_html(html, c_item):
    c_name = c_item["county_name"]
    c_code = str(c_item["county_code"])
    pref = c_item["prefecture"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    must = REGION_MUST.get(c_code, [c_name])
    ban = REGION_BAN.get(c_code, [])

    cards = re.findall(r'<a[^>]*class="[^"]*list-item-a[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
    if not cards:
        for tm in re.finditer(r'class="[^"]*info-title[^"]*"[^>]*>', html):
            cards.append(html[max(0, tm.start() - 150): min(len(html), tm.end() + 900)])

    rows = []
    for item in cards:
        title_m = re.search(r'class="[^"]*info-title[^"]*"[^>]*>\s*([^<]+?)\s*<', item)
        if not title_m:
            continue
        title = re.sub(r"\s+", " ", title_m.group(1)).strip()
        sal = ""
        sm = re.search(r'class="[^"]*info-salary[^"]*"[^>]*>\s*([^<]+?)\s*<', item)
        if sm:
            sal = sm.group(1).strip()
        comp = ""
        for cls in ("company", "employer"):
            cm = re.search(rf'class="[^"]*{cls}[^"]*"[^>]*>\s*([^<]+?)\s*<', item)
            if cm and cm.group(1).strip():
                comp = cm.group(1).strip()
                break
        region = ""
        rm = re.search(r'class="[^"]*local_quXianName[^"]*"[^>]*>\s*([^<]+?)\s*<', item)
        if rm:
            region = rm.group(1).strip()

        blob = f"{title} {region} {comp}"
        if any(b in blob for b in ban):
            continue
        if c_code == "410181" and not any(m in region or m in title for m in must):
            continue
        if c_code == "410221" and ("祁县" in region or "祁县" in title):
            continue

        tags = re.findall(r'class="[^"]*info-tag[^"]*"[^>]*>\s*([^<]+?)\s*<', item)
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


def crawl_one(page, c_item):
    code = str(c_item["county_code"])
    urls = URL_OVERRIDE.get(code) or [c_item.get("url_mobile")]
    all_rows = []
    for url in urls:
        try:
            print(f"  goto {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)
            for _ in range(3):
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(800)
            html = page.content()
            title = page.title()
            final = page.url
            print(f"  title={title[:60]} final={final[:80]} len={len(html)}")
            if "验证码" in title or "verifycode" in final:
                print("  antibot, skip")
                continue
            bans = REGION_BAN.get(code, [])
            if any(b in title for b in bans):
                print(f"  page title geo mismatch, skip")
                continue
            must = REGION_MUST.get(code, [])
            if code != "410181" and must and not any(m in title or m in html[:120000] for m in must):
                print("  page missing county keyword, skip")
                continue
            rows = parse_html(html, c_item)
            print(f"  parsed {len(rows)} after geo filter")
            all_rows.extend(rows)
            if len(rows) >= 8:
                break
        except Exception as e:
            print(f"  err {type(e).__name__}: {e}")
    seen = set()
    uniq = []
    for r in all_rows:
        k = (r["招聘岗位"], r["企业名称"], r["工作区域"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return pd.DataFrame(uniq)


def main(codes):
    with open(SEEDS_PATH, encoding="utf-8") as f:
        seeds = json.load(f)
    want = {str(x) for x in codes}
    seeds = [c for c in seeds if str(c["county_code"]) in want]
    print("targets", [(c["county_code"], c["county_name"]) for c in seeds])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="zh-CN",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
        )
        page = ctx.new_page()
        for i, c in enumerate(seeds):
            code = c["county_code"]
            name = c["county_name"]
            out = os.path.join(RAW_HENAN_DIR, f"{code}_{name}.csv")
            print(f"[{i+1}/{len(seeds)}] {code} {name}")
            df = crawl_one(page, c)
            if len(df) == 0:
                print("  EMPTY")
                if os.path.exists(out):
                    os.remove(out)
                    print("  removed stale csv")
                continue
            preferred = ["企业名称", "招聘岗位", "工作城市", "工作区域", "最低月薪", "最高月薪", "职位描述", "学历要求", "招聘人数", "来源平台", "抓取时间"]
            cols = preferred + [x for x in df.columns if x not in preferred]
            df = df[cols]
            df.to_csv(out, index=False, encoding="utf-8-sig")
            print(f"  wrote {len(df)} -> {out}; 招聘人数空值 {int(df['招聘人数'].isna().sum())}/{len(df)}")
            time.sleep(random.uniform(1.5, 3.0))
        browser.close()


if __name__ == "__main__":
    main(["410181", "410221", "411525"])
