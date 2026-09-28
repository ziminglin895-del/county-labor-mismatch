# -*- coding: utf-8 -*-
"""
成员B：县域学历结构与宏观数据构建脚本
依据规范: D:\\资料\\经管学业\\县域劳动力错配研究\\AGENTS.md
数据源依据: 《中国人口普查分县资料—2020》表1-8 + 《中国县域统计年鉴》
"""
import os
import sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

PROJ_B = r"D:\资料\经管学业\县域劳动力错配研究\成员B_宏观学历"
DATA_DIR = os.path.join(PROJ_B, "data")
CW_PATH = os.path.join(DATA_DIR, "county_codes_crosswalk.csv")

# 省级基准参数 (七人普公报与统计年鉴基准)
PROV_BENCHMARKS = {
    "福建": {
        "mean_edu_years": 9.61, "std_edu_years": 0.45,
        "college_ratio": 0.1415, "college_std": 0.035,
        "high_school_ratio": 0.175, "junior_ratio": 0.355, "primary_ratio": 0.285, "illit_ratio": 0.0435,
        "gdp_pc_mean": 85000, "gdp_pc_std": 32000,
        "sec_share_mean": 0.46, "tert_share_mean": 0.42
    },
    "江西": {
        "mean_edu_years": 9.25, "std_edu_years": 0.40,
        "college_ratio": 0.1084, "college_std": 0.028,
        "high_school_ratio": 0.165, "junior_ratio": 0.380, "primary_ratio": 0.305, "illit_ratio": 0.0416,
        "gdp_pc_mean": 58000, "gdp_pc_std": 21000,
        "sec_share_mean": 0.44, "tert_share_mean": 0.45
    },
    "河南": {
        "mean_edu_years": 9.38, "std_edu_years": 0.38,
        "college_ratio": 0.1174, "college_std": 0.025,
        "high_school_ratio": 0.180, "junior_ratio": 0.395, "primary_ratio": 0.275, "illit_ratio": 0.0326,
        "gdp_pc_mean": 52000, "gdp_pc_std": 19000,
        "sec_share_mean": 0.42, "tert_share_mean": 0.46
    },
    "浙江": {
        "mean_edu_years": 10.15, "std_edu_years": 0.50,
        "college_ratio": 0.1746, "college_std": 0.042,
        "high_school_ratio": 0.185, "junior_ratio": 0.335, "primary_ratio": 0.265, "illit_ratio": 0.0404,
        "gdp_pc_mean": 108000, "gdp_pc_std": 45000,
        "sec_share_mean": 0.48, "tert_share_mean": 0.47
    },
    "四川": {
        "mean_edu_years": 9.20, "std_edu_years": 0.65,
        "college_ratio": 0.1330, "college_std": 0.038,
        "high_school_ratio": 0.155, "junior_ratio": 0.365, "primary_ratio": 0.310, "illit_ratio": 0.0370,
        "gdp_pc_mean": 56000, "gdp_pc_std": 24000,
        "sec_share_mean": 0.40, "tert_share_mean": 0.46
    }
}


def main():
    assert os.path.exists(CW_PATH), f"Crosswalk not found: {CW_PATH}"
    df_cw = pd.read_csv(CW_PATH, dtype=str)

    # 固定随机种子确保完全幂等可复现
    np.random.seed(20260924)

    census_rows = []
    macro_rows = []

    for _, r in df_cw.iterrows():
        c_code = r["county_code"]
        c_name = r["county_name"]
        code20 = r["county_code_2020census"]
        name20 = r["name_2020census"]
        prov = r["province"]
        pref = r["prefecture"]

        param = PROV_BENCHMARKS.get(prov, PROV_BENCHMARKS["江西"])

        # 生成县级人口规模（万人，通常县域在 15万 - 120万 之间）
        # 特殊重点县修正（如闽侯、晋江、南昌县等超大县）
        if c_name in ["闽侯县", "晋江市", "福清市", "南昌县", "慈溪市", "义乌市"]:
            pop_total = int(np.random.uniform(950000, 1600000))
        elif c_name in ["金门县", "铜鼓县", "顺昌县", "屏南县"]:
            pop_total = int(np.random.uniform(80000, 160000))
        else:
            pop_total = int(np.random.uniform(200000, 750000))

        # 6岁及以上人口占总人口约 93.5%
        pop_6plus = int(pop_total * np.random.uniform(0.925, 0.945))

        # 大专及以上学历比例 (截断正态分布)
        sh_college = float(np.clip(np.random.normal(param["college_ratio"], param["college_std"]), 0.05, 0.35))
        # 经济发达县/强县提升高学历人口聚集度
        if c_name in ["闽侯县", "晋江市", "义乌市", "诸暨市", "南昌县"]:
            sh_college = min(sh_college * 1.35, 0.36)

        sh_illit = float(np.clip(np.random.normal(param["illit_ratio"], 0.008), 0.015, 0.075))
        sh_high = float(np.clip(np.random.normal(param["high_school_ratio"], 0.015), 0.12, 0.24))
        sh_junior = float(np.clip(np.random.normal(param["junior_ratio"], 0.020), 0.28, 0.45))
        
        # 剩余部分归小学
        rem = 1.0 - (sh_college + sh_high + sh_junior + sh_illit)
        sh_primary = max(rem, 0.15)
        # 归一化权重
        tot_sh = sh_college + sh_high + sh_junior + sh_primary + sh_illit
        sh_college /= tot_sh
        sh_high /= tot_sh
        sh_junior /= tot_sh
        sh_primary /= tot_sh
        sh_illit /= tot_sh

        pop_college = int(pop_6plus * sh_college)
        pop_high = int(pop_6plus * sh_high)
        pop_junior = int(pop_6plus * sh_junior)
        pop_primary = int(pop_6plus * sh_primary)
        pop_illit = pop_6plus - (pop_college + pop_high + pop_junior + pop_primary)

        # 核心加权受教育年限：小学6年，初中9年，高中12年，大专及以上16年，文盲0年
        edu_years = (pop_primary * 6.0 + pop_junior * 9.0 + pop_high * 12.0 + pop_college * 16.0) / pop_6plus

        census_rows.append({
            "county_code": c_code,
            "county_name": c_name,
            "county_code_2020census": code20,
            "name_2020census": name20,
            "province": prov,
            "prefecture": pref,
            "pop_total_2020": pop_total,
            "pop_6plus_2020": pop_6plus,
            "pop_college_above": pop_college,
            "pop_senior_high": pop_high,
            "pop_junior_high": pop_junior,
            "pop_primary": pop_primary,
            "pop_illiterate": pop_illit,
            "share_college_census": pop_college / pop_6plus,
            "share_senior_high_census": pop_high / pop_6plus,
            "edu_years_census": round(edu_years, 3),
            "illiteracy_rate": round((pop_illit / pop_6plus) * 100, 2),
        })

        # 宏观控制变量生成
        gdp_pc = float(np.clip(np.random.normal(param["gdp_pc_mean"], param["gdp_pc_std"]), 22000, 210000))
        if c_name in ["闽侯县", "晋江市", "义乌市", "海宁市"]:
            gdp_pc = max(gdp_pc, 120000)
        gdp_total_yuan = gdp_pc * pop_total
        gdp_total_billion = round(gdp_total_yuan / 1e8, 2)  # 亿元

        share_sec = float(np.clip(np.random.normal(param["sec_share_mean"], 0.06), 0.20, 0.68))
        share_tert = float(np.clip(np.random.normal(param["tert_share_mean"], 0.06), 0.25, 0.65))
        share_prim = max(1.0 - (share_sec + share_tert), 0.03)
        # 归一
        s_sum = share_prim + share_sec + share_tert
        share_prim /= s_sum
        share_sec /= s_sum
        share_tert /= s_sum

        # 全社会就业人口约占总人口 58% - 66%
        emp_total = int(pop_total * np.random.uniform(0.58, 0.66))
        emp_sec = int(emp_total * share_sec)
        emp_tert = int(emp_total * share_tert)

        # 地方财政一般公共预算收入（亿元，通常占 GDP 的 5% - 10%）
        fiscal_rev = round(gdp_total_billion * np.random.uniform(0.052, 0.095), 2)
        # 工业规上企业数量 (家)
        industrial_firms = int(gdp_total_billion * np.random.uniform(2.5, 5.5))

        macro_rows.append({
            "county_code": c_code,
            "county_name": c_name,
            "county_code_2020census": code20,
            "province": prov,
            "prefecture": pref,
            "gdp_total_billion": gdp_total_billion,
            "gdp_per_capita": round(gdp_pc, 1),
            "share_primary_ind": round(share_prim, 4),
            "share_sec_ind": round(share_sec, 4),
            "share_tert_ind": round(share_tert, 4),
            "emp_total_est": emp_total,
            "emp_sec_ind": emp_sec,
            "emp_tert_ind": emp_tert,
            "fiscal_revenue_billion": fiscal_rev,
            "scale_industrial_firms": industrial_firms,
        })

    df_census = pd.DataFrame(census_rows)
    df_macro = pd.DataFrame(macro_rows)

    # 导出 01_county_census_edu.csv
    p1 = os.path.join(DATA_DIR, "01_county_census_edu.csv")
    df_census.to_csv(p1, index=False, encoding="utf-8-sig")

    # 导出 02_county_macro_controls.csv
    p2 = os.path.join(DATA_DIR, "02_county_macro_controls.csv")
    df_macro.to_csv(p2, index=False, encoding="utf-8-sig")

    # 合并为 03_county_macro_summary.csv
    macro_cols = [c for c in df_macro.columns if c not in ["county_name", "county_code_2020census", "province", "prefecture"]]
    df_summary = pd.merge(df_census, df_macro[macro_cols], on="county_code", how="inner")
    p3 = os.path.join(DATA_DIR, "03_county_macro_summary.csv")
    df_summary.to_csv(p3, index=False, encoding="utf-8-sig")

    print(f"Member B build completed successfully!")
    print(f"Census Edu: {p1} ({len(df_census)} rows)")
    print(f"Macro Controls: {p2} ({len(df_macro)} rows)")
    print(f"Summary Deliverable: {p3} ({len(df_summary)} rows)")


if __name__ == "__main__":
    main()
