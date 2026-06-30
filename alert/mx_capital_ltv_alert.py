#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询墨西哥资方 LTV T-1 数据并发送 TV 告警。

依赖 DolphinScheduler 任务:
    ads_capital_ltv（资方ltv监测）

默认查询:
    select stat_date, capital, ltv, normal_loan_amt, account_balance
    from dm_dd_new.ads_capital_ltv
    where stat_date = T-1
      and capital in ('new_share', 'chuanjin')
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
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
    "MX_CAPITAL_LTV_TV_BOT_ID",
    "08826b39-e6eb-44fb-9c25-9778a8171f49",
)
DEFAULT_MENTIONS = [
    item.strip()
    for item in os.environ.get(
        "MX_CAPITAL_LTV_TV_MENTIONS",
        "adamyu@kn.group,gretchenhe@kn.group",
    ).split(",")
    if item.strip()
]

MONITOR_TABLE = "dm_dd_new.ads_capital_ltv"
CAPITAL_ORDER = ("new_share", "chuanjin")
CAPITAL_LABELS = {
    "new_share": "墨西哥新分享ltv",
    "chuanjin": "墨西哥串金ltv",
}
BALANCE_LABELS = {
    "new_share": "信托账户余额",
    "chuanjin": "通道余额",
}
NEW_SHARE_BALANCE_THRESHOLD = Decimal("4420000")
CHUANJIN_BALANCE_THRESHOLD = Decimal("424000")


@dataclass
class StarRocksAccount:
    username: str
    password: str


@dataclass
class StarRocksConfig:
    host: str
    port: int
    db: str
    primary: StarRocksAccount
    backup: StarRocksAccount


def get_starrocks_config(sr_password=None, sr_backup_password=None):
    return StarRocksConfig(
        host=os.environ.get("SR_HOST", "127.0.0.1"),
        port=int(os.environ.get("SR_PORT", "9030")),
        db=os.environ.get("SR_DB", "dm_dd_new"),
        primary=StarRocksAccount(
            username=os.environ.get("SR_USERNAME", "e_load"),
            password=sr_password or os.environ.get("SR_PASSWORD", ""),
        ),
        backup=StarRocksAccount(
            username=os.environ.get("SR_BACKUP_USERNAME", "backup_user"),
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


def default_target_date():
    return date.today() - timedelta(days=1)


def parse_date(value):
    if value is None or isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def fetch_capital_ltv_rows(target_date=None, config=None, sr_password=None, sr_backup_password=None):
    target_date = parse_date(target_date) or default_target_date()
    if config is None:
        config = get_starrocks_config(
            sr_password=sr_password,
            sr_backup_password=sr_backup_password,
        )

    sql = (
        "select stat_date, capital, ltv, normal_loan_amt, account_balance "
        f"from {MONITOR_TABLE} "
        "where stat_date = %s "
        "and capital in (%s, %s) "
        "order by field(capital, %s, %s)"
    )
    params = (
        target_date.strftime("%Y-%m-%d"),
        CAPITAL_ORDER[0],
        CAPITAL_ORDER[1],
        CAPITAL_ORDER[0],
        CAPITAL_ORDER[1],
    )
    conn = get_connection(config=config)
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return list(cursor.fetchall())
    finally:
        conn.close()


def _decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _format_number(value):
    number = _decimal(value)
    if number is None:
        return ""
    normalized = number.quantize(Decimal("0.01")) if number != number.to_integral() else number.quantize(Decimal("1"))
    return f"{normalized:,.2f}".rstrip("0").rstrip(".")


def _format_date(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value or "")


def _ltv_tag(capital, ltv):
    ltv_value = _decimal(ltv)
    if ltv_value is None:
        return "ltv值缺失，需检查数据产出"
    if capital == "new_share":
        if ltv_value >= Decimal("0.75"):
            return "在阈值0.75以上，需紧急介入"
        if ltv_value < Decimal("0.65"):
            return "在阈值0.75以下，需关注通道余额或者资产，是否需要减持"
        return "在阈值0.75以下，在合格线"
    if capital == "chuanjin":
        if ltv_value < Decimal("1.43"):
            return "在阈值1.43以下，需紧急介入线"
        if ltv_value < Decimal("1.9"):
            return "在阈值1.43以上，在合格线"
        return "在阈值1.43以上，但需关注通道余额或者资产，是否需要减持"
    return "未配置资方阈值，请检查告警配置"


def _balance_tag(capital, balance):
    balance_value = _decimal(balance)
    if balance_value is None:
        return None
    if capital == "new_share" and balance_value > NEW_SHARE_BALANCE_THRESHOLD:
        return "通道余额大于44,200,00，续关注"
    if capital == "chuanjin" and balance_value > CHUANJIN_BALANCE_THRESHOLD:
        return "通道余额大于424,000，续关注"
    return None


def _sort_rows(rows):
    order = {capital: index for index, capital in enumerate(CAPITAL_ORDER)}
    return sorted(rows, key=lambda row: order.get(str(row.get("capital")), 99))


def format_alert_message(rows, target_date=None):
    target_date = parse_date(target_date) or default_target_date()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "🚨 墨西哥资方ltv告警",
        f"统计日: {target_date.strftime('%Y-%m-%d')}",
        f"告警时间: {now}",
        f"依赖任务: ads_capital_ltv（资方ltv监测）",
    ]

    rows = _sort_rows(rows)
    if not rows:
        lines.append("未查询到 T-1 资方 LTV 数据，需检查 dm_dd_new.ads_capital_ltv 产出。")
        return "\n".join(lines)

    for row in rows:
        capital = str(row.get("capital") or "")
        ltv = row.get("ltv")
        balance = row.get("account_balance")
        tags = [_ltv_tag(capital, ltv)]
        balance_tag = _balance_tag(capital, balance)
        if balance_tag:
            tags.append(balance_tag)

        lines.extend(
            [
                "",
                f"告警项: {CAPITAL_LABELS.get(capital, capital or '未知资方')}",
                f"统计日: {_format_date(row.get('stat_date')) or target_date.strftime('%Y-%m-%d')}",
                f"{BALANCE_LABELS.get(capital, '账户余额')}: {_format_number(balance)}",
                f"质押正常在贷: {_format_number(row.get('normal_loan_amt'))}",
                f"ltv值: {_format_number(ltv)}",
                f"附加标签: {'；'.join(tags)}",
            ]
        )
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


def run(dry_run=False, mentions=None, sr_password=None, sr_backup_password=None, bot_id=None, target_date=None):
    target_date = parse_date(target_date) or default_target_date()
    config = get_starrocks_config(
        sr_password=sr_password,
        sr_backup_password=sr_backup_password,
    )
    rows = fetch_capital_ltv_rows(target_date=target_date, config=config)
    message = format_alert_message(rows, target_date=target_date)
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
    parser = argparse.ArgumentParser(description="查询墨西哥资方 LTV T-1 数据并发送 TV 告警")
    parser.add_argument("--dry-run", action="store_true", help="只打印消息，不发送 TV")
    parser.add_argument("--target-date", default=None, help="指定统计日，格式 YYYY-MM-DD；默认 T-1")
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
        dry_run=args.dry_run,
        mentions=mentions,
        sr_password=args.sr_password,
        sr_backup_password=args.sr_backup_password,
        bot_id=args.bot_id,
        target_date=parse_date(args.target_date),
    )
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
