# -*- coding: utf-8 -*-
"""定时调度器：后台线程计时，同时调度"休息提醒"与"每日打卡提醒"。

- 休息提醒：按间隔（秒）循环，到点投递 ("show_popup", 文案)
- 打卡提醒：每日多次（默认上/午休/午休结束/下班共 4 次）HH:MM 触发，
  到点投递 ("show_checkin", 名称, 时刻, 文案)，触发后重算为次日
- 两者独立计时；同一时刻到点时打卡提醒优先投递

兼容旧接口（v1.1 的单条"下班提醒"）：
- 构造参数 get_offwork_spec 仍可用，内部包装为一条 kind="offwork" 的打卡，
  到点投递 ("show_offwork", 文案)；status() 保留 "offwork" 字段别名。

线程安全约定：本模块只操作事件队列与时间戳，绝不直接触碰 tkinter；
弹窗必须由 tkinter 主线程在轮询队列时创建。
时间统一使用 time.time()（墙钟），保证各时间戳可比较。
"""
import datetime
import threading
import time

INF = float("inf")


def next_daily_ts(hour, minute, now=None):
    """返回下一个 HH:MM 时刻的墙钟时间戳；今天已过则算明天。"""
    now = now if now is not None else time.time()
    base = datetime.datetime.fromtimestamp(now)
    target = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target.timestamp() <= now:
        target += datetime.timedelta(days=1)
    return target.timestamp()


# 旧接口别名（v1.1）：语义与 next_daily_ts 完全一致
next_offwork_ts = next_daily_ts


def _wrap_offwork(fn):
    """把旧的"单条下班提醒"规格函数包装成打卡列表（兼容层）。"""
    fn = fn or (lambda: None)

    def _specs():
        spec = fn()
        if not spec or not spec.get("enabled"):
            return []
        return [{
            "label": "下班提醒",
            "kind": "offwork",
            "hour": int(spec.get("hour", 18)),
            "minute": int(spec.get("minute", 0)),
            "message": str(spec.get("message", "")),
        }]

    return _specs


class ReminderScheduler(threading.Thread):
    def __init__(self, queue, get_interval_seconds, get_next_message,
                 get_offwork_spec=None, get_checkins_spec=None):
        """get_checkins_spec: () -> list[dict]，每项形如
        {"label": str, "hour": int, "minute": int, "message": str,
         "kind": "checkin"|"offwork"（可省略，默认 checkin）}
        仅需返回**已启用**的条目。
        未传 get_checkins_spec 时回退兼容旧的 get_offwork_spec（单条下班提醒，
        保持第 4 个位置参数不变以兼容既有调用）。
        """
        super().__init__(daemon=True, name="ReminderScheduler")
        self._queue = queue
        self._get_interval_seconds = get_interval_seconds  # 闭包读取最新间隔
        self._get_next_message = get_next_message          # 闭包读取最新休息文案
        if get_checkins_spec is not None:
            self._get_specs = get_checkins_spec
        else:
            self._get_specs = _wrap_offwork(get_offwork_spec)
        self._lock = threading.Lock()
        self._pause_evt = threading.Event()   # set = 运行中
        self._stop_evt = threading.Event()
        self._reset_evt = threading.Event()   # set = 唤醒并重算下一次时间
        self._next_rest_ts = 0.0
        self._defer_seconds = None            # 待生效的"稍后提醒"延后秒数
        self._checkins = []                   # 打卡条目（含 ts/label/message/kind）
        self._spec_cache = None               # 配置变化检测
        self._pause_evt.set()
        self.start()

    # ---------- 对外控制接口（线程安全） ----------
    @property
    def running(self) -> bool:
        return self._pause_evt.is_set()

    def pause(self):
        self._pause_evt.clear()
        self._reset_evt.set()

    def resume(self):
        self._pause_evt.set()
        self._reset_evt.set()

    def reset(self):
        """立即重算下一次提醒时间（修改间隔/时间/恢复时调用）。"""
        self._reset_evt.set()

    def defer(self, seconds):
        """【稍后提醒】把下一次休息提醒推后 seconds 秒，并重置休息计时。

        语义：用户在弹窗上点了"稍后 N 分钟" —— 这一次的提醒不算数，
        从当前时刻重新起算 N 分钟。只作用于**休息提醒**，
        打卡提醒到点即触发、不受影响。
        线程安全：只写一个待生效字段 + 置位唤醒事件，由调度线程自己重算。
        """
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            return
        with self._lock:
            self._defer_seconds = max(1.0, seconds)
        self._reset_evt.set()

    def stop(self):
        self._stop_evt.set()
        self._reset_evt.set()

    def status(self) -> dict:
        """供界面显示：运行状态 + 休息/最近一次打卡的剩余秒数（无效为 -1）。

        offwork 为兼容 v1.1 的别名，值与 checkin 相同。
        """
        now = time.time()
        with self._lock:
            running = self._pause_evt.is_set()
            rest = -1.0 if not running else max(0.0, self._next_rest_ts - now)
            nearest = min(self._checkins, key=lambda c: c["ts"]) \
                if self._checkins else None
            if not running or nearest is None:
                checkin, label = -1.0, ""
            else:
                checkin = max(0.0, nearest["ts"] - now)
                label = nearest["label"]
        return {
            "running": running,
            "rest": rest,
            "checkin": checkin,
            "checkin_label": label,
            "offwork": checkin,   # 兼容旧字段
        }

    # ---------- 线程主体 ----------
    def _rest_deadline(self, now):
        """下一次休息提醒的到期时刻：优先用待生效的 defer，否则用设定间隔。

        defer 是"一次性覆盖"：取走即清空，下一次恢复按正常间隔计。
        """
        with self._lock:
            defer = self._defer_seconds
            self._defer_seconds = None
        if defer is not None:
            return now + defer
        return now + max(1.0, float(self._get_interval_seconds()))

    def run(self):
        self._next_rest_ts = self._rest_deadline(time.time())
        self._sync_checkins(time.time(), force=True)
        while not self._stop_evt.is_set():
            running = self._pause_evt.is_set()
            now = time.time()
            if running:
                # 打卡到点？（优先于休息）
                event = self._take_due_checkin(now)
                if event is not None:
                    self._queue.put(event)
                    continue
                # 休息到点？
                if now >= self._next_rest_ts:
                    self._queue.put(("show_popup", self._get_next_message()))
                    with self._lock:
                        self._next_rest_ts = now + self._get_interval_seconds()
                    continue
                # 等待所有目标中最近的一个
                self._sync_checkins(now)  # 检测配置变化
                with self._lock:
                    targets = [self._next_rest_ts] + \
                        [ci["ts"] for ci in self._checkins]
                    wait = min(0.5, max(0.05, min(targets) - now))
            else:
                wait = 0.5  # 暂停时低速轮询，随时可恢复
            if self._reset_evt.wait(wait):
                # 被 reset 唤醒：重算下一次（暂停期间不计时；defer 在此生效）
                self._reset_evt.clear()
                now = time.time()
                self._next_rest_ts = self._rest_deadline(now)
                self._sync_checkins(now, force=True)
        # 线程结束

    def _take_due_checkin(self, now):
        """取出一条已到点的打卡：把它重排到次日，并返回待投递事件（无则 None）。"""
        with self._lock:
            for ci in self._checkins:
                if now >= ci["ts"]:
                    ci["ts"] = next_daily_ts(ci["hour"], ci["minute"], now)
                    if ci["kind"] == "offwork":
                        return ("show_offwork", ci["message"])
                    return ("show_checkin", ci["label"], ci["time"], ci["message"])
        return None

    def _sync_checkins(self, now, force=False):
        """依据当前打卡配置同步全部时间戳；配置无变化时跳过。"""
        specs = self._get_specs() or []
        key = tuple((str(s.get("kind", "checkin")), int(s.get("hour", 0)),
                     int(s.get("minute", 0))) for s in specs)
        with self._lock:
            if not (force or key != self._spec_cache):
                return
            self._spec_cache = key
            self._checkins = []
            for s in specs:
                hour = max(0, min(23, int(s.get("hour", 0))))
                minute = max(0, min(59, int(s.get("minute", 0))))
                self._checkins.append({
                    "ts": next_daily_ts(hour, minute, now),
                    "hour": hour,
                    "minute": minute,
                    "time": "%02d:%02d" % (hour, minute),
                    "label": str(s.get("label") or "打卡"),
                    "message": str(s.get("message") or ""),
                    "kind": str(s.get("kind", "checkin")),
                })
