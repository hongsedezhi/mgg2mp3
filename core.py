# -*- coding: utf-8 -*-
"""MGG/加密音频 -> MP3 核心流程（供 GUI 调用，不依赖 Qt）。

流程：
  1. qmc_decrypt 解析尾部 footer 并解密（无内嵌密钥时走 Frida 借壳，让 QQ 音乐客户端自己解密）
  2. soundfile 解码 FLAC/OGG，lameenc 编码 MP3
  3. 写入 ID3v2.3 标签（标题 / 歌手）
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import qmc_decrypt  # noqa: E402

SUPPORTED_EXT = {
    ".mgg", ".mgg0", ".mgg1", ".mggl",
    ".mflac", ".mflac0",
    ".qmc0", ".qmc2", ".qmc3", ".qmc4", ".qmc6", ".qmc8",
    ".qmcflac", ".qmcogg",
}


# ---------------------------------------------------------------- 配置
def _user_music_dir() -> Path:
    r"""跨平台猜一个"音乐"目录（Windows 是 <用户>\Music，其它用 ~/Music）。"""
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    return home / "Music"


DEFAULT_OUT_DIR = str(_user_music_dir() / "mgg2mp3")

CONFIG_DIR = Path(os.environ.get("APPDATA") or (Path.home() / ".config")) / "mgg2mp3"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict:
    """读取上次的设置（输出目录、码率）。读不到就返回空字典。"""
    try:
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    except Exception:
        return {}


def save_config(**kw) -> None:
    """把设置写回配置文件，失败静默（不影响主流程）。"""
    data = load_config()
    data.update(kw)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------- 环境检查
def qqmusic_running() -> bool:
    """QQMusic.exe 是否在运行（Frida 借壳的必要条件）。"""
    try:
        import frida

        dev = frida.get_local_device()
        return any("qqmusic" in p.name.lower() for p in dev.enumerate_processes())
    except Exception:
        return False


def frida_available() -> bool:
    try:
        import frida  # noqa: F401

        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 小工具
def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


def clean_stem(stem: str) -> str:
    """去掉 QQ 音乐加的 _H / _L / _H_ 之类音质后缀。"""
    return re.sub(r"_[A-Za-z]$", "", stem).strip() or stem


def split_title(stem: str) -> tuple[str, str]:
    """从 "歌手 - 歌名" 里拆出歌手和标题。"""
    base = clean_stem(stem)
    if " - " in base:
        artist, title = base.split(" - ", 1)
        return title.strip(), artist.strip()
    return base, ""


def build_id3v23(title: str, artist: str, album: str = "") -> bytes:
    def frame(fid: str, text: str) -> bytes:
        body = b"\x01" + b"\xff\xfe" + text.encode("utf-16-le")  # 带 BOM 的 UTF-16LE
        return fid.encode("ascii") + len(body).to_bytes(4, "big") + b"\x00\x00" + body

    frames = b""
    if title:
        frames += frame("TIT2", title)
    if artist:
        frames += frame("TPE1", artist)
    if album:
        frames += frame("TALB", album)
    size = len(frames)
    ss = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F,
                (size >> 7) & 0x7F, size & 0x7F])
    return b"ID3\x03\x00\x00" + ss + frames


def pick_bitrate(source_bps: float) -> int:
    """按源码率挑 MP3 码率：有损转有损，超过源码率没意义。"""
    if source_bps >= 150_000:
        return 320
    if source_bps >= 100_000:
        return 192
    return 128


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    n = 1
    while True:
        cand = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not cand.exists():
            return cand
        n += 1


# ---------------------------------------------------------------- 主流程
def convert_file(src: str, out_dir: str = DEFAULT_OUT_DIR, bitrate: int = 0,
                 log=None, progress=None, cancel: threading.Event | None = None) -> dict:
    """转换单个文件。

    bitrate: 0=自动（按源码率），其它为 128/192/320。
    返回 dict(path, bitrate, source_bps, ext, size)。
    """
    import lameenc
    import soundfile as sf

    log = log or (lambda *_: None)
    src_path = Path(src)
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)

    def report(pct: float):
        if progress:
            progress(max(0, min(100, int(pct))))

    tmpdir = tempfile.mkdtemp(prefix="mgg2mp3_")
    try:
        report(2)
        log(f"解密：{src_path.name}")

        def dec_progress(done, total):
            report(2 + 60 * (done / total if total else 0))

        decrypted, ext, dlog = qmc_decrypt.decrypt_file_streaming(
            str(src_path), tmpdir,
            progress_cb=dec_progress,
            cancel=cancel,
            frida_fallback=True,
        )
        for line in dlog:
            log("  " + line)
        if cancel is not None and cancel.is_set():
            raise qmc_decrypt.DecryptError("已取消")

        decrypted = Path(decrypted)
        report(64)

        # 解密结果本身就是 MP3 的话不用转码
        if ext.lower() == "mp3":
            title, artist = split_title(src_path.stem)
            target = _unique_path(out_dir_p / f"{clean_stem(src_path.stem)}.mp3")
            shutil.copyfile(decrypted, target)
            report(100)
            return {"path": str(target), "bitrate": 0, "source_bps": 0,
                    "ext": "mp3", "size": target.stat().st_size}

        info = sf.info(str(decrypted))
        duration = info.frames / info.samplerate
        source_bps = decrypted.stat().st_size * 8 / duration if duration else 0
        target_bps = bitrate or pick_bitrate(source_bps)
        log(f"  源：{info.samplerate}Hz {info.channels}ch  {duration/60:.2f} 分钟  "
            f"约 {source_bps/1000:.0f} kbps  →  MP3 {target_bps} kbps")

        title, artist = split_title(src_path.stem)
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(target_bps)
        encoder.set_in_sample_rate(info.samplerate)
        encoder.set_channels(info.channels)
        encoder.set_quality(2)

        target = _unique_path(out_dir_p / f"{clean_stem(src_path.stem)}.mp3")
        block = 1_048_576
        with sf.SoundFile(str(decrypted)) as handle, open(target, "wb") as fh:
            fh.write(build_id3v23(title, artist))
            done = 0
            while True:
                if cancel is not None and cancel.is_set():
                    raise qmc_decrypt.DecryptError("已取消")
                pcm = handle.read(block, dtype="int16", always_2d=True)
                if pcm.shape[0] == 0:
                    break
                fh.write(encoder.encode(pcm.tobytes()))
                done += pcm.shape[0]
                report(64 + 35 * (done / info.frames if info.frames else 0))
            fh.write(encoder.flush())

        report(100)
        return {"path": str(target), "bitrate": target_bps, "source_bps": source_bps,
                "ext": ext, "size": target.stat().st_size}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def collect_files(paths) -> list[str]:
    """接受文件/目录混合列表，展开目录并过滤受支持后缀。"""
    found: list[str] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXT:
                    found.append(str(f))
        elif path.is_file() and path.suffix.lower() in SUPPORTED_EXT:
            found.append(str(path))
    # 去重且保序
    seen, uniq = set(), []
    for f in found:
        k = os.path.normcase(os.path.abspath(f))
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq
