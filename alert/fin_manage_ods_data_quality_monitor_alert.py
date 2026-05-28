#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统计 StarRocks 数仓与财务库数据一致性校验表记录数并发送 TV 告警。

默认查询:
    select count(1) from fin.fin_manage_ods_data_quality_monitor
    select count(1) from fin.fin_manage_ods_data_quality_monitor where diff <> 0

真实密码请通过环境变量传入:
    SR_PASSWORD=... python3 alert/fin_manage_ods_data_quality_monitor_alert.py

也可以通过命令行参数传入:
    python3 alert/fin_manage_ods_data_quality_monitor_alert.py --sr-password '...'
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
    "FIN_MANAGE_ODS_DATA_QUALITY_TV_BOT_ID",
    "f82292a5-45c5-42ea-84da-272b4c81ebcc",
)
DEFAULT_MENTIONS = [
    item.strip()
    for item in os.environ.get(
        "FIN_MANAGE_ODS_DATA_QUALITY_TV_MENTIONS",
        "adamyu@kn.group,gretchenhe@kn.group",
    ).split(",")
    if item.strip()
]

MONITOR_TABLE = "fin.fin_manage_ods_data_quality_monitor"
LATEST_BATCH_TOTAL_COUNT_SQL = f"select count(1) as alert_count from {MONITOR_TABLE}"
LATEST_BATCH_EXCEPTION_COUNT_SQL = (
    f"select count(1) as alert_count from {MONITOR_TABLE} where diff <> 0"
)
DEFAULT_LIMIT = 1


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
        db=os.environ.get("SR_DB", "fin"),
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


def _count_from_row(row):
    row = row or {}
    if isinstance(row, dict):
        return int(row.get("alert_count") or row.get("count(1)") or 0)
    return int(row[0] or 0)


def fetch_latest_batch_counts(config=None, sr_password=None, sr_backup_password=None):
    if config is None:
        config = get_starrocks_config(
            sr_password=sr_password,
            sr_backup_password=sr_backup_password,
        )
    conn = get_connection(config=config)
    try:
        cursor = conn.cursor()
        cursor.execute(LATEST_BATCH_TOTAL_COUNT_SQL)
        alert_count = _count_from_row(cursor.fetchone())
        cursor.execute(LATEST_BATCH_EXCEPTION_COUNT_SQL)
        exception_count = _count_from_row(cursor.fetchone())
        return {
            "alert_count": alert_count,
            "exception_count": exception_count,
        }
    finally:
        conn.close()


def format_alert_message(alert_count, exception_count, mention_labels=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "🚨 StarRocks 数仓与财务库数据一致性校验",
        "集群: 中国",
        f"告警记录: {alert_count} 条，异常告警：{exception_count}条，",
        f"告警时间: {now}",
        f"查询表: {MONITOR_TABLE}",
    ]
    return "\n".join(lines)


def send_to_tv(message, mentions=None, bot_id=None, api_url=None):
    if mentions is None:
        mentions = DEFAULT_MENTIONS
    if not message.endswith("\n"):
        message = f"{message}\n"

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


def run(limit=DEFAULT_LIMIT, dry_run=False, mentions=None, sr_password=None, sr_backup_password=None, bot_id=None):
    config = get_starrocks_config(
        sr_password=sr_password,
        sr_backup_password=sr_backup_password,
    )
    counts = fetch_latest_batch_counts(config=config)
    message = format_alert_message(
        alert_count=counts["alert_count"],
        exception_count=counts["exception_count"],
    )
    if not message.endswith("\n"):
        message = f"{message}\n"

    if dry_run:
        print(message)
        return {"success": True, "status_code": None, "response": "dry_run"}

    result = send_to_tv(message, mentions=mentions, bot_id=bot_id)
    if result["success"]:
        print(f"✅ TV告警发送成功 (HTTP {result['status_code']})")
    else:
        print(f"❌ TV告警发送失败 (HTTP {result['status_code']})")
        print(result["response"])
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="统计 StarRocks 数仓与财务库数据一致性校验记录数并发送 TV 告警")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="兼容旧参数，当前告警不使用")
    parser.add_argument("--dry-run", action="store_true", help="只打印消息，不发送 TV")
    parser.add_argument("--sr-password", default=None, help="StarRocks 主账号密码")
    parser.add_argument("--sr-backup-password", default=None, help="StarRocks 备份账号密码")
    parser.add_argument("--bot-id", default=None, help="指定发送使用的 TV 机器人 ID")
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
        bot_id=args.bot_id,
    )
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
