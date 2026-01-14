#!/usr/bin/env bash
source ~/.bashrc
echo "已加载 Bash 环境"

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
echo "已切换到项目根目录: $ROOT_DIR"

conda activate py39_env
echo "已激活 Conda 环境: py39_env"

set -e
echo "开始执行启动脚本"

LOG_DIR="$ROOT_DIR/logs"
RUN_DIR="$ROOT_DIR/run"
mkdir -p "$LOG_DIR" "$RUN_DIR"
echo "已准备日志与运行目录: $LOG_DIR, $RUN_DIR"

# ===== 服务配置 =====
APP_PORT=8087
HEALTH_URL="http://127.0.0.1:${APP_PORT}/health"
APP_CMD="python $ROOT_DIR/src/web_predictor_debug_step5.py --port $APP_PORT"
APP_PROCESS_PATTERN="web_predictor_debug_step5.py"

echo "清理环境..."

# 1. 先停止看门狗，防止它重启服务
echo "停止看门狗进程..."
for i in {1..3}; do
    if pgrep -f "scripts/watchdog_guard.py" > /dev/null; then
        pkill -f "scripts/watchdog_guard.py"
        sleep 1
    else
        break
    fi
done

# 2. 再停止主程序
echo "停止主程序进程..."
for i in {1..5}; do
    if pgrep -f "$APP_PROCESS_PATTERN" > /dev/null; then
        echo "尝试停止主程序 (第 $i 次)..."
        pkill -f "$APP_PROCESS_PATTERN"
        sleep 1
    else
        break
    fi
done

# 如果仍有残留，强制杀死
if pgrep -f "$APP_PROCESS_PATTERN" > /dev/null; then
    echo "主程序未退出，执行强制清理..."
    pkill -9 -f "$APP_PROCESS_PATTERN" || true
    sleep 1
fi

# 3. 清理 PID 文件
rm -f "$RUN_DIR/app.pid" "$RUN_DIR/watchdog.pid"
echo "清理完成"

echo "主程序启动命令: $APP_CMD"

echo "以后台方式启动主程序..."
cd "$ROOT_DIR/src"
nohup $APP_CMD >> "$LOG_DIR/app.out" 2>&1 &
echo $! > "$RUN_DIR/app.pid"
echo "主程序 PID: $(cat "$RUN_DIR/app.pid")"
cd "$ROOT_DIR"

echo "以后台方式启动看门狗..."
nohup env \
    APP_START_CMD="$APP_CMD" \
    APP_LOG_DIR="$ROOT_DIR/logs" \
    GUARD_HEALTH_URL="$HEALTH_URL" \
    GUARD_PROCESS_PATTERN="$APP_PROCESS_PATTERN" \
    GUARD_MONITOR_ONLY=true \
    python "$ROOT_DIR/scripts/watchdog_guard.py" >> "$LOG_DIR/watchdog_guard.out" 2>&1 &
echo $! > "$RUN_DIR/watchdog.pid"
echo "看门狗 PID: $(cat "$RUN_DIR/watchdog.pid")"

echo "启动完成"
echo "服务地址: http://0.0.0.0:${APP_PORT}"
echo "健康检查: $HEALTH_URL"
echo "API文档: http://0.0.0.0:${APP_PORT}/docs"
exit 0