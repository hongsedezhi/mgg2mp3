# -*- coding: utf-8 -*-
"""MGG → MP3：QQ 音乐加密音频转 MP3 的小工具（PySide6 界面）。"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

import core

HERE = Path(__file__).resolve().parent

QSS = """
* { font-family: "Microsoft YaHei UI", "Segoe UI"; }
QWidget#root { background: #f5f6f8; }
QLabel { color: #1d2129; }
QLabel#title { font-size: 19px; font-weight: 600; color: #1d2129; }
QLabel#sub { font-size: 12px; color: #86909c; }
QLabel#badgeOk { font-size: 12px; color: #0f7b4f; background: #e8f7ef;
                border: 1px solid #b7e4cd; border-radius: 10px; padding: 3px 10px; }
QLabel#badgeBad { font-size: 12px; color: #b54708; background: #fff5e6;
                 border: 1px solid #f7dba7; border-radius: 10px; padding: 3px 10px; }
QFrame#drop { background: #ffffff; border: 2px dashed #c9cdd4; border-radius: 10px; }
QFrame#drop[drag="true"] { background: #eef4ff; border: 2px dashed #3370ff; }
QLabel#dropText { font-size: 14px; color: #4e5969; }
QLabel#dropHint { font-size: 12px; color: #a9aeb8; }
QTableWidget { background: #ffffff; border: 1px solid #e5e6eb; border-radius: 8px;
               gridline-color: #f2f3f5; }
QHeaderView::section { background: #fafbfc; border: none; border-bottom: 1px solid #e5e6eb;
                       padding: 7px 8px; color: #4e5969; font-weight: 600; }
QTableWidget::item { padding: 4px 6px; }
QPushButton { border-radius: 7px; padding: 8px 18px; font-size: 13px;
              border: 1px solid #d9dbe0; background: #ffffff; color: #1d2129; }
QPushButton:hover { border-color: #3370ff; color: #3370ff; }
QPushButton:disabled { color: #c9cdd4; border-color: #e5e6eb; }
QPushButton#primary { background: #3370ff; color: #ffffff; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #4e83fd; }
QPushButton#primary:disabled { background: #b8ccff; }
QComboBox { border: 1px solid #d9dbe0; border-radius: 7px; padding: 6px 10px;
            background: #ffffff; min-width: 110px; color: #1d2129; }
QComboBox QAbstractItemView { background: #ffffff; color: #1d2129;
                              selection-background-color: #eef4ff;
                              selection-color: #1d2129; outline: none; }
QLineEdit { background: #ffffff; border: 1px solid #d9dbe0; border-radius: 7px;
            padding: 7px 10px; color: #4e5969; font-size: 12px; }
QProgressBar { border: none; border-radius: 5px; background: #e5e6eb; height: 10px;
               text-align: center; font-size: 11px; color: #4e5969; }
QProgressBar::chunk { background: #3370ff; border-radius: 5px; }
QTextEdit { background: #ffffff; border: 1px solid #e5e6eb; border-radius: 8px;
            font-family: Consolas, "Microsoft YaHei UI"; font-size: 12px; color: #4e5969; }
"""


class DropZone(QFrame):
    """拖拽区：接受文件与文件夹。"""
    dropped = Signal(list)
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setMinimumHeight(112)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        icon = QLabel("♫")
        icon.setStyleSheet("font-size: 30px; color: #3370ff;")
        icon.setAlignment(Qt.AlignCenter)
        text = QLabel("把 .mgg / .mflac 文件拖到这里")
        text.setObjectName("dropText")
        text.setAlignment(Qt.AlignCenter)
        hint = QLabel("也可以拖整个文件夹，或点这里选择文件 · 支持多选")
        hint.setObjectName("dropHint")
        hint.setAlignment(Qt.AlignCenter)
        for w in (icon, text, hint):
            lay.addWidget(w)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.setProperty("drag", "true")
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, e):
        self.setProperty("drag", "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, e):
        self.setProperty("drag", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)
            e.acceptProposedAction()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


class Worker(QThread):
    log = Signal(str)
    row_status = Signal(int, str)
    progress = Signal(int)
    finished_all = Signal(int, int)

    def __init__(self, files, out_dir, bitrate, cancel, parent=None):
        super().__init__(parent)
        self.files = files
        self.out_dir = out_dir
        self.bitrate = bitrate
        self.cancel = cancel

    def run(self):
        ok = fail = 0
        for idx, f in enumerate(self.files):
            if self.cancel.is_set():
                self.row_status.emit(idx, "已取消")
                continue
            self.row_status.emit(idx, "转换中…")
            try:
                res = core.convert_file(
                    f, self.out_dir, self.bitrate,
                    log=lambda m: self.log.emit(m),
                    progress=self.progress.emit,
                    cancel=self.cancel,
                )
                got = res["bitrate"] or "-"
                self.row_status.emit(
                    idx, f"完成 · {got} kbps · {core._human(res['size'])}")
                ok += 1
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).splitlines()[0][:120] if str(exc) else exc.__class__.__name__
                self.log.emit(f"[失败] {Path(f).name}：{msg}")
                self.row_status.emit(idx, f"失败：{msg}")
                fail += 1
        self.progress.emit(100)
        self.finished_all.emit(ok, fail)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("MGG → MP3 · QQ 音乐加密音频转换")
        self.resize(820, 700)
        self.setStyleSheet(QSS)
        self.files: list[str] = []
        self.worker: Worker | None = None
        self.cancel = threading.Event()
        self._build()
        self._refresh_env()

    # ------------------------------------------------------------ UI
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        box = QVBoxLayout()
        box.setSpacing(2)
        title = QLabel("MGG → MP3")
        title.setObjectName("title")
        sub = QLabel("解密 QQ 音乐会员歌曲并转成通用 MP3")
        sub.setObjectName("sub")
        box.addWidget(title)
        box.addWidget(sub)
        head.addLayout(box)
        head.addStretch(1)
        self.badge = QLabel("检测中…")
        self.badge.setObjectName("badgeBad")
        head.addWidget(self.badge)
        root.addLayout(head)

        self.drop = DropZone()
        self.drop.dropped.connect(self.add_paths)
        self.drop.clicked.connect(self.choose_files)
        root.addWidget(self.drop)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["文件", "大小", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 250)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        root.addWidget(self.table, 1)

        opts = QHBoxLayout()
        opts.setSpacing(8)
        opts.addWidget(QLabel("输出到"))
        self.cfg = core.load_config()
        self.out_edit = QLineEdit(self.cfg.get("out_dir") or core.DEFAULT_OUT_DIR)
        self.out_edit.setReadOnly(True)
        self.out_edit.setCursorPosition(0)
        self.out_edit.setMinimumWidth(80)
        opts.addWidget(self.out_edit, 1)
        btn_dir = QPushButton("更改")
        btn_dir.clicked.connect(self.choose_out_dir)
        opts.addWidget(btn_dir)
        opts.addSpacing(8)
        lbl_br = QLabel("码率")
        lbl_br.setStyleSheet("color:#4e5969;")
        opts.addWidget(lbl_br)
        self.bitrate_box = QComboBox()
        self.bitrate_box.addItems(["自动（推荐）", "128 kbps", "192 kbps", "320 kbps"])
        self.bitrate_box.setCurrentIndex(int(self.cfg.get("bitrate", 0) or 0))
        self.bitrate_box.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        opts.addWidget(self.bitrate_box)
        root.addLayout(opts)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        root.addWidget(self.bar)

        actions = QHBoxLayout()
        self.btn_start = QPushButton("开始转换")
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self.start)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.do_cancel)
        self.btn_cancel.setEnabled(False)
        self.btn_clear = QPushButton("清空列表")
        self.btn_clear.clicked.connect(self.clear_list)
        self.btn_open = QPushButton("打开输出目录")
        self.btn_open.clicked.connect(self.open_out_dir)
        for b in (self.btn_start, self.btn_cancel, self.btn_clear, self.btn_open):
            actions.addWidget(b)
        actions.addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("sub")
        actions.addWidget(self.status)
        root.addLayout(actions)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(120)
        root.addWidget(self.log_view)

    # ------------------------------------------------------------ 环境
    def _refresh_env(self):
        if not core.frida_available():
            self.badge.setText("缺少 frida")
            self.badge.setObjectName("badgeBad")
            self.badge.setStyleSheet("")
        elif core.qqmusic_running():
            self.badge.setText("QQ 音乐已运行 · 可以解密")
            self.badge.setObjectName("badgeOk")
        else:
            self.badge.setText("QQ 音乐未运行")
            self.badge.setObjectName("badgeBad")
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    # ------------------------------------------------------------ 文件
    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择加密音频", "",
            "QQ 音乐加密音频 (*.mgg *.mgg0 *.mgg1 *.mggl *.mflac *.mflac0 "
            "*.qmc0 *.qmc3 *.qmcflac *.qmcogg);;所有文件 (*.*)")
        if files:
            self.add_paths(files)

    def add_paths(self, paths):
        new = core.collect_files(paths)
        if not new:
            self.log_view.append("[提示] 没有找到受支持的加密音频文件")
            return
        existing = {os.path.normcase(f) for f in self.files}
        added = 0
        for f in new:
            if os.path.normcase(f) in existing:
                continue
            self.files.append(f)
            r = self.table.rowCount()
            self.table.insertRow(r)
            name = QTableWidgetItem(Path(f).name)
            name.setToolTip(f)
            size = QTableWidgetItem(core._human(os.path.getsize(f)))
            size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            state = QTableWidgetItem("待转换")
            state.setForeground(Qt.GlobalColor.gray)
            for c, it in enumerate((name, size, state)):
                self.table.setItem(r, c, it)
            added += 1
        self.log_view.append(f"已添加 {added} 个文件")
        self.table.clearSelection()
        self._sync_buttons()
        if added:
            self.btn_start.setFocus()

    def clear_list(self):
        if self.worker and self.worker.isRunning():
            return
        self.files.clear()
        self.table.setRowCount(0)
        self.bar.setValue(0)
        self.status.setText("")
        self._sync_buttons()

    def _sync_buttons(self):
        running = bool(self.worker and self.worker.isRunning())
        self.btn_start.setEnabled(bool(self.files) and not running)
        self.btn_clear.setEnabled(not running)
        self.btn_cancel.setEnabled(running)

    # ------------------------------------------------------------ 目录 / 码率
    def choose_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录",
                                             self.out_edit.text())
        if d:
            self.out_edit.setText(d)
            self.out_edit.setCursorPosition(0)
            core.save_config(out_dir=d)

    def open_out_dir(self):
        d = self.out_edit.text()
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    # ------------------------------------------------------------ 执行
    def start(self):
        if not self.files:
            return
        if not core.qqmusic_running():
            QMessageBox.warning(
                self, "QQ 音乐未运行",
                "新版 QQ 音乐下载的文件不带解密密钥，必须让客户端自己解密。\n\n"
                "请先打开 QQ 音乐并登录（能正常播放这首歌），再点开始转换。")
            self._refresh_env()
            return
        bitrate = {0: 0, 1: 128, 2: 192, 3: 320}[self.bitrate_box.currentIndex()]
        core.save_config(out_dir=self.out_edit.text(),
                         bitrate=self.bitrate_box.currentIndex())
        self.cancel.clear()
        for r in range(self.table.rowCount()):
            self.table.item(r, 2).setText("待转换")
            self.table.item(r, 2).setForeground(Qt.GlobalColor.gray)
        self.bar.setValue(0)
        self.status.setText("准备中…")
        self.log_view.append("—" * 34)

        self.worker = Worker(self.files, self.out_edit.text(), bitrate, self.cancel)
        self.worker.log.connect(self.log_view.append)
        self.worker.row_status.connect(self._set_row_status)
        self.worker.progress.connect(self.bar.setValue)
        self.worker.finished_all.connect(self._on_done)
        self.worker.start()
        self._sync_buttons()
        self.status.setText("转换中…")

    def _set_row_status(self, row, text):
        if row < self.table.rowCount():
            item = self.table.item(row, 2)
            item.setText(text)
            if text.startswith("失败"):
                item.setForeground(Qt.GlobalColor.darkRed)
            elif text.startswith("完成"):
                item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                item.setForeground(Qt.GlobalColor.gray)

    def do_cancel(self):
        self.cancel.set()
        self.status.setText("正在取消…")

    def _on_done(self, ok, fail):
        self.status.setText(f"完成：成功 {ok} 个，失败 {fail} 个")
        self.bar.setValue(100)
        self._sync_buttons()
        self._refresh_env()


def apply_theme(qapp: QApplication) -> None:
    """强制浅色调色板。

    系统开着深色模式时，Qt6 会把默认文字色变成白色；本界面是浅色底，
    不显式指定颜色的文字就会"白字白底"看不见。这里锁死一份浅色调色板。
    """
    try:
        QGuiApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except Exception:
        pass
    qapp.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#f5f6f8"))
    pal.setColor(QPalette.WindowText, QColor("#1d2129"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#fafbfc"))
    pal.setColor(QPalette.Text, QColor("#1d2129"))
    pal.setColor(QPalette.Button, QColor("#ffffff"))
    pal.setColor(QPalette.ButtonText, QColor("#1d2129"))
    pal.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipText, QColor("#1d2129"))
    pal.setColor(QPalette.Highlight, QColor("#3370ff"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, QColor("#a9aeb8"))
    qapp.setPalette(pal)
    qapp.setStyleSheet(QSS)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MGG → MP3")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    apply_theme(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
