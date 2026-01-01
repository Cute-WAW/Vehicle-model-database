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
