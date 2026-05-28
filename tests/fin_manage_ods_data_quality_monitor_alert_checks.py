import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "alert" / "fin_manage_ods_data_quality_monitor_alert.py"


def load_module():
    spec = importlib.util.spec_from_file_location("fin_manage_ods_data_quality_monitor_alert", str(MODULE_PATH))
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
    def __init__(self, rows=None, one=None):
        self.rows = rows or []
        self.one = one
        self.fetchone_index = 0
        self.executed_sqls = []

    def execute(self, sql):
        self.executed_sqls.append(sql)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        if self.one is None and self.fetchone_index < len(self.rows):
            row = self.rows[self.fetchone_index]
            self.fetchone_index += 1
            return row
        return self.one


class FakeConnection:
    def __init__(self, rows=None, one=None):
        self.cursor_obj = FakeCursor(rows=rows, one=one)
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


class FinManageOdsDataQualityMonitorAlertTests(unittest.TestCase):
    def test_default_mentions_use_email_for_highlight_and_message(self):
        module = load_module()

        self.assertEqual(module.DEFAULT_MENTIONS, ["adamyu@kn.group", "strongliu@kn.group"])

    def test_fetch_random_rows_queries_random_one_from_monitor_table_by_default(self):
        module = load_module()
        fake_conn = FakeConnection([{"id": "q1"}])
        config = module.StarRocksConfig(
            host="sr.example.com",
            port=9031,
            fe_host="sr.example.com",
            fe_port=8031,
            db="fin",
            primary=module.StarRocksAccount(username="e_load", password="secret"),
            backup=module.StarRocksAccount(username="e_backup", password="backup-secret"),
        )

        with mock.patch.object(module.pymysql, "connect", return_value=fake_conn) as connect:
            rows = module.fetch_random_rows(config=config)

        self.assertEqual(rows, [{"id": "q1"}])
        executed_sql = fake_conn.cursor_obj.executed_sqls[0]
        self.assertIn("fin.fin_manage_ods_data_quality_monitor", executed_sql)
        self.assertIn("ORDER BY RAND()", executed_sql)
        self.assertTrue(executed_sql.rstrip().endswith("LIMIT 1"))
        connect.assert_called_once()
        self.assertTrue(fake_conn.closed)

    def test_fetch_latest_batch_counts_counts_all_and_diff_rows(self):
        module = load_module()
        fake_conn = FakeConnection(rows=[{"alert_count": 172326}, {"alert_count": 834}])
        config = module.StarRocksConfig(
            host="sr.example.com",
            port=9031,
            fe_host="sr.example.com",
            fe_port=8031,
            db="fin",
            primary=module.StarRocksAccount(username="e_load", password="secret"),
            backup=module.StarRocksAccount(username="e_backup", password="backup-secret"),
        )

        with mock.patch.object(module.pymysql, "connect", return_value=fake_conn):
            counts = module.fetch_latest_batch_counts(config=config)

        self.assertEqual(counts, {"alert_count": 172326, "exception_count": 834})
        self.assertEqual(len(fake_conn.cursor_obj.executed_sqls), 2)
        total_sql = fake_conn.cursor_obj.executed_sqls[0].lower()
        exception_sql = fake_conn.cursor_obj.executed_sqls[1].lower()
        self.assertEqual(
            total_sql.strip(),
            "select count(1) as alert_count from fin.fin_manage_ods_data_quality_monitor",
        )
        self.assertEqual(
            exception_sql.strip(),
            "select count(1) as alert_count from fin.fin_manage_ods_data_quality_monitor where diff <> 0",
        )
        self.assertTrue(fake_conn.closed)

    def test_format_alert_message_matches_summary_style(self):
        module = load_module()

        message = module.format_alert_message(alert_count=172326, exception_count=834)

        self.assertIn("🚨 StarRocks 数仓与财务库数据一致性校验", message)
        self.assertIn("集群: 中国", message)
        self.assertIn("告警记录: 172326 条，异常告警：834条，", message)
        self.assertIn("查询表: fin.fin_manage_ods_data_quality_monitor", message)
        self.assertIn("@Adam Yu (余红叶) @柳琴", message)
        self.assertNotIn("select count(1)", message)
        self.assertNotIn("这个sql查询结果", message)

    def test_send_to_tv_uses_requested_bot_and_mentions_field(self):
        module = load_module()
        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(200, '{"ok":true}')

        with mock.patch.object(module.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = module.send_to_tv(
                "告警内容",
                mentions=["strongliu@kn.group"],
                bot_id="4d0bcc9b-71bf-41c5-ba9f-89b7278f9214",
            )

        self.assertTrue(result["success"])
        self.assertEqual(captured["url"], module.TV_API_URL)
        self.assertEqual(captured["timeout"], 30)
        self.assertEqual(
            captured["body"],
            {
                "botId": "4d0bcc9b-71bf-41c5-ba9f-89b7278f9214",
                "message": "告警内容\n",
                "mentions": ["strongliu@kn.group"],
            },
        )

    def test_run_sends_latest_batch_counts_summary_even_when_exception_count_is_zero(self):
        module = load_module()
        sent = {}

        with mock.patch.object(
            module,
            "fetch_latest_batch_counts",
            return_value={"alert_count": 3, "exception_count": 0},
        ) as fetch_count:
            with mock.patch.object(module, "send_to_tv", return_value={"success": True, "status_code": 200, "response": "ok"}) as send:
                with mock.patch("builtins.print"):
                    result = module.run(
                        mentions=["adamyu@kn.group"],
                        sr_password="primary-secret",
                        sr_backup_password="backup-secret",
                        bot_id="4d0bcc9b-71bf-41c5-ba9f-89b7278f9214",
                    )

        self.assertTrue(result["success"])
        fetch_count.assert_called_once()
        sent["message"] = send.call_args.args[0]
        sent["mentions"] = send.call_args.kwargs["mentions"]
        self.assertIn("告警记录: 3 条，异常告警：0条，", sent["message"])
        self.assertIn("@Adam Yu (余红叶) @柳琴", sent["message"])
        self.assertTrue(sent["message"].endswith("\n"))
        self.assertEqual(sent["mentions"], ["adamyu@kn.group"])
        self.assertEqual(send.call_args.kwargs["bot_id"], "4d0bcc9b-71bf-41c5-ba9f-89b7278f9214")


if __name__ == "__main__":
    unittest.main()
