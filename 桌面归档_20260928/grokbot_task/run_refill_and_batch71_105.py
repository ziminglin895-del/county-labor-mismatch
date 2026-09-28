# -*- coding: utf-8 -*-
"""Execute refill for corrected counties (南乐、长垣) and crawl Batch 3 (Counties 71-105)."""
from grokbot_crawler import run_batch

REFILL = [
    "410923",  # 南乐县 (已配置 nanlexian 专属频道)
    "410783",  # 长垣市 (已配置 changyuan 专属频道)
]

if __name__ == "__main__":
    print("=== 1. 补抓已修复专属频道的县 (南乐、长垣) ===", flush=True)
    run_batch(county_codes=REFILL, max_pages=5, target_rows=80, skip_existing=False)
    
    print("=== 2. 批量抓取第 71–105 县 (收官批次 35 县) ===", flush=True)
    run_batch(start=71, end=105, max_pages=5, target_rows=80, skip_existing=False)
    
    print("=== 全部 105 县抓取任务执行完毕！===", flush=True)
