/*
 * hook_qq_music.js — QQ音乐 .mflac/.mgg 借壳解密（Frida 注入脚本）
 *
 * 原理：不获取密钥，而是调用 QQMusic.exe 进程内自带的解密引擎
 *       （QQMusicCommon.dll 的 C++ 类 EncAndDesMediaFile），
 *       让客户端自己完成"取钥 + 解密"，把明文音频数据读出写盘。
 *
 * 想法来源（务必保留署名）：
 *   - 原始版：yllhwa/decrypt-mflac-frida   https://github.com/yllhwa/decrypt-mflac-frida
 *   - 简化版：ericjuice/music-decryptor    https://github.com/ericjuice/music-decryptor
 * 本脚本为独立重写，主要改进：
 *   1) 按精确签名匹配实例方法（区分重载与静态版，避免拿错函数产生坏数据）；
 *   2) 惰性初始化（Frida 17 中顶层 Module 调用会吞掉 rpc.exports 注册，
 *      故枚举/NativeFunction 全部推迟到首次 decrypt 调用时执行）。
 *
 * 用法：由 decrypt_frida.py 注入，调用 rpc.exports.decrypt(src, tmp)。
 * 仅用于解密自己合法下载、有权使用的音频文件。
 */
"use strict";

const TARGET_DLL = "QQMusicCommon.dll";

// 兼容 Frida ≤16（Module.enumerateExports）与 Frida 17+（Process.getModuleByName）
function listExports(dll) {
  if (typeof Module.enumerateExports === "function") {
    return Module.enumerateExports(dll);
  }
  const mod = Process.getModuleByName(dll);
  return mod.enumerateExports();
}

// 在导出表中按精确签名解析 EncAndDesMediaFile 的实例方法。
// 必须区分：实例(QAE=thiscall) vs 静态(SA)；默认构造 vs 拷贝构造；
// Open 有 (wchar*,bool,bool) 与 (wchar*,K,K,K) 两个重载，只认前者。
// 匹配不到时抛"缺方法"，避免拿错重载静默产出坏数据。
function resolveEncDecFile(dll) {
  const out = { ctor: null, dtor: null, open: null, getSize: null, read: null };
  let exports;
  try {
    exports = listExports(dll);
  } catch (e) {
    throw new Error("无法枚举 " + dll + " 的导出表: " + e);
  }
  for (const e of exports) {
    const n = e.name;
    if (n.indexOf("EncAndDesMediaFile") === -1) continue;
    if (n.startsWith("??0EncAndDesMediaFile") && n.endsWith("@@QAE@XZ")) out.ctor = e.address;
    else if (n.startsWith("??1EncAndDesMediaFile") && n.endsWith("@@QAE@XZ")) out.dtor = e.address;
    else if (n.indexOf("?Open@EncAndDesMediaFile@@QAE_NPB_W_N1@Z") !== -1) out.open = e.address;
    else if (n.indexOf("?GetSize@EncAndDesMediaFile@@QAEKXZ") !== -1) out.getSize = e.address;
    else if (n.indexOf("?Read@EncAndDesMediaFile@@QAEKPAEK_J@Z") !== -1) out.read = e.address;
  }
  if (!out.ctor || !out.dtor || !out.open || !out.getSize || !out.read) {
    throw new Error(
      "未能在 " + dll + " 中找到 EncAndDesMediaFile 全部方法——客户端版本可能已更新，" +
      "请升级本工具或等待适配（QQ 更新算法会导致此类符号变动）"
    );
  }
  return out;
}

// 惰性初始化：Frida 17 中在脚本顶层调用 Module API 会吞掉 rpc.exports 注册，
// 因此枚举与 NativeFunction 创建全部推迟到首次 decrypt 调用时执行。
var _engine = null;

function getEngine() {
  if (_engine !== null) {
    return _engine;
  }
  const f = resolveEncDecFile(TARGET_DLL);
  _engine = {
    Ctor: new NativeFunction(f.ctor, "pointer", ["pointer"], "thiscall"),
    Dtor: new NativeFunction(f.dtor, "void", ["pointer"], "thiscall"),
    Open: new NativeFunction(f.open, "bool", ["pointer", "pointer", "bool", "bool"], "thiscall"),
    GetSize: new NativeFunction(f.getSize, "uint32", ["pointer"], "thiscall"),
    Read: new NativeFunction(f.read, "uint", ["pointer", "pointer", "uint32", "uint64"], "thiscall"),
  };
  return _engine;
}

rpc.exports = {
  decrypt: function (srcFileName, tmpFileName) {
    const eng = getEngine();

    // 对象大小 0x28：与原始方案一致，足以容纳该类的解密上下文
    const obj = Memory.alloc(0x28);
    eng.Ctor(obj);

    const nameUtf16 = Memory.allocUtf16String(srcFileName);
    if (!eng.Open(obj, nameUtf16, 1, 0)) {
      eng.Dtor(obj);
      throw new Error("EncAndDesMediaFile::Open 失败: " + srcFileName);
    }

    const size = eng.GetSize(obj);
    const buf = Memory.alloc(size);
    eng.Read(obj, buf, size, 0);
    const data = buf.readByteArray(size);

    eng.Dtor(obj);

    const tmp = new File(tmpFileName, "wb");
    tmp.write(data);
    tmp.close();
  },
};
