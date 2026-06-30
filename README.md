# StarRocks TV Alert Scripts

仓库当前包含三条彼此独立的 TV 告警脚本：

- `alert/manage_model_global_pl_monitor_alert.py`
  统计 `fin_global.manage_model_global_pl_monitor` 最新 `etl_create_time` 批次的总记录数和 `diff <> 0` 异常记录数，按摘要告警格式发送到 TV 机器人。
- `alert/fin_manage_ods_data_quality_monitor_alert.py`
  统计 `fin.fin_manage_ods_data_quality_monitor` 的总记录数与 `diff <> 0` 的异常记录数，按“数仓与财务库数据一致性校验”格式发送到 TV 机器人。
- `alert/mx_capital_ltv_alert.py`
  查询墨西哥 `dm_dd_new.ads_capital_ltv` T-1 的 `new_share` 与 `chuanjin` 资方 LTV、账户余额和质押正常在贷，按资方阈值生成“墨西哥资方ltv告警”。

## 运行

原有 PL 监控告警：

```bash
python3 alert/manage_model_global_pl_monitor_alert.py \
  --sr-password '主账号密码' \
  --sr-backup-password '备份账号密码' \
  --bot-id '4d0bcc9b-71bf-41c5-ba9f-89b7278f9214' \
  --mentions 'adamyu@kn.group,gretchenhe@kn.group'
```

新增数仓与财务库数据一致性校验告警：

```bash
python3 alert/fin_manage_ods_data_quality_monitor_alert.py \
  --sr-password '主账号密码' \
  --sr-backup-password '备份账号密码' \
  --bot-id '4d0bcc9b-71bf-41c5-ba9f-89b7278f9214' \
  --mentions 'adamyu@kn.group,gretchenhe@kn.group'
```

墨西哥资方 LTV 告警：

```bash
SR_HOST='墨西哥StarRocks地址' \
SR_PORT='9030' \
SR_DB='dm_dd_new' \
SR_USERNAME='e_load' \
SR_BACKUP_USERNAME='backup_user' \
python3 alert/mx_capital_ltv_alert.py \
  --sr-password '主账号密码' \
  --sr-backup-password '备份账号密码' \
  --bot-id '08826b39-e6eb-44fb-9c25-9778a8171f49' \
  --mentions 'owner@kn.group,backup@kn.group'
```

只预览不发送：

```bash
python3 alert/manage_model_global_pl_monitor_alert.py \
  --sr-password '主账号密码' \
  --sr-backup-password '备份账号密码' \
  --dry-run
```

```bash
python3 alert/fin_manage_ods_data_quality_monitor_alert.py \
  --sr-password '主账号密码' \
  --sr-backup-password '备份账号密码' \
  --dry-run
```

```bash
python3 alert/mx_capital_ltv_alert.py \
  --sr-password '主账号密码' \
  --sr-backup-password '备份账号密码' \
  --target-date '2026-06-21' \
  --dry-run
```

## 配置

默认配置：

- StarRocks: `nlb-ngj6e0efsvv7wm73v3.cn-shanghai.nlb.aliyuncsslb.com:9031`
- PL 监控默认 DB: `ods`
- 数据一致性校验默认 DB: `fin`
- 主账号: `e_load`
- 备份账号: `e_backup`
- TV Bot: `f82292a5-45c5-42ea-84da-272b4c81ebcc`
- 默认 @ 人: `adamyu@kn.group,gretchenhe@kn.group`
- 数据一致性校验默认 @ 人: `adamyu@kn.group,gretchenhe@kn.group`
- 墨西哥资方 LTV 默认 DB: `dm_dd_new`
- 墨西哥资方 LTV 默认主账号: `e_load`
- 墨西哥资方 LTV 默认备份账号: `backup_user`

可通过命令行参数覆盖默认值，例如任务传参 `--mentions 'owner@kn.group,backup@kn.group'`。也可通过环境变量覆盖：`SR_HOST`、`SR_PORT`、`SR_DB`、`SR_USERNAME`、`SR_BACKUP_USERNAME`、`TV_API_URL`、`MANAGE_MODEL_GLOBAL_PL_TV_BOT_ID`、`MANAGE_MODEL_GLOBAL_PL_TV_MENTIONS`、`FIN_MANAGE_ODS_DATA_QUALITY_TV_BOT_ID`、`FIN_MANAGE_ODS_DATA_QUALITY_TV_MENTIONS`。
墨西哥资方 LTV 还可通过 `MX_CAPITAL_LTV_TV_BOT_ID`、`MX_CAPITAL_LTV_TV_MENTIONS` 覆盖 TV 机器人和默认 @ 人。

## n8n 接入

参考 `n8n/mx_capital_ltv_alert_workflow.json`。设计与现有 PL 告警一致：

1. `Webhook` 触发，建议路径 `MX_ZF_LTV`。
2. `资方LTV告警代码拉取` 下载 `chenjiuxuan1/starrocks-ltv-mx-tv-alert` 的 GitHub main 分支到跳板机 `/root/starrocks-ltv-mx-tv-alert`。
3. `资方LTV告警触发` 执行 `python3 alert/mx_capital_ltv_alert.py`，并通过环境变量传入墨西哥 StarRocks 地址、库名和账号。

模板已按“智能告警修复-墨西哥”的 n8n 配置写入墨西哥跳板机 `172.20.220.165`、SSH 凭据 `7oQDoS8H2buTjr7H / 墨西哥跳板机`、DB 连接信息和默认 @ 人 `liorawu@kn.group`；TV Bot 固定为 `08826b39-e6eb-44fb-9c25-9778a8171f49`。
