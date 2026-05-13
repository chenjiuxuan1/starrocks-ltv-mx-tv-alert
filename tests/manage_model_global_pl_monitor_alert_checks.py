import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "alert" / "manage_model_global_pl_monitor_alert.py"


def load_module():
    spec = importlib.util.spec_from_file_location("manage_model_global_pl_monitor_alert", str(MODULE_PATH))
    module = importlib.util.module_from_spec(spec)
    fake_pymysql = types.SimpleNamespace(
        connect=mock.Mock(),
        cursors=types.SimpleNamespace(DictCursor=object),
    )
    with mock.patch.dict(
        sys.modules,
        {
            "pymysql": fake_pymysql,
            "pymysql.cursors": fake_pymysql.cursors,
        },
    ):
        spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status_code, body):
        self._status_code = status_code
        self._body = body

    def getcode(self):
        return self._status_code

    def read(self):
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed_sql = None

    def execute(self, sql):
        self.executed_sql = sql

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


class ManageModelGlobalPlMonitorAlertTests(unittest.TestCase):
    def test_fetch_random_rows_queries_random_ten_from_monitor_table(self):
        module = load_module()
        fake_conn = FakeConnection([{"query_id": "q1"}])
        config = module.StarRocksConfig(
            host="sr.example.com",
            port=9031,
            fe_host="sr.example.com",
            fe_port=8031,
            db="ods",
            primary=module.StarRocksAccount(username="e_load", password="secret"),
            backup=module.StarRocksAccount(username="e_backup", password="backup-secret"),
        )

        with mock.patch.object(module.pymysql, "connect", return_value=fake_conn) as connect:
            rows = module.fetch_random_rows(limit=10, config=config)

        self.assertEqual(rows, [{"query_id": "q1"}])
        self.assertIn("fin_global.manage_model_global_pl_monitor", fake_conn.cursor_obj.executed_sql)
        self.assertIn("ORDER BY RAND()", fake_conn.cursor_obj.executed_sql)
        self.assertIn("LIMIT 10", fake_conn.cursor_obj.executed_sql)
        connect.assert_called_once()
        self.assertTrue(fake_conn.closed)

    def test_format_alert_message_includes_rows_as_alarm_details(self):
        module = load_module()
        rows = [
            {
                "start_time": "2026-05-13 10:00:00",
                "query_id": "query-001",
                "conn_id": 123,
                "db": "dm_tmk",
                "user": "e_ds_tmk",
                "scan_bytes": "6.604 GB",
                "scan_rows": 1624644596,
                "sql": "select count(*) from t",
            }
        ]

        message = module.format_alert_message(rows)

        self.assertIn("🚨 StarRocks PL监控告警", message)
        self.assertIn("随机抽样告警记录: 1 条", message)
        self.assertIn("开始时间: 2026-05-13 10:00:00", message)
        self.assertIn("查询ID: query-001", message)
        self.assertIn("扫描行数: 1624644596", message)
        self.assertIn("SQL: select count(*) from t", message)

    def test_send_to_tv_uses_requested_bot_and_mentions_field(self):
        module = load_module()
        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(200, '{"ok":true}')

        with mock.patch.object(module.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = module.send_to_tv("告警内容", mentions=["strongliu@kn.group"])

        self.assertTrue(result["success"])
        self.assertEqual(captured["url"], module.TV_API_URL)
        self.assertEqual(captured["timeout"], 30)
        self.assertEqual(
            captured["body"],
            {
                "botId": "f82292a5-45c5-42ea-84da-272b4c81ebcc",
                "message": "告警内容",
                "mentions": ["strongliu@kn.group"],
            },
        )

    def test_main_passes_starrocks_passwords_from_command_line(self):
        module = load_module()
        captured = {}

        def fake_run(limit, dry_run, mentions, sr_password=None, sr_backup_password=None):
            captured["limit"] = limit
            captured["dry_run"] = dry_run
            captured["mentions"] = mentions
            captured["sr_password"] = sr_password
            captured["sr_backup_password"] = sr_backup_password
            return {"success": True, "status_code": None, "response": "ok"}

        with mock.patch.object(module, "run", side_effect=fake_run):
            exit_code = module.main(
                [
                    "--sr-password",
                    "primary-secret",
                    "--sr-backup-password",
                    "backup-secret",
                    "--limit",
                    "10",
                    "--mentions",
                    "strongliu@kn.group,jerrycai@kn.group",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["limit"], 10)
        self.assertFalse(captured["dry_run"])
        self.assertEqual(captured["mentions"], ["strongliu@kn.group", "jerrycai@kn.group"])
        self.assertEqual(captured["sr_password"], "primary-secret")
        self.assertEqual(captured["sr_backup_password"], "backup-secret")


if __name__ == "__main__":
    unittest.main()
