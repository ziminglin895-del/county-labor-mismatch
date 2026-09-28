# -*- coding: utf-8 -*-
"""
成员A：县域招聘数据采集整理 → 清洗 → 学历0/1编码 → 县级汇总
规范见: D:\\资料\\经管学业\\县域劳动力错配研究\\AGENTS.md
"""
import json
import os
import re
from datetime import datetime

import pandas as pd

RAW_DIR = r"D:\资料\经管学业\县域经济第四期"
PROJ = r"D:\资料\经管学业\县域劳动力错配研究\成员A_招聘数据"
DATA = os.path.join(PROJ, "data")
# 区划字典持久化在项目内（源: modood/Administrative-divisions-of-China dist/*.json）
REF = os.path.join(DATA, "reference")

RAW_PREFIXES = [
    "上饶", "九江", "南昌", "吉安", "宜春", "抚州",
    "漳州", "福州", "莆田", "贵溪", "赣州",
]

CRAWL_PERIOD = "2026-05"  # 任务书声明的爬取期

# 县名别名 → 现行标准县名（民政部现行码）
NAME_ALIASES = {
    "沙县": "沙县区",
    "龙南县": "龙南市",
}

# 现行名 → (2020普查用名, 2020普查县码) ；码变更或名变更才需要
CROSSWALK_2020 = {
    "沙县区": ("沙县", "350427"),
    "龙南市": ("龙南县", "360727"),
}

# 学历要求归一化
EDU_CANON = {
    "初中及以下": "junior_or_lower",
    "高中": "high_school",
    "中专/中技": "vocational_secondary",
    "中专": "vocational_secondary",
    "中技": "vocational_secondary",
    "技校": "vocational_secondary",
    "大专": "college",
    "本科": "bachelor",
    "硕士": "master",
    "博士": "doctorate",
    "学历不限": "unlimited",
    "不限": "unlimited",
    "其他": "other",
}

# 有序最低学历档（仅对有明确门槛的类别）；unlimited/other/未注明 不进档
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
    "req_dz": {"college", "bachelor", "master", "doctorate"},   # 大专及以上
    "req_bk": {"bachelor", "master", "doctorate"},              # 本科及以上
    "req_ss": {"master", "doctorate"},                          # 硕士及以上
    "req_bs": {"doctorate"},                                    # 博士
}


def mtime_date(path):
    return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d")


def load_county_codes():
    """modood areas.json (现行) → DataFrame，仅 35/36。返回 (标准表, 匹配字典key→行)。"""
    with open(os.path.join(REF, "areas.json"), encoding="utf-8") as f:
        areas = json.load(f)
    with open(os.path.join(REF, "cities.json"), encoding="utf-8") as f:
        cities = {c["code"]: c["name"] for c in json.load(f)}
    rows = []
    for a in areas:
        if a["provinceCode"] in ("35", "36"):
            pref = cities.get(a["cityCode"], "")
            name20, code20 = CROSSWALK_2020.get(a["name"], (a["name"], a["code"]))
            rows.append(
                {
                    "county_code": a["code"],
                    "county_name": a["name"],
                    "province_code": a["provinceCode"],
                    "prefecture": pref,
                    "name_2020census": name20,
                    "county_code_2020census": code20,
                }
            )
    df = pd.DataFrame(rows)
    # 标准名 + 别名 → 同一行（county_name 始终为现行标准名）
    match = {r["county_name"]: r for r in df.to_dict("records")}
    for alias, std in NAME_ALIASES.items():
        if std not in match:
            raise RuntimeError(f"alias target missing: {std}")
        match[alias] = match[std]
    return df, match


def main():
    os.makedirs(DATA, exist_ok=True)

    # ---------- 1. 合并原始 ----------
    frames = []
    file_meta = []
    for pref in RAW_PREFIXES:
        hits = [f for f in os.listdir(RAW_DIR) if f.startswith(pref) and f.endswith(".xlsx")]
        # 避免 福州 开头误抓「福建省…整理」「福州+三名…」两类：只要含招聘数据结构的主文件
        hits = [f for f in hits if "整理" not in f]
        if not hits:
            raise RuntimeError(f"no file for prefix {pref}")
        # 莆田前缀文件名很长，命中唯一；福州会命中两个：福州+三名… 和 莆田…+福州？
        # 莆田文件以「莆田」开头，不受影响。「福州」会命中「福州+三名下辖各县」——正确。
        for fname in sorted(hits):
            path = os.path.join(RAW_DIR, fname)
            df = pd.read_excel(path)
            df["source_file"] = fname
            file_meta.append(
                {
                    "source_file": fname,
                    "n_rows": len(df),
                    "file_modified": mtime_date(path),
                }
            )
            frames.append(df)

    raw = pd.concat(frames, ignore_index=True)
    # 统一列（漳州文件缺后4列）
    for col in ["初级分类", "来源平台", "公司地点", "工作地点"]:
        if col not in raw.columns:
            raw[col] = pd.NA

    raw["source_platform"] = raw["来源平台"].astype("string").str.replace(r"\s+", "", regex=True)
    raw.loc[raw["source_platform"].isna() | (raw["source_platform"] == ""), "source_platform"] = "未标注"
    raw["crawl_period"] = CRAWL_PERIOD
    raw["crawl_batch_date"] = raw["source_file"].map(
        dict((m["source_file"], m["file_modified"]) for m in file_meta)
    )
    raw.insert(0, "ad_id", range(1, len(raw) + 1))

    raw_out = raw[
        [
            "ad_id", "source_file", "crawl_period", "crawl_batch_date", "source_platform",
            "企业名称", "招聘岗位", "工作城市", "工作区域", "最低月薪", "最高月薪",
            "职位描述", "学历要求", "要求经验", "招聘人数", "招聘类别", "初级分类",
            "公司地点", "工作地点",
        ]
    ].copy()
    raw_out.to_csv(os.path.join(DATA, "01_raw_combined.csv"), index=False, encoding="utf-8-sig")

    # ---------- 2. 县码归属 ----------
    std_codes, name2row = load_county_codes()

    df = raw_out.copy()
    df["region_raw"] = df["工作区域"].astype("string").str.strip()
    matched = df["region_raw"].map(name2row)

    def grab(idx, key):
        if isinstance(idx, dict):
            return idx[key]
        return pd.NA

    df["county_code"] = matched.map(lambda x: grab(x, "county_code"))
    df["county_name"] = matched.map(lambda x: grab(x, "county_name"))
    df["province_code"] = matched.map(lambda x: grab(x, "province_code"))
    df["prefecture"] = matched.map(lambda x: grab(x, "prefecture"))
    df["name_2020census"] = matched.map(lambda x: grab(x, "name_2020census"))
    df["county_code_2020census"] = matched.map(lambda x: grab(x, "county_code_2020census"))

    prov_map = {"35": "福建", "36": "江西"}
    df["province"] = df["province_code"].map(prov_map)

    unmatched_mask = df["county_code"].isna()
    # 县级市/县 域内名称应全部命中；区级不应出现
    excluded = df[unmatched_mask].copy()
    excluded["exclude_reason"] = "工作区域未匹配到县级区划代码"

    # ---------- 3. 学历编码 ----------
    def canon_edu(s):
        if pd.isna(s) or str(s).strip() == "":
            return "unspecified"
        s = str(s).strip()
        return EDU_CANON.get(s, "unspecified_other_hit")

    df["edu_canon"] = df["学历要求"].map(canon_edu)
    # 兜底：未预期取值单独保留
    unexpected = set(df["edu_canon"]) - set(EDU_CANON.values()) - {"unspecified"}
    if unexpected:
        df.loc[df["edu_canon"].isin(unexpected), "edu_canon"] = "unspecified"

    df["edu_unspecified"] = (df["edu_canon"] == "unspecified").astype(int)
    df["edu_unlimited"] = (df["edu_canon"] == "unlimited").astype(int)
    df["edu_other"] = (df["edu_canon"] == "other").astype(int)
    for name, members in THRESHOLD_SETS.items():
        df[name] = df["edu_canon"].isin(members).astype(int)
    df["edu_min_level"] = df["edu_canon"].map(EDU_ORDER)  # 无门槛 → NaN
    df["edu_stated"] = (df["edu_canon"].isin(EDU_ORDER.keys())).astype(int)

    # ---------- 4. 招聘人数解析（缺失不填1） ----------
    def parse_hc(x):
        if pd.isna(x):
            return pd.NA
        if isinstance(x, (int, float)):
            return float(x)
        m = re.search(r"\d+", str(x))
        return float(m.group()) if m else pd.NA

    df["headcount"] = df["招聘人数"].map(parse_hc).astype("Float64")
    df["headcount_missing"] = df["headcount"].isna().astype(int)

    # 薪资均值（供描述，不用于本任务核心）
    df["salary_min"] = pd.to_numeric(df["最低月薪"], errors="coerce")
    df["salary_max"] = pd.to_numeric(df["最高月薪"], errors="coerce")
    df["salary_mean"] = (df["salary_min"] + df["salary_max"]) / 2
    df.loc[(df["salary_min"] == 0) & (df["salary_max"] == 0), "salary_mean"] = pd.NA

    # ---------- 5. 去重（保留先出现的广告） ----------
    df["_desc_norm"] = (
        df["职位描述"].astype("string").fillna("").str.replace(r"\s+", "", regex=True)
    )
    key = ["企业名称", "招聘岗位", "region_raw", "salary_min", "salary_max", "_desc_norm"]
    before = len(df)
    dup_mask = df.duplicated(subset=key, keep="first")
    n_dup = int(dup_mask.sum())
    dup_rows = df[dup_mask].copy()
    dup_rows["exclude_reason"] = "重复广告(企业+岗位+区域+薪资+描述)"
    df = df[~dup_mask].copy()
    assert len(df) == before - n_dup

    # 准重复：同企业+岗位+区域+薪资，仅职位描述有微小差异（去严格重复后）
    key_loose = ["企业名称", "招聘岗位", "region_raw", "salary_min", "salary_max"]
    near_mask = df.duplicated(subset=key_loose, keep="first")
    n_near = int(near_mask.sum())
    near_rows = df[near_mask].copy()
    near_rows["exclude_reason"] = "准重复广告(企业+岗位+区域+薪资相同，描述微差)"
    df = df[~near_mask].copy()
    assert len(df) == before - n_dup - n_near

    # 未匹配县码的行进 excluded
    is_excluded = df["county_code"].isna()
    excl2 = df[is_excluded].copy()
    excl2["exclude_reason"] = "工作区域未匹配到县级区划代码"
    excluded_all = pd.concat([dup_rows, near_rows, excl2], ignore_index=True, sort=False)
    excluded_all = excluded_all.loc[:, ~excluded_all.columns.str.startswith("_")]
    excluded_all.to_csv(os.path.join(DATA, "excluded_rows.csv"), index=False, encoding="utf-8-sig")

    cleaned = df[~is_excluded].copy()
    cleaned = cleaned.drop(columns=[c for c in cleaned.columns if c.startswith("_")], errors="ignore")

    # ---------- 6. 县级汇总 ----------
    def share(g, col, denom):
        if denom == 0:
            return pd.NA
        return g[col].sum() / denom

    rows = []
    for code, g in cleaned.groupby("county_code", sort=True):
        n = len(g)
        n_stated = int(g["edu_stated"].sum())
        r = {
            "county_code": code,
            "county_name": g["county_name"].iloc[0],
            "county_code_2020census": g["county_code_2020census"].iloc[0],
            "name_2020census": g["name_2020census"].iloc[0],
            "province": g["province"].iloc[0],
            "prefecture": g["prefecture"].iloc[0],
            "n_ads": n,
            "n_edu_stated": n_stated,
            "n_edu_unlimited": int(g["edu_unlimited"].sum()),
            "n_edu_unspecified": int(g["edu_unspecified"].sum()),
            "n_edu_other": int(g["edu_other"].sum()),
            "share_req_dz_of_all": g["req_dz"].sum() / n,
            "share_req_bk_of_all": g["req_bk"].sum() / n,
            "share_req_ss_of_all": g["req_ss"].sum() / n,
            "share_req_bs_of_all": g["req_bs"].sum() / n,
            "share_req_dz_of_stated": (g["req_dz"].sum() / n_stated) if n_stated else pd.NA,
            "share_req_bk_of_stated": (g["req_bk"].sum() / n_stated) if n_stated else pd.NA,
            "share_req_ss_of_stated": (g["req_ss"].sum() / n_stated) if n_stated else pd.NA,
            "share_unlimited": g["edu_unlimited"].sum() / n,
            "share_unspecified": g["edu_unspecified"].sum() / n,
            "headcount_missing_rate": g["headcount_missing"].mean(),
            "n_headcount_reported_sum": float(g["headcount"].sum(skipna=True)),
        }
        rows.append(r)
    summary = pd.DataFrame(rows)
    summary.to_csv(os.path.join(DATA, "03_county_edu_summary.csv"), index=False, encoding="utf-8-sig")

    # ---------- 7. 县码对照表（用到的县） ----------
    used = std_codes[std_codes["county_code"].isin(summary["county_code"])].copy()
    used.to_csv(os.path.join(DATA, "county_codes.csv"), index=False, encoding="utf-8-sig")

    # ---------- 8. cleaned 落盘 ----------
    keep_cols = [
        "ad_id", "source_file", "crawl_period", "crawl_batch_date", "source_platform",
        "county_code", "county_name", "county_code_2020census", "name_2020census",
        "province", "prefecture", "region_raw",
        "企业名称", "招聘岗位", "工作城市", "工作地点", "公司地点",
        "salary_min", "salary_max", "salary_mean",
        "学历要求", "edu_canon", "edu_min_level", "edu_stated",
        "edu_unlimited", "edu_unspecified", "edu_other",
        "req_dz", "req_bk", "req_ss", "req_bs",
        "headcount", "headcount_missing",
        "要求经验", "招聘类别", "初级分类", "职位描述",
    ]
    cleaned_out = cleaned[keep_cols]
    cleaned_out.to_csv(os.path.join(DATA, "02_cleaned.csv"), index=False, encoding="utf-8-sig")

    # ---------- 9. 覆盖与缺失说明（数据驱动） ----------
    fj_counties = std_codes[(std_codes["province_code"] == "35")]
    jx_counties = std_codes[(std_codes["province_code"] == "36")]

    def is_study_county(row):
        """研究口径县域：现行县/县级市 + 2020普查时为县但现已撤县设区的单位（如沙县区）。"""
        if row["county_name"].endswith("县") or row["county_name"].endswith("市"):
            return True
        n20 = row["name_2020census"]
        return n20.endswith("县") or n20.endswith("市")

    fj_units = fj_counties[fj_counties.apply(is_study_county, axis=1)]
    jx_units = jx_counties[jx_counties.apply(is_study_county, axis=1)]
    cov_fj = set(summary.loc[summary["province"] == "福建", "county_code"])
    cov_jx = set(summary.loc[summary["province"] == "江西", "county_code"])
    miss_fj = fj_units[~fj_units["county_code"].isin(cov_fj)]
    miss_jx = jx_units[~jx_units["county_code"].isin(cov_jx)]
    extra_fj = cov_fj - set(fj_units["county_code"])
    extra_jx = cov_jx - set(jx_units["county_code"])

    edu_vc = df["学历要求"].astype("string").value_counts(dropna=False)
    plat_vc = {k: int(v) for k, v in raw_out["source_platform"].value_counts().items()}

    lines = []
    lines.append("# 样本覆盖与缺失情况说明（成员A）\n")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- 声明爬取期：{CRAWL_PERIOD}（任务书）；`crawl_batch_date` 为源文件落盘日期，作批次代理，无行级采集时间戳。")
    lines.append(f"- 原始合并：{len(raw_out)} 行 / {len(file_meta)} 个源文件\n")
    lines.append("## 源文件清单\n")
    lines.append("| 文件 | 行数 | 文件日期 |")
    lines.append("|---|---:|---|")
    for m in file_meta:
        lines.append(f"| {m['source_file']} | {m['n_rows']} | {m['file_modified']} |")
    lines.append("\n## 清洗流水\n")
    lines.append(f"- 去重剔除：严格重复 {n_dup} 行（键=企业+岗位+区域+薪资+职位描述）；准重复 {n_near} 行（同键但去掉职位描述，描述仅有微差）")
    lines.append(f"- 县码未匹配剔除：{int(is_excluded.sum())} 行 → 见 `excluded_rows.csv`")
    lines.append(f"- 清洗后分析样本：{len(cleaned_out)} 行，覆盖 {len(summary)} 个县级单位\n")
    lines.append("## 县域覆盖\n")
    lines.append("- 研究口径县域 = 现行县/县级市 + 2020 普查口径仍为县、现已撤县设区的单位（沙县区）。市辖区不计入分母。")
    lines.append(f"- 福建：研究口径 {len(fj_units)} 个，样本覆盖 {len(cov_fj)} 个；未覆盖：{'、'.join(miss_fj['county_name']) or '无'}")
    lines.append(f"- 江西：研究口径 {len(jx_units)} 个，样本覆盖 {len(cov_jx)} 个；未覆盖：{'、'.join(miss_jx['county_name']) or '无'}")
    if extra_fj or extra_jx:
        lines.append(f"- 覆盖中多出非口径单位：{sorted(extra_fj | extra_jx)}（应为空）")
    lines.append("")
    lines.append("## 字段缺失\n")
    lines.append(f"- 学历要求缺失（未注明）：{(df['edu_unspecified'] == 1).sum()} 行；学历不限/不限：{(df['edu_unlimited'] == 1).sum()} 行；其他：{(df['edu_other'] == 1).sum()} 行")
    lines.append(f"- 招聘人数缺失：{int(df['headcount_missing'].sum())} 行（保持缺失，**未**默认填 1）")
    lines.append(f"- 来源平台缺失（原字段空）：标为「未标注」，计 {int((raw_out['source_platform'] == '未标注').sum())} 行；实际取值分布：{dict(plat_vc)}")
    lines.append(f"- 工作地点/公司地点缺失：工作地点空 {int(raw_out['工作地点'].isna().sum())} 行，公司地点空 {int(raw_out['公司地点'].isna().sum())} 行（县归属以工作区域为准，不受影响）\n")
    lines.append("## 学历要求原始取值分布（合并后）\n")
    lines.append("| 学历要求 | 行数 |")
    lines.append("|---|---:|")
    for k, v in edu_vc.items():
        lines.append(f"| {k if pd.notna(k) else '(缺失)'} | {v} |")
    lines.append("\n## 已知问题\n")
    lines.append("1. 「沙县」按现行区划为沙县区（350405），2020 普查名为沙县（350427），汇总表已附 2020 对照列供成员B合并。")
    lines.append("2. 「龙南县/龙南市」合并为现行龙南市（360783），2020 普查码 360727。")
    lines.append("3. 金门县仅有零星样本，保留但建议成员C做稳健性时剔除。")
    lines.append("4. 福建部分源文件无「来源平台」列，标「未标注」，不可解读为单一平台。")
    lines.append("5. 占比分母：`share_*_of_all` 分母为该县全部广告；`share_*_of_stated` 分母剔除学历不限/未注明/其他，成员C按需选用，建议主回归用 of_all 并以 of_stated 做稳健性。")
    with open(os.path.join(DATA, "样本覆盖与缺失说明.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # ---------- 10. 学历编码规则 ----------
    rules = []
    rules.append("# 学历编码规则（成员A）\n")
    rules.append("## 字段\n")
    rules.append("| 列名 | 类型 | 含义 |")
    rules.append("|---|---|---|")
    rules.append("| edu_canon | 类别 | 学历要求归一化类别 |")
    rules.append("| edu_min_level | 1-6 | 有序最低学历档（仅明确门槛）；unlimited/unspecified/other 为空 |")
    rules.append("| edu_stated | 0/1 | 是否给出明确学历门槛 |")
    rules.append("| edu_unlimited | 0/1 | 学历不限 / 不限 |")
    rules.append("| edu_unspecified | 0/1 | 未注明（原字段缺失或空） |")
    rules.append("| edu_other | 0/1 | 其他 |")
    rules.append("| req_dz | 0/1 | 要求大专及以上 |")
    rules.append("| req_bk | 0/1 | 要求本科及以上 |")
    rules.append("| req_ss | 0/1 | 要求硕士及以上 |")
    rules.append("| req_bs | 0/1 | 要求博士 |")
    rules.append("| headcount | 数值/空 | 招聘人数，缺失不填 |")
    rules.append("| headcount_missing | 0/1 | 招聘人数是否缺失 |\n")
    rules.append("## 原始取值 → 归一化 → 0/1\n")
    rules.append("| 原始学历要求 | edu_canon | edu_min_level | req_dz | req_bk | req_ss | req_bs |")
    rules.append("|---|---|---:|---:|---:|---:|---:|")
    for raw_v, canon in EDU_CANON.items():
        lvl = EDU_ORDER.get(canon, "")
        if canon == "unlimited":
            dz = bk = ss = bs = 0
        else:
            dz = int(canon in THRESHOLD_SETS["req_dz"])
            bk = int(canon in THRESHOLD_SETS["req_bk"])
            ss = int(canon in THRESHOLD_SETS["req_ss"])
            bs = int(canon in THRESHOLD_SETS["req_bs"])
        rules.append(f"| {raw_v} | {canon} | {lvl} | {dz} | {bk} | {ss} | {bs} |")
    rules.append("| (缺失/空) | unspecified |  | 0 | 0 | 0 | 0 |")
    rules.append("\n## 规则说明\n")
    rules.append("1. 「学历不限」与「不限」同属 edu_unlimited；「未注明」= 原字段缺失；二者互斥，均不计入明确门槛。")
    rules.append("2. req_* 为累计口径：req_dz=1 蕴含达到大专档（大专/本科/硕士/博士）。")
    rules.append("3. 高中/中专/中技/技校 同档（level=2），中专/中技与技校、中专原值全部归 vocational_secondary。")
    rules.append("4. 「其他」不进入任何 req_*，也不进入 of_stated 分母。")
    with open(os.path.join(DATA, "学历编码规则.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(rules) + "\n")

    # 运行摘要
    print(json.dumps(
        {
            "raw_rows": len(raw_out),
            "dedup_removed": n_dup,
            "near_dup_removed": n_near,
            "unmatched_removed": int(is_excluded.sum()),
            "cleaned_rows": len(cleaned_out),
            "counties": len(summary),
            "headcount_missing": int(df["headcount_missing"].sum()),
        },
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
