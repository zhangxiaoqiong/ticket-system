# 顺心分单诊断工单系统

一个用于承接 Dify 诊断结果的轻量工单系统。Dify 创建工单后，系统保存工单、展示处理页面，并自动推送丰声 Next 群消息。

## 功能

- 创建诊断工单
- 工单列表与详情页
- 诊断上下文 JSON 展示，中文不转义
- 工单状态管理：`NEW`、`PROCESSING`、`RESOLVED`、`CLOSED`
- 未关闭前可多次更新状态和处理说明
- 关闭后禁止继续操作
- 创建工单后推送丰声 Next 群消息
- 支持 Dify 传入外部工单号 `ticketNo`
- 支持幂等键 `idempotentKey` 防重复建单

## 目录结构

```text
ticket-system/
  app/
    routers/          # API 和页面路由
    services/         # 工单、通知、编号服务
    templates/        # Jinja2 页面模板
    config.py         # 配置
    database.py       # 数据库连接
    main.py           # FastAPI 入口
    models.py         # SQLAlchemy 模型
    schemas.py        # 请求/响应模型
    send_message.py   # 丰声 Next 消息发送工具
  .env.example
  requirements.txt
  run.py
```

## 环境准备

Python 3.12 可用。安装依赖：

```bash
pip install -r requirements.txt
```

创建配置文件：

```bash
cp .env.example .env
```

修改 `.env`：

```env
app_name="顺心分单诊断工单系统"
base_url="http://实际可访问地址/ticket-system"
app_base_path="/ticket-system"

database_url="mysql+pymysql://用户:密码@数据库地址:3306/ticket_system?charset=utf8mb4"

robot_enabled=true

fs_next_enabled=true
fs_next_client_id="丰声Next client_id"
fs_next_client_secret="丰声Next client_secret"
fs_next_group_ids="丰声群ID"
```

`base_url` 不要用 `127.0.0.1` 做生产配置，否则丰声消息里的工单链接别人打不开。

如果服务直接部署在域名根路径，`app_base_path` 留空即可；如果通过 Nginx 主路径区分，例如 `/ticket-system`，则 `base_url` 和 `app_base_path` 都要带这个路径。

## 启动

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问：

```text
http://127.0.0.1:8000/tickets
```

服务启动时会自动创建数据库表。

## Nginx 子路径部署

如果生产环境统一通过 Nginx 按主路径区分系统，推荐让 Nginx 对后端转发时去掉 `/ticket-system` 前缀，FastAPI 使用 `app_base_path` 生成正确页面链接。

`.env` 示例：

```env
base_url="https://example.com/ticket-system"
app_base_path="/ticket-system"
```

Nginx 示例：

```nginx
location /ticket-system/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

访问地址：

```text
https://example.com/ticket-system/tickets
```

Dify 创建工单接口也要使用带主路径的地址：

```http
POST https://example.com/ticket-system/api/tickets
```

## Dify 接入

在 Dify 中添加 HTTP 请求节点：

```http
POST http://工单系统地址:8000/api/tickets
Content-Type: application/json
```

请求体示例：

```json
{
  "ticketNo": "SX260518190001",
  "sourceChannel": "DIFY_ADDRESS_DIAGNOSIS_AGENT",
  "businessType": "SXFD_DIAGNOSIS",
  "reporterAccount": "{{用户账号}}",
  "reporterName": "{{用户名称}}",
  "channelUserId": "{{用户ID}}",
  "sessionId": "{{conversation_id}}",
  "userQuery": "{{用户原始问题}}",
  "fullAddress": "{{完整地址}}",
  "expectedResult": "{{用户期望结果}}",
  "waybillNo": "{{运单号}}",
  "issueType": "{{问题类型}}",
  "severityType": "{{严重程度}}",
  "priority": "P3",
  "diagnosisSummary": "{{诊断摘要}}",
  "internalSuggestion": "{{内部处理建议}}",
  "customerReplyType": "{{对客回复类型}}",
  "diagnosisPayload": {
    "flowVersion": "address_diag_v1.0",
    "v5Result": {
      "vilName": "{{村名}}"
    }
  },
  "idempotentKey": "{{conversation_id}}_{{运单号}}_{{完整地址}}"
}
```

字段说明：

- `ticketNo`：可选。生产建议由 Dify 生成并传入；不传时后端会生成测试号。
- `idempotentKey`：建议必传，用于防重复建单。
- `priority`：只能是 `P1`、`P2`、`P3`、`P4`。
- `diagnosisPayload`：可放完整诊断上下文 JSON。

成功响应：

```json
{
  "success": true,
  "code": "0",
  "message": "工单创建成功",
  "data": {
    "ticketNo": "SX260518190001",
    "ticketUrl": "http://工单系统地址:8000/tickets/SX260518190001",
    "status": "NEW",
    "duplicated": false
  }
}
```

重复请求时：

```json
{
  "success": true,
  "code": "0",
  "message": "工单已存在",
  "data": {
    "ticketNo": "SX260518190001",
    "ticketUrl": "http://工单系统地址:8000/tickets/SX260518190001",
    "status": "NEW",
    "duplicated": true
  }
}
```

## 工单状态

状态生命周期：

- `NEW`：新建
- `PROCESSING`：处理中
- `RESOLVED`：已解决
- `CLOSED`：已关闭

页面操作区只有一个状态表单：

- 选择工单状态
- 填写处理说明
- 保存状态

未关闭前可以多次调整状态，也可以在同一状态下多次补充处理说明。选择 `CLOSED` 时必须填写处理说明；关闭后不可再操作。

## 丰声 Next 配置

默认按 `.env` 中的 `fs_next_group_ids` 推送到固定群：

```env
fs_next_group_ids="cidxxxx"
```

也可以按业务类型、来源渠道、优先级分群：

```env
fs_next_group_map="{\"default\":\"默认群ID\",\"SXFD_DIAGNOSIS\":\"诊断群ID\",\"P1\":\"紧急群ID\"}"
```

匹配顺序：

1. `business_type`
2. `source_channel`
3. `priority`
4. `default`

消息推送结果会写入工单处理记录：

- `FS_NEXT_NOTIFIED`：发送成功
- `FS_NEXT_NOTIFY_FAILED`：发送失败
- `FS_NEXT_NOTIFY_SKIPPED`：配置缺失，跳过发送

## 常用接口

创建工单：

```http
POST /api/tickets
```

查询工单列表：

```http
GET /api/tickets?pageNo=1&pageSize=20
```

查询工单详情：

```http
GET /api/tickets/{ticket_no}
```

更新状态：

```http
POST /api/tickets/{ticket_no}/status
Content-Type: application/json

{
  "status": "PROCESSING",
  "operatorAccount": "user001",
  "operatorName": "张三",
  "comment": "已联系网点核实"
}
```

关闭工单也可以通过状态接口：

```json
{
  "status": "CLOSED",
  "operatorAccount": "user001",
  "operatorName": "张三",
  "comment": "问题已确认解决，关闭工单"
}
```

## 注意事项

- 生产环境建议由 Dify 生成 `ticketNo`，后端负责唯一性校验。
- 一定要传 `idempotentKey`，避免 Dify 重试造成重复工单。
- `.env` 不要提交到代码仓库。
- 当前项目使用 `Base.metadata.create_all` 自动建表，正式生产如需严谨变更管理，建议引入迁移工具。
