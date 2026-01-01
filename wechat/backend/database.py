"""
数据库模块 - SQLite

管理用户和估价历史记录
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from contextlib import contextmanager

# 数据库路径
DB_PATH = Path(__file__).parent / "price_eval.db"


@dataclass
class UserRecord:
    """用户记录"""
    id: int
    openid: str
    nickname: str
    avatar_url: str
    created_at: str
    last_login: str


@dataclass
class EvaluationRecord:
    """估价记录"""
    id: int
    user_id: int
    vehicle_full_name: str
    brand_series: str
    years: float
    mileage: float
    grade: str
    predicted_price: float
    price_low: float
    price_high: float
    explanation_json: str  # JSON string
    created_at: str
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        # 解析 explanation JSON
        try:
            result['explanation'] = json.loads(self.explanation_json)
        except:
            result['explanation'] = None
        del result['explanation_json']
        return result


@contextmanager
def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """初始化数据库表"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 用户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                openid TEXT UNIQUE NOT NULL,
                nickname TEXT DEFAULT '用户',
                avatar_url TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 估价历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                vehicle_full_name TEXT NOT NULL,
                brand_series TEXT NOT NULL,
                years REAL NOT NULL,
                mileage REAL DEFAULT 0,
                grade TEXT DEFAULT '中',
                predicted_price REAL NOT NULL,
                price_low REAL,
                price_high REAL,
                explanation_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_user_id ON evaluations(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_created_at ON evaluations(created_at)")
        
        conn.commit()
        print(f"Database initialized: {DB_PATH}")


# ========== 用户操作 ==========

def get_or_create_user(openid: str, nickname: str = "用户", avatar_url: str = "") -> UserRecord:
    """获取或创建用户"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 尝试获取
        cursor.execute("SELECT * FROM users WHERE openid = ?", (openid,))
        row = cursor.fetchone()
        
        if row:
            # 更新最后登录时间
            cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (row['id'],))
            conn.commit()
            return UserRecord(**dict(row))
        
        # 创建新用户
        cursor.execute(
            "INSERT INTO users (openid, nickname, avatar_url) VALUES (?, ?, ?)",
            (openid, nickname, avatar_url)
        )
        conn.commit()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,))
        row = cursor.fetchone()
        return UserRecord(**dict(row))


def get_user_by_id(user_id: int) -> Optional[UserRecord]:
    """通过 ID 获取用户"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return UserRecord(**dict(row)) if row else None


# ========== 估价历史操作 ==========

def save_evaluation(
    user_id: int,
    vehicle_full_name: str,
    brand_series: str,
    years: float,
    mileage: float,
    grade: str,
    predicted_price: float,
    price_low: float,
    price_high: float,
    explanation: Optional[Dict] = None
) -> int:
    """保存估价记录，返回 ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        explanation_json = json.dumps(explanation, ensure_ascii=False) if explanation else None
        
        cursor.execute("""
            INSERT INTO evaluations 
            (user_id, vehicle_full_name, brand_series, years, mileage, grade, 
             predicted_price, price_low, price_high, explanation_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, vehicle_full_name, brand_series, years, mileage, grade,
              predicted_price, price_low, price_high, explanation_json))
        
        conn.commit()
        return cursor.lastrowid


def get_user_evaluations(user_id: int, limit: int = 50, offset: int = 0) -> List[Dict]:
    """获取用户的估价历史"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM evaluations 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        """, (user_id, limit, offset))
        
        rows = cursor.fetchall()
        return [EvaluationRecord(**dict(row)).to_dict() for row in rows]


def get_evaluation_by_id(eval_id: int, user_id: int) -> Optional[Dict]:
    """获取单条估价记录"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM evaluations WHERE id = ? AND user_id = ?",
            (eval_id, user_id)
        )
        row = cursor.fetchone()
        return EvaluationRecord(**dict(row)).to_dict() if row else None


def delete_evaluation(eval_id: int, user_id: int) -> bool:
    """删除估价记录"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM evaluations WHERE id = ? AND user_id = ?",
            (eval_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0


def get_user_evaluation_count(user_id: int) -> int:
    """获取用户估价总数"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM evaluations WHERE user_id = ?", (user_id,))
        return cursor.fetchone()[0]


# 初始化
if __name__ == "__main__":
    init_db()
    
    # 测试
    user = get_or_create_user("test_openid_123", "测试用户")
    print(f"User: {user}")
    
    eval_id = save_evaluation(
        user_id=user.id,
        vehicle_full_name="丰田 凯美瑞 2015款",
        brand_series="丰田-凯美瑞",
        years=10.0,
        mileage=8.5,
        grade="中",
        predicted_price=5.5,
        price_low=5.0,
        price_high=6.0,
        explanation={"summary": "测试"}
    )
    print(f"Saved evaluation ID: {eval_id}")
    
    history = get_user_evaluations(user.id)
    print(f"History: {history}")
