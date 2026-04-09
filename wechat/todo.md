# 二手车估价微信小程序 - 开发规划

## 项目目标
将 `/predict` API 封装到微信小程序，让业务人员可以在手机上随时估价。

---

## 需求确认 ✅

| 需求项 | 决定 |
|--------|------|
| 小程序账号 | 测试账号开发 → 企业账号上线 |
| 部署方案 | 云服务器 (生产环境) |
| 用户权限 | ✅ 需要登录/权限控制 |
| 历史记录 | ✅ 需要保存估价历史 |

---

## 开发进度

### Phase 1: 后端增强 ✅ 完成
- [x] `/predict` API 已就绪
- [x] 返回格式已包含 `explanation`
- [x] 用户认证 (JWT) - `wechat/backend/auth.py`
- [x] 数据库设计 - `wechat/backend/database.py`
- [x] 小程序 API 路由 - `wechat/backend/api.py`

### Phase 2: 微信小程序开发 ✅ 完成
- [x] 创建小程序项目结构
- [x] 首页 - 车辆信息输入 (`pages/index`)
- [x] 结果页 - 估价结果展示 (`pages/result`)
- [x] 历史页 - 估价记录列表 (`pages/history`)
- [x] 全局样式和配置

### Phase 3: 部署上线 🔄 待进行
- [ ] 集成 API 到主服务
- [ ] 后端部署到云服务器
- [ ] 配置 HTTPS + 域名
- [ ] 小程序提交审核
- [ ] 发布上线

### Phase 4: 未来功能升级规划 📅
- [ ] **用户身份强化**：跟进最新的微信接口能力（如 `chooseAvatar` 和 `nickName` 输入框），允许并存储用户提供真实个人头像与昵称，取代当前的灰图和默认 wx_xxx 名称。

---

## 项目结构

```
wechat/
├── todo.md                    # 本文件
├── backend/
│   ├── auth.py                # JWT 认证 ✅
│   ├── database.py            # SQLite 数据库 ✅
│   ├── api.py                 # FastAPI 路由 ✅
│   └── price_eval.db          # 数据库文件 (自动创建)
└── miniprogram/
    ├── app.js                 # 全局逻辑 ✅
    ├── app.json               # 全局配置 ✅
    ├── app.wxss               # 全局样式 ✅
    └── pages/
        ├── index/             # 首页 ✅
        ├── result/            # 结果页 ✅
        └── history/           # 历史页 ✅
```

---

## 下一步: 测试运行

### 1. 集成 API 到主服务
修改 `src/web_predictor_debug_step5.py` 引入小程序 API：

```python
from wechat.backend.api import router as wechat_router
app.include_router(wechat_router)
```

### 2. 使用微信开发者工具
1. 下载 [微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
2. 打开项目 `wechat/miniprogram` 目录
3. 使用测试 AppID 或申请测试账号
4. 启动本地 API 服务 (localhost:8003)
5. 在开发者工具中预览测试

### 3. 获取测试 Token
```bash
curl http://localhost:8003/api/test/token
```
