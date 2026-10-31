"""
file: build_standalone.py
description: 打包免安装版「批量导出插件」（在开发机执行，需要 PyInstaller）
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.

使用方法：
    pip install pyinstaller
    python build_standalone.py             # 单文件版：build_standalone/dist/批量导出插件.exe
    python build_standalone.py --onedir    # 文件夹版（推荐）：build_standalone/dist/批量导出插件/

打包结果：
    单文件版：
        build_standalone/dist/批量导出插件.exe
        build_standalone/批量导出插件/使用说明.txt
        build_standalone/批量导出插件/更新说明.txt
    文件夹版（--onedir）：
        build_standalone/dist/批量导出插件/批量导出插件.exe
        build_standalone/dist/批量导出插件/_internal/...（运行文件）
        build_standalone/dist/批量导出插件/批量导出插件.lnk（双击启动的快捷方式）
        build_standalone/dist/批量导出插件/使用说明.txt
        build_standalone/dist/批量导出插件/更新说明.txt
"""
import os
import shutil
import subprocess
import sys

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_ROOT = os.path.join(PLUGIN_DIR, 'build_standalone')
DIST_DIR = os.path.join(BUILD_ROOT, 'dist')
WORK_DIR = os.path.join(BUILD_ROOT, 'work')
SPEC_DIR = os.path.join(BUILD_ROOT, 'spec')
APP_NAME = '批量导出插件'
ENTRY_SCRIPT = os.path.join(PLUGIN_DIR, 'standalone.py')
ICON_FILE = os.path.join(PLUGIN_DIR, 'icon.ico')
RELEASE_NOTES_FILE = os.path.join(PLUGIN_DIR, '更新说明.txt')

# NX 后台 worker 需要使用的后端源码（打包时放到 plugin_backend 子目录，由 worker 在 NX 中导入）
BACKEND_FILES = [
    'nxmodules.py',
    'modelmodules.py',
    'batchmodules.py',
    'pdfmodules.py',
    'pluginoptions.py',
    'language.py',
    'version.py',
    'remote_worker.py',
    'remote_server.py',
    'remote_jobs.py',
]

# 界面层数据文件
DATA_FILES = ['icon.ico']

USAGE_TEXT = """批量导出插件（免安装版）—— Siemens NX2412 批量导出工具

功能：
  1. 图纸导出：批量把 NX 工程图导出为 PDF / DWG（可同时导出两种格式）
  2. 模型导出：批量把单个模型或装配体导出为 XT(.x_t) / STP(.stp)
  3. 合并 PDF：把多个 PDF 合并为一个文件

启动方式（文件夹版）：
  1. 双击本文件夹内的「批量导出插件.lnk」快捷方式（或直接双击「批量导出插件.exe」）启动；
  2. 本文件夹可整体复制到其他电脑使用（需要该电脑已安装 NX2412 并具备可用许可）；
  3. 把文件夹复制到新位置/新电脑后，如果快捷方式打不开，双击本文件夹内的
     「创建快捷方式.cmd」重新生成一次即可；也可以直接双击「批量导出插件.exe」；
  4. 「_internal」文件夹是程序运行所需的文件，请不要删除或单独移动里面的文件。

使用：
  1. 启动后不需要先打开 NX；
  2. 在对应页签中添加 .prt 文件或文件夹，设置输出选项后点击「开始导出」；
  3. 程序启动后会自动在后台预热 NX 转换引擎（首次约 10~20 秒，界面可正常操作）；
     之后每次导出都复用同一个后台 NX 进程，不再重复等待启动时间；
  4. 如果已经打开了 NX，插件仍使用独立的后台 NX 进程完成导出，不会影响已打开的 NX。

「使用 NX 后台转换引擎」勾选项（免安装版界面下方）：
  - 勾选（默认，推荐）：常驻暖机模式。程序启动即后台预热 NX，之后导出更快；
    空闲约 30 分钟后后台 NX 自动退出以释放内存，下次导出会自动重新启动
  - 取消勾选：每次导出临时启动一个 NX 后台进程（每次多等约 10~20 秒，不在后台常驻）
  - 两种方式都不需要打开 NX。若想使用「已经打开的 NX」以及它的「已打开文件 /
    工作部件」：受 NX 接口限制，免安装版无法接管另一个 NX 图形会话，
    请在 NX 内运行插件（Alt+F8 运行 NX-batch-PDF-exporter.py）

合并 PDF：
  1. 点「打开文件」添加要合并的 PDF（按列表序号从小到大依次合并）；
  2. 保存路径默认自动填为第一个 PDF 所在文件夹；文件名默认「组合1」（自动补 .pdf，可修改）；
  3. 也可以点「选择」手动指定保存路径；
  4. 勾选「保存时重命名」后，点「开始合并」会先弹出另存为对话框，可选择最终的路径和文件名；
  5. 不勾选重命名时，如果目标文件夹里已有同名文件，会提示是否覆盖；
  6. 列表中的文件可通过「设置选中项 / 设置所有」调整是否参与合并。

提示：
  - 首次运行如果提示找不到 NX2412，请选择 NX 安装目录
    （例如 D:\\Program Files\\Siemens\\NX2412，目录下应有 NXBIN 文件夹）
  - 第一次双击启动较慢时，可能是杀毒软件扫描新程序，稍等或加入白名单即可
  - 空白图纸页（没有任何视图的页，如 NX 默认的 Sheet 1）会自动跳过，
    不会产生多余 DWG/PDF 文件
  - 图纸文件名中带 dwg 的是图纸文件，不带的是模型文件；
    图纸导出页默认只添加带 dwg 的文件，模型导出页默认排除带 dwg 的文件
  - DWG 转换较慢（单张图纸约 30~60 秒），STP 约 10~20 秒/件，请耐心等待
  - 本工具为绿色免安装程序，不会写入注册表；配置文件为同目录下的
    「批量导出插件.config.json」（仅记录 NX 安装目录）

本工具参考开源项目：
  https://github.com/IYATT-yx/NX-batch-PDF-exporter
修改用 AI 智能体为 DEEPSEEK HARNESS  DEEPSEEK-V4.1 Flash1017 创造模式
"""

# 文件夹版附带的「重新生成快捷方式」批处理（内容保持纯 ASCII，避免复制到不同区域设置时乱码；
# 中文只出现在文件名上，由文件系统处理）
CREATE_SHORTCUT_BAT = """@echo off
setlocal
cd /d "%~dp0"
for %%F in ("%~dp0*.exe") do (
    set "PLUGIN_EXE=%%~fF"
    set "PLUGIN_LNK=%%~dpnF.lnk"
)
if not defined PLUGIN_EXE (
    echo ERROR: program exe not found in this folder.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut($env:PLUGIN_LNK); $sc.TargetPath = $env:PLUGIN_EXE; $sc.WorkingDirectory = (Split-Path $env:PLUGIN_EXE); $sc.IconLocation = ($env:PLUGIN_EXE + ',0'); $sc.Description = 'Siemens NX2412 Batch Export Tool'; $sc.Save()"
echo.
echo Shortcut created or updated next to the program.
pause
exit /b 0
"""

VERSION_INFO_TEMPLATE = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(2026, 10, 31, 1),
    prodvers=(2026, 10, 31, 1),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '080404b0',
          [StringStruct('CompanyName', 'DEEPSEEK HARNESS'),
           StringStruct('FileDescription', 'Siemens NX2412 批量导出工具（免安装版）'),
           StringStruct('FileVersion', '2026.10.31.01'),
           StringStruct('InternalName', 'NX-Batch-Exporter'),
           StringStruct('LegalCopyright', 'MIT License'),
           StringStruct('OriginalFilename', '批量导出插件.exe'),
           StringStruct('ProductName', '批量导出插件'),
           StringStruct('ProductVersion', '2026.10.31.01')])
      ]
    ),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""


def checkPyInstaller() -> bool:
    """
    检查是否安装了 PyInstaller

    Returns:
        bool: 是否可用
    """
    try:
        import PyInstaller  # noqa: F401
        return True
    except Exception:
        pass
    print('未检测到 PyInstaller，请先执行：')
    print('    %s -m pip install pyinstaller' % sys.executable)
    return False


def writeVersionFile() -> str:
    """
    生成 PyInstaller 版本信息文件

    Returns:
        str: 文件路径
    """
    os.makedirs(SPEC_DIR, exist_ok=True)
    versionPath = os.path.join(SPEC_DIR, 'version_info.txt')
    with open(versionPath, 'w', encoding='utf-8') as f:
        f.write(VERSION_INFO_TEMPLATE)
    return versionPath


def writeUsageFiles(outputFolder: str, includeShortcutHelper: bool = False):
    """
    生成使用说明、复制更新说明（文件夹版还会生成重新创建快捷方式的批处理）

    Args:
        outputFolder (str): 输出目录
        includeShortcutHelper (bool): 是否生成「创建快捷方式.cmd」
    """
    os.makedirs(outputFolder, exist_ok=True)
    with open(os.path.join(outputFolder, '使用说明.txt'), 'w', encoding='utf-8') as f:
        f.write(USAGE_TEXT)
    if os.path.isfile(RELEASE_NOTES_FILE):
        shutil.copyfile(RELEASE_NOTES_FILE, os.path.join(outputFolder, '更新说明.txt'))
    if includeShortcutHelper:
        with open(os.path.join(outputFolder, '创建快捷方式.cmd'), 'w', encoding='ascii', newline='\r\n') as f:
            f.write(CREATE_SHORTCUT_BAT)


def createShortcut(folder: str, exePath: str) -> bool:
    """
    在输出文件夹中创建可双击启动的快捷方式（批量导出插件.lnk）

    Args:
        folder (str): 文件夹路径
        exePath (str): 目标 exe 路径

    Returns:
        bool: 是否创建成功
    """
    if sys.platform != 'win32':
        return False
    lnkPath = os.path.join(folder, APP_NAME + '.lnk')
    psScript = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$sc = $ws.CreateShortcut('%s'); "
        "$sc.TargetPath = '%s'; "
        "$sc.WorkingDirectory = '%s'; "
        "$sc.IconLocation = '%s,0'; "
        "$sc.Description = 'Siemens NX2412 批量导出工具'; "
        "$sc.Save()" % (lnkPath, exePath, folder, exePath)
    )
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', psScript],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0 and os.path.isfile(lnkPath)
    except Exception:
        return False


def build(mode: str = 'onefile') -> int:
    """
    执行打包

    Args:
        mode (str): 'onefile'（单文件版）或 'onedir'（文件夹版）

    Returns:
        int: 进程退出码
    """
    if not checkPyInstaller():
        return 1
    if not os.path.isfile(ICON_FILE):
        print('缺少图标文件 icon.ico')
        return 1

    for folder in (DIST_DIR, WORK_DIR, SPEC_DIR):
        os.makedirs(folder, exist_ok=True)

    args = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--clean',
        '--windowed',
        '--name', APP_NAME,
        '--icon', ICON_FILE,
        '--distpath', DIST_DIR,
        '--workpath', WORK_DIR,
        '--specpath', SPEC_DIR,
        '--version-file', writeVersionFile(),
        '--hidden-import', 'pypdf',
    ]
    if mode == 'onedir':
        args += ['--onedir', '--contents-directory', '_internal']
    else:
        args += ['--onefile']

    pypdfDir = os.path.join(PLUGIN_DIR, 'lib', 'pypdf-6.7.5')
    if os.path.isdir(pypdfDir):
        args += ['--paths', pypdfDir]

    for dataFile in DATA_FILES:
        source = os.path.join(PLUGIN_DIR, dataFile)
        if os.path.isfile(source):
            args += ['--add-data', '%s%s.' % (source, os.pathsep)]

    for backendFile in BACKEND_FILES:
        source = os.path.join(PLUGIN_DIR, backendFile)
        if not os.path.isfile(source):
            print('缺少后端文件:', backendFile)
            return 1
        args += ['--add-data', '%s%splugin_backend' % (source, os.pathsep)]

    args.append(ENTRY_SCRIPT)

    print('开始打包（%s）：' % ('文件夹版' if mode == 'onedir' else '单文件版'))
    print('    ' + ' '.join(args))
    result = subprocess.run(args, cwd=PLUGIN_DIR)
    if result.returncode != 0:
        print('打包失败，退出码:', result.returncode)
        return result.returncode

    print()
    if mode == 'onedir':
        outputFolder = os.path.join(DIST_DIR, APP_NAME)
        exePath = os.path.join(outputFolder, APP_NAME + '.exe')
        if not os.path.isfile(exePath):
            print('未找到打包产物:', exePath)
            return 1
        writeUsageFiles(outputFolder, includeShortcutHelper=True)
        shortcutOk = createShortcut(outputFolder, exePath)
        totalBytes = 0
        for root, dirs, files in os.walk(outputFolder):
            for fileName in files:
                totalBytes += os.path.getsize(os.path.join(root, fileName))
        print('打包完成（文件夹版）：')
        print('    %s' % outputFolder)
        print('    主程序：%s（%.1f MB）' % (exePath, os.path.getsize(exePath) / 1024.0 / 1024.0))
        print('    使用说明 / 更新说明：已生成')
        print('    快捷方式：%s' % ('已创建 批量导出插件.lnk' if shortcutOk else '创建失败（可手动创建）'))
        print('    文件夹总大小：%.1f MB' % (totalBytes / 1024.0 / 1024.0))
        return 0

    exePath = os.path.join(DIST_DIR, APP_NAME + '.exe')
    if not os.path.isfile(exePath):
        print('未找到打包产物:', exePath)
        return 1
    usageDir = os.path.join(BUILD_ROOT, APP_NAME)
    writeUsageFiles(usageDir)
    sizeMB = os.path.getsize(exePath) / 1024.0 / 1024.0
    print('打包完成（单文件版）：')
    print('    %s（%.1f MB）' % (exePath, sizeMB))
    print('    使用说明：%s' % os.path.join(usageDir, '使用说明.txt'))
    return 0


def main() -> int:
    """
    入口：解析命令行参数

    Returns:
        int: 退出码
    """
    mode = 'onedir' if '--onedir' in sys.argv[1:] else 'onefile'
    return build(mode)


if __name__ == '__main__':
    sys.exit(main())
