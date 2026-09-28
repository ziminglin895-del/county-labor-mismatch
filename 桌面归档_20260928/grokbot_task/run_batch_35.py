# -*- coding: utf-8 -*-
from grokbot_crawler import run_batch
if __name__ == "__main__":
    run_batch(limit=35, max_pages=5, target_rows=80, skip_existing=False)
