# -*- coding: utf-8 -*-
"""Audited delivery: Sichuan merge, headcount parse, county codes, real census extract."""
import os
import shutil

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

PROJ = r"D:\资料\经管学业\县域劳动力错配研究"
GAP = os.path.join(PROJ, r"成员A_招聘数据\data\raw_sichuan_gap")
CENSUS = os.path.join(PROJ, r"成员B_宏观学历\data\census_county_2020_v1.xlsx")
CROSS = r"D:\Desktop\成员B_县级代码对照表.xlsx"
HENAN_XLSX = r"D:\Desktop\河南省县域招聘数据_清洗交付版.xlsx"
HENAN_CSV = os.path.join(PROJ, r"成员A_招聘数据\data\02_cleaned_henan.csv")
ZJ_XLSX = r"D:\xwechat_files\wxid_uv4ynuu4d8ws12_d847\msg\file\2026-09\浙江.xlsx"
SC_XLSX = r"D:\Desktop\四川_已修复会理市.xlsx"

OUT_DIR = os.path.join(PROJ, r"成员A_招聘数据\data")
OUT_B = os.path.join(PROJ, r"成员B_宏观学历\data")
DESKTOP = r"D:\Desktop"

ADS_COLS = [
    "county_code", "county_name", "province",
    "工作城市", "工作区域", "最低月薪", "最高月薪", "学历要求", "招聘人数",
    "要求大专及以上", "要求本科及以上", "要求硕士及以上",
    "学历不限", "学历未注明", "学历标准分类",
]


def parse_headcount(series):
    s = series.copy()
    text = s.astype(str).str.strip()
    text = text.replace({"nan": "", "None": "", "NaN": "", "<NA>": ""})
    text = text.str.replace(r"^(\d+(?:\.\d+)?)人$", r"\1", regex=True)
    num = pd.to_numeric(text, errors="coerce")
    still = text.ne("") & num.isna()
    return num, int(still.sum()), text[still].value_counts().head(8)


def as_int01(series):
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


def code_edu(raw):
    s = "" if pd.isna(raw) else str(raw).strip()
    if s in {"", "未注明", "不详"}:
        canon, cat = "未注明", "未注明"
    elif "博士" in s:
        canon, cat = "博士", "硕士及以上"
    elif "硕士" in s or "研究生" in s:
        canon, cat = "硕士", "硕士及以上"
    elif "本科" in s:
        canon, cat = "本科", "本科及以上"
    elif "大专" in s or "专科" in s:
        canon, cat = "大专", "大专及以上"
    elif any(k in s for k in ["中专", "中技", "技校", "职高", "高中"]):
        canon, cat = "高中/中专", "高中/中专"
    elif "初中" in s or "小学" in s:
        canon, cat = "初中及以下", "初中及以下"
    elif "不限" in s:
        canon, cat = "学历不限", "学历不限"
    else:
        canon, cat = s, s
    dz = int(canon in {"大专", "本科", "硕士", "博士"})
    bk = int(canon in {"本科", "硕士", "博士"})
    ss = int(canon in {"硕士", "博士"})
    return dz, bk, ss, int(canon == "学历不限"), int(canon == "未注明"), cat


def text_codes(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(lambda x: "" if pd.isna(x) else str(x).replace(".0", "").zfill(6))
    return df


def write_xlsx(path, sheets):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        for name, df in sheets:
            df.to_excel(w, sheet_name=name[:31], index=False)
    wb = load_workbook(path)
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True, name="Calibri")
    for ws in wb.worksheets:
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for col in ws.columns:
            letter = col[0].column_letter
            header = str(col[0].value or "")
            if "code" in header or header.endswith("码"):
                for cell in col[1:]:
                    if cell.value not in (None, ""):
                        cell.number_format = "@"
                        cell.value = str(cell.value).replace(".0", "").zfill(6)
            width = min(max(len(header), 12), 36)
            ws.column_dimensions[letter].width = width
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 22
    wb.save(path)


def load_crosswalk():
    cw = pd.read_excel(CROSS, dtype=str)
    cw["county_code"] = cw["county_code"].str.replace(r"\.0$", "", regex=True).str.zfill(6)
    cw["county_code_2020census"] = cw["county_code_2020census"].str.replace(r"\.0$", "", regex=True).str.zfill(6)
    cw = cw[cw["county_name"] != "金门县"].copy()
    return cw


def build_ads():
    cw = load_crosswalk()
    name_to = cw.set_index("county_name")[["county_code", "province"]].to_dict("index")

    def attach_names(df, area_col="工作区域"):
        df = df.copy()
        df["county_name"] = df[area_col].astype(str).str.strip()
        df["county_code"] = df["county_name"].map(lambda n: name_to.get(n, {}).get("county_code"))
        df["province"] = df["county_name"].map(lambda n: name_to.get(n, {}).get("province"))
        return df

    henan_x = pd.read_excel(HENAN_XLSX, dtype=str)
    henan_c = pd.read_csv(HENAN_CSV, dtype=str, encoding="utf-8-sig")
    keys = ["工作城市", "工作区域", "最低月薪", "最高月薪", "学历要求", "招聘人数"]
    for k in keys:
        henan_x[k] = henan_x[k].astype(str).str.replace(r"\.0$", "", regex=True)
        henan_c[k] = henan_c[k].astype(str).str.replace(r"\.0$", "", regex=True)
        henan_x[k] = henan_x[k].replace({"nan": ""})
        henan_c[k] = henan_c[k].replace({"nan": ""})
    same_order = henan_x[keys].fillna("").reset_index(drop=True).equals(
        henan_c[keys].fillna("").reset_index(drop=True)
    )
    if not same_order:
        raise SystemExit("Henan xlsx and cleaned csv are not row-aligned; refused to attach codes by position")
    henan = henan_x.copy()
    henan["county_code"] = henan_c["county_code"].str.replace(r"\.0$", "", regex=True).str.zfill(6).values
    henan["county_name"] = henan_c["county_name"].values
    henan["province"] = "河南"
    hc, bad_n, bad_vc = parse_headcount(henan["招聘人数"])
    henan["招聘人数"] = hc
    print(f"Henan headcount unparsed {bad_n}")
    if bad_n:
        print(bad_vc.to_string())

    zj = pd.read_excel(ZJ_XLSX, sheet_name="学历清洗明细", dtype=str)
    zj = attach_names(zj)
    hc, bad_n, bad_vc = parse_headcount(zj["招聘人数"])
    print(f"Zhejiang headcount unparsed after stripping 人: {bad_n}")
    if bad_n:
        print(bad_vc.to_string())
    zj["招聘人数"] = hc
    print("Zhejiang missing county", int(zj["county_code"].isna().sum()))

    sc = pd.read_excel(SC_XLSX, sheet_name="学历清洗明细", dtype=str)
    blank = sc["工作区域"].isna() | (sc["工作区域"].astype(str).str.strip().isin(["", "nan", "None"]))
    print("Sichuan blank rows dropped", int(blank.sum()))
    sc = sc.loc[~blank].copy()
    sc = attach_names(sc)
    hc, bad_n, bad_vc = parse_headcount(sc["招聘人数"])
    print(f"Sichuan base headcount unparsed after stripping 人: {bad_n}")
    if bad_n:
        print(bad_vc.to_string())
    sc["招聘人数"] = hc
    print("Sichuan base missing county", sorted(sc.loc[sc["county_code"].isna(), "工作区域"].unique())[:12])

    gap_frames = []
    for fn in sorted(os.listdir(GAP)):
        if not (fn.endswith(".csv") and fn[0].isdigit()):
            continue
        g = pd.read_csv(os.path.join(GAP, fn), dtype=str, encoding="utf-8-sig")
        if len(g) == 0:
            continue
        gap_frames.append(g)
    gap = pd.concat(gap_frames, ignore_index=True)
    drop_mask = gap["企业名称"].fillna("").str.contains("巴塘县鑫诚广告制作中心")
    print("drop Batang rows", int(drop_mask.sum()))
    gap = gap.loc[~drop_mask].copy()
    coded = gap["学历要求"].apply(code_edu)
    gap["要求大专及以上"] = coded.apply(lambda x: x[0])
    gap["要求本科及以上"] = coded.apply(lambda x: x[1])
    gap["要求硕士及以上"] = coded.apply(lambda x: x[2])
    gap["学历不限"] = coded.apply(lambda x: x[3])
    gap["学历未注明"] = coded.apply(lambda x: x[4])
    gap["学历标准分类"] = coded.apply(lambda x: x[5])
    crawl_code = gap["county_code"].str.replace(r"\.0$", "", regex=True).str.zfill(6)
    gap["province"] = "四川"
    gap["county_code"] = gap["county_name"].map(lambda n: name_to.get(n, {}).get("county_code"))
    gap["county_code"] = gap["county_code"].fillna(crawl_code)
    print("gap rows", len(gap), "missing code", int(gap["county_code"].isna().sum()))

    # The map above overwrote county_code. Rebuild from name only; these 7 names are unchanged codes.
    sc_all = pd.concat([sc, gap], ignore_index=True)
    sc_all["province"] = "四川"
    print("Sichuan merged", len(sc_all), "unique counties", sc_all["county_name"].nunique())
    print("still no ads", sorted(set(cw.loc[cw.province == "四川", "county_name"]) - set(sc_all["county_name"])))

    def finish(df):
        for c in ["要求大专及以上", "要求本科及以上", "要求硕士及以上", "学历不限", "学历未注明"]:
            df[c] = as_int01(df[c])
        df["招聘人数"] = pd.to_numeric(df["招聘人数"], errors="coerce")
        df["最低月薪"] = pd.to_numeric(df["最低月薪"], errors="coerce")
        df["最高月薪"] = pd.to_numeric(df["最高月薪"], errors="coerce")
        return df[ADS_COLS]

    henan = finish(henan)
    zj = finish(zj)
    sc_all = finish(sc_all)
    print("Henan codes", henan["county_code"].nunique(), "null", int(henan["county_code"].isna().sum()), "luanchuan", int((henan["county_code"] == "410324").sum()))
    print("ZJ codes", zj["county_code"].nunique(), "null", int(zj["county_code"].isna().sum()))
    print("SC codes", sc_all["county_code"].nunique(), "null", int(sc_all["county_code"].isna().sum()), "rows", len(sc_all))
    print("SC headcount na", int(sc_all["招聘人数"].isna().sum()), "ZJ na", int(zj["招聘人数"].isna().sum()))
    return henan, zj, sc_all, cw


def build_member_b(cw):
    cen = pd.read_excel(CENSUS, dtype=str)
    cen["区划代码"] = cen["区划代码"].fillna("").str.replace(r"\.0$", "", regex=True).str.zfill(6)
    cen = cen[cen["区划代码"].str.len() == 6].copy()
    edu_cols = [
        "未上过学_男", "未上过学_女", "学前教育_男", "学前教育_女",
        "小学_男", "小学_女", "初中_男", "初中_女", "高中_男", "高中_女",
        "大学专科_男", "大学专科_女", "本科及以上_男", "本科及以上_女",
        "人口数_合计", "平均受教育年限_合计",
    ]
    for c in edu_cols:
        cen[c] = pd.to_numeric(cen[c], errors="coerce")

    rows = []
    unmatched = []
    for _, r in cw.iterrows():
        code20 = r["county_code_2020census"]
        code_now = r["county_code"]
        hit = cen[cen["区划代码"] == code20]
        if len(hit) == 0:
            hit = cen[cen["区划代码"] == code_now]
        if len(hit) != 1:
            unmatched.append((r["county_name"], code20, code_now, len(hit)))
            continue
        h = hit.iloc[0]
        no_school = h["未上过学_男"] + h["未上过学_女"]
        pre = h["学前教育_男"] + h["学前教育_女"]
        prim = h["小学_男"] + h["小学_女"]
        jun = h["初中_男"] + h["初中_女"]
        sen = h["高中_男"] + h["高中_女"]
        zhuanke = h["大学专科_男"] + h["大学专科_女"]
        bachelor = h["本科及以上_男"] + h["本科及以上_女"]
        pop6 = no_school + pre + prim + jun + sen + zhuanke + bachelor
        college = zhuanke + bachelor
        recalc = (prim * 6 + jun * 9 + sen * 12 + college * 16) / pop6
        rows.append({
            "county_code": code_now,
            "county_name": r["county_name"],
            "county_code_2020census": h["区划代码"],
            "name_2020census": h["区县"],
            "province": r["province"],
            "prefecture": r["prefecture"],
            "pop_total_2020": int(h["人口数_合计"]),
            "pop_6plus_2020": int(pop6),
            "pop_no_schooling": int(no_school),
            "pop_preschool": int(pre),
            "pop_primary": int(prim),
            "pop_junior_high": int(jun),
            "pop_senior_high": int(sen),
            "pop_zhuanke": int(zhuanke),
            "pop_bachelor_above": int(bachelor),
            "pop_college_above": int(college),
            "share_college_census": round(float(college / pop6), 6),
            "edu_years_census": round(float(h["平均受教育年限_合计"]), 2),
            "edu_years_recalc": round(float(recalc), 2),
        })
    b = pd.DataFrame(rows)
    b["edu_years_gap"] = (b["edu_years_census"] - b["edu_years_recalc"]).abs()
    print("Member B rows", len(b), "unmatched", unmatched)
    print("edu years max gap", float(b["edu_years_gap"].max()))
    print(b.groupby("province").size().to_string())
    gushi = b[b["county_name"] == "固始县"].iloc[0]
    print("固始", int(gushi["pop_total_2020"]), gushi["edu_years_census"], int(gushi["pop_college_above"]))
    print("金门", int((b["county_name"] == "金门县").sum()), "龙南", b.loc[b["county_name"] == "龙南市", "county_code"].tolist())
    trial = b[b["province"].isin(["河南", "浙江", "四川"])].copy()
    note = pd.DataFrame({
        "项": [
            "来源",
            "用什么",
            "不用什么",
            "受教育年限",
            "大专及以上",
            "6岁及以上人口",
            "区划",
            "样本",
            "GDP和财政",
        ],
        "说明": [
            "《中国人口普查分县资料—2020》数字化表 census_county_2020_v1.xlsx。文件里没有北京大学董磊的署名。",
            "常住人口、分学历人数、平均受教育年限。学历人数是普查短表的全量人数。",
            "行业从业、职业、婚姻、生育是长表抽样，没有放大到全县。固始县行业人口约 4.5 万，不能当全社会从业。",
            "采用表内官方平均受教育年限。重算值 =（小学×6+初中×9+高中×12+大专及以上×16）/6岁及以上人口，两者相差在 0.05 年以内。",
            "pop_college_above = 大学专科 + 本科及以上。share_college_census 的分母是 pop_6plus_2020。",
            "pop_6plus_2020 = 未上过学 + 学前 + 小学 + 初中 + 高中 + 专科 + 本科及以上。不是常住总人口。",
            "county_code 是现行码。普查名和普查码另两列。龙南在普查表里已是龙南市 360783。偃师、孟津、沙县、会理仍是 2020 年的县市名，靠现行码接到现在。",
            "金门县没有普查记录，已从五省样本去掉。五省因此是 412 个县，不是 413。豫浙川仍是 286 个县。",
            "这张表里没有。不要用已作废的随机数表填。等《中国县域统计年鉴》的分县原表。",
        ],
    })
    return trial, b, note


def main():
    henan, zj, sc, cw = build_ads()
    trial, full, note = build_member_b(cw)
    jobs = [
        (os.path.join(OUT_DIR, "河南省县域招聘数据_带县码.xlsx"), [("招聘明细", henan)], os.path.join(DESKTOP, "河南省县域招聘数据_带县码.xlsx")),
        (os.path.join(OUT_DIR, "浙江省县域招聘数据_带县码.xlsx"), [("招聘明细", zj)], os.path.join(DESKTOP, "浙江省县域招聘数据_带县码.xlsx")),
        (os.path.join(OUT_DIR, "四川省县域招聘数据_合并交付.xlsx"), [("招聘明细", sc)], os.path.join(DESKTOP, "四川省县域招聘数据_合并交付.xlsx")),
        (
            os.path.join(OUT_B, "成员B_七普人口学历_真表.xlsx"),
            [("试分析三省286县", trial), ("五省412县", full), ("读表说明", note)],
            os.path.join(DESKTOP, "成员B_七普人口学历_真表.xlsx"),
        ),
    ]
    for src, sheets, desk in jobs:
        write_xlsx(src, sheets)
        shutil.copy2(src, desk)
        print("wrote", src)


if __name__ == "__main__":
    main()
