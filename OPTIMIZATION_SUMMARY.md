# 国际宾客支持 — 项目优化总结

## 项目概况

| 指标 | 数值 |
|------|------|
| 产品名称 | 国际宾客支持 (WaiBin) |
| 域名 | internationalguestsupport.com |
| 技术栈 | Python 3.12 + Flask + Vercel Fluid Compute |
| 代码总量 | 5,607 行 (Python 2,179 / HTML 3,367 / JS 61) |
| 文件数量 | 71 个文件 |
| Blueprint 数量 | 8 个模块 |
| 中文页面 | 16 个 HTML 模板 |

## 核心功能矩阵

### Phase A（已完成）
| 功能 | 路由 | 描述 |
|------|------|------|
| 多语种翻译 | `/dashboard` | DeepSeek AI 驱动的菜单/物料翻译，支持 12 语种 |
| 门店信息管理 | `/console` (panel: profile) | 酒店/餐厅信息录入与管理 |
| Google 商家上架 | `/gmb` | GMB OAuth 一键创建商家页面 |
| TripAdvisor 上架 | `/tripadvisor` | 5 步图解指南 |
| 多格式导出 | 翻译面板内集成 | PDF 导出 + 高清图片 ZIP 导出 |
| 境外支付诊断 | `/payment/diagnosis` | 6 题诊断 → 推荐最佳支付方案 |
| 支付接入教程 | `/payment/tutorials` | Bank POS / 连连国际 / Airwallex 图示教程 |

### Phase B（已完成）
| 功能 | 路由 | 描述 |
|------|------|------|
| PSB 登记培训 | `/psb` | 5 步图解外宾住宿登记指南 |
| 护照 MRZ 识别 | `/psb/mrz` | ICAO 9303 标准护照机读码解析 |
| 出入境机构查询 | `/psb/contacts` | 50 城 PSB 出入境管理局联系信息 |
| 订阅支付 | `/subscription` | PayJS 微信支付三档套餐 |
| Beta 反馈 | `/beta/feedback` | 用户反馈提交与历史查询 |
| 健康检查 | `/api/health` | DeepSeek API + KV 存储 + 会话状态检测 |

### 三档订阅套餐
| 套餐 | 价格 | 日翻译量 | 语种数 |
|------|------|----------|--------|
| 免费版 | ¥0/月 | 20 次 | 4 种 |
| 专业版 | ¥29/月 | 200 次 | 8 种 |
| 企业版 | ¥99/月 | 1000 次 | 12 种 |

## 架构设计

```
api/index.py          → 入口点（Vercel Serverless）
app/__init__.py        → Flask App 工厂 + Session 配置
├── app/auth.py        → 手机验证码登录 + 速率限制 + 防暴力破解
├── app/translate.py   → DeepSeek API 翻译 + 翻译记录管理
├── app/merchant.py    → 门店信息 CRUD
├── app/gmb.py         → Google My Business OAuth
├── app/payment.py     → 支付诊断 + 教程页面
├── app/psb.py         → MRZ 解析 + PSB 指南 + 机构查询
├── app/psb_contacts.py → 50 城出入境管理局数据
├── app/payjs.py       → PayJS 微信支付订阅
├── app/beta.py        → 健康检查 + 反馈 + 错误日志
├── app/kv_client.py   → KV 存储抽象层 (Upstash Redis / Flask Session)
├── app/image_export.py → PDF + 图片导出
├── app/constants.py   → 中心化常量管理
└── app/static/app.js  → 共享前端 JS（msg, escapeHtml, requireAuth）
```

## 已修复问题

### P0 安全
- **TOCTOU 竞态条件**：速率限制从 GET-then-INCR 改为 INCR-first 原子模式
- **暴力破解防护**：验证码接口新增 5 次尝试限制（5 分钟封锁）
- **API Key 损坏**：移除错误的 ASCII 编码过滤，修复密钥字符被截断
- **PayJS 回调容错**：Redis 失败时写入 `pending_upgrade` 兜底键，防止丢单
- **Admin 端点认证**：新增 ADMIN_TOKEN 双重认证机制

### P1 可靠性
- **会话密钥回退**：移除有缺陷的 KV 回退逻辑，恢复简单 env var 模式
- **反馈列表修复**：修复时间戳遍历 bug，改用 `redis_keys(pattern)` 模式匹配
- **错误日志集中化**：新增 `log_error_to_kv()` 统一错误收集（环形缓冲 100 条）
- **翻译异常上报**：所有 translate.py URLError 接入错误日志系统

### P2 代码质量
- **共享 JS 抽取**：消除 5+ 模板中的重复 `msg()` / `escapeHtml()` / `requireAuth()`
- **常量中心化**：所有 TTL、限制值、模式标志移至 `constants.py`
- **环境变量文档化**：新建 `.env.example`，完整标注 13 个变量
- **Python 版本锁定**：`.python-version` 固定 3.12
- **全局重定向防护**：`_authRedirecting` guard 防止并发重定向 Bug

### UI/UX
- **Landing Page**：新建中文营销首页，英文 tagline "Turn your hotel foreign-guest-ready in 10 minutes"
- **产品更名**：全局 20 文件替换 "外宾接待助手" → "国际宾客支持"
- **Logo 图标**：16 个模板统一更新为 "客"
- **侧边栏重构**：7 大功能分区，新增外宾合规 + 支付中心 + 账户分区

## 部署信息

| 项目 | 值 |
|------|-----|
| 平台 | Vercel Fluid Compute |
| 运行时 | Python 3.12 |
| 域名 | internationalguestsupport.com |
| 项目文件 | `.vercel/project.json` |
| 环境变量 | 13 个（DeepSeek API Key + Upstash Redis + PayJS + GMB OAuth） |

---

*最后更新：2026-06-04*
