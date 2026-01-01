"""
用户认证模块 - JWT 认证

提供微信小程序登录和 JWT token 管理
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

import jwt
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# JWT 配置
SECRET_KEY = os.getenv("JWT_SECRET", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 天

security = HTTPBearer()


@dataclass
class User:
    """用户信息"""
    id: int
    openid: str
    nickname: str
    created_at: datetime
    
    def to_dict(self):
        return {
            "id": self.id,
            "openid": self.openid[:8] + "***",  # 隐藏部分
            "nickname": self.nickname,
            "created_at": self.created_at.isoformat()
        }


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """解码 JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 Token")


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    从请求头获取当前用户
    
    用法:
        @app.get("/protected")
        def protected_route(user: dict = Depends(get_current_user)):
            return {"user_id": user["user_id"]}
    """
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None or "user_id" not in payload:
        raise HTTPException(status_code=401, detail="无效的认证信息")
    return payload


def hash_openid(openid: str) -> str:
    """对 openid 进行哈希 (用于日志等场景)"""
    return hashlib.sha256(openid.encode()).hexdigest()[:16]


# 测试用: 创建测试 token
def create_test_token(user_id: int = 1, nickname: str = "测试用户") -> str:
    """生成测试用 token"""
    return create_access_token({
        "user_id": user_id,
        "nickname": nickname,
        "type": "test"
    })


if __name__ == "__main__":
    # 测试
    token = create_test_token()
    print(f"Test Token: {token}")
    
    decoded = decode_access_token(token)
    print(f"Decoded: {decoded}")
