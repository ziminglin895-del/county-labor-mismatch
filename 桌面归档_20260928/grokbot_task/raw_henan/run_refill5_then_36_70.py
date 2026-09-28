# -*- coding: utf-8 -*-
from grokbot_crawler import run_batch

REFILL = ["410181", "410185", "410323", "410324", "410327"]  # 巩义 登封 新安 栾川 宜阳

if __name__ == "__main__":
    print("=== REFILL 5 counties ===", flush=True)
    run_batch(county_codes=REFILL, max_pages=5, target_rows=80, skip_existing=False)
    print("=== BATCH seed 36-70 ===", flush=True)
    run_batch(start=36, end=70, max_pages=5, target_rows=80, skip_existing=False)
