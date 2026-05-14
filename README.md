# StarRocks PL Monitor TV Alert

独立脚本：统计 `fin_global.manage_model_global_pl_monitor` 最新 `current_hour` 的告警记录数，按摘要告警格式发送到 TV 机器人。

## 运行

```bash
python3 alert/manage_model_global_pl_monitor_alert.py \
  --sr-password '主账号密码' \
  --sr-backup-password '备份账号密码' \
  --bot-id '4d0bcc9b-71bf-41c5-ba9f-89b7278f9214'
```

只预览不发送：

```bash
python3 alert/manage_model_global_pl_monitor_alert.py \
  --sr-password '主账号密码' \
  --sr-backup-password '备份账号密码' \
  --dry-run
```

## 配置

默认配置：

- StarRocks: `nlb-ngj6e0efsvv7wm73v3.cn-shanghai.nlb.aliyuncsslb.com:9031`
- DB: `ods`
- 主账号: `e_load`
- 备份账号: `e_backup`
- TV Bot: `f82292a5-45c5-42ea-84da-272b4c81ebcc`
- 默认 @ 人: `adamyu@kn.group`

可通过环境变量覆盖：`SR_HOST`、`SR_PORT`、`SR_DB`、`SR_USERNAME`、`SR_BACKUP_USERNAME`、`TV_API_URL`、`MANAGE_MODEL_GLOBAL_PL_TV_BOT_ID`、`MANAGE_MODEL_GLOBAL_PL_TV_MENTIONS`。
