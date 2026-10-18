# NOTICE — 第三方组件与来源说明

本项目**自有代码**（`app.py`、`core.py`、`frida_mode/*`、启动脚本、文档）以 MIT 协议发布，
见 [LICENSE](LICENSE)。

以下组件来自第三方，版权归各自作者所有，本仓库仅作整合与少量修改。

---

## 1. `qmc_decrypt.py`

- **来源**：[mzj3920/qqmusic-decrypt](https://github.com/mzj3920/qqmusic-decrypt)
- **算法参照**：[unlock-music](https://git.unlock-music.dev/um) 的 Rust 实现（`lib_um_crypto_rust`）
- **本仓库的改动**：未修改算法主体，仅作为模块被 `core.py` 调用
- **上游许可**：仓库未声明 LICENSE 文件。若你是上游作者并希望调整署名或许可方式，请开 issue 联系。

该文件负责 QMC v1 / v2 格式的解析、EKey 解码、RC4/Map 流密码解密，以及
「PC MusicEx 无内嵌密钥 → 交回调用方走 Frida 借壳」的分支判断。

## 2. `frida_mode/`

- **思路来源**：
  - [yllhwa/decrypt-mflac-frida](https://github.com/yllhwa/decrypt-mflac-frida) — 原始方案
  - [ericjuice/music-decryptor](https://github.com/ericjuice/music-decryptor) — 简化版参考
- **本仓库实现**：独立重写（`hook_qq_music.js` + `decrypt_frida.py` + `__init__.py`），主要改进：
  1. 按**精确 C++ 签名**匹配 `EncAndDesMediaFile` 的实例方法，区分重载 / 静态版 / 拷贝构造，
     匹配不到时报错而不是静默产出坏数据；
  2. **惰性初始化**——Frida 17 中在脚本顶层调用 `Module` API 会导致 `rpc.exports` 注册失败，
     故导出表枚举与 `NativeFunction` 创建全部推迟到首次调用；
  3. 引擎在进程内 **attach 一次、多文件复用**；
  4. 用 Frida 进程枚举替代 `tasklist`，避免中文 Windows 下 GBK 输出导致的解码异常。
- **上游许可**：上述仓库均未声明 LICENSE 文件。

## 3. Python 依赖

| 包 | 许可 |
|---|---|
| PySide6 (Qt for Python) | LGPL-3.0 |
| frida | wxWindows Library Licence |
| soundfile (libsndfile) | BSD-3-Clause（libsndfile 为 LGPL-2.1） |
| lameenc (LAME) | LGPL-2.0 |
| numpy | BSD-3-Clause |

---

## 商标声明

「QQ 音乐」「QQMusic」是腾讯公司的商标。本项目与腾讯公司**无任何关联**，
未获其授权或认可，仅为个人互操作性研究用途。
