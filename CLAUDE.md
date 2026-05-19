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
```

启动时自动创建数据库表（`Base.metadata.create_all`）。

## 项目结构

```
app/
  main.py              # FastAPI 入口，注册路由
  config.py            # pydantic-settings 配置，读取 .env
  database.py          # SQLAlchemy engine / session
  models.py            # ticket / ticket_event 两张表
  schemas.py           # 请求/响应 Pydantic 模型（camelCase 入参）
  send_message.py      # 丰声 Next 消息发送工具
  routers/
    ticket_api.py      # RESTful API（/api/tickets）
    ticket_pages.py    # Jinja2 页面路由（/tickets）
  services/
    id_generator.py    # 工单编号生成
    notify_service.py  # 丰声 Next + 备用 webhook 通知
    ticket_service.py  # 工单核心业务逻辑
  templates/
    ticket_list.html   # 工单列表页
    ticket_detail.html # 工单详情页
```

## 架构要点

### 工单编号来源

- 生产环境由 Dify 传入 `ticketNo`，后端只做唯一性校验
- 不传时后端使用测试编号 `ADDR{yyyymmdd}{seq}`

### 幂等设计

- 请求必须携带 `idempotentKey`
- 后端先查 `idempotent_key`，存在则返回已有工单（`duplicated=true`），不重复创建、不重复推送消息

### 工单状态

四个状态：`NEW` → `PROCESSING` → `RESOLVED` → `CLOSED`

- 通过状态表单选择目标状态 + 填写处理说明保存
- 选择 `CLOSED` 时必须填写处理说明，写入 `resolved_result` 和 `closed_at`
- 已关闭工单禁止继续操作

### 通知服务

优先使用丰声 Next（`notify_service.py`），支持按 `business_type` / `source_channel` / `priority` 分群推送。丰声失败时回退到通用 webhook，但不会阻塞工单创建。

### 子路径部署

- `base_url`：对外完整地址（丰声消息里的工单链接用这个）
- `app_base_path`：Nginx 子路径前缀，如 `/ticket-system`
- Nginx 转发时去掉前缀：`location /ticket-system/ { proxy_pass http://127.0.0.1:8000/; }`

### API 接口

| 方法   | 路径                            | 说明       |
| ------ | ------------------------------- | ---------- |
| POST   | `/api/tickets`                  | 创建工单   |
| GET    | `/api/tickets`                  | 工单列表   |
| GET    | `/api/tickets/{ticket_no}`      | 工单详情   |
| POST   | `/api/tickets/{ticket_no}/status` | 更新状态 |

### 页面路由

| 方法   | 路径                                      | 说明           |
| ------ | ----------------------------------------- | -------------- |
| GET    | `/tickets`                                | 工单列表       |
| GET    | `/tickets/{ticket_no}`                    | 工单详情       |
| POST   | `/tickets/{ticket_no}/status-form`        | 提交状态更新   |

### 数据库

- 仅两张表：`ticket`（工单主表）、`ticket_event`（事件流水表）
- 诊断明细存储在 `diagnosis_payload` JSON 字段中，后续扩展无需改表
- 启动时 `Base.metadata.create_all` 自动建表，非生产环境够用
