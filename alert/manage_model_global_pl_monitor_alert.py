#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
随机抽取 StarRocks PL 监控记录并发送 TV 告警。

默认查询:
    select * from fin_global.manage_model_global_pl_monitor order by rand() limit 10

真实密码请通过环境变量传入:
    SR_PASSWORD=... python3 alert/manage_model_global_pl_monitor_alert.py

也可以通过命令行参数传入:
    python3 alert/manage_model_global_pl_monitor_alert.py --sr-password '...'
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymysql
from pymysql.cursors import DictCursor

try:
    from config import auto_load_env  # noqa: F401
except Exception:
    auto_load_env = None


TV_API_URL = os.environ.get(
    "TV_API_URL",
    "https://tv-service-alert.kuainiu.chat/alert/v2/array",
)
TV_BOT_ID = os.environ.get(
    "MANAGE_MODEL_GLOBAL_PL_TV_BOT_ID",
    "f82292a5-45c5-42ea-84da-272b4c81ebcc",
)
DEFAULT_MENTIONS = [
    item.strip()
    for item in os.environ.get(
        "MANAGE_MODEL_GLOBAL_PL_TV_MENTIONS",
        "余红叶",
    ).split(",")
    if item.strip()
]

MONITOR_TABLE = "fin_global.manage_model_global_pl_monitor"
DEFAULT_LIMIT = 10


@dataclass
class StarRocksAccount:
    username: str
    password: str


@dataclass
class StarRocksConfig:
    host: str
    port: int
    fe_host: str
    fe_port: int
    db: str
    primary: StarRocksAccount
    backup: StarRocksAccount


def get_starrocks_config(sr_password=None, sr_backup_password=None):
    return StarRocksConfig(
        host=os.environ.get(
            "SR_HOST",
            "nlb-ngj6e0efsvv7wm73v3.cn-shanghai.nlb.aliyuncsslb.com",
        ),
        port=int(os.environ.get("SR_PORT", "9031")),
        fe_host=os.environ.get(
            "SR_FE_HOST",
            "nlb-ngj6e0efsvv7wm73v3.cn-shanghai.nlb.aliyuncsslb.com",
        ),
        fe_port=int(os.environ.get("SR_FE_PORT", "8031")),
        db=os.environ.get("SR_DB", "ods"),
        primary=StarRocksAccount(
            username=os.environ.get("SR_USERNAME", "e_load"),
            password=sr_password or os.environ.get("SR_PASSWORD", ""),
        ),
        backup=StarRocksAccount(
            username=os.environ.get("SR_BACKUP_USERNAME", "e_backup"),
            password=sr_backup_password or os.environ.get("SR_BACKUP_PASSWORD", ""),
        ),
    )


def _connect_with_account(config, account):
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=account.username,
        password=account.password,
        database=config.db,
        charset="utf8mb4",
        cursorclass=DictCursor,
    )


def get_connection(config=None):
    config = config or get_starrocks_config()
    errors = []

    for label, account in (("primary", config.primary), ("backup", config.backup)):
        if not account.password:
            errors.append(f"{label} account {account.username} missing password")
            continue
        try:
            return _connect_with_account(config, account)
        except Exception as exc:
            errors.append(f"{label} account {account.username} failed: {exc}")

    raise RuntimeError("StarRocks connection failed: " + "; ".join(errors))


def fetch_random_rows(limit=DEFAULT_LIMIT, config=None, sr_password=None, sr_backup_password=None):
    safe_limit = max(1, int(limit))
    sql = f"SELECT * FROM {MONITOR_TABLE} ORDER BY RAND() LIMIT {safe_limit}"
    if config is None:
        config = get_starrocks_config(
            sr_password=sr_password,
            sr_backup_password=sr_backup_password,
        )
    conn = get_connection(config=config)
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        return list(cursor.fetchall())
    finally:
        conn.close()


def _stringify(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _get(row, *names):
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _append_known_line(lines, row, label, *names):
    value = _get(row, *names)
    if value not in (None, ""):
        lines.append(f"• {label}: {_stringify(value)}")
        return True
    return False


def _format_row(row, index):
    lines = [f"【告警记录 {index}】"]
    used = set()
    known_fields = [
        ("开始时间", ("start_time", "query_start_time", "starttime", "startTime")),
        ("查询ID", ("query_id", "queryid", "queryId")),
        ("连接ID", ("conn_id", "connection_id", "connid", "connectionId")),
        ("数据库", ("db", "database", "database_name", "db_name")),
        ("用户", ("user", "username", "user_name")),
        ("扫描字节", ("scan_bytes", "scan_bytes_human", "scanBytes")),
        ("扫描行数", ("scan_rows", "scanRows", "scan_row_count")),
        ("内存使用", ("mem_usage", "memory_usage", "memUsage", "memory")),
        ("CPU时间", ("cpu_time", "cpuTime", "cpu_cost")),
        ("执行时间", ("exec_time", "execute_time", "query_time", "duration")),
        ("仓库", ("warehouse", "warehouse_name")),
        ("资源组", ("resource_group", "resource_group_name", "resourceGroup")),
        ("SQL", ("sql", "sql_text", "stmt", "statement")),
    ]

    lowered_to_original = {str(key).lower(): key for key in row}
    for label, names in known_fields:
        if _append_known_line(lines, row, label, *names):
            for name in names:
                original = lowered_to_original.get(name.lower())
                if original:
                    used.add(original)

    query_id = _get(row, "query_id", "queryid", "queryId")
    if query_id:
        lines.append(f"• SQL详情: https://sr-admin.kuainiujinke.com/queryid/{query_id}")

    extra_items = [
        (key, value)
        for key, value in row.items()
        if key not in used and value not in (None, "")
    ]
    if extra_items:
        lines.append("• 其他字段:")
        for key, value in extra_items:
            lines.append(f"  - {key}: {_stringify(value)}")

    return "\n".join(lines)


def format_alert_message(rows):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "🚨 StarRocks PL监控告警",
        f"集群: 墨西哥",
        f"告警原因: manage_model_global_pl_monitor 随机抽样告警记录: {len(rows)} 条",
        f"告警时间: {now}",
        f"查询表: {MONITOR_TABLE}",
    ]

    if not rows:
        lines.append("查询结果: 未查询到记录")
        return "\n".join(lines)

    lines.append("查询详情:")
    for index, row in enumerate(rows, 1):
        lines.append("")
        lines.append(_format_row(row, index))

    return "\n".join(lines)


def send_to_tv(message, mentions=None, bot_id=None, api_url=None):
    if mentions is None:
        mentions = DEFAULT_MENTIONS

    payload = {
        "botId": bot_id or TV_BOT_ID,
        "message": message,
        "mentions": mentions,
    }
    json_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        api_url or TV_API_URL,
        data=json_data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status_code = response.getcode()
            response_body = response.read().decode("utf-8")
            return {
                "success": 200 <= status_code < 300,
                "status_code": status_code,
                "response": response_body,
            }
    except urllib.error.HTTPError as exc:
        response_body = ""
        if exc.fp is not None:
            try:
                response_body = exc.fp.read().decode("utf-8")
            except Exception:
                response_body = ""
        return {
            "success": False,
            "status_code": exc.code,
            "response": response_body or str(exc.reason),
        }
    except Exception as exc:
        return {
            "success": False,
            "status_code": None,
            "response": str(exc),
        }


def run(limit=DEFAULT_LIMIT, dry_run=False, mentions=None, sr_password=None, sr_backup_password=None):
    rows = fetch_random_rows(
        limit=limit,
        sr_password=sr_password,
        sr_backup_password=sr_backup_password,
    )
    message = format_alert_message(rows)

    if dry_run:
        print(message)
        return {"success": True, "status_code": None, "response": "dry_run"}

    result = send_to_tv(message, mentions=mentions)
    if result["success"]:
        print(f"✅ TV告警发送成功 (HTTP {result['status_code']})")
    else:
        print(f"❌ TV告警发送失败 (HTTP {result['status_code']})")
        print(result["response"])
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="随机抽取 StarRocks PL 监控记录并发送 TV 告警")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="随机抽样条数，默认 10")
    parser.add_argument("--dry-run", action="store_true", help="只打印消息，不发送 TV")
    parser.add_argument("--sr-password", default=None, help="StarRocks 主账号密码")
    parser.add_argument("--sr-backup-password", default=None, help="StarRocks 备份账号密码")
    parser.add_argument(
        "--mentions",
        default=",".join(DEFAULT_MENTIONS),
        help="逗号分隔的提醒邮箱列表",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    mentions = [item.strip() for item in args.mentions.split(",") if item.strip()]
    result = run(
        limit=args.limit,
        dry_run=args.dry_run,
        mentions=mentions,
        sr_password=args.sr_password,
        sr_backup_password=args.sr_backup_password,
    )
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
