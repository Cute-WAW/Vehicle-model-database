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

from auth import create_access_token, get_current_user, create_test_token
from database import (
    init_db, get_or_create_user, get_user_evaluations,
    get_evaluation_by_id, delete_evaluation, save_evaluation,
    get_user_evaluation_count
)

# 初始化数据库
init_db()

router = APIRouter(prefix="/api", tags=["小程序API"])


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


# ========== 认证接口 ==========

@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    微信登录
    
    小程序调用 wx.login() 获取 code，发送到此接口换取 token
    """
    # TODO: 实际环境需要调用微信 API 换取 openid
    # https://api.weixin.qq.com/sns/jscode2session
    
    # 这里简化处理，直接用 code 作为 openid (仅测试)
    openid = f"wx_{request.code}"
    
    user = get_or_create_user(openid, request.nickname, request.avatar_url)
    
    token = create_access_token({
        "user_id": user.id,
        "nickname": user.nickname
    })
    
    return {
        "success": True,
        "token": token,
        "user": user.to_dict() if hasattr(user, 'to_dict') else {
            "id": user.id,
            "nickname": user.nickname
        }
    }


@router.post("/auth/test-login", response_model=LoginResponse)
async def test_login(request: TestLoginRequest):
    """
    测试登录 (开发用)
    
    不需要真实微信 code，直接使用测试 openid
    """
    user = get_or_create_user(request.test_openid, request.nickname)
    
    token = create_access_token({
        "user_id": user.id,
        "nickname": user.nickname,
        "type": "test"
    })
    
    return {
        "success": True,
        "token": token,
        "user": {
            "id": user.id,
            "nickname": user.nickname
        }
    }


# ========== 随机车辆接口 ==========

@router.get("/random_vehicle")
async def random_vehicle():
    """获取随机一辆车的信息"""
    import random
    from dataclasses import asdict
    from residual_predictor_step5 import ResidualPredictor
    
    # 使用共享的预测器实例 (如果有的话)
    # 这里的路径需要确保正确
    predictor = ResidualPredictor(
        residual_data_csv=str(Path(__file__).parent.parent.parent / 'output' / 'residual_value_data_for_build_model.csv')
    )
    
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
    from residual_predictor_step5 import ResidualPredictor
    from price_logic_step6 import explain_price
    
    # 使用共享的预测器实例 (如果有的话)
    predictor = ResidualPredictor(
        residual_data_csv=str(Path(__file__).parent.parent.parent / 'output' / 'residual_value_data_for_build_model.csv')
    )
    
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
    
    # 保存历史
    eval_id = None
    if request.save_history:
        eval_id = save_evaluation(
            user_id=user['user_id'],
            vehicle_full_name=request.vehicle_full_name,
            brand_series=request.brand_series,
            years=request.years,
            mileage=request.mileage,
            grade=request.grade,
            predicted_price=result.predicted_price,
            price_low=price_low,
            price_high=price_high,
            explanation=explanation
        )
    
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
    items = get_user_evaluations(user['user_id'], limit, offset)
    total = get_user_evaluation_count(user['user_id'])
    
    return {
        "success": True,
        "total": total,
        "items": items
    }


@router.get("/history/{eval_id}")
async def get_history_detail(
    eval_id: int,
    user: dict = Depends(get_current_user)
):
    """获取单条估价记录详情"""
    item = get_evaluation_by_id(eval_id, user['user_id'])
    
    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")
    
    return {
        "success": True,
        "item": item
    }


@router.delete("/history/{eval_id}")
async def delete_history(
    eval_id: int,
    user: dict = Depends(get_current_user)
):
    """删除估价记录"""
    success = delete_evaluation(eval_id, user['user_id'])
    
    if not success:
        raise HTTPException(status_code=404, detail="记录不存在")
    
    return {"success": True, "message": "已删除"}


# ========== 测试接口 ==========

@router.get("/test/token")
async def get_test_token():
    """获取测试 Token (仅开发环境)"""
    from database import get_or_create_user
    
    user = get_or_create_user("test_dev_user", "开发测试")
    token = create_access_token({
        "user_id": user.id,
        "nickname": user.nickname,
        "type": "dev"
    })
    
    return {
        "token": token,
        "user_id": user.id,
        "usage": "添加到请求头: Authorization: Bearer <token>"
    }
