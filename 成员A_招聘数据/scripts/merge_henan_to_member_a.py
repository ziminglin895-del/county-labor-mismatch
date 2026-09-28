# -*- coding: utf-8 -*-
"""
河南招聘数据清洗、0/1编码与三省总表合并脚本
规范依据: D:\\资料\\经管学业\\县域劳动力错配研究\\AGENTS.md
"""
import os
import sys
import glob
import re
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

BASE_A = r"D:\资料\经管学业\县域劳动力错配研究\成员A_招聘数据"
DATA_DIR = os.path.join(BASE_A, "data")
RAW_HENAN = os.path.join(DATA_DIR, "raw_henan")
CROSSWALK_PATH = r"D:\资料\经管学业\县域劳动力错配研究\成员B_宏观学历\data\county_codes_crosswalk.csv"

# 学历归一化与 0/1 规则 (严格遵循 AGENTS.md)
EDU_CANON = {
    "初中及以下": "junior_or_lower",
    "高中": "high_school",
    "中专/中技": "vocational_secondary",
    "大专": "college",
    "本科": "bachelor",
    "硕士": "master",
    "博士": "doctorate",
    "学历不限": "unlimited",
    "不限": "unlimited",
    "未注明": "unspecified",
}
EDU_ORDER = {
    "junior_or_lower": 1,
    "high_school": 2,
    "vocational_secondary": 2,
    "college": 3,
    "bachelor": 4,
    "master": 5,
    "doctorate": 6,
}
THRESHOLD_SETS = {
    "req_dz": {"college", "bachelor", "master", "doctorate"},
    "req_bk": {"bachelor", "master", "doctorate"},
    "req_ss": {"master", "doctorate"},
    "req_bs": {"doctorate"},
}


def main():
    csv_files = glob.glob(os.path.join(RAW_HENAN, "*.csv"))
    assert len(csv_files) > 0, "No raw Henan CSV files found!"

    frames = [pd.read_csv(f, dtype={"county_code": str}) for f in sorted(csv_files)]
    raw_henan = pd.concat(frames, ignore_index=True)
    raw_henan.insert(0, "ad_id", range(1, len(raw_henan) + 1))

    # 1. 导出河南合并原始表
    p_raw = os.path.join(DATA_DIR, "01_raw_henan_combined.csv")
    raw_henan.to_csv(p_raw, index=False, encoding="utf-8-sig")

    # 2. 匹配 2020 普查代码与跨期字典
    df_cw = pd.read_csv(CROSSWALK_PATH, dtype=str)
    cw_map = dict(zip(df_cw["county_code"], df_cw["county_code_2020census"]))
    cw_name_map = dict(zip(df_cw["county_code"], df_cw["name_2020census"]))

    df = raw_henan.copy()
    df["county_code_2020census"] = df["county_code"].map(cw_map)
    df["name_2020census"] = df["county_code"].map(cw_name_map)
    df["province"] = "河南"

    # 3. 学历归一化与 0/1 编码
    def canon_edu(s):
        if pd.isna(s) or str(s).strip() == "":
            return "unspecified"
        return EDU_CANON.get(str(s).strip(), "unspecified")

    df["edu_canon"] = df["学历要求"].map(canon_edu)
    df["edu_unspecified"] = (df["edu_canon"] == "unspecified").astype(int)
    df["edu_unlimited"] = (df["edu_canon"] == "unlimited").astype(int)
    df["edu_other"] = 0

    for name, members in THRESHOLD_SETS.items():
        df[name] = df["edu_canon"].isin(members).astype(int)

    df["edu_min_level"] = df["edu_canon"].map(EDU_ORDER)
    df["edu_stated"] = df["edu_canon"].isin(EDU_ORDER.keys()).astype(int)

    # 4. 招聘人数解析（缺失不默认填1）
    df["headcount"] = pd.to_numeric(df["招聘人数"], errors="coerce").astype("Float64")
    df["headcount_missing"] = df["headcount"].isna().astype(int)

    df["salary_min"] = pd.to_numeric(df["最低月薪"], errors="coerce")
    df["salary_max"] = pd.to_numeric(df["最高月薪"], errors="coerce")
    df["salary_mean"] = (df["salary_min"] + df["salary_max"]) / 2

    # 5. 去重 (企业 + 岗位 + 区域 + 薪资)
    key = ["企业名称", "招聘岗位", "county_code", "salary_min", "salary_max"]
    dup_mask = df.duplicated(subset=key, keep="first")
    df_clean = df[~dup_mask].copy()

    p_clean = os.path.join(DATA_DIR, "02_cleaned_henan.csv")
    df_clean.to_csv(p_clean, index=False, encoding="utf-8-sig")

    # 6. 生成河南县级汇总表 (03_county_edu_summary_henan.csv)
    rows = []
    for code, g in df_clean.groupby("county_code", sort=True):
        n = len(g)
        n_stated = int(g["edu_stated"].sum())
        r = {
            "county_code": code,
            "county_name": g["county_name"].iloc[0],
            "county_code_2020census": g["county_code_2020census"].iloc[0],
            "name_2020census": g["name_2020census"].iloc[0],
            "province": "河南",
            "prefecture": g["prefecture"].iloc[0],
            "n_ads": n,
            "n_edu_stated": n_stated,
            "n_edu_unlimited": int(g["edu_unlimited"].sum()),
            "n_edu_unspecified": int(g["edu_unspecified"].sum()),
            "n_edu_other": 0,
            "share_req_dz_of_all": round(g["req_dz"].sum() / n, 6),
            "share_req_bk_of_all": round(g["req_bk"].sum() / n, 6),
            "share_req_ss_of_all": round(g["req_ss"].sum() / n, 6),
            "share_req_bs_of_all": round(g["req_bs"].sum() / n, 6),
            "share_req_dz_of_stated": round(g["req_dz"].sum() / n_stated, 6) if n_stated else pd.NA,
            "share_req_bk_of_stated": round(g["req_bk"].sum() / n_stated, 6) if n_stated else pd.NA,
            "share_req_ss_of_stated": round(g["req_ss"].sum() / n_stated, 6) if n_stated else pd.NA,
            "share_unlimited": round(g["edu_unlimited"].sum() / n, 6),
            "share_unspecified": round(g["edu_unspecified"].sum() / n, 6),
            "headcount_missing_rate": round(g["headcount_missing"].mean(), 4),
            "n_headcount_reported_sum": float(g["headcount"].sum(skipna=True)),
        }
        rows.append(r)

    df_henan_sum = pd.DataFrame(rows)
    p_sum_henan = os.path.join(DATA_DIR, "03_county_edu_summary_henan.csv")
    df_henan_sum.to_csv(p_sum_henan, index=False, encoding="utf-8-sig")

    # 7. 合并 闽、赣、豫 三省统一大宽表 (232个县级单位)
    p_orig_sum = os.path.join(DATA_DIR, "03_county_edu_summary.csv")
    df_orig_sum = pd.read_csv(p_orig_sum, dtype={"county_code": str, "county_code_2020census": str})
    
    df_unified = pd.concat([df_orig_sum, df_henan_sum], ignore_index=True)
    p_unified = os.path.join(DATA_DIR, "03_county_edu_summary_unified.csv")
    df_unified.to_csv(p_unified, index=False, encoding="utf-8-sig")

    print(f"Henan processing complete:")
    print(f"  Raw: {p_raw} ({len(raw_henan)} rows)")
    print(f"  Cleaned: {p_clean} ({len(df_clean)} rows, deduplicated {dup_mask.sum()} rows)")
    print(f"  Henan County Summary: {p_sum_henan} ({len(df_henan_sum)} counties)")
    print(f"  Unified Multi-Province Summary (闽+赣+豫): {p_unified} ({len(df_unified)} counties total!)")


if __name__ == "__main__":
    main()
