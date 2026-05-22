# 中国智能告警修复系统

**版本**: v2.12-cn  
**日期**: 2026-05-22  
**作者**: OpenClaw

---

## 📋 系统概览

本仓库已按 `PH-Intelligent-Alarm-Repair-Assistant` 的项目结构补齐，当前同时承载两类能力：

| 模块 | 功能 | 说明 |
|------|------|------|
| **DS 调度运维骨架** | DolphinScheduler 配置、工具脚本、复验/调度检查 | 结构与菲律宾项目保持一致，方便后续统一 skill 路由 |
| **中国 PL 监控告警** | 统计 `fin_global.manage_model_global_pl_monitor` 最新批次记录数并发送 TV 告警 | 中国仓库原有能力，已保留并并入统一结构 |

---

## 📁 目录结构

```
.
├── README.md
├── SYSTEM_MEMORY.md
├── MAINTENANCE_GUIDE.md
├── MEMORY.md
├── .env.example
│
├── config/                      # 运行时配置与环境变量加载
├── core/                        # 核心定时任务骨架
├── dolphinscheduler/            # DS API / 工作流 / 调度检查脚本
├── tools/                       # DS 运维工具脚本
├── docs/                        # 说明文档
├── templates/                   # 模板文件
├── data/                        # 数据说明
├── memory/                      # 记忆记录
├── backup/                      # 历史备份
├── auto_repair_records/         # 运行记录
├── cron_jobs/                   # 定时任务记录
├── pymysql/                     # vendored pymysql
│
├── alert/                       # 告警脚本
│   └── manage_model_global_pl_monitor_alert.py
└── tests/                       # 本地校验测试
```

---

## 🚀 快速开始

### 1. 配置环境

```bash
cp .env.example .env.local
```

至少补齐这些变量：

```bash
export DS_TOKEN='your_ds_token'
export DB_PASSWORD='your_db_password'
export SR_PASSWORD='your_starrocks_password'
```

如果要使用中国默认 DS 集群，可参考 `.env.example` 中预填的国内默认值：
- `DS_BASE_URL=http://172.20.0.235:12345/dolphinscheduler`
- `DS_PROJECT_CODE=158514956085248`
- `DS_FUYAN_PROJECT_CODE=158515019231232`
- `DS_TENANT_CODE=dolphinscheduler`

### 2. 验证配置与脚本

```bash
python3 tests/country_config_checks.py
python3 tests/extract_ds_sql_checks.py
python3 tests/manage_model_global_pl_monitor_alert_checks.py
```

### 3. 常用命令

```bash
# 中国 PL 监控告警
python3 alert/manage_model_global_pl_monitor_alert.py --dry-run

# DS 配置检查
python3 tools/task_execution_checker.py --task all

# DS SQL 提取
python3 tools/extract_ds_sql.py --project-name '国内数仓-工作流' --output ./sql_export/cn
```

---

## 🔧 中国 PL 监控告警

脚本位置：`alert/manage_model_global_pl_monitor_alert.py`

用途：统计 `fin_global.manage_model_global_pl_monitor` 最新批次的总记录数与异常记录数，并发送 TV 摘要告警。

示例：

```bash
python3 alert/manage_model_global_pl_monitor_alert.py   --sr-password '主账号密码'   --sr-backup-password '备份账号密码'   --bot-id '4d0bcc9b-71bf-41c5-ba9f-89b7278f9214'
```

只预览不发送：

```bash
python3 alert/manage_model_global_pl_monitor_alert.py --dry-run
```

---

## 🔧 DS 相关说明

`config/`、`dolphinscheduler/`、`tools/` 目录已经与菲律宾项目同构，后续可以和 `INE/MX/PH/PK/TH` 一样按国家路由使用。

当前中国默认使用国内 DS 历史默认值作为起点；如果你线上实际项目编码、环境编码、租户编码有变化，优先改 `.env.local`，不要改业务脚本。
