#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Frida 借壳解密模式（命令行版，Windows + QQ 音乐客户端运行中）

原理：不获取密钥，而是用 Frida 注入 QQMusic.exe 进程，调用其内置解密引擎
      （QQMusicCommon.dll 的 EncAndDesMediaFile 类）把 .mflac/.mgg 明文读出。
      相当于让 QQ 音乐客户端亲手替你解密——绕开"PC 端密钥不进磁盘"的限制。

想法来源（务必保留署名）：
  - 原始版：yllhwa/decrypt-mflac-frida   https://github.com/yllhwa/decrypt-mflac-frida
  - 简化版：ericjuice/music-decryptor    https://github.com/ericjuice/music-decryptor

依赖（仅此模式需要）：pip install frida
限制：
  - 仅 Windows 10/11（依赖 QQMusic.exe 进程）
  - 需先启动 QQ 音乐客户端并登录（无需播放）
  - 客户端更新加密算法后可能失效（hook 脚本会报缺方法，等待适配）

用法：
  python frida_mode/decrypt_frida.py -i <输入目录> -o <输出目录>

主程序已集成：python qmc_decrypt.py --frida-fallback <文件/目录> 也可自动走本引擎。

仅用于解密自己合法下载、有权使用的音频文件。
"""
import argparse
import logging
import os
import sys

# 使 `python frida_mode/decrypt_frida.py` 也能 import 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frida_mode import available, client_running, decrypt_file  # noqa: E402

SUPPORTED_EXT = {'.mflac': '.flac', '.mgg': '.ogg'}  # 解密后按实际音频类型重命名


def run_decrypt(input_dir, output_dir):
    if not available():
        sys.exit('[!] 需要可选依赖 frida：pip install frida')
    if not client_running():
        sys.exit('[!] 未找到 QQMusic.exe 进程——请先启动 QQ 音乐客户端并登录，再运行本工具')

    logging.info('hook 已就绪，开始批量解密 ...')
    os.makedirs(output_dir, exist_ok=True)

    ok = fail = skip = 0
    for root, _dirs, files in os.walk(input_dir):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in SUPPORTED_EXT:
                continue
            src = os.path.join(root, name)
            out_path = os.path.join(output_dir, os.path.splitext(name)[0] + SUPPORTED_EXT[ext])
            if os.path.exists(out_path):
                logging.info('已存在，跳过: %s', out_path)
                skip += 1
                continue
            try:
                decrypt_file(src, out_path)
                ok += 1
                logging.info('解密成功: %s', out_path)
            except Exception as e:
                fail += 1
                logging.error('解密失败 %s: %s', name, e)

    logging.info('完成：成功 %d，跳过 %d，失败 %d', ok, skip, fail)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    ap = argparse.ArgumentParser(description='Frida 借壳解密（QQ 音乐客户端须运行）')
    ap.add_argument('-i', '--input', required=True, help='输入目录（含 .mflac/.mgg）')
    ap.add_argument('-o', '--output', default='output', help='输出目录')
    args = ap.parse_args()
    run_decrypt(args.input, args.output)
