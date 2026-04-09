# -*- coding: utf-8 -*-
"""
优信拍真实成交数据 - 价格预测系统标准测评脚本

数据来源: data/youxinpai_vehicles-11-100.csv (优信拍真实成交价格)
测评目标: 评估预测系统在真实市场数据上的准确性

命中定义: 实际成交价格落入 c2BPrices.b [low, high] 区间内
"""

import sys
import os
import json
import time
import random
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import requests

API_URL = "http://60.205.246.51:8090/predict"
DATA_PATH = "data/youxinpai_vehicles-11-100.csv"
RESULT_PATH = "experiment/youxinpai_eval_results.csv"
STATS_PATH = "experiment/youxinpai_eval_stats.json"

# 采样数量（-1 = 全量）
SAMPLE_SIZE = 800
REQUEST_TIMEOUT = 15
SLEEP_BETWEEN_REQUESTS = 0.1  # 秒


def parse_grade(rating_code: str) -> str:
    """
    优信拍评级代码 → 优/中/差
    格式: 数字分数 + 字母代码 (如 60DB, 75BB, 95AA)
    分数 >= 80: 优, 60-79: 中, < 60: 差
    """
    try:
        score = int(rating_code[:2])
        if score >= 80:
            return "优"
        elif score >= 60:
            return "中"
        else:
            return "差"
    except Exception:
        return "中"


def parse_price(price_str: str) -> float:
    """解析价格字符串，如 '4.50万元' → 4.50"""
    try:
        return float(str(price_str).replace("万元", "").replace("万", "").strip())
    except Exception:
        return None


def parse_mileage(mileage_str: str) -> float:
    """解析里程，如 '109933公里' → 10.9933 (万公里)"""
    try:
        km = float(str(mileage_str).replace("公里", "").strip())
        return round(km / 10000, 4)
    except Exception:
        return None


def parse_date_to_months(date_str: str) -> int:
    """解析日期 '2026年03月' → 总月数
    字符: 2026年03月 → [0:4]=年份, [5:7]=月份
    """
    try:
        date_str = str(date_str).strip()
        year = int(date_str[:4])
        month = int(date_str[5:7])
        return year * 12 + month
    except Exception:
        return None


def parse_vehicle_name(name: str):
    """
    解析车辆名称，提取品牌、车系、full_name
    格式: '丰田/卡罗拉/2021款 1.2T ...'
    """
    parts = str(name).split("/")
    if len(parts) >= 2:
        brand = parts[0].strip()
        series = parts[1].strip()
        brand_series = f"{brand}-{series}"
        # 重建 vehicle_full_name (用空格替换/)
        full_name = " ".join(parts).strip()
        return brand, series, brand_series, full_name
    return None, None, None, str(name)


def call_predict_api(vehicle_full_name, brand_series, years, grade, city, mileage):
    """调用价格预测API"""
    payload = {
        "vehicle_full_name": vehicle_full_name,
        "brand_series": brand_series,
        "years": round(float(years), 2),
        "grade": grade,
        "city": str(city),
        "mileage": round(float(mileage), 2) if mileage is not None else None,
    }
    # 移除 None 字段
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        resp = requests.post(API_URL, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"success": False, "error_message": f"HTTP {resp.status_code}"}
    except requests.Timeout:
        return {"success": False, "error_message": "timeout"}
    except Exception as e:
        return {"success": False, "error_message": str(e)}


def extract_prices(api_result):
    """从API结果提取关键价格"""
    pm = api_result.get("price_matrix", {})
    c2b = pm.get("c2BPrices", {}).get("b", {})
    b2b = pm.get("b2BPrices", {}).get("b", {})
    return {
        "predicted_price": api_result.get("predicted_price"),
        "c2b_low": c2b.get("low"),
        "c2b_mid": c2b.get("mid"),
        "c2b_high": c2b.get("up"),
        "b2b_low": b2b.get("low"),
        "b2b_mid": b2b.get("mid"),
        "b2b_high": b2b.get("up"),
        "residual_rate": api_result.get("residual_rate"),
        "model_type": api_result.get("debug", {}).get("model_used", ""),
        "new_price": api_result.get("new_price"),
    }


def price_segment(price: float) -> str:
    if price is None:
        return "未知"
    if price < 1:
        return "<1万"
    elif price < 3:
        return "1-3万"
    elif price < 5:
        return "3-5万"
    elif price < 10:
        return "5-10万"
    elif price < 20:
        return "10-20万"
    else:
        return ">20万"


def age_segment(years: float) -> str:
    if years < 3:
        return "0-3年"
    elif years < 5:
        return "3-5年"
    elif years < 8:
        return "5-8年"
    elif years < 10:
        return "8-10年"
    else:
        return ">10年"


def run_evaluation():
    print("=" * 60)
    print("优信拍成交数据 - 价格预测系统测评")
    print(f"API: {API_URL}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 读取数据
    df = pd.read_csv(DATA_PATH, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    print(f"原始数据: {len(df)} 条")

    # 数据预处理
    df["actual_price"] = df["成交价格"].apply(parse_price)
    df["mileage_wan"] = df["行驶里程"].apply(parse_mileage)
    df["trade_months"] = df["成交时间"].apply(parse_date_to_months)
    df["reg_months"] = df["上牌时间"].apply(parse_date_to_months)
    df["years"] = (df["trade_months"] - df["reg_months"]) / 12
    df["grade"] = df["车辆评级"].apply(parse_grade)

    parsed = df["车辆名称"].apply(parse_vehicle_name)
    df["brand"] = parsed.apply(lambda x: x[0])
    df["series"] = parsed.apply(lambda x: x[1])
    df["brand_series"] = parsed.apply(lambda x: x[2])
    df["vehicle_full_name"] = parsed.apply(lambda x: x[3])

    # 过滤无效数据
    valid = df[
        df["actual_price"].notna()
        & df["mileage_wan"].notna()
        & df["years"].notna()
        & (df["years"] > 0)
        & (df["years"] < 30)
        & (df["actual_price"] > 0)
    ].copy()
    print(f"有效数据: {len(valid)} 条")

    # 采样
    if SAMPLE_SIZE > 0 and SAMPLE_SIZE < len(valid):
        # 按价格段分层采样
        valid["price_seg"] = valid["actual_price"].apply(price_segment)
        seg_counts = valid["price_seg"].value_counts()
        sample_per_seg = max(1, SAMPLE_SIZE // len(seg_counts))
        sampled_parts = []
        for seg, count in seg_counts.items():
            n = min(count, max(1, round(SAMPLE_SIZE * count / len(valid))))
            sampled_parts.append(valid[valid["price_seg"] == seg].sample(n=n, random_state=42))
        sample = pd.concat(sampled_parts).sample(frac=1, random_state=42).reset_index(drop=True)
        # 截断到目标大小
        sample = sample.head(SAMPLE_SIZE)
        print(f"分层采样: {len(sample)} 条")
    else:
        sample = valid.reset_index(drop=True)
        print(f"全量测试: {len(sample)} 条")

    # 调用API
    results = []
    success_count = 0
    fail_count = 0

    print(f"\n开始调用API，共 {len(sample)} 条...\n")
    for i, row in sample.iterrows():
        idx = results.__len__() + 1
        if idx % 50 == 0 or idx == 1:
            print(f"  进度: {idx}/{len(sample)} ({idx/len(sample)*100:.1f}%)")

        api_result = call_predict_api(
            vehicle_full_name=row["vehicle_full_name"],
            brand_series=row["brand_series"],
            years=row["years"],
            grade=row["grade"],
            city=row["车辆所在地"],
            mileage=row["mileage_wan"],
        )

        record = {
            "idx": idx,
            "vehicle_name": row["车辆名称"],
            "brand": row["brand"],
            "series": row["series"],
            "brand_series": row["brand_series"],
            "actual_price": row["actual_price"],
            "grade": row["grade"],
            "rating_code": row["车辆评级"],
            "years": round(row["years"], 2),
            "mileage_wan": row["mileage_wan"],
            "city": row["车辆所在地"],
            "price_seg": price_segment(row["actual_price"]),
            "age_seg": age_segment(row["years"]),
        }

        if api_result.get("success"):
            success_count += 1
            prices = extract_prices(api_result)
            record.update(prices)

            # 命中判断 (c2b_b 区间)
            actual = row["actual_price"]
            c2b_l = prices["c2b_low"]
            c2b_h = prices["c2b_high"]
            b2b_l = prices["b2b_low"]
            b2b_h = prices["b2b_high"]

            record["hit_c2b"] = (
                c2b_l is not None and c2b_h is not None and c2b_l <= actual <= c2b_h
            )
            record["hit_b2b"] = (
                b2b_l is not None and b2b_h is not None and b2b_l <= actual <= b2b_h
            )

            pred = prices["predicted_price"]
            if pred and pred > 0:
                record["error"] = pred - actual
                record["abs_error"] = abs(pred - actual)
                record["pct_error"] = (pred - actual) / actual * 100
                record["abs_pct_error"] = abs(pred - actual) / actual * 100
            else:
                record["error"] = None
                record["abs_error"] = None
                record["pct_error"] = None
                record["abs_pct_error"] = None

            record["api_success"] = True
        else:
            fail_count += 1
            record["api_success"] = False
            record["error_message"] = api_result.get("error_message", "unknown")
            record["hit_c2b"] = False
            record["hit_b2b"] = False

        results.append(record)

        if SLEEP_BETWEEN_REQUESTS > 0:
            time.sleep(SLEEP_BETWEEN_REQUESTS)

    print(f"\nAPI调用完成: 成功={success_count}, 失败={fail_count}")

    # 保存详细结果
    results_df = pd.DataFrame(results)
    results_df.to_csv(RESULT_PATH, index=False, encoding="utf-8-sig")
    print(f"详细结果已保存: {RESULT_PATH}")

    # 统计分析
    stats = compute_stats(results_df)

    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"统计结果已保存: {STATS_PATH}")

    return stats, results_df


def compute_stats(df: pd.DataFrame) -> dict:
    """计算各维度统计指标"""
    success_df = df[df["api_success"] == True].copy()
    n_total = len(df)
    n_success = len(success_df)

    stats = {
        "总体": {
            "总样本数": n_total,
            "API成功数": n_success,
            "API成功率": round(n_success / n_total * 100, 2) if n_total > 0 else 0,
        }
    }

    if n_success == 0:
        return stats

    # 命中率
    hit_c2b = success_df["hit_c2b"].sum()
    hit_b2b = success_df["hit_b2b"].sum()
    stats["总体"]["C2B命中数"] = int(hit_c2b)
    stats["总体"]["C2B命中率(%)"] = round(hit_c2b / n_success * 100, 2)
    stats["总体"]["B2B命中数"] = int(hit_b2b)
    stats["总体"]["B2B命中率(%)"] = round(hit_b2b / n_success * 100, 2)

    # 误差指标
    err_df = success_df[success_df["abs_pct_error"].notna()].copy()
    if len(err_df) > 0:
        stats["总体"]["MAE(万元)"] = round(err_df["abs_error"].mean(), 3)
        stats["总体"]["MAPE(%)"] = round(err_df["abs_pct_error"].mean(), 2)
        stats["总体"]["中位数APE(%)"] = round(err_df["abs_pct_error"].median(), 2)
        stats["总体"]["R²"] = round(
            1 - err_df["abs_error"].pow(2).sum()
            / ((err_df["actual_price"] - err_df["actual_price"].mean()).pow(2).sum() + 1e-9),
            4,
        )

    # 按价格段
    seg_order = ["<1万", "1-3万", "3-5万", "5-10万", "10-20万", ">20万"]
    seg_stats = []
    for seg in seg_order:
        seg_df = success_df[success_df["price_seg"] == seg]
        if len(seg_df) == 0:
            continue
        n = len(seg_df)
        h = seg_df["hit_c2b"].sum()
        e_df = seg_df[seg_df["abs_pct_error"].notna()]
        seg_stats.append({
            "价格段": seg,
            "样本数": n,
            "命中数": int(h),
            "命中率(%)": round(h / n * 100, 1),
            "MAPE(%)": round(e_df["abs_pct_error"].mean(), 1) if len(e_df) > 0 else None,
        })
    stats["按价格段"] = seg_stats

    # 按车龄段
    age_order = ["0-3年", "3-5年", "5-8年", "8-10年", ">10年"]
    age_stats = []
    for seg in age_order:
        seg_df = success_df[success_df["age_seg"] == seg]
        if len(seg_df) == 0:
            continue
        n = len(seg_df)
        h = seg_df["hit_c2b"].sum()
        e_df = seg_df[seg_df["abs_pct_error"].notna()]
        age_stats.append({
            "车龄段": seg,
            "样本数": n,
            "命中数": int(h),
            "命中率(%)": round(h / n * 100, 1),
            "MAPE(%)": round(e_df["abs_pct_error"].mean(), 1) if len(e_df) > 0 else None,
        })
    stats["按车龄段"] = age_stats

    # 按评级
    grade_stats = []
    for grade in ["优", "中", "差"]:
        seg_df = success_df[success_df["grade"] == grade]
        if len(seg_df) == 0:
            continue
        n = len(seg_df)
        h = seg_df["hit_c2b"].sum()
        e_df = seg_df[seg_df["abs_pct_error"].notna()]
        grade_stats.append({
            "评级": grade,
            "样本数": n,
            "命中数": int(h),
            "命中率(%)": round(h / n * 100, 1),
            "MAPE(%)": round(e_df["abs_pct_error"].mean(), 1) if len(e_df) > 0 else None,
        })
    stats["按车况评级"] = grade_stats

    # 按品牌Top10
    brand_stats = []
    top_brands = success_df["brand"].value_counts().head(15).index
    for brand in top_brands:
        seg_df = success_df[success_df["brand"] == brand]
        n = len(seg_df)
        h = seg_df["hit_c2b"].sum()
        e_df = seg_df[seg_df["abs_pct_error"].notna()]
        brand_stats.append({
            "品牌": brand,
            "样本数": n,
            "命中数": int(h),
            "命中率(%)": round(h / n * 100, 1),
            "MAPE(%)": round(e_df["abs_pct_error"].mean(), 1) if len(e_df) > 0 else None,
        })
    stats["按品牌Top15"] = brand_stats

    # 典型案例
    if len(success_df) > 0:
        # 命中案例（误差最小的几条）
        hit_cases = success_df[success_df["hit_c2b"] == True].nsmallest(5, "abs_pct_error")
        miss_cases = success_df[success_df["hit_c2b"] == False].nsmallest(5, "abs_pct_error")

        def format_case(row):
            return {
                "车辆": row["vehicle_name"],
                "实际成交价(万)": row["actual_price"],
                "预测价(万)": row["predicted_price"],
                "C2B区间": f"[{row['c2b_low']}, {row['c2b_high']}]",
                "误差(%)": round(row["pct_error"], 1) if row["pct_error"] is not None else None,
                "命中": "✓" if row["hit_c2b"] else "✗",
                "车龄(年)": row["years"],
                "里程(万km)": row["mileage_wan"],
                "评级": row["rating_code"],
            }

        stats["命中案例"] = [format_case(r) for _, r in hit_cases.iterrows()]
        stats["未命中案例"] = [format_case(r) for _, r in miss_cases.iterrows()]

    return stats


if __name__ == "__main__":
    random.seed(42)
    np.random.seed(42)
    stats, results_df = run_evaluation()

    print("\n" + "=" * 60)
    print("测评结果摘要")
    print("=" * 60)
    g = stats["总体"]
    print(f"  样本数:      {g['总样本数']}")
    print(f"  API成功率:   {g['API成功率']}%")
    print(f"  C2B命中率:   {g.get('C2B命中率(%)', 'N/A')}%")
    print(f"  B2B命中率:   {g.get('B2B命中率(%)', 'N/A')}%")
    print(f"  MAE:         {g.get('MAE(万元)', 'N/A')} 万元")
    print(f"  MAPE:        {g.get('MAPE(%)', 'N/A')}%")
    print("=" * 60)
    print("详见 experiment/youxinpai_eval_stats.json")
