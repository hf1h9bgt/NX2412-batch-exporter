"""
file: standalone.py
description: 免安装版入口 —— 独立运行图形界面，导出时自动调用本机 NX2412 后台转换
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.

说明：
- 源码调试：用系统 Python 运行 `python standalone.py` 即可（不需要 NX 正在运行）；
- 正式发布：由 build_standalone.py 用 PyInstaller 打包为免安装的「批量导出插件.exe」；
- 也支持命令行模式（测试/自动化用）：`批量导出插件.exe --cli <job.json>`。
"""
import json
import os
import sys


def _ensurePluginPath() -> str:
    """
    把插件源码目录加入 sys.path（源码运行时为当前目录，冻结运行时为解包目录）

    Returns:
        str: 插件源码根目录
    """
    if getattr(sys, 'frozen', False):
        baseDir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        baseDir = os.path.dirname(os.path.abspath(__file__))
    if baseDir not in sys.path:
        sys.path.insert(0, baseDir)
    # 免安装包中，NX 后台 worker 需要的后端源码放在 plugin_backend 子目录
    pluginBackend = os.path.join(baseDir, 'plugin_backend')
    if os.path.isdir(pluginBackend) and pluginBackend not in sys.path:
        sys.path.insert(0, pluginBackend)
    return baseDir


BASE_DIR = _ensurePluginPath()

import tkinter as tk  # noqa: E402
from tkinter import filedialog, messagebox  # noqa: E402

import application  # noqa: E402
from language import init_i18n  # noqa: E402
from remote_backend import RemoteBackend  # noqa: E402


def createBackend() -> RemoteBackend:
    """
    创建后端，必要时引导用户手动指定 NX 安装目录

    Returns:
        RemoteBackend: 后端实例
    """
    backend = RemoteBackend()
    if backend.isAvailable():
        return backend

    # 用一个临时隐藏窗口承载对话框，避免额外弹窗
    tempRoot = None
    try:
        tempRoot = tk.Tk()
        tempRoot.withdraw()
        answer = messagebox.askyesno(
            '未找到 NX 2412',
            '未能自动找到本机 NX 2412 安装目录。\n\n'
            '是否手动选择 NX 安装目录？\n'
            '（选择包含 NXBIN 文件夹的目录，例如 D:\\Program Files\\Siemens\\NX2412）',
            parent=tempRoot)
        if answer:
            folder = filedialog.askdirectory(
                title='选择 NX 2412 安装目录（包含 NXBIN 文件夹）', parent=tempRoot)
            if folder:
                if backend.setNxRoot(folder):
                    messagebox.showinfo('已找到 NX2412', 'NX 安装目录：\n' + backend.nxRoot, parent=tempRoot)
                else:
                    messagebox.showerror(
                        '目录无效',
                        '该目录下未找到 NXBIN\\run_journal.exe，请确认选择的是 NX 2412 安装目录。',
                        parent=tempRoot)
    except Exception:
        pass
    finally:
        if tempRoot is not None:
            try:
                tempRoot.destroy()
            except Exception:
                pass
    return backend


def runGui():
    """启动免安装版图形界面"""
    init_i18n()
    backend = createBackend()
    application.run(backend=backend)


def runCli(argv: list) -> int:
    """
    命令行模式：执行 job JSON 描述的导出任务（供自动化测试/高级用户使用）

    Args:
        argv (list): 命令行参数

    Returns:
        int: 退出码（0 成功；非 0 表示有失败或异常）
    """
    init_i18n()
    jobPath = ''
    logPath = ''
    resultPath = ''
    try:
        jobPath = argv[argv.index('--cli') + 1]
        # 兼容带 BOM 的 UTF-8（Windows PowerShell 5.1 的 Out-File/Set-Content 会写 BOM）
        with open(jobPath, 'r', encoding='utf-8-sig') as f:
            job = json.load(f)
        logPath = job.get('cliLogPath') or (jobPath + '.log')
        resultPath = job.get('resultPath') or (jobPath + '.result.json')

        def writeMsg(msg, level: str = 'info'):
            try:
                with open(logPath, 'a', encoding='utf-8') as f:
                    f.write('[{0}] {1}\n'.format(level, msg))
            except Exception:
                pass

        backend = RemoteBackend()
        try:
            result = backend.runJobAuto(job, writeMsg, progress=None)
        finally:
            # 命令行模式没有界面关闭流程，任务结束后必须显式释放常驻 NX 后台进程
            try:
                backend.shutdown()
            except Exception:
                pass
        try:
            with open(resultPath, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return 0 if result.get('failed', 0) == 0 else 1
    except Exception:
        # 命令行模式下不能留下未处理异常（windowed exe 会弹错误对话框并挂起），
        # 统一写入日志/结果文件并返回非 0 退出码
        import traceback
        errorText = traceback.format_exc()
        if logPath:
            try:
                with open(logPath, 'a', encoding='utf-8') as f:
                    f.write('[error] 命令行模式执行异常：\n' + errorText + '\n')
            except Exception:
                pass
        if resultPath:
            try:
                with open(resultPath, 'w', encoding='utf-8') as f:
                    json.dump({'success': 0, 'failed': 0, 'skipped': 0, 'total': 0,
                               'elapsed': 0.0, 'error': errorText}, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
        return 3


def _writeCrashLog(errorText: str):
    """
    把未处理异常写入程序目录下的错误日志（便于用户反馈问题）

    Args:
        errorText (str): 异常堆栈文本
    """
    try:
        if getattr(sys, 'frozen', False):
            baseDir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            baseDir = BASE_DIR
        with open(os.path.join(baseDir, '批量导出插件.error.log'), 'a', encoding='utf-8') as f:
            f.write(errorText + '\n')
    except Exception:
        pass


def main():
    """入口"""
    try:
        if '--cli' in sys.argv:
            sys.exit(runCli(sys.argv))
        runGui()
    except Exception:
        import traceback
        errorText = traceback.format_exc()
        _writeCrashLog(errorText)
        try:
            messagebox.showerror('批量导出插件 运行错误',
                                 '程序发生未处理异常，详细信息已写入程序目录下的\n'
                                 '「批量导出插件.error.log」。\n\n' + errorText[-1500:])
        except Exception:
            pass
        sys.exit(1)


if __name__ == '__main__':
    main()
