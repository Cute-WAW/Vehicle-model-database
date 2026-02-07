import sys
import os
from pathlib import Path
import pandas as pd

script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir))
os.chdir(script_dir)

from src.entity_extractor import EntityExtractor
from src.vehicle_index import VehicleIndex
from src.matching_engine import MatchingEngine

def load_index():
    extractor = EntityExtractor("config/entity_rules.yaml")
    index = VehicleIndex(extractor)
    idx_path = Path("index/vehicle_index.pkl")
    if idx_path.exists():
        print("加载现有车型库索引...")
        index.load(str(idx_path))
    else:
        print("索引不存在，请先运行: python scripts\\build_index.py")
        raise SystemExit(1)
    return extractor, index

def main():
    inp = r"tests\cheyipai_more_data_clean.csv"
    outp = r"output\unmatched_cheyipai_more.csv"
    os.makedirs("output", exist_ok=True)

    try:
        df = pd.read_csv(inp)
    except UnicodeDecodeError:
        df = pd.read_csv(inp, encoding="gbk")

    print(f"输入记录数: {len(df)}")

    extractor, index = load_index()
    engine = MatchingEngine(extractor, index)

    vehicle_col = "车型" if "车型" in df.columns else df.columns[0]
    unmatched_rows = []

    for _, row in df.iterrows():
        vehicle_name = str(row[vehicle_col]).strip()
        if not vehicle_name or vehicle_name.startswith("中升车源") or len(vehicle_name) < 5:
            continue
        result = engine.match(vehicle_name, top_k=1)
        if not result.matches:
            unmatched_rows.append(row)

    if unmatched_rows:
        out_df = pd.DataFrame(unmatched_rows, columns=df.columns)
        # 优先用 gbk 保存，便于与源文件一致
        try:
            out_df.to_csv(outp, index=False, encoding="gbk")
        except Exception:
            out_df.to_csv(outp, index=False)
        print(f"未匹配记录数: {len(out_df)}")
        print(f"已导出到: {outp}")
    else:
        print("所有记录均已匹配")

if __name__ == "__main__":
    main()
