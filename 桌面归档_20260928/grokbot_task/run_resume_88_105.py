# -*- coding: utf-8 -*-
from grokbot_crawler import run_batch
if __name__ == "__main__":
    run_batch(start=88, end=105, max_pages=5, target_rows=80, skip_existing=True)
    print("=== RESUME 88-105 DONE ===", flush=True)
