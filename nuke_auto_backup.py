import nuke
import os
import json
import time
import locale
import glob
import shutil
import threading
from PySide6 import QtWidgets, QtCore

# ==============================================
# 自定义署名 & 版本号
AUTHOR = "Michael_Pu"
VERSION = "1.0"
# ==============================================

BACKUP_SUFFIX = "_backup"
GLOBAL_TIMER = None
RUN_FLAG = False
REFRESH_INTERVAL = 1
next_backup_time = 0
backup_interval_sec = 0
max_backup_num = 10
AUTO_START_INTERVAL_MIN = 20

panel_instance = None
SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".nuke", "autobackup_settings.json")
CUR_LANG = "en"

# ---------------------- 双语语言包（已嵌入署名/版本占位符） ----------------------
I18N = {
    "en": {
        "title": "Auto Backup - Project Folder",
        "interval_label": "Backup Interval (min):",
        "max_label": "Max Backups Keep:",
        "status_idle": "Status: Stopped",
        "next": "Next backup: {m:02d}min {s:02d}sec",
        "info": "Backup folder: {proj}_autobackup\nOriginal file NOT modified.\nAuthor: {author} | Version: {ver}",
        "start_btn": "Start Backup",
        "stop_btn": "Stop Backup",
        "switch_btn": "Switch to 中文",
        "err_num": "Please enter valid numbers!",
        "err_gt0": "Value must be greater than 0!",
        "started": "AutoBackup Started\nInterval: {min} min\nFolder: {folder}",
        "stopped": "AutoBackup Stopped",
        "running": "Already running!"
    },
    "cn": {
        "title": "自动备份 - 工程名文件夹",
        "interval_label": "备份间隔(分钟):",
        "max_label": "最大保留份数:",
        "status_idle": "状态：已停止",
        "next": "下次备份：{m:02d}分 {s:02d}秒",
        "info": "备份目录：{proj}_autobackup\n原文件不会被修改\n作者: {author} | 版本: {ver}",
        "start_btn": "启动备份",
        "stop_btn": "停止备份",
        "switch_btn": "Switch to English",
        "err_num": "请输入有效数字！",
        "err_gt0": "数值必须大于0！",
        "started": "自动备份已启动\n间隔：{min} 分钟\n目录：{folder}",
        "stopped": "自动备份已停止",
        "running": "备份已在运行！"
    }
}

# ---------------------- 语言逻辑 ----------------------
def detect_system_language():
    try:
        sys_lang = locale.getdefaultlocale()[0]
        return "cn" if (sys_lang and sys_lang.startswith("zh")) else "en"
    except:
        return "en"

def load_language():
    global CUR_LANG
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r', encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("lang") in ("en", "cn"):
                    CUR_LANG = cfg["lang"]
                    return
        except:
            pass
    CUR_LANG = detect_system_language()

def save_language(lang):
    global CUR_LANG
    CUR_LANG = lang
    try:
        with open(SETTINGS_PATH, 'w', encoding="utf-8") as f:
            json.dump({"lang": lang}, f, ensure_ascii=False, indent=2)
    except:
        pass

load_language()

# ---------------------- 工程名 / 备份逻辑 ----------------------
def get_project_name():
    current_script = nuke.root().name()
    return "untitled" if current_script == "" else os.path.splitext(os.path.basename(current_script))[0]

def save_backup_file(max_count):
    current_script = nuke.root().name()
    if current_script == "" or not current_script.endswith(".nk"):
        print("[AutoBackup] Project not saved. Skip.")
        return

    dir_path = os.path.dirname(current_script)
    project_name = get_project_name()
    backup_dir = os.path.join(dir_path, f"{project_name}_autobackup")
    os.makedirs(backup_dir, exist_ok=True)

    name_no_ext, ext = os.path.splitext(os.path.basename(current_script))
    backup_pattern = os.path.join(backup_dir, f"{name_no_ext}{BACKUP_SUFFIX}*{ext}")
    backup_files = sorted(glob.glob(backup_pattern), key=lambda x: os.path.getmtime(x))

    while len(backup_files) >= max_count:
        try:
            os.remove(backup_files.pop(0))
        except:
            pass

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    new_backup_path = os.path.join(backup_dir, f"{name_no_ext}{BACKUP_SUFFIX}_{timestamp}{ext}")
    try:
        nuke.scriptSave()
        shutil.copy2(current_script, new_backup_path)
        print(f"[AutoBackup] Saved: {os.path.basename(new_backup_path)}")
    except:
        pass

def auto_backup_loop(interval_sec, max_count):
    global RUN_FLAG, next_backup_time
    while True:
        if not RUN_FLAG:
            time.sleep(1)
            continue
        if time.time() >= next_backup_time:
            save_backup_file(max_count)
            next_backup_time = time.time() + interval_sec
        time.sleep(REFRESH_INTERVAL)

# ---------------------- 主面板 ----------------------
class AutoBackupPanel(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.build_ui()
        self.retranslate_ui()

    def build_ui(self):
        self.setFixedSize(420, 300)
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(14)

        # 第1行：间隔
        self.h1 = QtWidgets.QHBoxLayout()
        self.interval_label = QtWidgets.QLabel()
        self.interval_edit = QtWidgets.QLineEdit("20")
        self.h1.addWidget(self.interval_label)
        self.h1.addWidget(self.interval_edit)
        self.main_layout.addLayout(self.h1)

        # 第2行：最大份数
        self.h2 = QtWidgets.QHBoxLayout()
        self.max_label = QtWidgets.QLabel()
        self.max_edit = QtWidgets.QLineEdit("10")
        self.h2.addWidget(self.max_label)
        self.h2.addWidget(self.max_edit)
        self.main_layout.addLayout(self.h2)

        # 状态/倒计时
        self.time_label = QtWidgets.QLabel()
        self.main_layout.addWidget(self.time_label)

        # 说明文本（嵌入署名+版本）
        self.info_label = QtWidgets.QLabel()
        self.info_label.setStyleSheet("font-size:11px; color:#666;")
        self.main_layout.addWidget(self.info_label)

        # 按钮行
        self.btn_layout = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton()
        self.btn_stop = QtWidgets.QPushButton()
        self.btn_lang = QtWidgets.QPushButton()
        self.btn_layout.addWidget(self.btn_start)
        self.btn_layout.addWidget(self.btn_stop)
        self.btn_layout.addWidget(self.btn_lang)
        self.main_layout.addLayout(self.btn_layout)

        # 定时器
        self.ui_timer = QtCore.QTimer(self)
        self.ui_timer.timeout.connect(self.update_countdown)
        self.ui_timer.start(1000)

        # 绑定事件
        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_lang.clicked.connect(self.switch_language)

        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)

    def retranslate_ui(self):
        """统一刷新所有界面文字"""
        txt = I18N[CUR_LANG]
        self.setWindowTitle(txt["title"])
        self.interval_label.setText(txt["interval_label"])
        self.max_label.setText(txt["max_label"])
        self.time_label.setText(txt["status_idle"])
        self.info_label.setText(
            txt["info"].format(
                proj=get_project_name(),
                author=AUTHOR,
                ver=VERSION
            )
        )
        self.btn_start.setText(txt["start_btn"])
        self.btn_stop.setText(txt["stop_btn"])
        self.btn_lang.setText(txt["switch_btn"])

    def switch_language(self):
        new_lang = "cn" if CUR_LANG == "en" else "en"
        save_language(new_lang)
        self.retranslate_ui()

    def update_countdown(self):
        txt = I18N[CUR_LANG]
        if not RUN_FLAG:
            self.time_label.setText(txt["status_idle"])
            return
        remain = max(0, int(next_backup_time - time.time()))
        self.time_label.setText(txt["next"].format(m=remain//60, s=remain%60))

    def on_start(self):
        txt = I18N[CUR_LANG]
        global RUN_FLAG, backup_interval_sec, max_backup_num, next_backup_time, GLOBAL_TIMER
        try:
            interval_min = float(self.interval_edit.text().strip())
            max_num = int(self.max_edit.text().strip())
            if interval_min <= 0 or max_num <= 0:
                nuke.message(txt["err_gt0"])
                return
        except:
            nuke.message(txt["err_num"])
            return

        if RUN_FLAG:
            nuke.message(txt["running"])
            return

        backup_interval_sec = interval_min * 60
        max_backup_num = max_num
        next_backup_time = time.time() + backup_interval_sec
        RUN_FLAG = True

        if GLOBAL_TIMER is None or not GLOBAL_TIMER.is_alive():
            GLOBAL_TIMER = threading.Thread(
                target=auto_backup_loop,
                args=(backup_interval_sec, max_num),
                daemon=True
            )
            GLOBAL_TIMER.start()

        nuke.message(txt["started"].format(min=interval_min, folder=f"{get_project_name()}_autobackup"))

    def on_stop(self):
        global RUN_FLAG
        RUN_FLAG = False
        nuke.message(I18N[CUR_LANG]["stopped"])

# ---------------------- 工程保存自动启动 ----------------------
def auto_start_callback():
    global RUN_FLAG, backup_interval_sec, max_backup_num, next_backup_time, GLOBAL_TIMER
    if RUN_FLAG or nuke.root().name() == "":
        return
    backup_interval_sec = AUTO_START_INTERVAL_MIN * 60
    max_backup_num = 10
    next_backup_time = time.time() + backup_interval_sec
    RUN_FLAG = True
    if GLOBAL_TIMER is None or not GLOBAL_TIMER.is_alive():
        GLOBAL_TIMER = threading.Thread(target=auto_backup_loop, args=(backup_interval_sec, max_backup_num), daemon=True)
        GLOBAL_TIMER.start()

nuke.addOnScriptSave(auto_start_callback)

# ---------------------- 菜单入口 ----------------------
def show_panel():
    global panel_instance
    if panel_instance is None:
        panel_instance = AutoBackupPanel()
    panel_instance.show()
    panel_instance.raise_()

nuke.menu("Nuke").addCommand("Scripts/Auto Backup", show_panel)