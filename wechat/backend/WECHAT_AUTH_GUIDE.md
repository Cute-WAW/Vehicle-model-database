# 微信小程序登录与 Supabase 物联集成指南

本文档描述了如何将微信小程序的“静默登录”与主系统的 Supabase 数据库打通，并预留了相关接口说明。

## 1. 核心流程概述

1.  **小程序端**：调用 `wx.login()` 获取临时登录凭证 `code`。
2.  **后端 (`api.py`)**：接收 `code`，调用微信官方接口 `jscode2session` 换取唯一的 `openid`。
3.  **数据库层 (`db_supabase.py`)**：
    *   使用 `openid` 在 Supabase `users` 表中查询是否有匹配记录。
    *   **若有**：返回用户信息。
    *   **若无**：为该微信用户自动创建一个 Web 账号，并记录其 `openid`。
4.  **授权响应**：后端签发 JWT Token 返回给小程序，后续所有请求（如历史记录、估价）均通过此 Token 识别用户。

---

## 2. 环境配置 (启用真实微信登录)

目前后端代码在检测到以下环境变量不为空时，会自动从“模拟登录”切换为“真实微信验证”：

在项目根目录或 `wechat/backend/` 下的 `.env` 文件中配置：
```bash
WECHAT_APPID=您的微信小程序AppID
WECHAT_SECRET=您的微信小程序AppSecret
```

> [!IMPORTANT]
> 若以上配置为空，系统将回退到 **Mock 模式**（即直接将 `code` 视为 `openid`），方便离线开发调试。

---

## 3. 数据库结构 (Supabase - 已就绪)

目前系统已连接了 `.env` 文件中配置的远程 Supabase 数据库，并且所有支持微信登录与估价历史存储的表结构**均已准备就绪**，不仅不需要再手动执行任何 `ALTER TABLE` 操作，`users` 表与 `prediction_history` 表也完全支持跨端数据连通。

### 小程序相关数据表结构：

**`users` 表 (用户中心)**
| 字段名 | 说明 |
| :--- | :--- |
| `id` | 主键，自增分配 |
| `username` | 自动生成的绑定用户名 (形如 `wx_随机串...`) |
| `wechat_openid` | **微信用户的唯一标识** (已存在且已设置 UNIQUE 索引) |
| `nickname` | 用户昵称 |
| `avatar_url` | 用户头像地址 |
| `last_login_at` | 最新活跃时间记录 |

**`prediction_history` 表 (估价历史与收藏)**
| 字段名 | 说明 |
| :--- | :--- |
| `id` | 历史记录唯一主键 |
| `username` | 记录归属的用户名 (作为外键关联回 `users` 表) |
| `vehicle_info` | 存储小程序提交的车辆源信息（含品牌、年限、里程等） |
| `prediction_result` | 完整存储预测出的 9 宫格价格矩阵和评估解读报告 |
| `is_favorite` | Boolean：是否收藏该估价记录 |
| `created_at` | 该条记录的估价产生时间 |

---

## 4. 关键接口说明

### 后端预留接口 (`wechat/backend/api.py`)

*   **路径**: `POST /api/auth/login`
*   **功能**: 自动识别 `code`。若为真实 code 且配置了 Secret，则向 `https://api.weixin.qq.com/sns/jscode2session` 发起请求。
*   **逻辑**: 内部调用 `db_supabase.py` 中的 `create_wechat_user_if_not_exists` 方法实现数据库联动。

### 数据库驱动接口 (`src/db_supabase.py`)

*   **`get_user_by_openid(openid)`**: 优先从 Supabase REST API 查询记录，若失败则通过 SQLAlchemy 或 SQLite 顺序降级查询。
*   **`create_wechat_user_if_not_exists(...)`**: 封装了“查不到即注册”的完整事务逻辑。

---

## 5. 后续开发建议

1.  **AppID 申请**: 需在[微信公众平台](https://mp.weixin.qq.com/)注册小程序获取 AppID。
2.  **域名白名单**: 在生产环境上线前，需将您的后端服务器域名添加到微信公众平台的“request 合法域名”中。
3.  **用户信息获取**: 微信目前已收回直接获取头像昵称的权限，建议在小程序端通过 `bindchooseavatar` 和 `input` 让用户手动补充，再通过 `POST /api/auth/login` 更新到数据库。
