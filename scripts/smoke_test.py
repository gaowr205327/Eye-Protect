# -*- coding: utf-8 -*-
"""自动化冒烟测试（开发用，不打包进 exe）：
1. 配置读写与损坏回退（含每日打卡表、旧下班提醒迁移）
2. 调度器：休息定时投递 / 暂停 / 恢复 / 打卡到点投递 / 次日重算 / 旧接口兼容
3. GUI 主程序启动：进程存活、无 traceback、正常退出
"""
import json
import os
import queue
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

# ---------- 1. 配置模块 ----------
print("== config ==")
import config as cfg_mod

with tempfile.TemporaryDirectory() as td:
    cfg_mod.CONFIG_DIR = td
    cfg_mod.CONFIG_PATH = os.path.join(td, "config.json")
    c = cfg_mod.load()
    assert c["interval_minutes"] == 45, "默认间隔应为 45"
    assert c["offwork_time"] == "18:00", "默认下班时间应为 18:00"
    assert c["button_text"] == "知道了，继续干活", "默认按钮文字错误"
    assert c["theme"] == "classic", "默认皮肤应为经典蓝"
    c["interval_minutes"] = 30
    c["messages"] = ["测试文案A", "测试文案B"]
    c["offwork_enabled"] = True
    c["offwork_time"] = "17:30"
    c["offwork_message"] = "下班啦！"
    c["button_text"] = "我先眯一会儿"
    cfg_mod.save(c)
    c2 = cfg_mod.load()
    assert c2["offwork_enabled"] is True and c2["offwork_time"] == "17:30" \
        and c2["offwork_message"] == "下班啦！", "下班字段读写不一致"
    assert c2["button_text"] == "我先眯一会儿", "按钮文字读写不一致"
    # 非法下班时间应被修正（clamp 到合法范围）
    c["offwork_time"] = "25:99"
    cfg_mod.save(c)
    assert cfg_mod.load()["offwork_time"] == "23:59", "非法时间未修正"

    # 打卡表（v1.7）：默认 4 条；读写一致；非法条目被规整
    c_chk = cfg_mod.load()
    assert len(c_chk["checkins"]) == 4, "默认应有 4 条打卡"
    assert c_chk["checkins"][0]["time"] == "09:00", "默认首条打卡时间错误"
    assert c_chk["checkin_button_text"] == "已打卡，继续", "默认打卡按钮文字错误"
    c_chk["checkins"][0].update({"enabled": False, "time": "07:05",
                                 "message": "早起打卡"})
    cfg_mod.save(c_chk)
    saved = cfg_mod.load()["checkins"]
    assert saved[0]["enabled"] is False and saved[0]["time"] == "07:05" \
        and saved[0]["message"] == "早起打卡", "打卡字段读写不一致"
    # 非法/缺失条目应被补齐与 clamp
    c_chk["checkins"] = [{"label": "", "time": "99:99", "enabled": "yes"}]
    cfg_mod.save(c_chk)
    fixed = cfg_mod.load()["checkins"]
    assert len(fixed) == 4, "打卡条数应补齐为 4"
    assert fixed[0]["time"] == "23:59", "非法打卡时间未修正"
    assert fixed[0]["label"] == cfg_mod.DEFAULT_CHECKINS[0]["label"], \
        "空打卡名称应回退默认"
    assert fixed[0]["enabled"] is True, "字符串 yes 应解析为 True"
    # 旧版下班提醒迁移：无 checkins 字段且旧下班已启用 → 并入第 4 条
    with open(cfg_mod.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"offwork_enabled": True, "offwork_time": "17:30",
                   "offwork_message": "旧下班"}, f, ensure_ascii=False)
    migrated = cfg_mod.load()["checkins"]
    assert migrated[3]["time"] == "17:30" and migrated[3]["enabled"] is True \
        and migrated[3]["message"] == "旧下班", "旧下班提醒未迁移进打卡表"
    print("checkins config + 旧配置迁移 PASS")

    # 配色：单一固定样式（星露谷），任何值都回退到 classic
    c["theme"] = "classic"
    cfg_mod.save(c)
    assert cfg_mod.load()["theme"] == "classic", "配色读写不一致"
    c["theme"] = "不存在的皮肤"
    cfg_mod.save(c)
    assert cfg_mod.load()["theme"] == "classic", "非法配色应回退默认"
    print("theme config PASS")
    # 损坏回退
    with open(cfg_mod.CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write("{ 这不是合法JSON")
    c3 = cfg_mod.load()
    assert c3["interval_minutes"] == 45, "损坏配置应回退默认"
    assert os.path.exists(cfg_mod.CONFIG_PATH + ".bak"), "应备份坏文件"

    # ---- 安全回归（v1.3 审查修复） ----
    # 1) bool 字符串混淆：JSON 中 "false"（字符串）不得被误判为 True
    with open(cfg_mod.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"running": "false", "sound": "0", "auto_start": "yes"},
                  f, ensure_ascii=False)
    c4 = cfg_mod.load()
    assert c4["running"] is False, "字符串 false 应解析为 False"
    assert c4["sound"] is False, "字符串 0 应解析为 False"
    assert c4["auto_start"] is True, "字符串 yes 应解析为 True"
    # 无法识别的值回退默认；真布尔/整数 1 仍正常
    with open(cfg_mod.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"running": "garbage", "sound": True, "auto_start": 1}, f)
    c5 = cfg_mod.load()
    assert c5["running"] is True, "无法识别应回退默认(True)"
    assert c5["sound"] is True and c5["auto_start"] is True, "真布尔/整数1应保留"
    print("bool strictness PASS")

    # 2) 超大配置（>1MB）应视为损坏回退默认
    with open(cfg_mod.CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write('{"messages": ["' + "a" * (cfg_mod.MAX_CONFIG_SIZE + 10) + '"]}')
    c6 = cfg_mod.load()
    assert c6["messages"] == cfg_mod.DEFAULTS["messages"], "超大配置未回退默认"
    assert os.path.exists(cfg_mod.CONFIG_PATH + ".bak"), "超大配置应备份"
    print("oversize config PASS")

    # 3) 原子写：保存后不应残留 .tmp 文件
    cfg_mod.save(cfg_mod.DEFAULTS)
    assert not os.path.exists(cfg_mod.CONFIG_PATH + ".tmp"), "原子写残留 .tmp"
    assert os.path.exists(cfg_mod.CONFIG_PATH), "配置应已写入"
    print("atomic write PASS")

    # 4) messages 条数/长度上限
    big = {"messages": ["x" * 500] * 150}
    cfg_mod.save(big)
    c7 = cfg_mod.load()
    assert len(c7["messages"]) == cfg_mod.MAX_MESSAGES, "条数未截断"
    assert all(len(m) <= cfg_mod.MAX_MESSAGE_LEN for m in c7["messages"]), \
        "单条长度未截断"
    print("messages limits PASS")
print("config PASS")

# ---------- 2. 调度器 ----------
print("== scheduler ==")
from scheduler import ReminderScheduler, next_offwork_ts  # noqa: E402
import datetime  # noqa: E402

q = queue.Queue()
sched = ReminderScheduler(
    q,
    get_interval_seconds=lambda: 0.15,
    get_next_message=lambda: "休息一下",
    get_offwork_spec=lambda: {"enabled": False, "hour": 18, "minute": 0,
                              "message": ""})
# 休息定时投递
evt = q.get(timeout=2)
assert evt[0] == "show_popup" and evt[1] == "休息一下", f"投递内容错误: {evt}"
print("rest timer PASS")
# 暂停：0.5s 内无新事件
sched.pause()
time.sleep(0.5)
assert q.empty(), "暂停期间不应投递"
print("pause PASS")
# 恢复：重新计时并投递
sched.resume()
evt = q.get(timeout=2)
assert evt[0] == "show_popup", f"恢复后未投递: {evt}"
print("resume PASS")
# status 接口
st = sched.status()
assert st["running"] is True and st["rest"] > 0 and st["offwork"] == -1, \
    f"status 错误: {st}"
sched.pause()
assert sched.status()["rest"] == -1, "暂停时 rest 应为 -1"
print("status PASS")
sched.stop()

# 打卡调度（v1.7 新接口）：注入未来 0.3 秒触发
q2 = queue.Queue()
sched2 = ReminderScheduler(
    q2,
    get_interval_seconds=lambda: 60,
    get_next_message=lambda: "休息",
    get_checkins_spec=lambda: [{"label": "上班打卡", "hour": 9, "minute": 0,
                                "message": "记得打卡"}])
time.sleep(0.3)  # 等首次同步完成，避免注入被覆盖
assert sched2.status()["checkin"] > 0, "启用打卡时 checkin 应 > 0"
assert sched2.status()["checkin_label"] == "上班打卡", "打卡名称未同步"
sched2._checkins[0]["ts"] = time.time() + 0.3   # 测试注入：提前触发
evt = q2.get(timeout=2)
assert evt == ("show_checkin", "上班打卡", "09:00", "记得打卡"), \
    f"打卡投递错误: {evt}"
print("checkin fire PASS")
# 触发后应重算为明天（不再立即触发）
time.sleep(0.4)
assert q2.empty(), "打卡触发后不应重复触发"
assert sched2.status()["checkin"] > 0, "打卡后应已重算次日"
print("checkin next-day recalc PASS")
sched2.stop()

# 旧接口兼容（v1.1 单条下班提醒 → 内部包装为一条 offwork 打卡）
q4 = queue.Queue()
sched4 = ReminderScheduler(
    q4,
    get_interval_seconds=lambda: 60,
    get_next_message=lambda: "休息",
    get_offwork_spec=lambda: {"enabled": True, "hour": 18, "minute": 0,
                              "message": "下班啦"})
time.sleep(0.3)
sched4._checkins[0]["ts"] = time.time() + 0.3
evt = q4.get(timeout=2)
assert evt[0] == "show_offwork" and evt[1] == "下班啦", f"旧接口投递错误: {evt}"
assert sched4.status()["offwork"] > 0, "旧接口触发后应已重算次日"
print("offwork legacy compat PASS")
sched4.stop()

# 下班禁用时 status 为 -1
q3 = queue.Queue()
sched3 = ReminderScheduler(q3, lambda: 60, lambda: "休息",
                           lambda: {"enabled": False, "hour": 18,
                                    "minute": 0, "message": ""})
assert sched3.status()["offwork"] == -1, "禁用下班时 offwork 应为 -1"
assert sched3.status()["checkin"] == -1, "禁用下班时 checkin 应为 -1"
sched3.stop()
print("offwork disabled PASS")

# next_offwork_ts：今天 18:00 已过 → 明天；未过 → 今天
now = time.time()
assert next_offwork_ts(18, 0, now) > now, "已过时间应算明天"
future = datetime.datetime.fromtimestamp(now) + datetime.timedelta(minutes=5)
assert next_offwork_ts(future.hour, future.minute, now) <= now + 3600, \
    "未过时间应算今天"
print("next_offwork_ts PASS")

# ---------- 2.5 文本清洗（popup 安全） ----------
print("== sanitize ==")
from popup import _sanitize_text  # noqa: E402

# 保留换行、折叠空白、去空行
s = _sanitize_text("第一行  有空格\n\n第二行")
assert s == "第一行 有空格\n第二行", f"换行/空白处理错误: {s!r}"
# 控制字符清除
s2 = _sanitize_text("abc\x00\x1b[31mred\x07def")
assert "\x00" not in s2 and "\x1b" not in s2 and "\x07" not in s2, "控制字符未清除"
# 超长截断
s3 = _sanitize_text("x" * 500)
assert s3.endswith("…") and len(s3) <= 111, "超长未截断"
# 非字符串输入
assert _sanitize_text(None) == "休息一下吧", "None 应回退默认文案"
# 空/纯空白回退
assert _sanitize_text("   \n  ") == "休息一下吧", "空白文案应回退默认"
print("sanitize PASS")

# ---------- 2.6 单实例降级逻辑 ----------
print("== single-instance fallback ==")
import socket as _socket  # noqa: E402

# 直接测试 main 模块逻辑（占住主端口模拟"其他程序"）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "src"))
import main as main_mod  # noqa: E402

# 场景 A：端口被"其他程序"占用（只 listen，不响应握手）
fake = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
fake.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
fake.bind(("127.0.0.1", main_mod.SINGLE_INSTANCE_PORT))
fake.listen(1)
# 绑定应失败
assert not main_mod._acquire_single_instance(main_mod.SINGLE_INSTANCE_PORT), \
    "端口被占时绑定不应成功"
# 握手探测应识别为"非本应用实例"（无正确响应）
assert not main_mod._is_real_instance(main_mod.SINGLE_INSTANCE_PORT), \
    "假占用应被识别为非真实实例"
# 降级端口应可用，且握手成功
assert main_mod._acquire_single_instance(main_mod.BACKUP_INSTANCE_PORT), \
    "备选端口应可绑定"
assert main_mod._is_real_instance(main_mod.BACKUP_INSTANCE_PORT), \
    "备选端口握手探测应成功"
# 场景 B：恶意连接（不发送握手字节）不应杀死监听线程
bad = _socket.create_connection(("127.0.0.1", main_mod.BACKUP_INSTANCE_PORT), 1)
bad.close()  # 连接后立即关闭，不发握手
time.sleep(0.3)
assert main_mod._is_real_instance(main_mod.BACKUP_INSTANCE_PORT), \
    "监听线程应存活（恶意空连接不应杀死它）"
# 场景 C：正常握手应触发 open_settings 事件
with _socket.create_connection(("127.0.0.1", main_mod.BACKUP_INSTANCE_PORT), 1) as c:
    c.settimeout(1)
    c.sendall(main_mod._HANDSHAKE_REQ)
    resp = c.recv(2)
    assert resp.startswith(main_mod._HANDSHAKE_RESP), "握手响应缺失"
# 清理
main_mod._lock_socket.close()
main_mod._lock_socket = None
fake.close()
print("single-instance fallback + handshake PASS")

# ---------- 3. GUI 主程序 ----------
print("== GUI main ==")
src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "main.py")
proc = subprocess.Popen([sys.executable, src],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, encoding="utf-8", errors="replace")
time.sleep(4)
if proc.poll() is not None:
    out, err = proc.communicate()
    print("!! 程序提前退出，stderr:\n", err)
    sys.exit(1)
print("process alive PASS")
proc.terminate()
try:
    proc.wait(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()
out, err = proc.communicate()
if err.strip():
    print("!! stderr 有输出:\n", err)
else:
    print("no stderr PASS")
print("ALL SMOKE TESTS PASS")
