# 二手车估价微信小程序 - 部署与集成总结

本文档总结了 2026-03-25 完成的小程序后端架构升级、Supabase 数据库对接及身份验证修复工作。

## 🛠 已完成的修改操作

### 1. 后端架构 (Backend)
- **启动入口**: 创建了 `wechat/backend/main.py`，支持 FastAPI 路由挂载、CORS 跨域（兼容开发者工具）以及 `sys.path` 自动修复。
- **单例模式**: 实现了残值预测器 (`ResidualPredictor`) 的全局单例，解决了模型文件重复加载导致的内存与启动延迟问题。
- **启动脚本**: 提供 `wechat/start_wechat_backend.bat`，可一键启动服务并自动检查依赖。

### 2. 数据库集成 (Supabase Sync)
- **身份共享**: 彻底废弃了原有的本地 SQLite (`price_eval.db`)，将用户注册与记录系统迁移至 **Supabase**。
- **静默注册**: 实现了基于微信 OpenID 的自动注册逻辑。
- **历史记录**: 小程序端的估价历史现在与 Web 端共用 `prediction_history` 表，实现了**跨终端数据互通**。

### 3. 身份验证修复 (401 Error Fix)
- **Secret 持久化**: 在 `auth.py` 中固定了 `SECRET_KEY`，解决了后端热重启导致 Token 集体失效的问题。
- **前端重连**: 在 `app.js` 中新增了 401 自动拦截器。当检测到证书失效时，小程序会自动尝试 `testLogin` 换领新票并重新执行中断的请求包。
- **详细日志**: 在 `wechat_auth` 和 `wechat_api` 模块中增加了冗余日志，方便后续调试。

### 4. 环境补全 (Dependencies)
- **依赖库**: 确认并补全了 `scipy` (v1.13.1) 环境，确保 `scikit-learn` 模型预测链路完整。
- **结构适配**: 调整了 `api.py` 的返回 JSON 结构，确保其与前端 `result.wxml` 和 `history.js` 的变量名 (`predicted_price`, `similar_vehicles` 等) 完全一致。

## 📂 核心文件清单

| 文件路径 | 说明 |
|----------|------|
| `wechat/backend/main.py` | 后端服务主入口 (FastAPI) |
| `wechat/backend/api.py` | 业务协议层 (已对接 Supabase) |
| `wechat/backend/auth.py` | JWT 鉴权逻辑 (已修复密钥随机性) |
| `wechat/miniprogram/app.js` | 小程序全局配置 (含 401 自动重连) |
| `wechat/start_wechat_backend.bat` | Windows 启动脚本 |
| `src/db_supabase.py` | 数据库访问层 (新增微信适配函数) |

## 🚀 后续维护建议

- **生产环境**: 部署至云服务器时，请在 `.env` 中设置 `JWT_SECRET` 为高强度随机字符串。
- **微信 AppID**: 若要接入真实微信登录，请在 `api.py` 中配置 `WECHAT_APPID` 和 `WECHAT_SECRET`。
- **数据库**: 所有历史数据现在均在 Supabase 控制台的 `prediction_history` 表中，可通过 `username` 字段（格式为 `wx_user_ID`）进行筛选。
