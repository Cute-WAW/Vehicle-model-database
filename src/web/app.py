"""
Web 调试界面
根据 .spec/spec_web_ui.md 规格实现
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn
import pandas as pd
import numpy as np
import math

from src.entity_extractor import EntityExtractor
from src.vehicle_index import VehicleIndex
from src.matching_engine import MatchingEngine


# Pydantic 请求模型
class MatchRequest(BaseModel):
    query: str
    top_k: int = 5
    min_score: float = 150.0


class ConfigUpdate(BaseModel):
    min_score: Optional[float] = None
    year_tolerance: Optional[int] = None
    top_k: Optional[int] = None


# FastAPI 应用
app = FastAPI(title="车型库匹配调试工具", version="1.0.0")

# 静态文件和模板
static_path = Path(__file__).parent / "static"
templates_path = Path(__file__).parent / "templates"

static_path.mkdir(exist_ok=True)
templates_path.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
templates = Jinja2Templates(directory=str(templates_path))

# 全局变量（延迟加载）
entity_extractor: Optional[EntityExtractor] = None
vehicle_index: Optional[VehicleIndex] = None
matching_engine: Optional[MatchingEngine] = None


def get_engine():
    """获取或初始化匹配引擎"""
    global entity_extractor, vehicle_index, matching_engine
    
    if matching_engine is None:
        config_path = project_root / "config" / "entity_rules.yaml"
        index_path = project_root / "index" / "vehicle_index.pkl"
        matching_config_path = project_root / "config" / "matching_config.yaml"
        
        entity_extractor = EntityExtractor(str(config_path))
        vehicle_index = VehicleIndex(entity_extractor)
        
        if index_path.exists():
            vehicle_index.load(str(index_path))
        else:
            # 构建索引
            import pandas as pd
            data_path = project_root / "data" / "力洋车型库精简5.csv"
            if data_path.exists():
                df = pd.read_csv(data_path)
                vehicle_index.build(df)
                index_path.parent.mkdir(exist_ok=True)
                vehicle_index.save(str(index_path))
        
        matching_engine = MatchingEngine(
            entity_extractor, 
            vehicle_index, 
            str(matching_config_path)
        )
    
    return matching_engine


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """主页"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/analysis", response_class=HTMLResponse)
async def analysis_page(request: Request):
    """分析报告页面"""
    return templates.TemplateResponse("analysis.html", {"request": request})

@app.get("/api/analysis/report")
async def get_analysis_report():
    """获取分析报告数据"""
    csv_path = project_root / 'output' / 'batch_modeling_results.csv'
    
    if not csv_path.exists():
        return {"error": "数据文件不存在"}
    
    try:
        df = pd.read_csv(csv_path)
        
        # 强制转换数值列，处理类似 '0+.39' 的脏数据
        numeric_cols = ['误差率', '误差', '使用年限', '二手车的成交价', '新车的价格', '行驶里程', '预测值']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        df['abs_error_pct'] = df['误差率'].abs()
        
        # 辅助函数：安全浮点数转换（处理 NaN/Inf）
        def safe_float(val):
            if pd.isna(val) or np.isinf(val):
                return 0.0
            return float(val)

        # 1. 核心指标
        summary = {
            "total": int(len(df)),
            "mape": safe_float(df['abs_error_pct'].mean()),
            "acc_20": safe_float((df['abs_error_pct'] <= 0.20).mean()),
            "avg_bias": safe_float(df['误差'].mean())
        }
        
        # 2. 品牌分析 (Top 10)
        brand_stats = df.groupby('品牌车系').agg({
            '车辆全称': 'count',
            'abs_error_pct': 'mean'
        }).reset_index()
        brand_stats.columns = ['name', 'count', 'mape']
        top_brands = brand_stats[brand_stats['count'] >= 5].sort_values('count', ascending=False).head(10)
        
        # 处理品牌数据中的 NaN
        brands_data = []
        for _, row in top_brands.iterrows():
            brands_data.append({
                "name": str(row['name']),
                "count": int(row['count']),
                "mape": safe_float(row['mape'])
            })
        
        # 3. 车龄曲线
        df['age_group'] = pd.cut(df['使用年限'], bins=[0, 1, 3, 5, 8, 10, 20], labels=['0-1年', '1-3年', '3-5年', '5-8年', '8-10年', '10年以上'])
        
        df['保值率'] = df['二手车的成交价'] / df['新车的价格']
        # 过滤掉无效的保值率
        df_valid_rate = df[np.isfinite(df['保值率'])]
        
        age_stats = df_valid_rate.groupby('age_group', observed=True).agg({'保值率': 'mean'}).reset_index()
        age_curve = [{"group": str(row['age_group']), "rate": safe_float(row['保值率'])} for _, row in age_stats.iterrows() if pd.notna(row['保值率'])]
        
        # 4. 异常案例
        anomalies = df.sort_values('abs_error_pct', ascending=False).head(5)
        anomalies_data = []
        for _, row in anomalies.iterrows():
            anomalies_data.append({
                "name": str(row['车辆全称']),
                "year": safe_float(row['使用年限']),
                "mileage": safe_float(row['行驶里程']) if '行驶里程' in row else 0.0,
                "city": str(row['城市']) if '城市' in row and pd.notna(row['城市']) else "未知",
                "actual": safe_float(row['二手车的成交价']),
                "pred": safe_float(row['预测值']),
                "error_pct": safe_float(row['abs_error_pct']),
                "bias": safe_float(row['误差'])
            })
            
        return {
            "summary": summary,
            "brands": brands_data,
            "age_curve": age_curve,
            "anomalies": anomalies_data
        }
    except Exception as e:
        print(f"Error analyzing report: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.post("/api/match")
async def match(request: MatchRequest):
    """匹配接口"""
    engine = get_engine()
    result = engine.match(
        request.query,
        top_k=request.top_k,
        min_score=request.min_score
    )
    return result.to_dict()


@app.get("/api/extract")
async def extract(q: str):
    """仅实体识别"""
    engine = get_engine()
    entities = engine.entity_extractor.extract(q)
    return entities.to_dict()


@app.get("/api/health")
async def health():
    """健康检查"""
    engine = get_engine()
    return {
        "status": "ok",
        "index_size": len(engine.vehicle_index.detail_store),
        "brands_count": len(engine.vehicle_index.brand_index),
        "series_count": len(engine.vehicle_index.series_index)
    }


@app.get("/api/config")
async def get_config():
    """获取当前配置"""
    engine = get_engine()
    return {
        "min_score": engine.min_score,
        "high_confidence": engine.high_confidence,
        "weights": engine.weights,
        "fuzzy_rules": engine.fuzzy_rules
    }


@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    """更新配置"""
    engine = get_engine()
    
    if update.min_score is not None:
        engine.min_score = update.min_score
    if update.year_tolerance is not None:
        if "year" not in engine.fuzzy_rules:
            engine.fuzzy_rules["year"] = {}
        engine.fuzzy_rules["year"]["tolerance"] = update.year_tolerance
    
    return {"message": "配置已更新", "config": await get_config()}


if __name__ == "__main__":
    import os
    os.chdir(project_root)
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
