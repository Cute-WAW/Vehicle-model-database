"""
看门狗守护进程

功能：
1. 监控日志目录活动，检测服务是否卡死
2. 定期健康检查，检测服务是否响应
3. 异常时自动重启服务

环境变量配置：
  APP_START_CMD           - 启动命令 (默认: python src/web_predictor_debug_step5.py)
  APP_LOG_DIR             - 日志目录 (默认: logs)
  GUARD_HEALTH_URL        - 健康检查URL (默认: http://127.0.0.1:8087/health)
  GUARD_HEALTH_INTERVAL_SEC - 健康检查间隔秒数 (默认: 10)
  GUARD_HEALTH_TIMEOUT_SEC  - 健康检查超时秒数 (默认: 3)
  GUARD_HEALTH_FAILS      - 连续失败次数阈值 (默认: 3)
  GUARD_LOG_IDLE_SEC      - 日志无活动超时秒数 (默认: 120)
  GUARD_RESTART_BACKOFF_SEC - 重启前等待秒数 (默认: 3)
  GUARD_OBSERVER          - 文件观察器类型 (默认: inotify)
  GUARD_MONITOR_ONLY      - 仅监控模式，不自行启动进程 (默认: false)
"""

import os
import sys
import time
import threading
import subprocess
import shlex
from pathlib import Path
import requests
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver


class LogHandler(FileSystemEventHandler):
    def __init__(self, on_event):
        self.on_event = on_event

    def on_modified(self, event):
        if not event.is_directory:
            self.on_event()

    def on_created(self, event):
        if not event.is_directory:
            self.on_event()


class Guard:
    def __init__(
        self,
        log_dir: Path,
        start_cmd: str,
        health_url: str,
        health_interval_sec: int,
        health_timeout_sec: int,
        health_fail_threshold: int,
        log_idle_sec: int,
        restart_backoff_sec: int,
        observer_kind: str,
        monitor_only: bool = False,
        process_pattern: str = "web_predictor_debug_step5.py"
    ):
        self.log_dir = log_dir
        self.start_cmd = start_cmd
        self.health_url = health_url
        self.health_interval_sec = health_interval_sec
        self.health_timeout_sec = health_timeout_sec
        self.health_fail_threshold = health_fail_threshold
        self.log_idle_sec = log_idle_sec
        self.restart_backoff_sec = restart_backoff_sec
        self.observer_kind = observer_kind
        self.last_activity = time.monotonic()
        self.health_fail = 0
        self.unhealthy = False
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.monitor_only = monitor_only
        self.process_pattern = process_pattern

    def _observer(self):
        if self.observer_kind.lower() == "polling":
            return PollingObserver()
        return Observer()

    def _update_activity(self):
        with self.lock:
            self.last_activity = time.monotonic()

    def _set_unhealthy(self):
        with self.lock:
            self.unhealthy = True

    def _reset_health(self):
        with self.lock:
            self.unhealthy = False
            self.health_fail = 0

    def _child_start(self):
        # 使用 shell=False 防止产生子 shell 导致信号无法传递给实际进程 (避免僵尸进程)
        args = shlex.split(self.start_cmd)
        return subprocess.Popen(args, shell=False)

    def _child_stop(self, p: subprocess.Popen):
        try:
            p.terminate()
        except Exception:
            pass
        try:
            p.wait(timeout=10)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

    def _kill_existing_app(self):
        """杀死现有的应用程序进程"""
        try:
            subprocess.run(
                f'pkill -f "{self.process_pattern}"',
                shell=True,
                check=False
            )
        except Exception:
            pass

    def _health_loop(self):
        while not self.stop_event.is_set():
            ok = False
            try:
                r = requests.get(self.health_url, timeout=self.health_timeout_sec)
                ok = 200 <= r.status_code < 300
            except Exception:
                ok = False
            with self.lock:
                if ok:
                    self.health_fail = 0
                else:
                    self.health_fail += 1
                    if self.health_fail >= self.health_fail_threshold:
                        self.unhealthy = True
            time.sleep(self.health_interval_sec)

    def run(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        obs = self._observer()
        handler = LogHandler(self._update_activity)
        obs.schedule(handler, str(self.log_dir), recursive=True)
        obs.start()
        p = None
        if not self.monitor_only:
            p = self._child_start()
        ht = threading.Thread(target=self._health_loop, daemon=True)
        ht.start()
        try:
            while not self.stop_event.is_set():
                dead = p is not None and p.poll() is not None
                with self.lock:
                    idle = time.monotonic() - self.last_activity
                    need_restart = self.unhealthy or idle >= self.log_idle_sec
                if dead:
                    p = self._child_start()
                    self._reset_health()
                    self._update_activity()
                elif need_restart:
                    if self.monitor_only:
                        self._kill_existing_app()
                    else:
                        if p is not None:
                            self._child_stop(p)
                    time.sleep(self.restart_backoff_sec)
                    p = self._child_start()
                    self._reset_health()
                    self._update_activity()
                time.sleep(1)
        finally:
            self.stop_event.set()
            try:
                obs.stop()
                obs.join()
            except Exception:
                pass
            if p and p.poll() is None:
                self._child_stop(p)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]

    # 日志目录 (默认: logs)
    log_dir_env = os.getenv("APP_LOG_DIR") or os.getenv("GUARD_LOG_DIR")
    log_dir = Path(log_dir_env) if log_dir_env else project_root / "logs"

    # 启动命令 (默认: python src/web_predictor_debug_step5.py)
    start_cmd = os.getenv("APP_START_CMD", f"python {project_root}/src/web_predictor_debug_step5.py")

    # 健康检查URL (默认: http://127.0.0.1:8003/health)
    health_url = os.getenv("GUARD_HEALTH_URL", "http://127.0.0.1:8087/health")

    # 进程匹配模式
    process_pattern = os.getenv("GUARD_PROCESS_PATTERN", "web_predictor_debug_step5.py")

    # 其他配置
    health_interval_sec = _env_int("GUARD_HEALTH_INTERVAL_SEC", 10)
    health_timeout_sec = _env_int("GUARD_HEALTH_TIMEOUT_SEC", 3)
    health_fail_threshold = _env_int("GUARD_HEALTH_FAILS", 3)
    log_idle_sec = _env_int("GUARD_LOG_IDLE_SEC", 120)
    restart_backoff_sec = _env_int("GUARD_RESTART_BACKOFF_SEC", 3)
    observer_kind = os.getenv("GUARD_OBSERVER", "inotify")
    monitor_only = os.getenv("GUARD_MONITOR_ONLY", "false").lower() == "true"

    print(f"看门狗启动")
    print(f"  日志目录: {log_dir}")
    print(f"  启动命令: {start_cmd}")
    print(f"  健康检查: {health_url}")
    print(f"  监控模式: {monitor_only}")

    Guard(
        log_dir=log_dir,
        start_cmd=start_cmd,
        health_url=health_url,
        health_interval_sec=health_interval_sec,
        health_timeout_sec=health_timeout_sec,
        health_fail_threshold=health_fail_threshold,
        log_idle_sec=log_idle_sec,
        restart_backoff_sec=restart_backoff_sec,
        observer_kind=observer_kind,
        monitor_only=monitor_only,
        process_pattern=process_pattern,
    ).run()