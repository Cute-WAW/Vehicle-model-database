"""
二手车残值预测 Web 调试接口

功能：
1. 提供 POST /predict 端点进行残值预测
2. 返回完整调试信息
3. 支持批量预测
4. 用户认证与权限管理

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
from typing import Optional, List, Union, Any
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import uuid
import base64
import random
import string
from captcha.image import ImageCaptcha

# 切换到正确的工作目录
import os
os.chdir(Path(__file__).parent.parent)

from residual_predictor_step5 import ResidualPredictor, ResidualPredictionResult
from price_logic_step6 import explain_price
from db_supabase import (
    verify_user, create_user, change_password, delete_user,
    add_history_record, toggle_favorite, get_user_history, delete_history_records
)

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
    captcha_id: str
    captcha_code: str


class CaptchaResponse(BaseModel):
    captcha_id: str
    image: str


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str
    password: str
    nickname: Optional[str] = "用户"
    email: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str

class DeleteHistoryRequest(BaseModel):
    """批量删除历史记录请求"""
    record_ids: List[Union[int, str]]

class DeleteAccountRequest(BaseModel):
    """注销账号请求"""
    password: str

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
    new_price: Optional[float] = 0.0
    residual_rate: float = 0.0
    price_matrix: dict = {}
    identical_records: List[dict] = []
    debug: Optional[dict] = None
    explanation: Optional[dict] = None  # 价格解释报告
    error_message: str = ""
    record_id: Optional[Union[int, str]] = None
    is_favorite: bool = False


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

# 添加 Session 中间件
# 注意：在生产环境中应该使用更安全的 SECRET_KEY，并将其放在环境变量中
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-here", max_age=86400) # 24小时过期

# 挂载静态文件
static_path = Path(__file__).parent / 'web' / 'static'
if not static_path.exists():
    # 尝试在开发环境中查找
    static_path = Path("src/web/static").absolute()

if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
else:
    logger.warning(f"静态文件目录未找到: {static_path}")

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
    
    # 优先使用融合后的数据
    path_with_dates = Path("output/merged_residual_value_data_with_dates.csv").absolute()
    path_cheyipai = Path("output/cheyipai_more_residual_value.csv").absolute()
    path_default = Path("output/merged_residual_value_data.csv").absolute()
    
    if path_with_dates.exists():
        data_path = path_with_dates
    elif path_cheyipai.exists():
        data_path = path_cheyipai
    elif path_default.exists():
        data_path = path_default
    else:
        logger.warning(f"主要数据文件不存在，尝试使用备用文件")
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


# Captcha store (In-memory for simplicity)
CAPTCHA_STORE = {}


# ============= 认证依赖 =============

async def get_current_user(request: Request):
    """获取当前登录用户"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
        )
    return user

async def login_required(request: Request):
    """页面访问需要登录，否则跳转"""
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")
    return user


# ============= 页面路由 =============

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    # 如果已登录，跳转到首页
    if request.session.get("user"):
        return RedirectResponse(url="/")
        
    login_html_path = Path(__file__).parent / 'web' / 'templates' / 'login.html'
    if login_html_path.exists():
        return HTMLResponse(content=login_html_path.read_text(encoding='utf-8'))
    return HTMLResponse(content="<h1>Login Page Not Found</h1>", status_code=404)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """注册页面"""
    if request.session.get("user"):
        return RedirectResponse(url="/")
        
    register_html_path = Path(__file__).parent / 'web' / 'templates' / 'register.html'
    if register_html_path.exists():
        return HTMLResponse(content=register_html_path.read_text(encoding='utf-8'))
    return HTMLResponse(content="<h1>Register Page Not Found</h1>", status_code=404)


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    """用户中心页面"""
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")
        
    profile_html_path = Path(__file__).parent / 'web' / 'templates' / 'profile.html'
    if profile_html_path.exists():
        return HTMLResponse(content=profile_html_path.read_text(encoding='utf-8'))
        
    # 如果模板不存在，先返回简单的HTML
    return HTMLResponse(content=f"""
    <html>
        <body>
            <h1>User Profile</h1>
            <p>Welcome, {user['nickname']} ({user['username']})</p>
            <a href="/">Back to Home</a>
        </body>
    </html>
    """)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """首页 - 提供简单的测试界面 (需要登录)"""
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")
        
    home_html_path = Path(__file__).parent / 'web' / 'templates' / 'home.html'
    if home_html_path.exists():
        return HTMLResponse(content=home_html_path.read_text(encoding='utf-8'))
    
    # Fallback to simple HTML if template not found
    return HTMLResponse(content="""
    <html>
        <body>
            <h1>Error: home.html not found</h1>
            <p>Please check src/web/templates/home.html</p>
        </body>
    </html>
    """)


# ============= API 路由 =============

@app.get("/api/auth/captcha", response_model=CaptchaResponse)
async def generate_captcha():
    """生成验证码"""
    # Generate 4-char random code
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    
    # Generate image
    image = ImageCaptcha(width=160, height=60)
    data = image.generate(code)
    
    # Encode to base64
    image_base64 = base64.b64encode(data.read()).decode('utf-8')
    
    # Generate ID and store
    captcha_id = str(uuid.uuid4())
    CAPTCHA_STORE[captcha_id] = code.lower()
    
    return CaptchaResponse(captcha_id=captcha_id, image=image_base64)


@app.post("/api/auth/login")
async def api_login(request: Request, auth_data: AuthRequest):
    """用户登录接口"""
    # Verify captcha
    stored_code = CAPTCHA_STORE.get(auth_data.captcha_id)
    
    if not stored_code:
        return {"success": False, "message": "验证码已过期，请刷新"}
        
    if stored_code != auth_data.captcha_code.lower():
        # Clean up used captcha to prevent brute force on same captcha
        if auth_data.captcha_id in CAPTCHA_STORE:
            del CAPTCHA_STORE[auth_data.captcha_id]
        return {"success": False, "message": "验证码错误"}
    
    # Clean up used captcha
    if auth_data.captcha_id in CAPTCHA_STORE:
        del CAPTCHA_STORE[auth_data.captcha_id]

    success, user, message = verify_user(auth_data.username, auth_data.password)
    if success:
        request.session["user"] = user
        return {"success": True, "token": "session-based", "user": user, "message": message}
    return {"success": False, "message": message}


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


@app.post("/api/auth/logout")
async def api_logout(request: Request):
    """退出登录"""
    request.session.clear()
    return {"success": True, "message": "已退出登录"}


@app.post("/api/auth/change_password")
async def api_change_password(request: Request, data: ChangePasswordRequest):
    """修改密码"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
        
    success, message = change_password(user['username'], data.old_password, data.new_password)
    if success:
        return {"success": True, "message": message}
    return {"success": False, "message": message}


@app.post("/api/auth/delete_account")
async def api_delete_account(request: Request, data: DeleteAccountRequest):
    """注销账号"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
        
    success, message = delete_user(user['username'], data.password)
    if success:
        request.session.clear()
        return {"success": True, "message": message}
    return {"success": False, "message": message}

@app.get("/api/user/me")
async def get_me(request: Request):
    """获取当前用户信息"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return {"success": True, "user": user}


@app.get("/api/user/history")
async def api_get_history(request: Request, favorites_only: bool = False):
    """获取用户预测历史"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
        
    history = get_user_history(user['username'], favorites_only)
    return {"success": True, "history": history}


# ============= 选项数据 API =============

@app.get("/api/options/brands")
async def get_brands():
    """获取所有品牌"""
    if predictor is None:
        return {"success": False, "error": "Predictor not initialized"}
    
    # 从索引中提取品牌，并按热度（记录数）排序
    # brand_index keys are brands
    brand_counts = []
    for brand, indices in predictor.data_index.brand_index.items():
        brand_counts.append((brand, len(indices)))
    
    # Sort by count desc, then name asc
    brand_counts.sort(key=lambda x: (-x[1], x[0]))
    
    brands = [b[0] for b in brand_counts]
    return {"success": True, "data": brands}

import re

@app.get("/api/options/series")
async def get_series(brand: str):
    """获取品牌下的车系"""
    if predictor is None:
        return {"success": False, "error": "Predictor not initialized"}
    
    # 遍历 brand_series_index，找到匹配该品牌的车系
    # brand_series format: "Brand-Series"
    series_list = []
    prefix = f"{brand}-"
    
    for bs, indices in predictor.data_index.brand_series_index.items():
        if bs == brand or bs.startswith(prefix):
             # Extract series name (remove brand prefix)
             if '-' in bs:
                 series_name = bs.split('-', 1)[1]
                 series_list.append({
                     "full": bs, 
                     "name": series_name,
                     "count": len(indices)
                 })
             else:
                 series_list.append({
                     "full": bs, 
                     "name": bs,
                     "count": len(indices)
                 })
    
    # Sort by count desc, then name asc
    series_list.sort(key=lambda x: (-x['count'], x['name']))
    return {"success": True, "data": series_list}

@app.get("/api/options/model_years")
async def get_model_years(brand_series: str):
    """获取车系下的所有车款年份"""
    if predictor is None:
        return {"success": False, "error": "Predictor not initialized"}
        
    if brand_series not in predictor.data_index.brand_series_index:
        return {"success": True, "data": []}
        
    indices = predictor.data_index.brand_series_index[brand_series]
    years = set()
    
    for idx in indices:
        record = predictor.data_index.records[idx]
        # 从 vehicle_full_name 中提取年份 (如 "2016款")
        match = re.search(r'(\d{4})款', record.vehicle_full_name)
        if match:
            years.add(match.group(1))
            
    # Sort years descending
    sorted_years = sorted(list(years), reverse=True)
    return {"success": True, "data": sorted_years}

@app.get("/api/options/models")
async def get_models(brand_series: str, model_year: str = None):
    """获取车系下的具体车型，支持按年份筛选"""
    if predictor is None:
        return {"success": False, "error": "Predictor not initialized"}
        
    if brand_series not in predictor.data_index.brand_series_index:
        return {"success": True, "data": []}
        
    indices = predictor.data_index.brand_series_index[brand_series]
    models = []
    seen = set()
    
    for idx in indices:
        record = predictor.data_index.records[idx]
        
        # 如果指定了年份，进行过滤
        if model_year:
            # 检查车型全称是否包含该年份款
            # 这里我们假设格式总是 "20xx款"，或者严格匹配提取结果
            # 为了更稳健，我们再次提取并比较
            match = re.search(r'(\d{4})款', record.vehicle_full_name)
            if not match or match.group(1) != model_year:
                continue
        
        if record.vehicle_full_name not in seen:
            seen.add(record.vehicle_full_name)
            models.append({
                "name": record.vehicle_full_name,
                "new_price": record.new_price,
                "year": record.years # Optional
            })
            
    # Sort by name
    models.sort(key=lambda x: x['name'])
    return {"success": True, "data": models}

@app.get("/api/options/cities")
async def get_cities():
    """获取城市列表 (按省份分组)"""
    province_city_map = {
        "直辖市": ["北京", "上海", "天津", "重庆"],
        "广东": ["广州", "深圳", "珠海", "汕头", "佛山", "韶关", "湛江", "肇庆", "江门", "茂名", "惠州", "梅州", "汕尾", "河源", "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮"],
        "四川": ["成都", "绵阳", "自贡", "攀枝花", "泸州", "德阳", "广元", "遂宁", "内江", "乐山", "资阳", "宜宾", "南充", "达州", "雅安", "阿坝", "甘孜", "凉山", "广安", "巴中", "眉山"],
        "江苏": ["南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港", "淮安", "盐城", "扬州", "镇江", "泰州", "宿迁"],
        "浙江": ["杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华", "衢州", "舟山", "台州", "丽水"],
        "山东": ["济南", "青岛", "淄博", "枣庄", "东营", "烟台", "潍坊", "济宁", "泰安", "威海", "日照", "临沂", "德州", "聊城", "滨州", "菏泽"],
        "河南": ["郑州", "开封", "洛阳", "平顶山", "安阳", "鹤壁", "新乡", "焦作", "濮阳", "许昌", "漯河", "三门峡", "南阳", "商丘", "信阳", "周口", "驻马店", "济源"],
        "河北": ["石家庄", "唐山", "秦皇岛", "邯郸", "邢台", "保定", "张家口", "承德", "沧州", "廊坊", "衡水"],
        "湖北": ["武汉", "黄石", "十堰", "宜昌", "襄阳", "鄂州", "荆门", "孝感", "荆州", "黄冈", "咸宁", "随州", "恩施", "仙桃", "潜江", "天门", "神农架"],
        "湖南": ["长沙", "株洲", "湘潭", "衡阳", "邵阳", "岳阳", "常德", "张家界", "益阳", "郴州", "永州", "怀化", "娄底", "湘西"],
        "福建": ["福州", "厦门", "莆田", "三明", "泉州", "漳州", "南平", "龙岩", "宁德"],
        "安徽": ["合肥", "芜湖", "蚌埠", "淮南", "马鞍山", "淮北", "铜陵", "安庆", "黄山", "滁州", "阜阳", "宿州", "六安", "亳州", "池州", "宣城"],
        "陕西": ["西安", "铜川", "宝鸡", "咸阳", "渭南", "延安", "汉中", "榆林", "安康", "商洛"],
        "辽宁": ["沈阳", "大连", "鞍山", "抚顺", "本溪", "丹东", "锦州", "营口", "阜新", "辽阳", "盘锦", "铁岭", "朝阳", "葫芦岛"],
        "吉林": ["长春", "吉林", "四平", "辽源", "通化", "白山", "松原", "白城", "延边"],
        "黑龙江": ["哈尔滨", "齐齐哈尔", "鸡西", "鹤岗", "双鸭山", "大庆", "伊春", "佳木斯", "七台河", "牡丹江", "黑河", "绥化", "大兴安岭"],
        "广西": ["南宁", "柳州", "桂林", "梧州", "北海", "防城港", "钦州", "贵港", "玉林", "百色", "贺州", "河池", "来宾", "崇左"],
        "山西": ["太原", "大同", "阳泉", "长治", "晋城", "朔州", "晋中", "运城", "忻州", "临汾", "吕梁"],
        "云南": ["昆明", "曲靖", "玉溪", "保山", "昭通", "丽江", "普洱", "临沧", "楚雄", "红河", "文山", "西双版纳", "大理", "德宏", "怒江", "迪庆"],
        "贵州": ["贵阳", "六盘水", "遵义", "安顺", "毕节", "铜仁", "黔西南", "黔东南", "黔南"],
        "江西": ["南昌", "景德镇", "萍乡", "九江", "新余", "鹰潭", "赣州", "吉安", "宜春", "抚州", "上饶"],
        "海南": ["海口", "三亚", "三沙", "儋州", "五指山", "琼海", "文昌", "万宁", "东方", "定安", "屯昌", "澄迈", "临高", "白沙", "昌江", "乐东", "陵水", "保亭", "琼中"],
        "内蒙古": ["呼和浩特", "包头", "乌海", "赤峰", "通辽", "鄂尔多斯", "呼伦贝尔", "巴彦淖尔", "乌兰察布", "兴安", "锡林郭勒", "阿拉善"],
        "宁夏": ["银川", "石嘴山", "吴忠", "固原", "中卫"],
        "甘肃": ["兰州", "嘉峪关", "金昌", "白银", "天水", "武威", "张掖", "平凉", "酒泉", "庆阳", "定西", "陇南", "临夏", "甘南"],
        "青海": ["西宁", "海东", "海北", "黄南", "海南", "果洛", "玉树", "海西"],
        "新疆": ["乌鲁木齐", "克拉玛依", "吐鲁番", "哈密", "昌吉", "博尔塔拉", "巴音郭楞", "阿克苏", "克孜勒苏", "喀什", "和田", "伊犁", "塔城", "阿勒泰"],
        "西藏": ["拉萨", "日喀则", "昌都", "林芝", "山南", "那曲", "阿里"]
    }
    
    # 获取数据库中存在但未在地图中的城市
    if predictor:
        available_cities = set(r.city for r in predictor.data_index.records if r.city)
        mapped_cities = set()
        for cities in province_city_map.values():
            mapped_cities.update(cities)
            
        others = []
        for city in available_cities:
            if city not in mapped_cities:
                others.append(city)
        
        if others:
            province_city_map["其他"] = sorted(others)
            
    return {"success": True, "data": province_city_map}


@app.delete("/api/history")
async def api_delete_history(request: Request, data: DeleteHistoryRequest):
    """批量删除历史记录"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
        
    success, message = delete_history_records(user['username'], data.record_ids)
    if success:
        return {"success": True, "message": message}
    return {"success": False, "message": message}


@app.post("/api/history/{record_id}/favorite")
async def api_toggle_favorite(request: Request, record_id: str):
    """切换收藏状态"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
        
    success, is_favorite, message = toggle_favorite(user['username'], record_id)
    if success:
        return {"success": True, "is_favorite": is_favorite, "message": message}
    return {"success": False, "message": message}


# ============= 业务 API (受保护) =============

@app.post("/predict", response_model=PredictResponse)
async def predict(request: Request, predict_request: PredictRequest):
    """
    预测二手车残值价格 (需要登录)
    """
    # 检查登录状态
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")

    if predictor is None:
        raise HTTPException(status_code=500, detail="预测器未初始化")
    
    result = predictor.predict(
        vehicle_full_name=predict_request.vehicle_full_name,
        brand_series=predict_request.brand_series,
        years=predict_request.years,
        grade=predict_request.grade,
        city=predict_request.city,
        mileage=predict_request.mileage,
        new_price=predict_request.new_price
    )
    
    # 生成价格解释报告
    response_data = result.to_dict()
    if result.success:
        try:
            report = explain_price(
                result,
                years=predict_request.years,
                mileage=predict_request.mileage,
                grade=predict_request.grade
            )
            response_data['explanation'] = report.to_dict()
        except Exception as e:
            logger.warning(f"生成价格解释失败: {e}")
            response_data['explanation'] = None
    
    # 自动保存历史记录
    try:
        # 将 Pydantic 对象转换为 dict 用于保存
        vehicle_info = predict_request.dict()
        # 简化结果数据，避免存储过多冗余
        save_result = {
            "predicted_price": result.predicted_price,
            "new_price": result.new_price,
            "residual_rate": result.residual_rate,
            "success": result.success,
            "error_message": result.error_message
        }
        
        saved, record_id, msg = add_history_record(user['username'], vehicle_info, save_result)
        if saved:
            response_data['record_id'] = record_id
            response_data['is_favorite'] = False # 默认不收藏
    except Exception as e:
        logger.error(f"保存历史记录失败: {e}")

    return response_data


@app.post("/batch_predict", response_model=BatchPredictResponse)
async def batch_predict(request: Request, batch_request: BatchPredictRequest):
    """批量预测 (需要登录)"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")

    if predictor is None:
        raise HTTPException(status_code=500, detail="预测器未初始化")
    
    results = []
    for item in batch_request.items:
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
async def random_vehicle(request: Request):
    """获取随机一辆车的信息 (需要登录)"""
    try:
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="请先登录")

        import random
        import math
        import traceback
        
        if predictor is None:
            raise HTTPException(status_code=500, detail="预测器未初始化")
        
        records = predictor.data_index.records
        if not records:
            return {"success": False, "error": "没有可用的车辆数据"}
        
        # 随机选择一条记录
        record = random.choice(records)
        
        # 解析品牌
        brand_series = str(record.brand_series) if record.brand_series is not None else ""
        brand = brand_series.split('-')[0] if '-' in brand_series else brand_series
        
        # 处理 NaN
        new_price = record.new_price
        if isinstance(new_price, float) and (math.isnan(new_price) or math.isinf(new_price)):
            new_price = None

        years = record.years
        if isinstance(years, float) and (math.isnan(years) or math.isinf(years)):
            years = 0.0
            
        mileage = record.mileage
        if isinstance(mileage, float) and (math.isnan(mileage) or math.isinf(mileage)):
            mileage = 0.0

        return {
            "success": True,
            "brand": brand,
            "vehicle_full_name": str(record.vehicle_full_name),
            "brand_series": brand_series,
            "years": years,
            "grade": record.grade,
            "city": record.city,
            "mileage": mileage,
            "new_price": new_price
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = f"Random vehicle error: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return {"success": False, "error": error_msg}


@app.get("/models", response_model=ModelListResponse)
async def list_models(request: Request):
    """获取可用的模型列表 (需要登录)"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")

    if predictor is None:
        raise HTTPException(status_code=500, detail="预测器未初始化")
    
    return {
        "brand_series_models": predictor.get_available_brand_series(),
        "car_type_models": predictor.get_available_car_types()
    }


@app.get("/health")
async def health():
    """健康检查 (公开)"""
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
