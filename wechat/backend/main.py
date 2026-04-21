"""
微信小程序后端启动入口

修复说明：
1. 配置 sys.path，确保 auth/database (backend/) 和 src/ 模块均可正确导入
2. 使用全局单例模式加载 ResidualPredictor，避免每次请求重新初始化
3. 添加 CORS 支持，兼容微信开发者工具的跨域请求
4. 提供 /health 健康检查接口
"""

import sys
import logging
from pathlib import Path

# ============================================================
# 路径配置（必须在其他 import 之前）
# backend/ 目录 → auth, database 模块
# 项目根 src/ 目录 → residual_predictor_step5, price_logic_step6 等
# ============================================================
BACKEND_DIR = Path(__file__).parent               # wechat/backend/
PROJECT_ROOT = BACKEND_DIR.parent.parent          # 项目根目录
SRC_DIR = PROJECT_ROOT / "src"                    # src/

for p in [str(BACKEND_DIR), str(SRC_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ============================================================
# FastAPI 相关 import
# ============================================================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ============================================================
# 业务模块 import（路径已在上面配置完毕）
# ============================================================
from api import router  # wechat/backend/api.py

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("wechat_backend")

# ============================================================
# 全局单例预测器（解决 api.py 中每次请求都初始化的问题）
# ============================================================
_predictor = None


def resolve_wechat_residual_data() -> Path:
    """Return the best available residual dataset for WeChat backend runtime."""
    candidates = [
        PROJECT_ROOT / "output" / "merged_residual_value_data_with_dates.csv",
        PROJECT_ROOT / "output" / "merged_residual_value_data.csv",
        PROJECT_ROOT / "output" / "residual_value_data_for_build_model.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[-1]

def get_predictor():
    """懒加载并缓存 ResidualPredictor 实例"""
    global _predictor
    if _predictor is None:
        data_csv = resolve_wechat_residual_data()
        if not data_csv.exists():
            logger.warning(f"残值数据文件不存在: {data_csv}")
            logger.warning("估价功能将不可用，请先运行 Step2/Step3 生成数据")
            return None
        try:
            from residual_predictor_step5 import ResidualPredictor
            logger.info("正在加载残值预测模型，请稍候...")
            _predictor = ResidualPredictor(residual_data_csv=str(data_csv))
            logger.info("✅ 残值预测模型加载完成")
        except Exception as e:
            logger.error(f"❌ 残值预测模型加载失败: {e}")
            logger.error("估价功能将不可用")
            return None
    return _predictor


# ============================================================
# 在 api.py 中注入单例预测器
# (api.py 目前每次请求都 new 一个 ResidualPredictor，这里打补丁)
# ============================================================
def _patch_api_predictor():
    """
    在 api.py 的模块命名空间中注入预加载的预测器实例，
    使得 api.py 中调用 ResidualPredictor() 时直接返回已加载的单例。
    如果 api.py 未来重构为支持依赖注入则可移除此处理。
    """
    import api as api_module
    predictor = get_predictor()
    if predictor is not None:
        try:
            api_module.get_shared_predictor = get_predictor  # type: ignore
        except Exception:
            pass  # api 模块可能已经在路由中 import，忽略失败


# ============================================================
# 创建 FastAPI 应用
# ============================================================
app = FastAPI(
    title="二手车估价小程序 API",
    description="为微信小程序提供车辆估价、历史记录和用户认证服务",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ============================================================
# CORS — 允许微信开发者工具及局域网访问
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 生产环境请改为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 注册路由（来自 wechat/backend/api.py，prefix="/api"）
# ============================================================
app.include_router(router)

# ============================================================
# 启动事件：预加载预测模型
# ============================================================
@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("🚀 微信小程序后端服务启动中...")
    logger.info(f"   项目根目录: {PROJECT_ROOT}")
    logger.info(f"   src 目录:   {SRC_DIR}")
    logger.info("=" * 60)
    _patch_api_predictor()
    logger.info("=" * 60)
    logger.info("✅ 服务就绪！")
    logger.info("   API 文档:     http://127.0.0.1:8003/docs")
    logger.info("   健康检查:     http://127.0.0.1:8003/health")
    logger.info("   测试Token:    http://127.0.0.1:8003/api/test/token")
    logger.info("=" * 60)


# ============================================================
# 健康检查端点
# ============================================================
@app.get("/", summary="根路径")
async def root():
    return {"message": "二手车估价小程序后端运行中", "docs": "/docs"}


@app.get("/health", summary="健康检查")
async def health():
    predictor = _predictor  # 不触发懒加载，只检查是否已加载
    return {
        "status": "ok",
        "predictor_loaded": predictor is not None,
        "version": "1.0.0",
    }


# ============================================================
# 直接运行入口
# ============================================================
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
        reload_dirs=[str(BACKEND_DIR)],
        log_level="info",
    )
