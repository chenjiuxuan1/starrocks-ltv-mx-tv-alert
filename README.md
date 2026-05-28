# StarRocks TV Alert Scripts

仓库当前包含两条彼此独立的 TV 告警脚本：

- `alert/manage_model_global_pl_monitor_alert.py`
  统计 `fin_global.manage_model_global_pl_monitor` 最新 `etl_create_time` 批次的总记录数和 `diff <> 0` 异常记录数，按摘要告警格式发送到 TV 机器人。
- `alert/fin_manage_ods_data_quality_monitor_alert.py`
  统计 `fin.fin_manage_ods_data_quality_monitor` 的总记录数与 `diff <> 0` 的异常记录数，按“数仓与财务库数据一致性校验”格式发送到 TV 机器人。

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

可通过命令行参数覆盖默认值，例如任务传参 `--mentions 'owner@kn.group,backup@kn.group'`。也可通过环境变量覆盖：`SR_HOST`、`SR_PORT`、`SR_DB`、`SR_USERNAME`、`SR_BACKUP_USERNAME`、`TV_API_URL`、`MANAGE_MODEL_GLOBAL_PL_TV_BOT_ID`、`MANAGE_MODEL_GLOBAL_PL_TV_MENTIONS`、`FIN_MANAGE_ODS_DATA_QUALITY_TV_BOT_ID`、`FIN_MANAGE_ODS_DATA_QUALITY_TV_MENTIONS`。
