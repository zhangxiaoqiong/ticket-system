# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## 项目概述

顺心分单诊断工单系统 — 承接 Dify 诊断结果的轻量工单系统（FastAPI + SQLAlchemy + MySQL + Jinja2）。

Dify 创建工单 → 落库 → 推送丰声 Next 群消息 → 运营人员通过 Web 页面处理闭环。

## 常用命令

```bash
# 启动开发服务
python run.py
# 等价于: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 安装依赖
pip install -r requirements.txt

# 测试数据（JSON）
test/测试数据_单地址.json
test/测试数据_多地址.json
```

无测试框架、无 lint 配置、无 CI 流水线配置。启动时 `Base.metadata.create_all` 自动建表。

## 项目结构

```
app/
  main.py              # FastAPI 入口，注册路由，启动时做字段兼容性检查（ALTER TABLE 补 reporter_group / actual_reporter_account / reporter_group_name）
  config.py            # pydantic-settings 配置，读取 .env
  database.py          # SQLAlchemy engine / session（pool_pre_ping, 1h recycle）
  models.py            # ticket / ticket_item / ticket_event 三张表
  schemas.py           # 请求/响应 Pydantic 模型（camelCase 入参）
  send_message.py      # 丰声 Next OAuth2 token + 模板 1312 消息发送
  routers/
    ticket_api.py      # RESTful API（/api/tickets）
    ticket_pages.py    # Jinja2 页面路由（/tickets）+ cookie 登录
  services/
    id_generator.py    # 工单编号生成 SX{yyMMddHHmmss}
    notify_service.py  # 丰声 Next 通知（分群 + @提醒 + 处理完成通知）
    ticket_service.py  # 工单核心业务逻辑（创建/状态流转/聚合）
  templates/
    login.html         # 操作员登录页
    ticket_list.html   # 工单列表页（分页 + 筛选）
    ticket_detail.html # 工单详情页（明细/事件/状态表单/关闭表单）
```

## 架构要点

### 批量工单 & 状态聚合

一个工单（Ticket）可包含多个地址明细（TicketItem），每个明细独立处理。父工单状态由子明细自动聚合：
- 全部 CLOSED → CLOSED
- 全部 RESOLVED/CLOSED → RESOLVED
- 有 PROCESSING → PROCESSING
- 否则 → NEW

聚合逻辑在 `ticket_service.aggregate_ticket_status()` 中实现。

### 工单编号来源

- 生产环境由 Dify 传入 `ticketNo`，后端只做唯一性校验
- 不传时后端使用 `SX{yyMMddHHmmss}` 格式生成测试编号

### 幂等设计

- 请求必须携带 `idempotentKey`
- 后端先查 `idempotent_key`，存在则返回已有工单（`duplicated=true`），不重复创建、不重复推送消息
- 未传时基于内容 MD5 生成，作为兜底

### 工单状态

四个状态：`NEW` → `PROCESSING` → `RESOLVED` → `CLOSED`

- 通过状态表单选择目标状态 + 填写处理说明保存
- 选择 `CLOSED` 时必须填写处理说明，写入 `resolved_result` 和 `closed_at`
- 已关闭工单禁止继续操作

### 通知服务

- **创建通知**：丰声 Next 模板 1312 消息，支持按 `business_type` / `source_channel` / `priority` 级联分群（精确匹配 → "default" 兜底）
- **处理通知**：明细状态变为 RESOLVED/CLOSED 时，可选通知报事人（通过 `notify_user_ids` JSON 字段配置 @提醒目标）
- **容错**：通知失败只记事件流水，不阻塞工单创建（API 层会 rollback 后抛异常）

### Web 页面认证

Cookie-based 简单认证（7 天过期，httponly + samesite=lax），操作员输入工号和姓名登录。无 JWT、无 session 存储。Cookie 名：`ticket_operator_account` / `ticket_operator_name`。

所有 `/tickets` 路由受 `operator_or_redirect()` 守卫，未登录重定向到 `/login?next=...`。

### 子路径部署

- `base_url`：对外完整地址（丰声消息里的工单链接用这个）
- `app_base_path`：Nginx 子路径前缀，如 `/ticket-system`
- Nginx 转发时去掉前缀：`location /ticket-system/ { proxy_pass http://127.0.0.1:8000/; }`

### 数据库 & 迁移

- 三张表：`ticket`（主表）、`ticket_item`（地址明细）、`ticket_event`（事件流水）
- 大量 JSON 字段（`diagnosis_payload`、`operation_suggestion`、`v5_result`、`village_result`、`notify_user_ids`）用于灵活扩展
- 无 Alembic；`main.py` 启动时 `ensure_compatible_schema()` 用 ALTER TABLE 补缺失列（如 `reporter_group`）
- 生产环境建议引入迁移工具做严格变更管理

### 配置

通过 `.env` 文件加载（pydantic-settings），`.env.example` 提供模板。关键配置项：
- `base_url` / `app_base_path` — 部署地址
- `database_url` — MySQL 连接串（PyMySQL 驱动）
- 丰声 Next：`fengsheng_client_id` / `fengsheng_client_secret` / `fengsheng_group_id`
- 处理完成通知：`processed_notify_enabled` / `processed_notify_statuses`

### 通用工具函数

- `clean(value)` — 全项目通用的字符串清洗，去除首尾空白并处理 None
- `local_now()` — 返回本地时间 datetime

### API 接口

| 方法   | 路径                                          | 说明           |
| ------ | --------------------------------------------- | -------------- |
| POST   | `/api/tickets`                                | 创建工单       |
| GET    | `/api/tickets`                                | 工单列表（分页 + 筛选） |
| GET    | `/api/tickets/{ticket_no}`                    | 工单详情       |
| POST   | `/api/tickets/{ticket_no}/status`             | 更新工单状态   |
| POST   | `/api/tickets/{ticket_no}/items/{item_id}/status` | 更新单个明细状态 |
| POST   | `/api/tickets/{ticket_no}/items/batch-status` | 批量更新明细状态 |
| POST   | `/api/tickets/{ticket_no}/comments`           | 添加备注       |
| POST   | `/api/tickets/{ticket_no}/close`              | 关闭工单       |

### 页面路由

| 方法   | 路径                                                      | 说明             |
| ------ | --------------------------------------------------------- | ---------------- |
| GET    | `/login`                                                  | 登录页           |
| POST   | `/login`                                                  | 提交登录         |
| GET    | `/logout`                                                 | 登出             |
| GET    | `/tickets`                                                | 工单列表         |
| GET    | `/tickets/{ticket_no}`                                    | 工单详情         |
| POST   | `/tickets/{ticket_no}/status-form`                        | 提交工单状态更新 |
| POST   | `/tickets/{ticket_no}/items/{item_id}/status-form`        | 提交明细状态更新 |
| POST   | `/tickets/{ticket_no}/items/batch-status-form`            | 批量提交明细状态 |
| POST   | `/tickets/{ticket_no}/comment-form`                       | 添加备注         |
| POST   | `/tickets/{ticket_no}/close-form`                         | 关闭工单         |
| POST   | `/tickets/{ticket_no}/actual-reporter-form`               | 更新实际反馈用户 |
