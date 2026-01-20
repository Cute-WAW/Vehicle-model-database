import os
import hashlib
import logging
from typing import Optional, Tuple, Dict, Any
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from supabase import create_client, Client

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

engine = None
supabase_client: Optional[Client] = None

def get_db_engine():
    global engine
    if engine is None and DATABASE_URL:
        try:
            # 创建数据库引擎
            engine = create_engine(DATABASE_URL, pool_pre_ping=True)
            logger.info("Supabase 数据库连接已初始化 (SQLAlchemy)")
        except Exception as e:
            logger.error(f"初始化数据库连接失败: {e}")
    return engine

def get_supabase_client():
    global supabase_client
    if supabase_client is None and SUPABASE_URL and SUPABASE_KEY:
        try:
            supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("Supabase 客户端已初始化 (REST API)")
        except Exception as e:
            logger.error(f"初始化 Supabase 客户端失败: {e}")
    return supabase_client

def hash_password(password: str) -> str:
    """
    对密码进行哈希处理 (SHA256)
    注意：生产环境建议使用 bcrypt 或 argon2
    """
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    验证用户登录
    优先使用 Supabase Client (REST API)，失败则回退到 SQLAlchemy (Direct Connection)，最后回退到 Mock
    
    Returns:
        (success, user_info, message)
    """
    hashed_pw = hash_password(password)
    
    # 1. 尝试使用 Supabase Client (REST API) - 推荐方式，不受 DNS 污染影响
    client = get_supabase_client()
    if client:
        try:
            # 查询用户
            response = client.table('users').select("*").or_(f"username.eq.{username},email.eq.{username}").execute()
            
            if not response.data:
                return False, None, "用户不存在"
            
            user_data = response.data[0]
            
            if user_data.get('status') != 'active':
                return False, None, "账号已被禁用"
            
            # 验证密码
            stored_hash = user_data.get('password_hash')
            if stored_hash == hashed_pw or stored_hash == password:
                user_info = {
                    "id": user_data['id'],
                    "username": user_data['username'],
                    "nickname": user_data['nickname']
                }
                
                # 更新最后登录时间
                try:
                    client.table('users').update({"last_login_at": "now()"}).eq("id", user_data['id']).execute()
                except Exception as e:
                    logger.warning(f"更新最后登录时间失败: {e}")
                
                return True, user_info, "登录成功"
            else:
                return False, None, "密码错误"
                
        except Exception as e:
            logger.error(f"Supabase Client 登录验证异常: {e}")
            # 继续尝试 SQLAlchemy 方式
    
    # 2. 尝试使用 SQLAlchemy (Direct Connection)
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                # 查询用户
                query = text("""
                    SELECT id, username, nickname, password_hash, status 
                    FROM users 
                    WHERE username = :u OR email = :u
                """)
                result = conn.execute(query, {"u": username}).mappings().fetchone()
                
                if not result:
                    return False, None, "用户不存在"
                
                if result['status'] != 'active':
                    return False, None, "账号已被禁用"
                    
                # 验证密码
                if result['password_hash'] == hashed_pw or result['password_hash'] == password:
                    user_info = {
                        "id": result['id'],
                        "username": result['username'],
                        "nickname": result['nickname']
                    }
                    
                    # 更新最后登录时间
                    try:
                        conn.execute(
                            text("UPDATE users SET last_login_at = NOW() WHERE id = :id"),
                            {"id": result['id']}
                        )
                        conn.commit()
                    except Exception:
                        pass
                    
                    return True, user_info, "登录成功"
                else:
                    return False, None, "密码错误"
                    
        except Exception as e:
            logger.error(f"SQLAlchemy 登录验证异常: {e}")
    
    # 3. 本地 Mock 模式
    if username == "admin" and password == "password123":
        logger.warning(">>> 启用本地模拟登录模式 (离线) <<<")
        mock_user = {
            "id": 999,
            "username": "admin",
            "nickname": "测试管理员(离线)"
        }
        return True, mock_user, "登录成功 (离线模式)"
            
    # 构建错误信息
    err_msg = "登录失败: "
    if not client and not engine:
        err_msg += "未配置有效的数据库连接 (SUPABASE_KEY 或 DATABASE_URL)"
    else:
        err_msg += "无法连接数据库，且凭证无效"
        
    return False, None, err_msg

def create_user(username: str, password: str, nickname: str = "用户", email: str = None) -> Tuple[bool, str]:
    """
    创建新用户
    """
    hashed_pw = hash_password(password)
    
    # 优先使用 Supabase Client
    client = get_supabase_client()
    if client:
        try:
            data = {
                "username": username,
                "password_hash": hashed_pw,
                "nickname": nickname,
                "email": email,
                "status": "active"
            }
            client.table('users').insert(data).execute()
            return True, "用户创建成功"
        except Exception as e:
            return False, f"用户创建失败 (Supabase Client): {e}"
            
    # 回退到 SQLAlchemy
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO users (username, password_hash, nickname, email, status)
                        VALUES (:u, :p, :n, :e, 'active')
                    """),
                    {"u": username, "p": hashed_pw, "n": nickname, "e": email}
                )
                conn.commit()
                return True, "用户创建成功"
        except Exception as e:
            return False, f"用户创建失败 (SQLAlchemy): {e}"
            
    return False, "未配置数据库连接"
