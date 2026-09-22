# -*- coding: utf-8 -*-
"""配置读写模块：JSON 存储于 %APPDATA%/EyeReminder/config.json。

安全设计：
- 文件大小上限（1MB）：超限视为损坏，防止超大/异常文件导致内存耗尽
- 原子写入：先写临时文件再 os.replace，避免崩溃/断电留下半写文件
- 严格类型校验：JSON 中的字符串 "false"/"0" 不会被误判为 True
- 损坏时自动备份为 .bak 并回退默认值
"""
import json
import os

import theme

APP_NAME = "EyeReminder"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

MAX_CONFIG_SIZE = 1024 * 1024   # 1MB：配置上限，超限视为损坏
MAX_MESSAGES = 100              # 提醒文案条数上限
MAX_MESSAGE_LEN = 200           # 单条文案长度上限
CHECKIN_COUNT = 4               # 每日打卡次数（上下班共 4 次）
MAX_CHECKIN_LABEL_LEN = 12      # 打卡名称长度上限
# 单次提醒同时弹出的弹窗个数上限
# （与 popup.MAX_POPUPS 保持一致；两处各自定义是为了让 config 不依赖 GUI 模块）
MAX_POPUP_COUNT = 6
MAX_DEFER_MINUTES = 60          # "稍后提醒"分钟数上限

# 默认打卡表：上班 / 午休 / 午休结束 / 下班，一天 4 次
DEFAULT_CHECKINS = [
    {"label": "上班打卡", "time": "09:00", "enabled": True,
     "message": "新的一天开始啦，记得打卡上班！"},
    {"label": "午休打卡", "time": "12:00", "enabled": True,
     "message": "午休时间到，记得打卡去吃饭～"},
    {"label": "午休结束", "time": "13:30", "enabled": True,
     "message": "午休结束，记得打卡回来上班。"},
    {"label": "下班打卡", "time": "18:00", "enabled": True,
     "message": "辛苦啦，到下班时间了！记得打卡，明天见～"},
]

DEFAULTS = {
    "interval_minutes": 45,      # 提醒间隔（分钟）
    "messages": [                # 提醒文案（多段，轮换/随机展示）
        "眼睛累了，看看远处 20 秒吧～\n记得眨眼，记得喝水，站起来活动一下。",
        "连续用眼时间不短了，闭眼休息 30 秒，向窗外远眺一下吧。",
        "护眼小贴士：看屏幕每 20 分钟，看向 6 米以外的地方至少 20 秒。",
    ],
    "random_order": False,       # True=随机取文案，False=顺序轮换
    "popup_seconds": 10,         # 弹窗停留秒数
    "popup_count": 1,            # 单次提醒同时弹出的弹窗个数（1~6，铺在桌面不同位置）
    "defer_minutes": 5,          # 弹窗"稍后提醒"按钮的延后分钟数
    "button_text": "知道了，继续干活",       # 休息弹窗按钮文字（可自定义）
    "checkin_button_text": "已打卡，继续",   # 打卡弹窗按钮文字（v1.7）
    "theme": theme.DEFAULT,      # 皮肤（v1.6）：theme.SKINS 中的键
    "sound": True,               # 弹窗时响提示音
    "auto_start": False,         # 开机自启
    "running": True,             # 启动后是否直接进入提醒运行状态
    # ---- 每日打卡提醒（v1.7）：固定 4 条 ----
    "checkins": [dict(item) for item in DEFAULT_CHECKINS],
    # ---- 下班提醒（v1.1，v1.7 起并入打卡表；仅作旧配置迁移来源） ----
    "offwork_enabled": False,    # 是否启用下班提醒
    "offwork_time": "18:00",     # 每日下班时间 HH:MM
    "offwork_message": "辛苦啦，到下班时间了！\n收拾好东西，明天见～",
}


_TRUE_STRINGS = {"true", "1", "yes", "on", "y", "是"}
_FALSE_STRINGS = {"false", "0", "no", "off", "n", "否"}


def _as_bool(value, default=False) -> bool:
    """严格布尔校验：接受 bool、0/1 整数与常见真假字符串，
    无法识别的值回退默认。防止 bool("false") 被误判为 True。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _TRUE_STRINGS:
            return True
        if v in _FALSE_STRINGS:
            return False
    return default


def _norm_hhmm(value, default="00:00") -> str:
    """把任意值规整为 HH:MM（各段 clamp 到合法范围），非法回退 default。"""
    try:
        h, m = str(value).split(":")
        return "%02d:%02d" % (max(0, min(23, int(h))), max(0, min(59, int(m))))
    except (ValueError, AttributeError, TypeError):
        return default


def _norm_checkins(value) -> list:
    """规整打卡表：固定 CHECKIN_COUNT 条，逐条清洗字段，缺失/非法回退默认。

    防御性：条目数不足自动补齐、超出自动截断；名称/提示词限长；
    时间用 _norm_hhmm 约束；enabled 用严格布尔解析。
    """
    items = value if isinstance(value, list) else []
    out = []
    for i, default in enumerate(DEFAULT_CHECKINS):
        raw = items[i] if i < len(items) and isinstance(items[i], dict) else {}
        label = raw.get("label")
        if not isinstance(label, str) or not label.strip():
            label = default["label"]
        message = raw.get("message")
        if not isinstance(message, str) or not message.strip():
            message = default["message"]
        out.append({
            "label": label.strip()[:MAX_CHECKIN_LABEL_LEN],
            "time": _norm_hhmm(raw.get("time"), default["time"]),
            "enabled": _as_bool(raw.get("enabled"), default["enabled"]),
            "message": message[:MAX_MESSAGE_LEN],
        })
    return out


def load() -> dict:
    """读取配置；任何异常都回退默认值（坏文件先备份为 .bak）。"""
    cfg = dict(DEFAULTS)
    raw = {}
    try:
        # 大小上限：超大文件视为损坏，防止内存耗尽
        if os.path.getsize(CONFIG_PATH) > MAX_CONFIG_SIZE:
            raise ValueError("config too large")
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            raw = data
            for k, v in data.items():
                if k in cfg:
                    cfg[k] = v
    except (OSError, ValueError, TypeError):
        try:
            if os.path.exists(CONFIG_PATH):
                os.replace(CONFIG_PATH, CONFIG_PATH + ".bak")
        except OSError:
            pass

    # 类型与范围校验
    try:
        cfg["interval_minutes"] = max(1, min(180, int(cfg["interval_minutes"])))
    except (TypeError, ValueError):
        cfg["interval_minutes"] = DEFAULTS["interval_minutes"]
    try:
        cfg["popup_seconds"] = max(3, min(120, int(cfg["popup_seconds"])))
    except (TypeError, ValueError):
        cfg["popup_seconds"] = DEFAULTS["popup_seconds"]
    try:
        cfg["popup_count"] = max(1, min(MAX_POPUP_COUNT, int(cfg["popup_count"])))
    except (TypeError, ValueError):
        cfg["popup_count"] = DEFAULTS["popup_count"]
    try:
        cfg["defer_minutes"] = max(1, min(MAX_DEFER_MINUTES,
                                          int(cfg["defer_minutes"])))
    except (TypeError, ValueError):
        cfg["defer_minutes"] = DEFAULTS["defer_minutes"]
    if not isinstance(cfg["messages"], list) or not cfg["messages"] or \
            not all(isinstance(m, str) and m.strip() for m in cfg["messages"]):
        cfg["messages"] = DEFAULTS["messages"]
    # 条数与单条长度上限（防御性限制）
    cfg["messages"] = cfg["messages"][:MAX_MESSAGES]
    cfg["messages"] = [m[:MAX_MESSAGE_LEN] for m in cfg["messages"]]
    if not cfg["messages"]:
        cfg["messages"] = DEFAULTS["messages"]
    cfg["random_order"] = _as_bool(cfg["random_order"], DEFAULTS["random_order"])
    cfg["sound"] = _as_bool(cfg["sound"], DEFAULTS["sound"])
    cfg["auto_start"] = _as_bool(cfg["auto_start"], DEFAULTS["auto_start"])
    cfg["running"] = _as_bool(cfg["running"], DEFAULTS["running"])
    # 下班时间 HH:MM 校验
    cfg["offwork_time"] = _norm_hhmm(cfg["offwork_time"], DEFAULTS["offwork_time"])
    cfg["offwork_enabled"] = _as_bool(cfg["offwork_enabled"],
                                      DEFAULTS["offwork_enabled"])
    if not isinstance(cfg["offwork_message"], str) or not cfg["offwork_message"].strip():
        cfg["offwork_message"] = DEFAULTS["offwork_message"]
    if not isinstance(cfg["button_text"], str) or not cfg["button_text"].strip():
        cfg["button_text"] = DEFAULTS["button_text"]
    if not isinstance(cfg["checkin_button_text"], str) \
            or not cfg["checkin_button_text"].strip():
        cfg["checkin_button_text"] = DEFAULTS["checkin_button_text"]
    # ---- 每日打卡（v1.7） ----
    # 旧版"下班提醒"迁移：配置文件里还没有 checkins 字段、且旧下班提醒已启用时，
    # 把旧设置并入第 4 条（下班打卡），避免用户已有配置丢失。
    if "checkins" not in raw and _as_bool(raw.get("offwork_enabled"), False):
        migrated = [dict(item) for item in DEFAULT_CHECKINS]
        migrated[3].update({
            "label": "下班打卡",
            "time": _norm_hhmm(raw.get("offwork_time"), DEFAULTS["offwork_time"]),
            "message": str(raw.get("offwork_message") or migrated[3]["message"]),
            "enabled": True,
        })
        cfg["checkins"] = migrated
    cfg["checkins"] = _norm_checkins(cfg.get("checkins"))
    # 皮肤：必须是预设皮肤键之一，非法值回退默认
    if cfg.get("theme") not in theme.SKINS:
        cfg["theme"] = theme.DEFAULT
    return cfg


def save(cfg: dict) -> None:
    """原子保存配置：写临时文件后 os.replace，崩溃/断电不留下半写文件。"""
    tmp_path = CONFIG_PATH + ".tmp"
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CONFIG_PATH)
    except OSError:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
