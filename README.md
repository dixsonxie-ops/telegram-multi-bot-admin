# Telegram 多机器人管理后台（Railway 一键部署版）

## 运行方式
Railway Start Command:
python app.py & python bot_runner.py

## 环境变量（Railway Variables）
- ROBOT_SECRET_KEY=自定义密钥（必须设置）
- DATA_DIR=data （可选，默认 data）

## 数据存储
SQLite 数据库保存在：data/bot.db
请在 Railway 开启 Volume 并挂载到 /app/data

## 后台入口
/
