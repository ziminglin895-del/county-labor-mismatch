# -*- coding: utf-8 -*-
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import grokbot_crawler as gc

TARGET = {"410181", "410221", "411525"}
seeds = [c for c in gc.load_seeds() if str(c.get("county_code")) in TARGET]
print(f"[test] counties={len(seeds)} -> {[c['county_name'] for c in seeds]}")

for idx, c in enumerate(seeds):
    c_code = c["county_code"]
    c_name = c["county_name"]
    out_csv = os.path.join(gc.RAW_HENAN_DIR, f"{c_code}_{c_name}.csv")
    print(f"[{idx+1}/{len(seeds)}] crawling {c_code} {c_name} ...")
    print(f"  urls: {c.get('url_pref_subpath')} | {c.get('url_mobile')}")
    df = gc.crawl_county(c)
    if len(df) > 0:
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"  OK rows={len(df)} -> {out_csv}")
        print(f"  cols={list(df.columns)}")
        print(f"  招聘人数 nulls={int(df['招聘人数'].isna().sum())}/{len(df)}")
    else:
        print(f"  EMPTY/BLOCKED -> no file written for {c_name}")
    import time, random
    time.sleep(random.uniform(0.6, 1.5))

print("[test] done")
print("RAW_HENAN_DIR=", gc.RAW_HENAN_DIR)
if os.path.isdir(gc.RAW_HENAN_DIR):
    for name in sorted(os.listdir(gc.RAW_HENAN_DIR)):
        p = os.path.join(gc.RAW_HENAN_DIR, name)
        print(f"  file {name} size={os.path.getsize(p)}")
