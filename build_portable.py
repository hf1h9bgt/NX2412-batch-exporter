r"""
file: build_portable.py
description: 打包「便携式发布包」——拆开的源码文件 + 内置 Python 运行时 + 启动器 + 快捷方式，压缩成 zip（GitHub Releases 便携版风格）
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.

使用方法（开发机，Windows）：
    python build_portable.py
    python build_portable.py --python-home "D:\\Program Files\\Python313"   # 手动指定 Python 3.13 安装目录
    python build_portable.py --no-zip                                     # 只生成文件夹，不压缩

产物：
    build_portable/dist/批量导出插件/                                （便携版文件夹，可直接使用）
    build_portable/dist/批量导出插件_便携版_v<version>_win64.zip    （解压即用的便携式压缩包）
    build_portable/dist/SHA256SUMS.txt

结构（解压后）：
    批量导出插件\
        批量导出插件.exe          启动器（仅负责调用 python\pythonw.exe standalone.py）
        批量导出插件.lnk          双击启动的快捷方式（相对路径，可随文件夹复制）
        启动批量导出插件.bat      备用启动方式
        创建快捷方式.cmd          快捷方式失效时重新生成
        standalone.py            免安装版入口
        NX-batch-PDF-exporter.py NX 内插件入口
        application.py ...       插件源码（与 GitHub 仓库相同，逐文件拆开）
        python\                  便携 Python 运行时（Python 3.13，含 tkinter，无需安装 Python）
        tcl\ lib\ locales\ doc\  附属资源
        使用说明.txt 更新说明.txt README.md LICENSE
"""
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_ROOT = os.path.join(PLUGIN_DIR, 'build_portable')
DIST_DIR = os.path.join(BUILD_ROOT, 'dist')
APP_NAME = '批量导出插件'
VERSION = '20261031.01'
ZIP_NAME = 'NX2412%s_便携版_v%s_win64.zip' % (APP_NAME, VERSION)
CSC_CANDIDATES = [
    r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe',
    r'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe',
]

# 便携包中需要逐文件拆开的源码（与仓库结构一致）
SOURCE_FILES = [
    'standalone.py',
    'NX-batch-PDF-exporter.py',
    'application.py',
    'listshow.py',
    'nxmodules.py',
    'modelmodules.py',
    'batchmodules.py',
    'pdfmodules.py',
    'pluginoptions.py',
    'backend_direct.py',
    'remote_backend.py',
    'remote_worker.py',
    'remote_server.py',
    'remote_jobs.py',
    'language.py',
    'version.py',
]

# 需要随包分发的资源目录（相对路径）
ASSET_DIRS = [
    'tcl',
    'locales',
    'doc',
]

# 单独复制的资源文件
ASSET_FILES = [
    'icon.ico',
    'icon.png',
    'icon.bmp',
    'README.md',
    'LICENSE',
    '更新说明.txt',
    'requirements-build.txt',
]

# 内置 Python 运行时需要的根目录文件（从 Python 安装目录复制）
PY_ROOT_FILES = [
    'python.exe',
    'pythonw.exe',
    'python313.dll',
    'python3.dll',
    'vcruntime140.dll',
    'vcruntime140_1.dll',
    'LICENSE.txt',
]

# 运行时 Lib 下不需要的目录（体积/开发用途，可安全删除）
PY_LIB_EXCLUDES = [
    'test',
    'idlelib',
    'ensurepip',
    'venv',
    'lib2to3',
    'turtledemo',
    'site-packages',
    'tkinter/test',
    'unittest/test',
]

PORTABLE_USAGE_TEXT = """批量导出插件（便携版）—— Siemens NX2412 批量导出工具

启动：
  1. 解压整个「批量导出插件」文件夹到任意位置（路径可含中文/空格）；
  2. 双击文件夹内的「批量导出插件.exe」启动（带图标，作用等同快捷方式，解压到任意路径都可用）；
     也可以双击备用启动文件「启动批量导出插件.vbs」（无控制台窗口）或「启动批量导出插件.bat」；
  3. 如果确实想要 Windows 快捷方式（.lnk）：双击本文件夹内的「创建快捷方式.cmd」一次，
     会在同目录生成「批量导出插件.lnk」，之后双击该 .lnk 即可（也可以把它拖到桌面）；
     （Windows 快捷方式文件保存的是绝对路径，压缩包里预置的 .lnk 解压到别的路径后会失效，
       所以 .lnk 需要在解压后的机器上生成一次；「批量导出插件.exe」不受此限制。）
  4. 本包已内置 Python 3.13 运行环境，解压即用，不需要安装 Python，也不需要安装本程序；
  5. 把整个文件夹复制到其他电脑也可以直接使用（需要该电脑已安装 NX2412 并具备可用许可）；
     如果复制/移动后 .lnk 打不开，双击「创建快捷方式.cmd」重新生成一次即可。

功能：
  1. 图纸导出：批量把 NX 工程图导出为 PDF / DWG（可同时导出两种格式）
  2. 模型导出：批量把单个模型或装配体导出为 XT(.x_t) / STP(.stp)
  3. 合并 PDF：把多个 PDF 合并为一个文件

使用：
  1. 启动后不需要先打开 NX；
  2. 在对应页签中添加 .prt 文件或文件夹，设置输出选项后点击「开始导出」；
  3. 程序启动后会自动在后台预热 NX 转换引擎（首次约 10~20 秒，界面可正常操作）；
     之后每次导出都复用同一个后台 NX 进程，不再重复等待启动时间；
  4. 如果已经打开了 NX，插件仍使用独立的后台 NX 进程完成导出，不会影响已打开的 NX。

「使用 NX 后台转换引擎」勾选项（便携版界面下方）：
  - 勾选（默认，推荐）：常驻暖机模式。程序启动即后台预热 NX，之后导出更快；
    空闲约 30 分钟后后台 NX 自动退出以释放内存，下次导出会自动重新启动；
  - 取消勾选：每次导出临时启动一个 NX 后台进程（每次多等约 10~20 秒，不在后台常驻）；
  - 两种方式都不需要打开 NX。若想使用「已经打开的 NX」以及它的「已打开文件 /
    工作部件」：受 NX 接口限制，便携版无法接管另一个 NX 图形会话，
    请在 NX 内运行插件（Alt+F8 运行本文件夹中的 NX-batch-PDF-exporter.py）。

合并 PDF：
  1. 点「打开文件」添加要合并的 PDF（按列表序号从小到大依次合并）；
  2. 保存路径默认自动填为第一个 PDF 所在文件夹；文件名默认「组合1」（自动补 .pdf，可修改）；
  3. 也可以点「选择」手动指定保存路径；
  4. 勾选「保存时重命名」后，点「开始合并」会先弹出另存为对话框，可选择最终的路径和文件名；
  5. 不勾选重命名时，如果目标文件夹里已有同名文件，会提示是否覆盖；
  6. 列表中的文件可通过「设置选中项 / 设置所有」调整是否参与合并。

目录说明：
  *.py                   插件源码（与 GitHub 仓库相同，逐文件拆开，可查看/修改）
  python\\                便携 Python 运行时（请勿删除；删了程序无法启动）
  tcl\\ lib\\ locales\\ doc\\  附属资源（NX 内插件模式、pypdf 库、多语言工具、文档图片）
  批量导出插件.exe        启动器（仅 70KB，负责调用 python\\pythonw.exe standalone.py，双击即用）
  启动批量导出插件.vbs    备用启动脚本（双击也可启动，无控制台窗口）
  启动批量导出插件.bat    备用启动脚本（双击也可启动）
  创建快捷方式.cmd        在本机生成 .lnk 快捷方式（复制/移动文件夹后重新运行一次即可）

提示：
  - 首次运行如果提示找不到 NX2412，请选择 NX 安装目录
    （例如 D:\\Program Files\\Siemens\\NX2412，目录下应有 NXBIN 文件夹）
  - 第一次双击启动较慢时，可能是杀毒软件扫描新解压的程序，稍等或加入白名单即可
  - 空白图纸页（没有任何视图的页，如 NX 默认的 Sheet 1）会自动跳过，
    不会产生多余 DWG/PDF 文件
  - 图纸文件名中带 dwg 的是图纸文件，不带的是模型文件；
    图纸导出页默认只添加带 dwg 的文件，模型导出页默认排除带 dwg 的文件
  - DWG 转换较慢（单张图纸约 30~60 秒），STP 约 10~20 秒/件，请耐心等待
  - 本工具为绿色便携程序，不写注册表；配置文件为同目录下的
    「批量导出插件.config.json」（仅记录 NX 安装目录）

本工具参考开源项目：
  https://github.com/IYATT-yx/NX-batch-PDF-exporter
修改用 AI 智能体为 DEEPSEEK HARNESS  DEEPSEEK-V4.1 Flash1017 创造模式
"""

LAUNCHER_BAT = """@echo off
setlocal
cd /d "%~dp0"
start "" "%~dp0python\\pythonw.exe" "%~dp0standalone.py" %*
"""

# VBS 启动器源文件（放在仓库 launcher/ 目录，便于按仓库结构管理）
LAUNCHER_VBS_FILE = os.path.join(PLUGIN_DIR, 'launcher', '启动批量导出插件.vbs')
LAUNCHER_BAT_NAME = '启动批量导出插件.bat'
LAUNCHER_VBS_NAME = '启动批量导出插件.vbs'

CREATE_SHORTCUT_BAT = """@echo off
setlocal
cd /d "%~dp0"
for %%F in ("%~dp0*.exe") do (
    set "PLUGIN_EXE=%%~fF"
    set "PLUGIN_LNK=%%~dpnF.lnk"
)
if not defined PLUGIN_EXE (
    echo ERROR: launcher exe not found in this folder.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut($env:PLUGIN_LNK); $sc.TargetPath = $env:PLUGIN_EXE; $sc.WorkingDirectory = (Split-Path $env:PLUGIN_EXE); $sc.IconLocation = ($env:PLUGIN_EXE + ',0'); $sc.Description = 'Siemens NX2412 Batch Export Tool'; $sc.Save()"
echo.
echo Shortcut created or updated next to the program.
pause
exit /b 0
"""

# 用 IShellLink COM 创建「相对路径」快捷方式（解压/复制到任意路径后仍然可用）
MAKE_RELATIVE_SHORTCUT_PS1_TEMPLATE = r"""$ErrorActionPreference = 'Stop'
$code = @"
using System;
using System.Runtime.InteropServices;
using System.Text;

[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
internal class ShellLink { }

[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
internal interface IShellLinkW
{
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszFile, int cch, IntPtr pfd, uint fFlags);
    void GetIDList(out IntPtr ppidl);
    void SetIDList(IntPtr pidl);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszName, int cch);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszDir, int cch);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszArgs, int cch);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
    void GetHotkey(out short pwHotkey);
    void SetHotkey(short wHotkey);
    void GetShowCmd(out int piShowCmd);
    void SetShowCmd(int iShowCmd);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder pszIconPath, int cch, out int piIcon);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, uint dwReserved);
    void Resolve(IntPtr hwnd, uint fFlags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
}

[ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
internal interface IPersistFile
{
    void GetClassID(out Guid pClassID);
    [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, uint dwMode);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, [MarshalAs(UnmanagedType.Bool)] bool fRemember);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string pszFileName);
    void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string ppszFileName);
}

public class ShortcutTool
{
    public static void Create(string lnkPath, string targetPath, string relativePath)
    {
        IShellLinkW link = (IShellLinkW)new ShellLink();
        link.SetPath(targetPath);
        if (!String.IsNullOrEmpty(relativePath)) { link.SetRelativePath(relativePath, 0); }
        ((IPersistFile)link).Save(lnkPath, true);
    }
}
"@
Add-Type -TypeDefinition $code -Language CSharp
[ShortcutTool]::Create('__LNK_PATH__', '__TARGET_PATH__', '__RELATIVE_PATH__')
"""


def log(message: str):
    """输出日志"""
    print(message)
    sys.stdout.flush()


def detectCsc() -> str:
    """查找 .NET Framework 的 csc.exe"""
    for path in CSC_CANDIDATES:
        if os.path.isfile(path):
            return path
    return ''


def detectPythonHome() -> str:
    """检测 Python 3.13 安装目录（用于复制便携运行时）"""
    candidates = []
    if '--python-home' in sys.argv:
        index = sys.argv.index('--python-home')
        if index + 1 < len(sys.argv):
            candidates.append(sys.argv[index + 1])
    envHome = os.environ.get('PORTABLE_PYTHON_HOME', '')
    if envHome:
        candidates.append(envHome)
    candidates.append(sys.base_prefix)
    for path in candidates:
        if path and os.path.isfile(os.path.join(path, 'python.exe')) \
                and os.path.isfile(os.path.join(path, 'pythonw.exe')) \
                and os.path.isdir(os.path.join(path, 'Lib')) \
                and os.path.isdir(os.path.join(path, 'DLLs')):
            return os.path.abspath(path)
    return ''


def copyTree(source: str, target: str, excludes=None):
    """复制目录（excludes 为相对路径列表）"""
    excludes = excludes or []
    shutil.copytree(source, target, dirs_exist_ok=True,
                    ignore=lambda directory, names: [name for name in names
                                                     if os.path.join(directory, name) in excludes])


def copyPythonRuntime(pythonHome: str, targetRoot: str):
    """复制精简后的便携 Python 运行时到目标目录下的 python 子目录"""
    pythonDir = os.path.join(targetRoot, 'python')
    os.makedirs(pythonDir, exist_ok=True)
    for name in PY_ROOT_FILES:
        source = os.path.join(pythonHome, name)
        if os.path.isfile(source):
            shutil.copyfile(source, os.path.join(pythonDir, name))
    shutil.copytree(os.path.join(pythonHome, 'DLLs'), os.path.join(pythonDir, 'DLLs'), dirs_exist_ok=True)
    shutil.copytree(os.path.join(pythonHome, 'Lib'), os.path.join(pythonDir, 'Lib'), dirs_exist_ok=True)
    for relative in PY_LIB_EXCLUDES:
        shutil.rmtree(os.path.join(pythonDir, 'Lib', relative), ignore_errors=True)
    for root, dirs, files in os.walk(os.path.join(pythonDir, 'Lib')):
        for name in list(dirs):
            if name == '__pycache__':
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
                dirs.remove(name)
    tclDir = os.path.join(pythonHome, 'tcl')
    if os.path.isdir(tclDir):
        shutil.copytree(tclDir, os.path.join(pythonDir, 'tcl'), dirs_exist_ok=True)
    return pythonDir


def copySourceTree(targetRoot: str):
    """复制插件源码与资源（逐文件拆开）"""
    for name in SOURCE_FILES:
        source = os.path.join(PLUGIN_DIR, name)
        if not os.path.isfile(source):
            raise RuntimeError('缺少源码文件: %s' % name)
        shutil.copyfile(source, os.path.join(targetRoot, name))

    for relative in ASSET_DIRS:
        source = os.path.join(PLUGIN_DIR, relative)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(targetRoot, relative), dirs_exist_ok=True)

    for name in ASSET_FILES:
        source = os.path.join(PLUGIN_DIR, name)
        if os.path.isfile(source):
            shutil.copyfile(source, os.path.join(targetRoot, name))

    # 第三方运行时库：只复制 pypdf 运行需要的包与许可证（仓库里 vendored 的完整目录含文档/测试，不需要）
    pypdfRoot = os.path.join(PLUGIN_DIR, 'lib', 'pypdf-6.7.5')
    if os.path.isdir(pypdfRoot):
        pypdfTarget = os.path.join(targetRoot, 'lib', 'pypdf-6.7.5')
        os.makedirs(pypdfTarget, exist_ok=True)
        shutil.copytree(os.path.join(pypdfRoot, 'pypdf'), os.path.join(pypdfTarget, 'pypdf'), dirs_exist_ok=True)
        for name in ('LICENSE', 'README.md'):
            source = os.path.join(pypdfRoot, name)
            if os.path.isfile(source):
                shutil.copyfile(source, os.path.join(pypdfTarget, name))


def writeLaunchers(targetRoot: str):
    """生成启动器脚本与快捷方式重建脚本"""
    with open(os.path.join(targetRoot, LAUNCHER_BAT_NAME), 'w', encoding='ascii', newline='\r\n') as f:
        f.write(LAUNCHER_BAT)
    if os.path.isfile(LAUNCHER_VBS_FILE):
        shutil.copyfile(LAUNCHER_VBS_FILE, os.path.join(targetRoot, LAUNCHER_VBS_NAME))
    else:
        log('[!] 缺少 launcher/启动批量导出插件.vbs（不影响 exe/bat 启动）')
    with open(os.path.join(targetRoot, '创建快捷方式.cmd'), 'w', encoding='ascii', newline='\r\n') as f:
        f.write(CREATE_SHORTCUT_BAT)
    with open(os.path.join(targetRoot, '使用说明.txt'), 'w', encoding='utf-8') as f:
        f.write(PORTABLE_USAGE_TEXT)


def buildLauncher(targetRoot: str) -> bool:
    """编译便携版启动器 exe（使用 .NET Framework 自带 csc）"""
    csc = detectCsc()
    source = os.path.join(PLUGIN_DIR, 'launcher', 'Launcher.cs')
    if not csc:
        log('[!] 未找到 csc.exe，跳过启动器编译（将只能使用 启动批量导出插件.bat）')
        return False
    if not os.path.isfile(source):
        log('[!] 缺少 launcher/Launcher.cs，跳过启动器编译')
        return False
    icon = os.path.join(PLUGIN_DIR, 'icon.ico')
    output = os.path.join(targetRoot, APP_NAME + '.exe')
    command = [csc, '/nologo', '/target:winexe', '/platform:anycpu',
               '/win32icon:' + icon, '/out:' + output, source]
    result = subprocess.run(command, cwd=PLUGIN_DIR)
    if result.returncode != 0 or not os.path.isfile(output):
        log('[!] 启动器编译失败（退出码 %s）' % result.returncode)
        return False
    return True


def createRelativeShortcut(targetRoot: str) -> bool:
    """
    在便携包内创建使用相对路径的快捷方式（解压/复制到任意路径后仍可用）

    Args:
        targetRoot (str): 便携包根目录

    Returns:
        bool: 是否创建成功
    """
    lnkPath = os.path.join(targetRoot, APP_NAME + '.lnk')
    targetPath = os.path.join(targetRoot, APP_NAME + '.exe')
    if not os.path.isfile(targetPath):
        return False
    ps1Path = os.path.join(BUILD_ROOT, 'make_shortcut.ps1')
    script = MAKE_RELATIVE_SHORTCUT_PS1_TEMPLATE
    script = script.replace('__LNK_PATH__', lnkPath.replace("'", "''"))
    script = script.replace('__TARGET_PATH__', targetPath.replace("'", "''"))
    script = script.replace('__RELATIVE_PATH__', (APP_NAME + '.exe').replace("'", "''"))
    os.makedirs(BUILD_ROOT, exist_ok=True)
    with open(ps1Path, 'w', encoding='utf-8-sig') as f:
        f.write(script)
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1Path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0 and os.path.isfile(lnkPath)
    except Exception:
        return False


def sha256File(filePath: str) -> str:
    """计算文件 SHA256"""
    digest = hashlib.sha256()
    with open(filePath, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def makeZip(packageDir: str, zipPath: str) -> int:
    """
    把便携包文件夹压缩成 zip（zip 内顶层目录为 批量导出插件/）

    不打包本机生成的 .lnk（Windows 快捷方式是绝对路径，解压到别处会失效）
    以及运行时产生的配置/日志文件。
    """
    skipNames = {APP_NAME + '.lnk', APP_NAME + '.config.json', APP_NAME + '.error.log'}
    skipSuffixes = ('.pyc', '.log.tmp')
    fileCount = 0
    with zipfile.ZipFile(zipPath, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for root, dirs, files in os.walk(packageDir):
            dirs[:] = [name for name in dirs if name != '__pycache__']
            for name in files:
                if name in skipNames or name.endswith(skipSuffixes):
                    continue
                fullPath = os.path.join(root, name)
                relative = os.path.relpath(fullPath, packageDir)
                archive.write(fullPath, os.path.join(APP_NAME, relative))
                fileCount += 1
    return fileCount


def build(noZip: bool = False) -> int:
    """执行便携版打包"""
    pythonHome = detectPythonHome()
    if not pythonHome:
        log('未找到可用的 Python 3.13 安装目录（需要 python.exe/pythonw.exe/Lib/DLLs/tcl）。')
        log('请用 --python-home 指定，例如：')
        log('    python build_portable.py --python-home "D:\\Program Files\\Python313"')
        return 1
    log('Python 运行时来源: %s' % pythonHome)

    packageDir = os.path.join(DIST_DIR, APP_NAME)
    shutil.rmtree(packageDir, ignore_errors=True)
    os.makedirs(packageDir, exist_ok=True)

    log('复制插件源码与资源 ...')
    copySourceTree(packageDir)
    log('复制便携 Python 运行时（首次约 1~2 分钟）...')
    copyPythonRuntime(pythonHome, packageDir)
    log('生成启动脚本/使用说明 ...')
    writeLaunchers(packageDir)
    log('编译启动器 ...')
    launcherOk = buildLauncher(packageDir)
    if not launcherOk:
        log('注意：启动器未生成，只能使用 启动批量导出插件.bat 启动。')
    log('创建相对路径快捷方式 ...')
    shortcutOk = createRelativeShortcut(packageDir)
    if not shortcutOk:
        log('注意：快捷方式创建失败，可双击 创建快捷方式.cmd 手动生成。')
    else:
        log('已创建快捷方式: %s.lnk（相对路径）' % APP_NAME)

    fileCount = 0
    totalBytes = 0
    for root, dirs, files in os.walk(packageDir):
        for name in files:
            fileCount += 1
            totalBytes += os.path.getsize(os.path.join(root, name))
    log('便携版文件夹: %s' % packageDir)
    log('    文件数: %d，总大小: %.1f MB' % (fileCount, totalBytes / 1024.0 / 1024.0))

    if noZip:
        return 0

    zipPath = os.path.join(DIST_DIR, ZIP_NAME)
    log('压缩便携包（文件较多，约需 1~2 分钟）...')
    zippedCount = makeZip(packageDir, zipPath)
    zipSize = os.path.getsize(zipPath)
    digest = sha256File(zipPath)
    sumsPath = os.path.join(DIST_DIR, 'SHA256SUMS.txt')
    with open(sumsPath, 'w', encoding='utf-8') as f:
        f.write('%s  %s\n' % (digest, ZIP_NAME))
    log('便携式压缩包: %s' % zipPath)
    log('    %d 个文件，%.1f MB' % (zippedCount, zipSize / 1024.0 / 1024.0))
    log('    SHA256: %s' % digest)
    log('    校验文件: %s' % sumsPath)
    return 0


def main() -> int:
    """入口"""
    return build(noZip='--no-zip' in sys.argv[1:])


if __name__ == '__main__':
    sys.exit(main())
