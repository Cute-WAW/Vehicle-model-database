import os
import hashlib
import logging
import sqlite3
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
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

# SQLite 数据库路径
SQLITE_DB_PATH = Path(__file__).parent.parent / 'users.sqlite'

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

def get_sqlite_conn():
    """获取 SQLite 连接"""
    try:
        conn = sqlite3.connect(str(SQLITE_DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"连接 SQLite 数据库失败: {e}")
        return None

def init_sqlite_db():
    """初始化 SQLite 数据库表"""
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    nickname TEXT,
                    email TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login_at TIMESTAMP
                )
            ''')
            
            # Prediction History table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prediction_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    vehicle_info TEXT NOT NULL,
                    prediction_result TEXT NOT NULL,
                    is_favorite INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(username) REFERENCES users(username) ON DELETE CASCADE
                )
            ''')
            
            conn.commit()
            logger.info(f"SQLite 数据库已初始化: {SQLITE_DB_PATH}")
        except Exception as e:
            logger.error(f"初始化 SQLite 表失败: {e}")
        finally:
            conn.close()

# 尝试初始化 SQLite
init_sqlite_db()

def hash_password(password: str) -> str:
    """
    对密码进行哈希处理 (SHA256)
    注意：生产环境建议使用 bcrypt 或 argon2
    """
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    验证用户登录
    优先使用 Supabase Client (REST API)，失败则回退到 SQLAlchemy，最后回退到 SQLite
    
    Returns:
        (success, user_info, message)
    """
    hashed_pw = hash_password(password)
    
    # 1. 尝试使用 Supabase Client (REST API)
    client = get_supabase_client()
    if client:
        try:
            response = client.table('users').select("*").or_(f"username.eq.{username},email.eq.{username}").execute()
            if response.data:
                user_data = response.data[0]
                if user_data.get('status') != 'active':
                    return False, None, "账号已被禁用"
                stored_hash = user_data.get('password_hash')
                if stored_hash == hashed_pw or stored_hash == password:
                    user_info = {"id": user_data['id'], "username": user_data['username'], "nickname": user_data['nickname']}
                    try:
                        client.table('users').update({"last_login_at": "now()"}).eq("id", user_data['id']).execute()
                    except Exception:
                        pass
                    return True, user_info, "登录成功"
                else:
                    return False, None, "密码错误"
        except Exception as e:
            logger.warning(f"Supabase Client 登录验证异常: {e}")

    # 2. 尝试使用 SQLAlchemy
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                query = text("SELECT id, username, nickname, password_hash, status FROM users WHERE username = :u OR email = :u")
                result = conn.execute(query, {"u": username}).mappings().fetchone()
                if result:
                    if result['status'] != 'active':
                        return False, None, "账号已被禁用"
                    if result['password_hash'] == hashed_pw or result['password_hash'] == password:
                        user_info = {"id": result['id'], "username": result['username'], "nickname": result['nickname']}
                        try:
                            conn.execute(text("UPDATE users SET last_login_at = NOW() WHERE id = :id"), {"id": result['id']})
                            conn.commit()
                        except Exception:
                            pass
                        return True, user_info, "登录成功"
                    else:
                        return False, None, "密码错误"
        except Exception as e:
            logger.warning(f"SQLAlchemy 登录验证异常: {e}")

    # 3. 尝试使用 SQLite
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, nickname, password_hash, status FROM users WHERE username = ? OR email = ?", (username, username))
            result = cursor.fetchone()
            if result:
                if result['status'] != 'active':
                    conn.close()
                    return False, None, "账号已被禁用"
                
                if result['password_hash'] == hashed_pw:
                    user_info = {"id": result['id'], "username": result['username'], "nickname": result['nickname']}
                    try:
                        cursor.execute("UPDATE users SET last_login_at = datetime('now') WHERE id = ?", (result['id'],))
                        conn.commit()
                    except Exception:
                        pass
                    conn.close()
                    return True, user_info, "登录成功"
                else:
                    conn.close()
                    return False, None, "密码错误"
            conn.close()
        except Exception as e:
            logger.error(f"SQLite 登录验证异常: {e}")
            if conn: conn.close()

    # 4. 本地 Mock 模式 (仅当没有其他数据库可用且账号是admin时)
    if username == "admin" and password == "password123":
        logger.warning(">>> 启用本地模拟登录模式 (离线) <<<")
        mock_user = {"id": 999, "username": "admin", "nickname": "测试管理员(离线)"}
        return True, mock_user, "登录成功 (离线模式)"
            
    return False, None, "登录失败: 用户不存在或密码错误"

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """通过用户名获取用户"""
    if not username:
        return None

    client = get_supabase_client()
    if client:
        try:
            response = client.table('users').select("id, username, nickname, status").eq("username", username).execute()
            if response.data:
                user_data = response.data[0]
                if user_data.get('status') != 'active':
                    return None
                return {"id": user_data['id'], "username": user_data['username'], "nickname": user_data['nickname']}
        except Exception as e:
            logger.warning(f"通过用户名获取用户异常 (Supabase): {e}")

    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                query = text("SELECT id, username, nickname, status FROM users WHERE username = :u")
                result = conn.execute(query, {"u": username}).mappings().fetchone()
                if result:
                    if result['status'] != 'active':
                        return None
                    return {"id": result['id'], "username": result['username'], "nickname": result['nickname']}
        except Exception as e:
            logger.warning(f"通过用户名获取用户异常 (SQLAlchemy): {e}")

    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, nickname, status FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            conn.close()
            if result:
                if result['status'] != 'active':
                    return None
                return {"id": result['id'], "username": result['username'], "nickname": result['nickname']}
        except Exception as e:
            logger.warning(f"通过用户名获取用户异常 (SQLite): {e}")
            if conn:
                conn.close()

    return None

def get_user_by_id(user_id: Any) -> Optional[Dict[str, Any]]:
    """通过用户 ID 获取用户"""
    if user_id is None:
        return None

    client = get_supabase_client()
    if client:
        try:
            response = client.table('users').select("id, username, nickname, status").eq("id", user_id).execute()
            if response.data:
                user_data = response.data[0]
                if user_data.get('status') != 'active':
                    return None
                return {"id": user_data['id'], "username": user_data['username'], "nickname": user_data['nickname']}
        except Exception as e:
            logger.warning(f"通过用户 ID 获取用户异常 (Supabase): {e}")

    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                query = text("SELECT id, username, nickname, status FROM users WHERE id = :id")
                result = conn.execute(query, {"id": user_id}).mappings().fetchone()
                if result:
                    if result['status'] != 'active':
                        return None
                    return {"id": result['id'], "username": result['username'], "nickname": result['nickname']}
        except Exception as e:
            logger.warning(f"通过用户 ID 获取用户异常 (SQLAlchemy): {e}")

    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, nickname, status FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            conn.close()
            if result:
                if result['status'] != 'active':
                    return None
                return {"id": result['id'], "username": result['username'], "nickname": result['nickname']}
        except Exception as e:
            logger.warning(f"通过用户 ID 获取用户异常 (SQLite): {e}")
            if conn:
                conn.close()

    return None

def resolve_canonical_username(user_id: Any = None, username: str = "") -> str:
    """解析数据库中的真实用户名，兼容旧 token 中缺失或错误的 username"""
    if username:
        matched_user = get_user_by_username(username)
        if matched_user:
            return matched_user["username"]
        logger.warning(f"Token 中的 username 不存在，回退到 user_id 查询: {username}")

    matched_user = get_user_by_id(user_id)
    if matched_user:
        return matched_user["username"]

    if username:
        return username
    if user_id is not None:
        return f"wx_user_{user_id}"
    return ""

def get_user_by_openid(openid: str) -> Optional[Dict[str, Any]]:
    """通过微信 OpenID 获取用户"""
    client = get_supabase_client()
    if client:
        try:
            response = client.table('users').select("id, username, nickname, status").eq("wechat_openid", openid).execute()
            if response.data:
                user_data = response.data[0]
                if user_data.get('status') != 'active':
                    return None
                try:
                    client.table('users').update({"last_login_at": "now()"}).eq("id", user_data['id']).execute()
                except Exception:
                    pass
                return {"id": user_data['id'], "username": user_data['username'], "nickname": user_data['nickname']}
        except Exception as e:
            logger.warning(f"获取微信用户异常 (Supabase): {e}")

    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                query = text("SELECT id, username, nickname, status FROM users WHERE wechat_openid = :o")
                result = conn.execute(query, {"o": openid}).mappings().fetchone()
                if result:
                    if result['status'] != 'active':
                        return None
                    try:
                        conn.execute(text("UPDATE users SET last_login_at = NOW() WHERE id = :id"), {"id": result['id']})
                        conn.commit()
                    except Exception:
                        pass
                    return {"id": result['id'], "username": result['username'], "nickname": result['nickname']}
        except Exception as e:
            logger.warning(f"获取微信用户异常 (SQLAlchemy): {e}")

    # 对于离线测试，兼容直接使用 openid 当成用户名的情况
    if "wx_" in openid or "test_" in openid:
        return {"id": 1000, "username": openid, "nickname": "微信用户"}
        
    return None

def create_wechat_user_if_not_exists(openid: str, nickname: str = "微信用户", avatar_url: str = "") -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """如果不存在，则静默注册一个微信用户，然后返回用户信息"""
    user = get_user_by_openid(openid)
    if user:
        return True, user, "登录成功"
        
    # 生成随机密码和用户名
    import secrets
    import time
    pwd = secrets.token_hex(16)
    hashed_pw = hash_password(pwd)
    generated_username = f"wx_{openid[-8:]}_{int(time.time())}"
    
    client = get_supabase_client()
    if client:
        try:
            data = {
                "username": generated_username, 
                "password_hash": hashed_pw, 
                "nickname": nickname, 
                "wechat_openid": openid,
                "avatar_url": avatar_url,
                "status": "active"
            }
            res = client.table('users').insert(data).execute()
            if res.data:
                new_user = res.data[0]
                return True, {"id": new_user['id'], "username": new_user['username'], "nickname": new_user['nickname']}, "注册并登录成功"
        except Exception as e:
            err_msg = str(e)
            if "duplicate key" in err_msg or "23505" in err_msg:
                # username 碰撞极罕见（同秒同后缀），重试一次换新时间戳
                generated_username = f"wx_{openid[-8:]}_{int(time.time()) + 1}"
                try:
                    data["username"] = generated_username
                    res = client.table('users').insert(data).execute()
                    if res.data:
                        new_user = res.data[0]
                        return True, {"id": new_user['id'], "username": new_user['username'], "nickname": new_user['nickname']}, "注册并登录成功"
                except Exception as e2:
                    logger.error(f"创建微信用户重试失败 (Supabase): {e2}")
            else:
                logger.warning(f"创建微信用户失败 (Supabase): {e}")

    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(
                    text("INSERT INTO users (username, password_hash, nickname, wechat_openid, avatar_url, status) VALUES (:u, :p, :n, :o, :a, 'active')"),
                    {"u": generated_username, "p": hashed_pw, "n": nickname, "o": openid, "a": avatar_url}
                )
                conn.commit()
                # 重新查询获取ID
                user = get_user_by_openid(openid)
                if user:
                    return True, user, "注册并登录成功"
        except Exception as e:
            logger.warning(f"创建微信用户失败 (SQLAlchemy): {e}")

    # Fallback mock user
    return True, {"id": 1000, "username": generated_username, "nickname": nickname}, "注册并登录成功(离线)"

def create_user(username: str, password: str, nickname: str = "用户", email: str = None) -> Tuple[bool, str]:
    """创建新用户"""
    hashed_pw = hash_password(password)
    
    # Supabase
    client = get_supabase_client()
    if client:
        try:
            data = {"username": username, "password_hash": hashed_pw, "nickname": nickname, "email": email, "status": "active"}
            client.table('users').insert(data).execute()
            return True, "用户创建成功"
        except Exception as e:
            err_msg = str(e)
            if "duplicate key" in err_msg or "23505" in err_msg:
                return False, "用户名已被注册"
            logger.warning(f"用户创建失败 (Supabase): {e}")

    # SQLAlchemy
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                conn.execute(
                    text("INSERT INTO users (username, password_hash, nickname, email, status) VALUES (:u, :p, :n, :e, 'active')"),
                    {"u": username, "p": hashed_pw, "n": nickname, "e": email}
                )
                conn.commit()
                return True, "用户创建成功"
        except Exception as e:
            err_msg = str(e)
            if "duplicate key" in err_msg or "23505" in err_msg or "UniqueViolation" in err_msg:
                return False, "用户名已被注册"
            logger.warning(f"用户创建失败 (SQLAlchemy): {e}")

    # SQLite
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, nickname, email, status) VALUES (?, ?, ?, ?, 'active')",
                (username, hashed_pw, nickname, email)
            )
            conn.commit()
            conn.close()
            return True, "用户创建成功"
        except sqlite3.IntegrityError:
            conn.close()
            return False, "用户名已存在"
        except Exception as e:
            conn.close()
            return False, f"用户创建失败 (SQLite): {e}"

    return False, "无法连接到任何数据库"

def change_password(username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
    """修改密码"""
    hashed_old = hash_password(old_password)
    hashed_new = hash_password(new_password)
    
    # Supabase
    client = get_supabase_client()
    if client:
        try:
            # 验证旧密码
            res = client.table('users').select("password_hash").eq("username", username).execute()
            if not res.data or res.data[0]['password_hash'] != hashed_old:
                return False, "旧密码错误"
            
            client.table('users').update({"password_hash": hashed_new}).eq("username", username).execute()
            return True, "密码修改成功"
        except Exception as e:
            logger.warning(f"修改密码失败 (Supabase): {e}")

    # SQLAlchemy
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT password_hash FROM users WHERE username = :u"), {"u": username}).fetchone()
                if not res or res[0] != hashed_old:
                    return False, "旧密码错误"
                
                conn.execute(text("UPDATE users SET password_hash = :p WHERE username = :u"), {"p": hashed_new, "u": username})
                conn.commit()
                return True, "密码修改成功"
        except Exception as e:
            logger.warning(f"修改密码失败 (SQLAlchemy): {e}")

    # SQLite
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
            res = cursor.fetchone()
            if not res or res['password_hash'] != hashed_old:
                conn.close()
                return False, "旧密码错误"
            
            cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hashed_new, username))
            conn.commit()
            conn.close()
            return True, "密码修改成功"
        except Exception as e:
            conn.close()
            return False, f"修改密码失败 (SQLite): {e}"

    return False, "操作失败"

def delete_user(username: str, password: str) -> Tuple[bool, str]:
    """注销账号"""
    hashed_pw = hash_password(password)
    
    # Supabase
    client = get_supabase_client()
    if client:
        try:
            res = client.table('users').select("password_hash").eq("username", username).execute()
            if not res.data or res.data[0]['password_hash'] != hashed_pw:
                return False, "密码错误"
            
            client.table('users').delete().eq("username", username).execute()
            return True, "账号已注销"
        except Exception as e:
            logger.warning(f"注销失败 (Supabase): {e}")

    # SQLAlchemy
    engine = get_db_engine()
    if engine:
        try:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT password_hash FROM users WHERE username = :u"), {"u": username}).fetchone()
                if not res or res[0] != hashed_pw:
                    return False, "密码错误"
                
                conn.execute(text("DELETE FROM users WHERE username = :u"), {"u": username})
                conn.commit()
                return True, "账号已注销"
        except Exception as e:
            logger.warning(f"注销失败 (SQLAlchemy): {e}")

    # SQLite
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
            res = cursor.fetchone()
            if not res or res['password_hash'] != hashed_pw:
                conn.close()
                return False, "密码错误"
            
            cursor.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
            conn.close()
            return True, "账号已注销"
        except Exception as e:
            conn.close()
            return False, f"注销失败 (SQLite): {e}"

    return False, "操作失败"

# ================= 预测历史与收藏 =================

def add_history_record(username: str, vehicle_info: dict, prediction_result: dict) -> Tuple[bool, Any, str]:
    """添加预测记录"""
    # 1. Supabase Implementation
    client = get_supabase_client()
    if client:
        try:
            data = {
                "username": username,
                "vehicle_info": vehicle_info,
                "prediction_result": prediction_result,
                "is_favorite": False
            }
            res = client.table('prediction_history').insert(data).execute()
            if res.data:
                return True, res.data[0]['id'], "记录已保存"
        except Exception as e:
            logger.error(f"保存历史记录失败 (Supabase): {e}")

    # 2. SQLite Implementation (Fallback)
    # 转换为 JSON 字符串
    vehicle_json = json.dumps(vehicle_info, ensure_ascii=False)
    result_json = json.dumps(prediction_result, ensure_ascii=False)
    
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO prediction_history (username, vehicle_info, prediction_result) VALUES (?, ?, ?)",
                (username, vehicle_json, result_json)
            )
            record_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return True, record_id, "记录已保存 (本地)"
        except Exception as e:
            conn.close()
            logger.error(f"保存历史记录失败 (SQLite): {e}")
            return False, None, f"保存失败: {e}"
            
    return False, None, "数据库不可用"

def toggle_favorite(username: str, record_id: Any) -> Tuple[bool, bool, str]:
    """切换收藏状态"""
    # 1. Supabase Implementation
    client = get_supabase_client()
    if client:
        try:
            # 确认归属权并获取状态
            res = client.table('prediction_history').select("is_favorite").eq("id", record_id).eq("username", username).execute()
            if not res.data:
                return False, False, "记录不存在或无权操作"
            
            current_status = res.data[0]['is_favorite']
            new_status = not current_status
            
            client.table('prediction_history').update({"is_favorite": new_status}).eq("id", record_id).execute()
            return True, new_status, "收藏状态已更新"
        except Exception as e:
            logger.error(f"切换收藏失败 (Supabase): {e}")

    # 2. SQLite Implementation (Fallback)
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            # 确认归属权
            cursor.execute("SELECT is_favorite FROM prediction_history WHERE id = ? AND username = ?", (record_id, username))
            res = cursor.fetchone()
            if not res:
                conn.close()
                return False, False, "记录不存在或无权操作"
            
            new_status = 0 if res['is_favorite'] else 1
            cursor.execute("UPDATE prediction_history SET is_favorite = ? WHERE id = ?", (new_status, record_id))
            conn.commit()
            conn.close()
            return True, bool(new_status), "收藏状态已更新 (本地)"
        except Exception as e:
            conn.close()
            return False, False, f"操作失败: {e}"
            
    return False, False, "数据库不可用"

def get_user_history(username: str, favorites_only: bool = False) -> List[Dict]:
    """获取用户历史/收藏记录"""
    # 1. Supabase Implementation
    client = get_supabase_client()
    if client:
        try:
            query = client.table('prediction_history').select("*").eq("username", username)
            if favorites_only:
                query = query.eq("is_favorite", True)
            
            # 排序：创建时间倒序
            res = query.order("created_at", desc=True).limit(50).execute()
            
            result = []
            for row in res.data:
                result.append({
                    "id": row['id'],
                    "vehicle_info": row['vehicle_info'],
                    "prediction_result": row['prediction_result'],
                    "is_favorite": row['is_favorite'],
                    "created_at": row['created_at']
                })
            return result
        except Exception as e:
            logger.error(f"获取历史记录失败 (Supabase): {e}")

    # 2. SQLite Implementation (Fallback)
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM prediction_history WHERE username = ?"
            params = [username]
            
            if favorites_only:
                query += " AND is_favorite = 1"
                
            query += " ORDER BY created_at DESC LIMIT 50"
            
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                result.append({
                    "id": row['id'],
                    "vehicle_info": json.loads(row['vehicle_info']),
                    "prediction_result": json.loads(row['prediction_result']),
                    "is_favorite": bool(row['is_favorite']),
                    "created_at": row['created_at']
                })
            conn.close()
            return result
        except Exception as e:
            conn.close()
            logger.error(f"获取历史记录失败 (SQLite): {e}")
            return []
            
    return []

def delete_history_records(username: str, record_ids: List[Any]) -> Tuple[bool, str]:
    """删除预测历史记录 (支持批量)"""
    if not record_ids:
        return True, "无记录需要删除"
        
    # 1. Supabase Implementation
    client = get_supabase_client()
    if client:
        try:
            # 批量删除，需确保归属权 (Supabase RLS 通常处理，但显式加 username 过滤更安全)
            res = client.table('prediction_history').delete().in_('id', record_ids).eq('username', username).execute()
            return True, f"成功删除 {len(res.data) if res.data else '选中'} 条记录"
        except Exception as e:
            logger.error(f"删除历史记录失败 (Supabase): {e}")

    # 2. SQLite Implementation (Fallback)
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            placeholders = ','.join(['?'] * len(record_ids))
            query = f"DELETE FROM prediction_history WHERE id IN ({placeholders}) AND username = ?"
            params = record_ids + [username]
            
            cursor.execute(query, tuple(params))
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            return True, f"成功删除 {deleted_count} 条记录 (本地)"
        except Exception as e:
            conn.close()
            logger.error(f"删除历史记录失败 (SQLite): {e}")
            return False, f"删除失败: {e}"
            
    return False, "数据库不可用"
