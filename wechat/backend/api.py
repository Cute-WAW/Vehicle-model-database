"""
微信小程序 API 路由

整合认证、估价、历史记录功能
"""

import sys
from pathlib import Path

# 添加父目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

import logging
from auth import create_access_token, get_current_user, create_test_token

logger = logging.getLogger("wechat_api")
from db_supabase import (
    create_wechat_user_if_not_exists,
    add_history_record,
    get_user_history,
    delete_history_records,
    resolve_canonical_username
)

router = APIRouter(prefix="/api", tags=["小程序API"])
get_shared_predictor = None


def get_db_username(user: dict) -> str:
    """统一从 token payload 中提取数据库用户名。"""
    return resolve_canonical_username(
        user_id=user.get("user_id"),
        username=user.get("username", "")
    )


# ========== 请求/响应模型 ==========

class LoginRequest(BaseModel):
    """登录请求"""
    code: str = Field(..., description="微信登录 code")
    nickname: str = Field("用户", description="用户昵称")
    avatar_url: str = Field("", description="用户头像")


class LoginResponse(BaseModel):
    """登录响应"""
    success: bool
    token: str
    user: dict


class TestLoginRequest(BaseModel):
    """测试登录请求"""
    test_openid: str = Field("test_user_001", description="测试用 openid")
    nickname: str = Field("测试用户", description="昵称")


class PredictRequest(BaseModel):
    """估价请求"""
    vehicle_full_name: str = Field(..., description="车辆全称")
    brand_series: str = Field(..., description="品牌-车系")
    years: float = Field(..., description="使用年限")
    grade: str = Field("中", description="车辆评级")
    city: str = Field("", description="城市")
    mileage: float = Field(0.0, description="行驶里程(万公里)")
    new_price: Optional[float] = Field(None, description="新车价格(万元)")
    save_history: bool = Field(True, description="是否保存到历史")


class HistoryListResponse(BaseModel):
    """历史记录列表"""
    success: bool
    total: int
    items: List[dict]


def _get_default_residual_csv() -> Path:
    """Prefer the richer merged dataset for WeChat runtime."""
    project_root = Path(__file__).parent.parent.parent
    candidates = [
        project_root / 'output' / 'merged_residual_value_data_with_dates.csv',
        project_root / 'output' / 'merged_residual_value_data.csv',
        project_root / 'output' / 'residual_value_data_for_build_model.csv',
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[-1]


def _get_predictor_instance():
    """Use the singleton predictor injected by `wechat.backend.main` when available."""
    global get_shared_predictor
    if callable(get_shared_predictor):
        predictor = get_shared_predictor()
        if predictor is not None:
            return predictor

    from residual_predictor_step5 import ResidualPredictor
    return ResidualPredictor(residual_data_csv=str(_get_default_residual_csv()))


# ========== 认证接口 ==========

@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    微信登录
    
    小程序调用 wx.login() 获取 code，发送到此接口换取 token。
    当前已预留调用微信 jscode2session 接口获取真实 OpenID 的逻辑代码。
    """
    import os
    import requests
    
    # =====================================================================
    # 【预留接口】真实获取微信 OpenID 逻辑 (后续需在 .env 配置这两项)
    # =====================================================================
    WECHAT_APPID = os.getenv("WECHAT_APPID", "")
    WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")
    
    openid = None
    
    if WECHAT_APPID and WECHAT_SECRET and not request.code.startswith("test_"):
        # 1. 生产环境：向微信服务器请求真实 openid
        url = f"https://api.weixin.qq.com/sns/jscode2session?appid={WECHAT_APPID}&secret={WECHAT_SECRET}&js_code={request.code}&grant_type=authorization_code"
        try:
            response = requests.get(url, timeout=5)
            data = response.json()
            if "openid" in data:
                openid = data["openid"]
                # session_key = data.get("session_key") # 若需解密加密数据可保存
            else:
                raise HTTPException(status_code=400, detail=f"微信登录失败: {data.get('errmsg', '未知错误')}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"请求微信接口异常: {str(e)}")
    else:
        # 2. 本地测试环境：自动回退使用 code 拼接模拟 openid
        openid = f"wx_mock_{request.code}"
        
    if not openid:
        raise HTTPException(status_code=400, detail="获取 OpenID 失败")

    # =====================================================================
    # 3. 将 OpenID 与 Supabase 数据库互联并注册/登录
    # =====================================================================
    success, user, msg = create_wechat_user_if_not_exists(
        openid=openid, 
        nickname=request.nickname, 
        avatar_url=request.avatar_url
    )
    
    if not success or not user:
        raise HTTPException(status_code=400, detail=msg or "微信登录失败")
    
    token = create_access_token({
        "user_id": user["id"],
        "username": user.get("username", ""),
        "nickname": user.get("nickname", "用户")
    })
    
    return {
        "success": True,
        "token": token,
        "user": user
    }


@router.post("/auth/test-login", response_model=LoginResponse)
async def test_login(request: TestLoginRequest):
    """
    测试登录 (开发用)
    
    不需要真实微信 code，直接使用测试 openid
    """
    success, user, msg = create_wechat_user_if_not_exists(
        openid=request.test_openid, 
        nickname=request.nickname
    )
    
    logger.info(f"Test login successful for openid: {request.test_openid}. User: {user}")
    
    token = create_access_token({
        "user_id": user["id"],
        "username": user.get("username", ""),
        "nickname": user.get("nickname", "用户"),
        "type": "test"
    })
    
    logger.info(f"Generated test token: {token[:15]}...")
    
    return {
        "success": True,
        "token": token,
        "user": user
    }


# ========== 随机车辆接口 ==========

@router.get("/random_vehicle")
async def random_vehicle():
    """获取随机一辆车的信息"""
    import random
    from dataclasses import asdict
    predictor = _get_predictor_instance()
    
    records = predictor.data_index.records
    if not records:
        return {"success": False, "error": "没有可用的车辆数据"}
    
    # 随机选择一条记录
    record = random.choice(records)
    record_dict = asdict(record)
    
    return {
        "success": True,
        **record_dict
    }


# ========== 估价接口 ==========

@router.post("/predict")
async def predict_with_auth(
    request: PredictRequest,
    user: dict = Depends(get_current_user)
):
    """
    车辆估价 (需登录)
    
    返回预测价格、价格区间、解释报告，并可选保存到历史
    """
    from price_logic_step6 import explain_price
    
    predictor = _get_predictor_instance()
    
    result = predictor.predict(
        vehicle_full_name=request.vehicle_full_name,
        brand_series=request.brand_series,
        years=request.years,
        grade=request.grade,
        city=request.city,
        mileage=request.mileage,
        new_price=request.new_price
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error_message or "预测失败")
    
    # 生成解释
    explanation = None
    try:
        report = explain_price(result, years=request.years, mileage=request.mileage, grade=request.grade)
        explanation = report.to_dict()
    except Exception as e:
        pass
    
    # 提取价格区间
    price_low = result.predicted_price * 0.9
    price_high = result.predicted_price * 1.1
    
    if result.price_matrix and 'b2BPrices' in result.price_matrix:
        grade_map = {'优': 'a', '中': 'b', '差': 'c'}
        target_col = grade_map.get(request.grade, 'b')
        b2b = result.price_matrix['b2BPrices'].get(target_col, {})
        price_low = float(b2b.get('low', price_low))
        price_high = float(b2b.get('up', price_high))
    
    # 保存历史 (对接 Supabase prediction_history)
    eval_id = None
    if request.save_history:
        vehicle_info = {
            "vehicle_full_name": request.vehicle_full_name,
            "brand_series": request.brand_series,
            "years": request.years,
            "mileage": request.mileage,
            "grade": request.grade
        }
        prediction_result = {
            "predicted_price": result.predicted_price,
            "price_low": price_low,
            "price_high": price_high,
            "new_price": result.new_price,
            "residual_rate": result.residual_rate,
            "price_matrix": result.price_matrix,
            "explanation": explanation
        }
        
        # 正确提取存入 token 的 username，以满足 Supabase 的 users 表外键关联
        db_username = get_db_username(user)
        
        success, record_id, msg = add_history_record(
            username=db_username,
            vehicle_info=vehicle_info,
            prediction_result=prediction_result
        )
        if success:
            eval_id = record_id
    
    # 获取最相关的10个成交记录
    similar_vehicles = []
    try:
        candidates = predictor.data_index.search_similar(
            vehicle_full_name=request.vehicle_full_name,
            brand_series=request.brand_series,
            years=request.years,
            grade=request.grade,
            city=request.city,
            mileage=request.mileage,
            top_k=10
        )
        
        # 格式化返回
        from dataclasses import asdict
        for cand in candidates:
            # 简化返回字段
            rec = cand.record
            similar_vehicles.append({
                "vehicle_full_name": rec.vehicle_full_name,
                "years": rec.years,
                "city": rec.city,
                "used_price": rec.used_price,
                "mileage": rec.mileage,
                "score": round(cand.score, 1),
                "grade": rec.grade,
                "reg_date_str": f"{int(2025 - rec.years)}年" # 简单估算上牌年份
            })
            
    except Exception as e:
        print(f"Similar Search Error: {e}")
        pass
    
    return {
        "success": True,
        "evaluation_id": eval_id,
        "predicted_price": result.predicted_price,
        "price_range": {
            "low": round(price_low, 2),
            "high": round(price_high, 2)
        },
        "new_price": result.new_price,
        "residual_rate": result.residual_rate,
        "explanation": explanation,
        "price_matrix": result.price_matrix,
        "similar_vehicles": similar_vehicles
    }


# ========== 历史记录接口 ==========

@router.get("/history", response_model=HistoryListResponse)
async def get_history(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user)
):
    """获取估价历史列表"""
    db_username = get_db_username(user)
    raw_items = get_user_history(username=db_username, favorites_only=False)
    
    # 格式化数据结构以适配小程序前端 history.wxml 的预期
    items = []
    for item in raw_items:
        v_info = item.get("vehicle_info", {})
        p_res = item.get("prediction_result", {})
        
        formatted = {
            "id": item["id"],
            "user_id": user['user_id'],
            "vehicle_full_name": v_info.get("vehicle_full_name", "未知车型"),
            "brand_series": v_info.get("brand_series", ""),
            "years": v_info.get("years", 0),
            "mileage": v_info.get("mileage", 0),
            "grade": v_info.get("grade", "中"),
            "predicted_price": p_res.get("predicted_price", 0),
            "price_low": p_res.get("price_low", 0),
            "price_high": p_res.get("price_high", 0),
            "explanation": p_res.get("explanation"),
            "created_at": str(item["created_at"])[:19] # 切割掉时区和微秒
        }
        items.append(formatted)
        
    # 处理分页
    total = len(items)
    paginated_items = items[offset:offset+limit]
    
    return {
        "success": True,
        "total": total,
        "items": paginated_items
    }

@router.get("/history/{eval_id}")
async def get_history_detail(
    eval_id: int,
    user: dict = Depends(get_current_user)
):
    """获取单条估价记录详情"""
    db_username = get_db_username(user)
    raw_items = get_user_history(username=db_username)
    
    item = next((x for x in raw_items if x["id"] == eval_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")
        
    v_info = item.get("vehicle_info", {})
    p_res = item.get("prediction_result", {})
    
    formatted = {
        "id": item["id"],
        "user_id": user['user_id'],
        "vehicle_full_name": v_info.get("vehicle_full_name", "未知车型"),
        "brand_series": v_info.get("brand_series", ""),
        "years": v_info.get("years", 0),
        "mileage": v_info.get("mileage", 0),
        "grade": v_info.get("grade", "中"),
        "predicted_price": p_res.get("predicted_price", 0),
        "price_low": p_res.get("price_low", 0),
        "price_high": p_res.get("price_high", 0),
        "explanation": p_res.get("explanation"),
        "created_at": str(item["created_at"])[:19]
    }
    
    return {
        "success": True,
        "item": formatted
    }

@router.delete("/history/{eval_id}")
async def delete_history(
    eval_id: int,
    user: dict = Depends(get_current_user)
):
    """删除估价记录"""
    db_username = get_db_username(user)
    success, msg = delete_history_records(username=db_username, record_ids=[eval_id])
    
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    return {"success": True, "message": "已删除"}


# ========== 测试接口 ==========

@router.get("/test/token")
async def get_test_token():
    """获取测试 Token (仅开发环境)"""
    success, user, msg = create_wechat_user_if_not_exists("test_dev_user", "开发测试")
    token = create_access_token({
        "user_id": user["id"],
        "username": user.get("username", ""),
        "nickname": user.get("nickname", "开发测试"),
        "type": "dev"
    })
    
    return {
        "token": token,
        "user_id": user["id"],
        "usage": "添加到请求头: Authorization: Bearer <token>"
    }
