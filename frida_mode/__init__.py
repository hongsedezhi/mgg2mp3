# -*- coding: utf-8 -*-
"""Frida 借壳解密引擎（可选依赖：pip install frida）。

原理：不获取密钥，而是用 Frida 注入 QQMusic.exe 进程，调用其内置解密引擎
      （QQMusicCommon.dll 的 EncAndDesMediaFile 类）把 .mflac/.mgg 明文读出，
      让客户端自己完成"取钥 + 解密"。

想法来源（务必保留署名）：
  - 原始版：yllhwa/decrypt-mflac-frida   https://github.com/yllhwa/decrypt-mflac-frida
  - 简化版：ericjuice/music-decryptor    https://github.com/ericjuice/music-decryptor

本引擎为独立重写，改进见 hook_qq_music.js 头部注释（精确签名匹配、惰性初始化、
Frida 17 兼容）。引擎在进程内 attach 一次、多文件复用。

仅用于解密自己合法下载、有权使用的音频文件。
"""

import os
import subprocess
import sys
import threading

_lock = threading.Lock()
_state = None  # (session, script) —— attach 一次，多文件复用


def available():
    """frida 是否已安装（可选依赖）。"""
    try:
        import frida  # noqa: F401
        return True
    except ImportError:
        return False


def client_running():
    """QQMusic.exe 进程是否在运行（仅 Windows）。探测失败时放行，让 attach 报真实错误。

    注意：不用 tasklist —— 中文 Windows 下其输出是 GBK，
    subprocess(text=True) 会按 UTF-8 解码而抛 UnicodeDecodeError（线程里刷屏）。
    这里直接用 Frida 的进程枚举，跨locale安全。
    """
    try:
        import frida
        dev = frida.get_local_device()
        return any('qqmusic' in p.name.lower() for p in dev.enumerate_processes())
    except Exception:
        return True


def _hook_path():
    # 源码布局：frida_mode/hook_qq_music.js；PyInstaller 打包后：_MEIPASS/frida_mode/
    here = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(here, 'hook_qq_music.js')
    if os.path.exists(p):
        return p
    meipass = getattr(sys, '_MEIPASS', '')
    p = os.path.join(meipass, 'frida_mode', 'hook_qq_music.js')
    if os.path.exists(p):
        return p
    raise RuntimeError('找不到 hook_qq_music.js（打包缺失或目录不完整）')


def _get_engine():
    global _state
    with _lock:
        if _state is None:
            import frida
            hook_path = _hook_path()
            session = frida.attach('QQMusic.exe')
            script = session.create_script(open(hook_path, encoding='utf-8').read())
            script.load()
            _state = (session, script)
        return _state


def decrypt_file(src, dst):
    """借壳解密单个文件：src（.mflac/.mgg）-> dst（明文）。

    路径会转为绝对路径再传给进程内脚本（进程内 CWD 不可靠）。
    """
    _, script = _get_engine()
    tmp = dst + '.frida_tmp'
    try:
        script.exports_sync.decrypt(os.path.abspath(src), os.path.abspath(tmp))
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def close():
    """释放注入会话（进程退出前可选调用）。"""
    global _state
    with _lock:
        if _state is not None:
            session, _ = _state
            try:
                session.detach()
            except Exception:
                pass
            _state = None
