"""
二手车残值预测 Web 调试接口

功能：
1. 提供 POST /predict 端点进行残值预测
2. 返回完整调试信息
3. 支持批量预测

启动方式：
    cd d:/antigravity/price_evaluation/车型库映射/src
    python web_predictor_debug.py
    
    # 或指定端口
    python web_predictor_debug.py --port 8087

访问：
    http://localhost:8087/
    http://localhost:8087/docs (API文档)
"""

import argparse
import logging
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn

# 切换到正确的工作目录
import os
os.chdir(Path(__file__).parent.parent)

from residual_predictor_step5 import ResidualPredictor, ResidualPredictionResult
from price_logic_step6 import explain_price
from db_supabase import verify_user, create_user

# 微信小程序 API
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'wechat' / 'backend'))
try:
    from api import router as wechat_router
    WECHAT_API_ENABLED = True
except ImportError as e:
    print(f"Warning: WeChat API not loaded: {e}")
    WECHAT_API_ENABLED = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============= API 模型定义 =============

class PredictRequest(BaseModel):
    """预测请求"""
    vehicle_full_name: str = Field(..., description="车辆全称", example="起亚 K3 2013款 1.6 手自一体 GLS")
    brand_series: str = Field(..., description="品牌-车系", example="起亚-K3")
    years: float = Field(..., description="使用年限", example=11.67)
    grade: str = Field("中", description="车辆评级", example="中")
    city: str = Field("", description="城市", example="成都")
    mileage: float = Field(0.0, description="行驶里程(万公里)", example=19.95)
    new_price: Optional[float] = Field(None, description="新车价格(万元)，不传则自动推断")


class AuthRequest(BaseModel):
    """认证请求"""
    username: str
    password: str


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str
    password: str
    nickname: Optional[str] = "用户"
    email: Optional[str] = None


class SimilarVehicleInfo(BaseModel):
    """相近车辆信息"""
    vehicle_full_name: str
    used_price: float
    adjusted_price: float
    years: float
    score: float
    matched_features: List[str]


class DebugInfo(BaseModel):
    """调试信息"""
    model_used: str
    model_name: str
    model_type: str
    model_r2: float
    model_prediction: float
    similar_vehicles: List[dict]
    similar_avg_price: float
    adjustment_method: str
    adjustment_params: dict
    adjustment_delta: float


class IdenticalRecord(BaseModel):
    """完全相同的记录"""
    vehicle_full_name: str
    used_price: float
    adjusted_price: float
    years: float
    city: str



class PredictResponse(BaseModel):
    """预测响应"""
    success: bool
    predicted_price: float = 0.0
    new_price: float = 0.0
    residual_rate: float = 0.0
    price_matrix: dict = {}
    identical_records: List[dict] = []
    debug: Optional[dict] = None
    explanation: Optional[dict] = None  # 价格解释报告
    error_message: str = ""


class BatchPredictRequest(BaseModel):
    """批量预测请求"""
    items: List[PredictRequest]


class BatchPredictResponse(BaseModel):
    """批量预测响应"""
    results: List[PredictResponse]


class ModelListResponse(BaseModel):
    """模型列表响应"""
    brand_series_models: List[str]
    car_type_models: List[str]


# ============= FastAPI 应用 =============

app = FastAPI(
    title="二手车残值预测 API",
    description="提供基于机器学习模型的二手车残值预测服务",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局预测器实例
predictor: Optional[ResidualPredictor] = None


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化预测器"""
    global predictor
    logger.info("初始化残值预测器...")
    
    # 切换回之前的总体数据
    # data_path = Path("output/batch_modeling_results.csv").absolute()
    # data_path = Path("output/residual_value_data_for_build_model.csv").absolute()
    data_path = Path("output/merged_residual_value_data.csv").absolute()
    
    if not data_path.exists():
        logger.warning(f"文件不存在: {data_path}，尝试使用备用文件")
        data_path = Path("output/batch_modeling_results.csv").absolute()
        
    logger.info(f"使用数据文件: {data_path}")
    
    # 注意：如果 residual_data_index.pkl 已存在且未包含 source 字段，
    # ResidualDataIndex 需要被强制重建才能生效。
    # 这里我们简单地依靠 ResidualDataIndex 的缓存检查机制（mtime check）。
    # 如果 batch_modeling_results.csv 是新的，它应该会触发重建。
    
    predictor = ResidualPredictor(residual_data_csv=str(data_path))
    logger.info("预测器初始化完成")
    
    # 集成微信小程序 API
    if WECHAT_API_ENABLED:
        app.include_router(wechat_router)
        logger.info("微信小程序 API 已加载: /api/*")


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """登录页面"""
    login_html_path = Path(__file__).parent / 'web' / 'templates' / 'login.html'
    if login_html_path.exists():
        return HTMLResponse(content=login_html_path.read_text(encoding='utf-8'))
    return HTMLResponse(content="<h1>Login Page Not Found</h1>", status_code=404)


@app.post("/api/auth/login")
async def api_login(request: AuthRequest):
    """用户登录接口"""
    success, user, message = verify_user(request.username, request.password)
    if success:
        return {"success": True, "token": "mock-token-for-now", "user": user, "message": message}
    return {"success": False, "message": message}


@app.get("/register", response_class=HTMLResponse)
async def register_page():
    """注册页面"""
    register_html_path = Path(__file__).parent / 'web' / 'templates' / 'register.html'
    if register_html_path.exists():
        return HTMLResponse(content=register_html_path.read_text(encoding='utf-8'))
    return HTMLResponse(content="<h1>Register Page Not Found</h1>", status_code=404)


@app.post("/api/auth/register")
async def api_register(request: RegisterRequest):
    """用户注册接口"""
    success, message = create_user(
        username=request.username, 
        password=request.password,
        nickname=request.nickname,
        email=request.email
    )
    if success:
        return {"success": True, "message": message}
    return {"success": False, "message": message}


@app.get("/", response_class=HTMLResponse)
async def root():
    """首页 - 提供简单的测试界面"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>二手车残值预测</title>
        <style>
            body { font-family: 'Segoe UI', Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
            h1 { color: #333; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; color: #555; }
            input, select { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
            button { background: #4CAF50; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; font-size: 16px; }
            button:hover { background: #45a049; }
            #result { margin-top: 20px; padding: 20px; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .section { margin-bottom: 20px; padding: 15px; background: #f9f9f9; border-radius: 4px; }
            .section h3 { margin-top: 0; color: #333; }
            .price { font-size: 24px; color: #4CAF50; font-weight: bold; }
            .debug-item { margin: 5px 0; padding: 5px; background: #fff; border-left: 3px solid #4CAF50; }
            pre { background: #f0f0f0; padding: 10px; overflow-x: auto; border-radius: 4px; }
            .similar-vehicle { padding: 8px; margin: 5px 0; background: #fff; border: 1px solid #eee; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>🚗 二手车残值预测</h1>
        
        <div class="section">
            <h3>输入车辆信息</h3>
            <div class="form-group">
                <label>车辆全称</label>
                <input type="text" id="vehicle_full_name" value="起亚 K3 2013款 1.6 手自一体 GLS">
            </div>
            <div class="form-group">
                <label>品牌-车系</label>
                <input type="text" id="brand_series" value="起亚-K3">
            </div>
            <div class="form-group">
                <label>使用年限</label>
                <input type="number" id="years" step="0.1" value="11.67">
            </div>
            <div class="form-group">
                <label>车辆评级</label>
                <select id="grade">
                    <option value="优">优</option>
                    <option value="中" selected>中</option>
                    <option value="差">差</option>
                </select>
            </div>
            <div class="form-group">
                <label>城市</label>
                <input type="text" id="city" value="成都">
            </div>
            <div class="form-group">
                <label>行驶里程(万公里)</label>
                <input type="number" id="mileage" step="0.1" value="19.95">
            </div>
            <div class="form-group">
                <label>新车价格(万元，可选)</label>
                <input type="number" id="new_price" step="0.01" placeholder="留空则自动推断">
            </div>
            <button onclick="predict()">预测残值</button>
            <button onclick="randomNext()" style="background: #2196F3; margin-left: 10px;">随机下一辆</button>
        </div>
        
        <div id="result" style="display: none;"></div>
        
        <script>
            async function predict() {
                const data = {
                    vehicle_full_name: document.getElementById('vehicle_full_name').value,
                    brand_series: document.getElementById('brand_series').value,
                    years: parseFloat(document.getElementById('years').value),
                    grade: document.getElementById('grade').value,
                    city: document.getElementById('city').value,
                    mileage: parseFloat(document.getElementById('mileage').value)
                };
                
                const newPrice = document.getElementById('new_price').value;
                if (newPrice) {
                    data.new_price = parseFloat(newPrice);
                }
                
                const resultDiv = document.getElementById('result');
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<p>预测中...</p>';
                
                try {
                    const response = await fetch('/predict', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data)
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        let html = `
                            <div class="section">
                                <h3>📊 预测结果</h3>
                                <p class="price">预测价格: ${result.predicted_price} 万元</p>
                                <p>新车价格: ${result.new_price} 万元</p>
                                <p>残值率: ${(result.residual_rate * 100).toFixed(1)}%</p>
                            </div>
                        `;
                        
                        if (result.price_matrix && result.price_matrix.b2BPrices) {
                            // 提取价格用于展示
                            const c2b = result.price_matrix.c2BPrices.b.mid;
                            const b2b = result.price_matrix.b2BPrices.b.mid;
                            const b2c = result.price_matrix.b2CPrices.b.mid;
                            
                            // 价格区间分布条
                            const currentGrade = document.getElementById('grade').value;
                            const gradeMap = { '优': 'a', '中': 'b', '差': 'c' };
                            const targetCol = gradeMap[currentGrade];

                            // 完整价格矩阵表
                            html += `
                                <div class="section">
                                    <h3>详细价格矩阵</h3>
                                    <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px;">
                                        <thead>
                                            <tr style="background: #f0f0f0;">
                                                <th style="padding: 10px; border: 1px solid #ddd; text-align: left;">交易类型</th>
                                                <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">优 (A级)</th>
                                                <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">中 (B级)</th>
                                                <th style="padding: 10px; border: 1px solid #ddd; text-align: center;">差 (C级)</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                            `;
                            
                            const types = [
                                { key: 'c2BPrices', name: '车商收购 (C2B)' },
                                { key: 'b2BPrices', name: '车商交易 (B2B)' },
                                { key: 'b2CPrices', name: '车商零售 (B2C)' }
                            ];
                            
                            types.forEach(t => {
                                const data = result.price_matrix[t.key];
                                if (data) {
                                    // 样式生成函数
                                    const getStyle = (col) => {
                                        let s = 'padding: 10px; border: 1px solid #ddd; text-align: center;';
                                        
                                        // 默认 B 级列背景
                                        if (col === 'b') s += ' background: #fffbe6;';
                                        
                                        // B2B 行且匹配当前评级的高亮
                                        if (t.key === 'b2BPrices' && col === targetCol) {
                                            s += ' font-weight: 900; color: black; border: 2px solid #333; transform: scale(1.05); box-shadow: 0 4px 8px rgba(0,0,0,0.1); background: #fff59d;'; 
                                            // 覆盖上面的背景，使用更明显的黄色
                                        }
                                        return s;
                                    };

                                    html += `<tr>
                                        <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold;">${t.name}</td>
                                        <td style="${getStyle('a')}">
                                            <div style="font-size: 1.1em;">${data.a.mid}</div>
                                            <div style="color: #666; font-size: 12px;">${data.a.low} ~ ${data.a.up}</div>
                                        </td>
                                        <td style="${getStyle('b')}">
                                            <div style="font-size: 1.1em;">${data.b.mid}</div>
                                            <div style="color: #666; font-size: 12px;">${data.b.low} ~ ${data.b.up}</div>
                                        </td>
                                        <td style="${getStyle('c')}">
                                            <div style="font-size: 1.1em;">${data.c.mid}</div>
                                            <div style="color: #666; font-size: 12px;">${data.c.low} ~ ${data.c.up}</div>
                                        </td>
                                    </tr>`;
                                }
                            });
                            
                            html += `
                                        </tbody>
                                    </table>
                                </div>
                            `;
                        }

                        // 完全相同记录 - 放在预测结果后面
                        if (result.identical_records && result.identical_records.length > 0) {
                            html += '<div class="section"><h3>📋 完全相同记录</h3>';
                            result.identical_records.forEach(r => {
                                // 计算差值百分比: |(成交价-预测价格)/成交价|
                                const errorPct = Math.abs((r.used_price - result.predicted_price) / r.used_price * 100).toFixed(1);
                                
                                // 判断是否在预测区间内
                                let rangeTag = '';
                                let bgStyle = 'background: #fff;';
                                if (r.in_range) {
                                    rangeTag = '<span style="background: #e8f5e9; color: #2e7d32; padding: 2px 6px; border-radius: 4px; margin-left: 10px; font-weight: bold; border: 1px solid #c8e6c9;">✅ 在预测区间内</span>';
                                    bgStyle = 'background: #f1f8e9; border: 1px solid #81c784;';
                                }
                                
                                html += `
                                    <div class="similar-vehicle" style="${bgStyle}">
                                        成交价: <strong>${r.used_price}万</strong> | 城市: ${r.city} | 年限: ${r.years}年 | 来源: ${r.source || 'unknown'} |
                                        <span style="color: ${parseFloat(errorPct) < 10 ? '#4CAF50' : parseFloat(errorPct) < 20 ? '#FF9800' : '#f44336'}; font-weight: bold;">
                                            误差: ${errorPct}%
                                        </span>
                                        ${rangeTag}
                                    </div>
                                `;
                            });
                            html += '</div>';
                        }
                        
                        // 价格解释报告
                        if (result.explanation) {
                            const exp = result.explanation;
                            html += `
                                <div class="section" style="background: linear-gradient(135deg, #e8f5e9 0%, #f1f8e9 100%); border: 2px solid #81c784;">
                                    <h3>📊 价格解释</h3>
                                    <p style="font-size: 14px; color: #666; margin-bottom: 15px;">${exp.summary}</p>
                                    <p><strong>置信度:</strong> <span style="color: ${exp.confidence === 'high' ? '#4CAF50' : exp.confidence === 'medium' ? '#FF9800' : '#f44336'};">${exp.confidence === 'high' ? '⭐⭐⭐ 高' : exp.confidence === 'medium' ? '⭐⭐ 中' : '⭐ 低'}</span></p>
                            `;
                            
                            if (exp.factors && exp.factors.length > 0) {
                                html += '<h4 style="margin-top: 15px;">🔍 影响因素</h4>';
                                exp.factors.forEach(f => {
                                    const deltaColor = f.delta >= 0 ? '#4CAF50' : '#f44336';
                                    const deltaSign = f.delta >= 0 ? '+' : '';
                                    html += `
                                        <div class="debug-item" style="display: flex; justify-content: space-between; align-items: center;">
                                            <span><strong>${f.label}</strong>: ${f.reason}</span>
                                            <span style="color: ${deltaColor}; font-weight: bold; white-space: nowrap; margin-left: 10px;">${deltaSign}${f.delta.toFixed(2)}万</span>
                                        </div>
                                    `;
                                });
                            }
                            html += '</div>';
                        }
                        
                        if (result.debug) {
                            const d = result.debug;
                            html += `
                                <div class="section">
                                    <h3>🔧 模型信息</h3>
                                    <div class="debug-item">使用模型: ${d.model_used}</div>
                                    <div class="debug-item">模型名称: ${d.model_name}</div>
                                    <div class="debug-item">模型类型: ${d.model_type}</div>
                                    <div class="debug-item">模型预测: ${d.model_prediction} 万元</div>
                                    <div class="debug-item">模型R²: ${d.model_r2.toFixed(4)}</div>
                                </div>
                                
                                <div class="section">
                                    <h3>⚙️ 价格调整</h3>
                                    <div class="debug-item">调整方法: ${d.adjustment_method}</div>
                                    <div class="debug-item">相近车辆均价: ${d.similar_avg_price} 万元</div>
                                    <div class="debug-item">调整参数: 偏差=${d.adjustment_params.deviation || 0}, 置信度=${d.adjustment_params.confidence || 0}, δ=${d.adjustment_params.delta || 0}</div>
                                    <div class="debug-item">调整量: ${d.adjustment_delta} 万元</div>
                                </div>
                            `;
                            
                            if (d.similar_vehicles && d.similar_vehicles.length > 0) {
                                html += '<div class="section"><h3>🚙 相近车辆</h3>';
                                d.similar_vehicles.forEach((v, idx) => {
                                    // 根据价格差异设置背景色
                                    const priceDiff = Math.abs(v.adjusted_price - result.predicted_price);
                                    const diffPct = (priceDiff / result.predicted_price * 100).toFixed(0);
                                    let bgColor = '#f5f5f5';
                                    let borderColor = '#e0e0e0';
                                    if (diffPct < 5) {
                                        bgColor = '#e8f5e9'; borderColor = '#81c784'; // 绿色 - 非常接近
                                    } else if (diffPct < 15) {
                                        bgColor = '#fff8e1'; borderColor = '#ffd54f'; // 黄色 - 接近
                                    }
                                    
                                    // 评级颜色
                                    const gradeColors = {'优': '#4CAF50', '中': '#FF9800', '差': '#f44336'};
                                    const gradeColor = gradeColors[v.grade] || '#999';
                                    
                                    html += `
                                        <div style="background: ${bgColor}; border: 1px solid ${borderColor}; border-radius: 8px; padding: 12px 15px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);">
                                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                                                <strong style="color: #333; font-size: 14px;">${v.vehicle_full_name}</strong>
                                                <span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500;">匹配 ${v.score}分</span>
                                            </div>
                                            <div style="display: flex; flex-wrap: wrap; gap: 10px; font-size: 13px; color: #555;">
                                                <span style="background: #fff; padding: 3px 10px; border-radius: 4px; border: 1px solid #ddd;">
                                                    💰 <strong style="color: #e65100;">${v.adjusted_price}万</strong>
                                                </span>
                                                <span style="background: #fff; padding: 3px 10px; border-radius: 4px; border: 1px solid #ddd;">
                                                    📅 ${v.years}年
                                                </span>
                                                <span style="background: #fff; padding: 3px 10px; border-radius: 4px; border: 1px solid ${gradeColor};">
                                                    ⭐ <span style="color: ${gradeColor}; font-weight: 500;">${v.grade || '-'}</span>
                                                </span>
                                                <span style="background: #fff; padding: 3px 10px; border-radius: 4px; border: 1px solid #ddd;">
                                                    📍 ${v.city || '-'}
                                                </span>
                                                <span style="background: #fff; padding: 3px 10px; border-radius: 4px; border: 1px solid #ddd;">
                                                    🛣️ ${v.mileage || 0}万km
                                                </span>
                                                <span style="background: #e3f2fd; padding: 3px 10px; border-radius: 4px; border: 1px solid #90caf9; color: #1565c0;">
                                                    📂 ${v.source || 'unknown'}
                                                </span>
                                            </div>
                                            <div style="margin-top: 8px; font-size: 11px; color: #888;">
                                                匹配项: ${v.matched_features.slice(0, 5).join(' • ')}${v.matched_features.length > 5 ? '...' : ''}
                                            </div>
                                        </div>
                                    `;
                                });
                                html += '</div>';
                            }
                        }
                        
                        resultDiv.innerHTML = html;
                    } else {
                        resultDiv.innerHTML = `<p style="color: red;">预测失败: ${result.error_message}</p>`;
                    }
                } catch (e) {
                    resultDiv.innerHTML = `<p style="color: red;">请求失败: ${e.message}</p>`;
                }
            }
            
            async function randomNext() {
                try {
                    const response = await fetch('/random_vehicle');
                    const v = await response.json();
                    
                    if (v.success) {
                        // 填充表单
                        document.getElementById('vehicle_full_name').value = v.vehicle_full_name;
                        document.getElementById('brand_series').value = v.brand_series;
                        document.getElementById('years').value = v.years;
                        document.getElementById('grade').value = v.grade;
                        document.getElementById('city').value = v.city;
                        document.getElementById('mileage').value = v.mileage;
                        document.getElementById('new_price').value = v.new_price || '';
                        
                        // 自动执行预测
                        await predict();
                    } else {
                        alert('获取随机车辆失败');
                    }
                } catch (e) {
                    alert('请求失败: ' + e.message);
                }
            }
        </script>
    </body>
    </html>
    """
    return html


@app.post("/predict", response_model=PredictResponse)
async def predict(request: PredictRequest):
    """
    预测二手车残值价格
    
    - **vehicle_full_name**: 车辆全称，如 "起亚 K3 2013款 1.6 手自一体 GLS"
    - **brand_series**: 品牌-车系，如 "起亚-K3"
    - **years**: 使用年限
    - **grade**: 车辆评级（优/中/差）
    - **city**: 城市
    - **mileage**: 行驶里程（万公里）
    - **new_price**: 新车价格（万元），可选，不传则自动推断
    """
    if predictor is None:
        raise HTTPException(status_code=500, detail="预测器未初始化")
    
    result = predictor.predict(
        vehicle_full_name=request.vehicle_full_name,
        brand_series=request.brand_series,
        years=request.years,
        grade=request.grade,
        city=request.city,
        mileage=request.mileage,
        new_price=request.new_price
    )
    
    # 生成价格解释报告
    response_data = result.to_dict()
    if result.success:
        try:
            report = explain_price(
                result,
                years=request.years,
                mileage=request.mileage,
                grade=request.grade
            )
            response_data['explanation'] = report.to_dict()
        except Exception as e:
            logger.warning(f"生成价格解释失败: {e}")
            response_data['explanation'] = None
    
    return response_data


@app.post("/batch_predict", response_model=BatchPredictResponse)
async def batch_predict(request: BatchPredictRequest):
    """批量预测"""
    if predictor is None:
        raise HTTPException(status_code=500, detail="预测器未初始化")
    
    results = []
    for item in request.items:
        result = predictor.predict(
            vehicle_full_name=item.vehicle_full_name,
            brand_series=item.brand_series,
            years=item.years,
            grade=item.grade,
            city=item.city,
            mileage=item.mileage,
            new_price=item.new_price
        )
        results.append(result.to_dict())
    
    return {"results": results}


@app.get("/random_vehicle")
async def random_vehicle():
    """获取随机一辆车的信息"""
    import random
    
    if predictor is None:
        raise HTTPException(status_code=500, detail="预测器未初始化")
    
    records = predictor.data_index.records
    if not records:
        return {"success": False, "error": "没有可用的车辆数据"}
    
    # 随机选择一条记录
    record = random.choice(records)
    
    return {
        "success": True,
        "vehicle_full_name": record.vehicle_full_name,
        "brand_series": record.brand_series,
        "years": record.years,
        "grade": record.grade,
        "city": record.city,
        "mileage": record.mileage,
        "new_price": record.new_price
    }


@app.get("/models", response_model=ModelListResponse)
async def list_models():
    """获取可用的模型列表"""
    if predictor is None:
        raise HTTPException(status_code=500, detail="预测器未初始化")
    
    return {
        "brand_series_models": predictor.get_available_brand_series(),
        "car_type_models": predictor.get_available_car_types()
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "predictor_ready": predictor is not None}


def main():
    parser = argparse.ArgumentParser(description='二手车残值预测 Web 服务')
    parser.add_argument('--port', type=int, default=8087, help='服务端口')
    parser.add_argument('--host', default='0.0.0.0', help='绑定地址')
    
    args = parser.parse_args()
    
    print(f"\n🚗 二手车残值预测服务")
    print(f"   地址: http://localhost:{args.port}")
    print(f"   文档: http://localhost:{args.port}/docs")
    print()
    
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
