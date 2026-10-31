"""
file: remote_backend.py
description: 免安装版后端：自动发现本机 NX 2412，通过 run_journal.exe 启动后台 NX 进程完成导出
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

# Windows 下隐藏后台 NX 进程的控制台窗口
CREATE_NO_WINDOW = 0x08000000

# 后台任务最长运行时间（秒），DWG/STP 转换较慢，给足余量
JOB_TIMEOUT_SECONDS = 12 * 3600

# 常驻后台转换服务启动超时（秒）
SERVER_STARTUP_TIMEOUT_SECONDS = 180.0

# 常驻服务空闲自动退出时间（秒），避免长期占用内存（界面启动时会重新预热）
SERVER_IDLE_TIMEOUT_SECONDS = 1800

# 轮询后台日志的间隔（秒）
POLL_INTERVAL_SECONDS = 0.2

# 配置文件（记住用户手动选择的 NX 安装目录）
CONFIG_FILE_NAME = '批量导出插件.config.json'


def _safeJsonText(text: str):
    """
    安全解析 JSON 文本

    Args:
        text (str): JSON 文本

    Returns:
        dict | None: 解析结果，失败返回 None
    """
    try:
        return json.loads(text)
    except Exception:
        return None


def _applyJsonLogLine(line: str, writeMsg, progress):
    """
    解析一行后台 JSON 日志并回调消息/进度

    日志格式：
        [MSG] {"level": "info", "msg": "..."}
        [PROGRESS] {"done": 1, "total": 3}
        [RESULT] {"success": 1, ...}
        [DONE]

    Args:
        line (str): 一行日志
        writeMsg (function): 消息回调
        progress (function): 进度回调

    Returns:
        tuple: (result, done)  result 为结果字典或 None；done 表示任务完成
    """
    line = line.strip()
    if not line:
        return None, False
    if line.startswith('[MSG] '):
        payload = _safeJsonText(line[6:])
        if isinstance(payload, dict):
            writeMsg(str(payload.get('msg', '')), str(payload.get('level', 'info')))
    elif line.startswith('[PROGRESS] '):
        payload = _safeJsonText(line[11:])
        if isinstance(payload, dict) and progress is not None:
            try:
                progress(int(payload.get('done', 0)), int(payload.get('total', 0)))
            except Exception:
                pass
    elif line.startswith('[RESULT] '):
        payload = _safeJsonText(line[9:])
        if isinstance(payload, dict):
            return payload, False
    elif line.startswith('[DONE]'):
        return None, True
    return None, False


class WarmNxServer:
    """
    常驻暖机 NX 后台转换服务。

    首次启动约 10~20 秒（NX 进程初始化），之后多次导出复用同一个 NX 进程，
    不再重复承担启动时间；空闲超过 SERVER_IDLE_TIMEOUT_SECONDS 后自动退出以释放内存。
    """

    def __init__(self, backend):
        self.backend = backend
        self.state = 'stopped'   # stopped / starting / ready / error
        self.process = None
        self.jobDir = ''
        self.readyInfo = {}
        self.lastError = ''
        self._counter = 0
        self._lock = threading.Lock()
        self._startThread = None
        self._shutdownRequested = False

    # ------------------------- 状态 -------------------------

    def isAlive(self) -> bool:
        """
        服务进程是否仍在运行

        Returns:
            bool: 是否运行中
        """
        return self.process is not None and self.process.poll() is None

    def isReady(self) -> bool:
        """
        服务是否已就绪

        Returns:
            bool: 是否就绪
        """
        if self.state == 'ready' and not self.isAlive():
            self.state = 'stopped'
        return self.state == 'ready' and self.isAlive()

    def refresh(self):
        """刷新状态（进程意外退出时从 ready 变为 stopped）"""
        if self.state == 'ready' and not self.isAlive():
            self.state = 'stopped'
            self._cleanup(removeDir=True)

    def statusSuffix(self) -> str:
        """
        状态文字后缀

        Returns:
            str: 状态描述
        """
        self.refresh()
        if not self.backend.isAvailable():
            return '未找到 NX2412'
        if not self.backend.warmEngineEnabled:
            return '临时启动模式'
        mapping = {
            'stopped': '待启动',
            'starting': '启动中…',
            'ready': '已就绪',
            'error': '启动失败',
        }
        return mapping.get(self.state, self.state)

    # ------------------------- 启动 / 停止 -------------------------

    def startAsync(self):
        """后台异步启动常驻服务（用于程序启动时预热，不阻塞界面）"""
        if self._shutdownRequested or not self.backend.warmEngineEnabled:
            return
        if self.isReady() or self.state == 'starting':
            return
        if self._startThread is not None and self._startThread.is_alive():
            return
        self._startThread = threading.Thread(target=self._startWorker, name='nx-warm-start', daemon=True)
        self._startThread.start()

    def _startWorker(self):
        """预热线程入口（异常只记录，不影响界面）"""
        try:
            self.start(writeMsg=None)
        except Exception as e:
            self.state = 'error'
            self.lastError = str(e)

    def start(self, writeMsg=None) -> bool:
        """
        启动常驻服务（阻塞直到就绪或失败）

        Args:
            writeMsg (function, optional): 消息回调

        Returns:
            bool: 是否就绪
        """
        with self._lock:
            if self.isReady():
                return True
            if self._shutdownRequested:
                self.state = 'stopped'
                return False
            if self.state == 'starting' and self.isAlive():
                return False
            self._cleanup(removeDir=True)
            self.state = 'starting'
            self.lastError = ''

            if not self.backend.isAvailable():
                self.state = 'error'
                self.lastError = '未找到 NX2412'
                return False
            serverScript = os.path.join(self.backend.pluginDir, 'remote_server.py')
            if not os.path.isfile(serverScript):
                self.state = 'error'
                self.lastError = '缺少后台服务脚本 remote_server.py'
                return False

            try:
                self.jobDir = tempfile.mkdtemp(prefix='nx_batch_server_')
                os.makedirs(os.path.join(self.jobDir, 'jobs'), exist_ok=True)
                os.makedirs(os.path.join(self.jobDir, 'logs'), exist_ok=True)
            except Exception as e:
                self.state = 'error'
                self.lastError = '无法创建后台任务目录: %s' % e
                return False

            env = os.environ.copy()
            env['DSH_NX_JOB_DIR'] = self.jobDir
            env['DSH_PLUGIN_DIR'] = self.backend.pluginDir
            env['DSH_SERVER_IDLE_TIMEOUT'] = str(SERVER_IDLE_TIMEOUT_SECONDS)
            env['UGII_BASE_DIR'] = self.backend.nxRoot

            try:
                self.process = subprocess.Popen(
                    [self.backend.runJournalPath, serverScript],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW)
            except Exception as e:
                self.state = 'error'
                self.lastError = '无法启动 NX 后台进程: %s' % e
                return False

            readyPath = os.path.join(self.jobDir, 'server_ready.json')
            startTime = time.time()
            lastHint = 0.0
            while time.time() - startTime < SERVER_STARTUP_TIMEOUT_SECONDS:
                if self._shutdownRequested:
                    self._killProcess()
                    self.state = 'stopped'
                    return False
                if os.path.isfile(readyPath):
                    self.readyInfo = _safeJsonText(openSafeText(readyPath)) or {}
                    self.state = 'ready'
                    return True
                if self.process.poll() is not None:
                    self.lastError = self._readServerError()
                    self.state = 'error'
                    return False
                if writeMsg is not None and time.time() - lastHint > 5.0:
                    lastHint = time.time()
                    msg = '  [i] NX 后台转换引擎启动中...（已等待 {seconds:.0f} 秒）'
                    writeMsg(msg.format(seconds=time.time() - startTime), 'info')
                time.sleep(0.25)

            self.lastError = '启动超时（%.0f 秒）' % SERVER_STARTUP_TIMEOUT_SECONDS
            self._killProcess()
            self.state = 'error'
            return False

    def submit(self, job: dict, writeMsg, progress) -> dict:
        """
        提交流程作业并等待完成（实时回传日志/进度）

        Args:
            job (dict): 作业描述
            writeMsg (function): 消息回调
            progress (function): 进度回调

        Returns:
            dict | None: 结果字典；常驻服务不可用/失败时返回 None（由调用方回退一次性模式）
        """
        if not self.start(writeMsg):
            return None

        self._counter += 1
        jobId = '%d_%d' % (int(time.time() * 1000), self._counter)
        jobsDir = os.path.join(self.jobDir, 'jobs')
        logsDir = os.path.join(self.jobDir, 'logs')
        jobPath = os.path.join(jobsDir, jobId + '.json')
        logPath = os.path.join(logsDir, jobId + '.jsonl')
        try:
            with open(jobPath, 'w', encoding='utf-8') as f:
                json.dump(job, f, ensure_ascii=False)
            with open(logPath, 'w', encoding='utf-8') as f:
                f.write('')
        except Exception as e:
            writeMsg('  [✘] 无法提交后台任务: %s' % e, 'error')
            return None

        writeMsg('  [i] 已连接常驻 NX 转换引擎（复用已启动的 NX 进程，无需等待启动）', 'info')
        result = None
        lineIndex = 0
        done = False
        startTime = time.time()
        while True:
            lines = RemoteBackend._readLogLines(logPath)
            for line in lines[lineIndex:]:
                lineResult, lineDone = _applyJsonLogLine(line, writeMsg, progress)
                if lineResult is not None:
                    result = lineResult
                if lineDone:
                    done = True
            lineIndex = len(lines)

            if done and result is not None:
                self.state = 'ready'
                return result
            if not self.isAlive():
                writeMsg('  [✘] 常驻 NX 转换引擎意外退出，作业未完成', 'error')
                self.state = 'error'
                self.lastError = self._readServerError()
                self._cleanup(removeDir=True)
                return None
            if time.time() - startTime > JOB_TIMEOUT_SECONDS:
                writeMsg('  [✘] 后台 NX 任务超时，已中止', 'error')
                return result
            time.sleep(POLL_INTERVAL_SECONDS)

    def shutdown(self):
        """停止常驻服务并释放资源（窗口关闭/取消勾选时调用）"""
        self._shutdownRequested = True
        self.state = 'stopped'
        if self.process is None:
            self._cleanup(removeDir=True)
            return
        try:
            stopPath = os.path.join(self.jobDir, 'stop')
            with open(stopPath, 'w', encoding='utf-8') as f:
                f.write('stop')
        except Exception:
            pass
        try:
            self.process.wait(timeout=20.0)
        except Exception:
            pass
        if self.process is not None and self.process.poll() is None:
            self._killProcess()
        self._cleanup(removeDir=True)

    # ------------------------- 内部工具 -------------------------

    def _killProcess(self):
        """强制结束服务进程树"""
        if self.process is None:
            return
        pid = self.process.pid
        try:
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=CREATE_NO_WINDOW, timeout=30)
        except Exception:
            pass
        try:
            self.process.kill()
        except Exception:
            pass
        try:
            self.process.wait(timeout=10.0)
        except Exception:
            pass

    def _readServerError(self) -> str:
        """读取服务端错误信息"""
        if not self.jobDir:
            return ''
        errorPath = os.path.join(self.jobDir, 'server_error.txt')
        text = openSafeText(errorPath)
        if text:
            return text.strip().splitlines()[-1][:300]
        return ''

    def _cleanup(self, removeDir: bool = False):
        """清理进程与任务目录引用"""
        self.process = None
        self.readyInfo = {}
        if removeDir and self.jobDir:
            shutil.rmtree(self.jobDir, ignore_errors=True)
        self.jobDir = ''
        if self.state == 'ready':
            self.state = 'stopped'


def openSafeText(filePath: str) -> str:
    """
    安全读取文本文件

    Args:
        filePath (str): 文件路径

    Returns:
        str: 文件内容，读取失败返回空字符串
    """
    try:
        with open(filePath, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception:
        return ''



class RemoteBackend:
    """
    免安装版后端。

    本模块运行在独立 Python（免安装包）中，本身不 import NXOpen；
    导出时通过 NX 自带的 `NXBIN\\run_journal.exe` 启动一个后台 NX 进程执行
    `remote_worker.py`，由 worker 在 NX 内置 Python 中调用插件导出模块，
    并通过 JSON 行日志把进度/消息/结果实时回传给本后端，最终显示在界面上。

    因此：
    - 不需要预先打开 NX；
    - 不需要在 NX 中添加命令按钮；
    - 如果用户已经打开了 NX，插件会额外启动一个独立的后台 NX 转换进程，
      不影响、也不会关闭用户已打开的 NX 会话。
    """

    supportsOpenedFiles = False
    supportsWarmEngine = True
    displayName = 'NX 后台转换'

    def __init__(self, nxRoot: str = ''):
        self.nxRoot = ''
        self.runJournalPath = ''
        self.workerScript = ''
        self.pluginDir = RemoteBackend.findPluginDir()

        if nxRoot:
            self.setNxRoot(nxRoot)
        else:
            savedRoot = self.loadSavedNxRoot()
            if savedRoot and self.setNxRoot(savedRoot):
                pass
            else:
                discovered = RemoteBackend.discoverNxRoot()
                if discovered:
                    self.setNxRoot(discovered)

        # 常驻暖机转换引擎（默认启用；用户可在界面取消勾选）
        self.warmEngineEnabled = True
        self.serverScript = os.path.join(self.pluginDir, 'remote_server.py')
        self.warmServer = WarmNxServer(self)

    # ------------------------- 资源路径 -------------------------

    @staticmethod
    def findPluginDir() -> str:
        """
        获取插件后端源码目录（worker 脚本与导出模块所在目录）

        免安装版（PyInstaller 冻结）下为解包目录中的 plugin_backend 子目录；
        源码运行时为插件目录本身。

        Returns:
            str: 目录路径
        """
        if getattr(sys, 'frozen', False):
            baseDir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            return os.path.join(baseDir, 'plugin_backend')
        return os.path.dirname(os.path.abspath(__file__))

    @staticmethod
    def getConfigPath() -> str:
        """
        获取配置文件路径（保存在 exe/插件目录下，便携）

        Returns:
            str: 配置文件路径
        """
        if getattr(sys, 'frozen', False):
            baseDir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            baseDir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(baseDir, CONFIG_FILE_NAME)

    def loadSavedNxRoot(self) -> str:
        """
        读取上次保存的 NX 安装目录

        Returns:
            str: NX 安装目录，未保存返回空字符串
        """
        try:
            with open(self.getConfigPath(), 'r', encoding='utf-8') as f:
                data = json.load(f)
            return str(data.get('nxRoot', ''))
        except Exception:
            return ''

    def saveNxRoot(self):
        """保存当前 NX 安装目录到配置文件"""
        try:
            with open(self.getConfigPath(), 'w', encoding='utf-8') as f:
                json.dump({'nxRoot': self.nxRoot}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ------------------------- NX 发现 -------------------------

    @staticmethod
    def normalizeNxRoot(root: str) -> str:
        """
        规范化 NX 安装目录（去引号/空格/末尾分隔符）

        Args:
            root (str): 用户输入或发现的目录

        Returns:
            str: 规范化后的目录
        """
        if not root:
            return ''
        root = str(root).strip().strip('"').strip("'").strip()
        root = os.path.normpath(root)
        if root.endswith(os.sep):
            root = root.rstrip(os.sep)
        return root

    @staticmethod
    def isValidNxRoot(root: str) -> bool:
        """
        判断目录是否是可用的 NX 安装目录（存在 NXBIN\\run_journal.exe）

        Args:
            root (str): NX 安装目录

        Returns:
            bool: 是否有效
        """
        if not root:
            return False
        try:
            return os.path.isfile(os.path.join(root, 'NXBIN', 'run_journal.exe'))
        except Exception:
            return False

    @staticmethod
    def discoverNxRoot() -> str:
        """
        自动发现本机 NX 安装目录（环境变量 → 注册表 → 常见安装目录，耗时 < 1 秒）

        Returns:
            str: NX 安装目录，未找到返回空字符串
        """
        # 1) 环境变量（NX 启动时通常会设置）
        for envName in ('UGII_BASE_DIR', 'UGII_ROOT_DIR'):
            root = os.environ.get(envName, '')
            if root:
                root = RemoteBackend.normalizeNxRoot(os.path.dirname(root) if envName == 'UGII_ROOT_DIR' else root)
                if RemoteBackend.isValidNxRoot(root):
                    return root

        # 2) 注册表：HKLM\\SOFTWARE\\Siemens\\NX <版本> 下的 INSTALLDIR / UGII_BASE_DIR
        try:
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    siemensKey = winreg.OpenKey(hive, r'SOFTWARE\Siemens')
                except Exception:
                    continue
                try:
                    index = 0
                    while True:
                        try:
                            subName = winreg.EnumKey(siemensKey, index)
                        except OSError:
                            break
                        index += 1
                        if not subName.upper().startswith('NX'):
                            continue
                        try:
                            subKey = winreg.OpenKey(siemensKey, subName)
                        except Exception:
                            continue
                        for valueName in ('UGII_BASE_DIR', 'INSTALLDIR', 'InstallDir'):
                            try:
                                value, _ = winreg.QueryValueEx(subKey, valueName)
                            except Exception:
                                continue
                            root = RemoteBackend.normalizeNxRoot(value)
                            if RemoteBackend.isValidNxRoot(root):
                                return root
                finally:
                    try:
                        winreg.CloseKey(siemensKey)
                    except Exception:
                        pass
        except Exception:
            pass

        # 3) 注册表卸载信息：DisplayName 形如 "Siemens NX 2412" 的 InstallLocation
        try:
            import winreg
            uninstallPaths = [
                r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
            ]
            for uninstallPath in uninstallPaths:
                try:
                    uninstallKey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, uninstallPath)
                except Exception:
                    continue
                try:
                    index = 0
                    while True:
                        try:
                            subName = winreg.EnumKey(uninstallKey, index)
                        except OSError:
                            break
                        index += 1
                        try:
                            subKey = winreg.OpenKey(uninstallKey, subName)
                            displayName, _ = winreg.QueryValueEx(subKey, 'DisplayName')
                            if 'NX' not in str(displayName).upper():
                                continue
                            installLocation, _ = winreg.QueryValueEx(subKey, 'InstallLocation')
                            root = RemoteBackend.normalizeNxRoot(installLocation)
                            if RemoteBackend.isValidNxRoot(root):
                                return root
                        except Exception:
                            continue
                finally:
                    try:
                        winreg.CloseKey(uninstallKey)
                    except Exception:
                        pass
        except Exception:
            pass

        # 4) 常见安装目录
        programDirs = [
            os.environ.get('ProgramFiles', r'C:\Program Files'),
            os.environ.get('ProgramW6432', r'C:\Program Files'),
            os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
            'D:\\Program Files',
            'D:\\',
            'C:\\',
        ]
        for programDir in programDirs:
            if not programDir:
                continue
            siemensDirs = [os.path.join(programDir, 'Siemens'), os.path.join(programDir, 'UGS')]
            for siemensDir in siemensDirs:
                try:
                    if not os.path.isdir(siemensDir):
                        continue
                    for entry in os.listdir(siemensDir):
                        root = os.path.join(siemensDir, entry)
                        if RemoteBackend.isValidNxRoot(root):
                            return root
                except Exception:
                    continue
        return ''

    def setNxRoot(self, nxRoot: str) -> bool:
        """
        设置 NX 安装目录

        Args:
            nxRoot (str): NX 安装目录（如 D:\\Program Files\\Siemens\\NX2412）

        Returns:
            bool: 是否设置成功
        """
        root = RemoteBackend.normalizeNxRoot(nxRoot)
        if not RemoteBackend.isValidNxRoot(root):
            return False
        self.nxRoot = root
        self.runJournalPath = os.path.join(root, 'NXBIN', 'run_journal.exe')
        self.workerScript = os.path.join(self.pluginDir, 'remote_worker.py')
        self.saveNxRoot()
        return True

    def isAvailable(self) -> bool:
        """
        后端是否可用（找到 NX 与 worker 脚本）

        Returns:
            bool: 是否可用
        """
        try:
            return bool(self.runJournalPath and os.path.isfile(self.runJournalPath)
                        and self.workerScript and os.path.isfile(self.workerScript))
        except Exception:
            return False

    def statusText(self) -> str:
        """
        状态栏显示文字（随常驻引擎状态动态变化）

        Returns:
            str: 状态描述
        """
        if not self.isAvailable():
            return '未找到 NX2412'
        suffix = self.warmServer.statusSuffix() if self.warmEngineEnabled else '临时启动模式'
        if suffix == '未找到 NX2412':
            return suffix
        return 'NX 后台转换（%s，%s）' % (os.path.basename(self.nxRoot), suffix)

    # ------------------------- 常驻转换引擎 -------------------------

    def isWarmEngineEnabled(self) -> bool:
        """
        是否启用常驻暖机转换引擎

        Returns:
            bool: 是否启用
        """
        return bool(self.warmEngineEnabled)

    def setWarmEngineEnabled(self, enabled: bool):
        """
        启用/禁用常驻暖机转换引擎（禁用时释放已启动的后台 NX 进程）

        Args:
            enabled (bool): 是否启用
        """
        enabled = bool(enabled)
        if enabled == self.warmEngineEnabled:
            return
        self.warmEngineEnabled = enabled
        if enabled:
            self.warmServer._shutdownRequested = False
        else:
            self.warmServer.shutdown()

    def prewarm(self):
        """异步预热常驻转换引擎（程序启动时调用，不阻塞界面）"""
        if self.warmEngineEnabled:
            # 之前调用过 shutdown 时 _shutdownRequested 可能仍为 True，这里重置以允许重新预热
            self.warmServer._shutdownRequested = False
            self.warmServer.startAsync()

    def shutdown(self):
        """停止常驻转换引擎（窗口关闭时调用，释放后台 NX 进程）"""
        try:
            self.warmServer.shutdown()
        except Exception:
            pass

    # ------------------------- 文件收集 -------------------------

    def selectFiles(self) -> list:
        """
        选择 NX 文件

        Returns:
            list[str]: NX 文件路径列表
        """
        from tkinter import filedialog
        files = filedialog.askopenfilenames(
            title='选择 NX 文件',
            filetypes=[('NX 文件', '*.prt')]
        )
        return list(files or [])

    def getFilesFromFolder(self, recursive: bool = False) -> list:
        """
        从选择的文件夹获取 NX 文件

        Args:
            recursive (bool): 是否递归子文件夹

        Returns:
            list[str]: NX 文件路径列表
        """
        from tkinter import filedialog
        folder = filedialog.askdirectory(title='选择包含 NX 文件的文件夹')
        if not folder:
            return []
        prts = []
        try:
            if recursive:
                for root, dirs, files in os.walk(folder):
                    for fileName in files:
                        if fileName.lower().endswith('.prt'):
                            prts.append(os.path.join(root, fileName))
            else:
                for fileName in os.listdir(folder):
                    if fileName.lower().endswith('.prt'):
                        prts.append(os.path.join(folder, fileName))
        except Exception:
            return []
        return prts

    def getOpenedFiles(self) -> list:
        """
        免安装版无法读取另一个 NX 会话的已打开文件

        Returns:
            list: 空列表
        """
        return []

    def getWorkFile(self) -> list:
        """
        免安装版无法读取另一个 NX 会话的工作部件

        Returns:
            list: 空列表
        """
        return []

    # ------------------------- 导出 -------------------------

    def exportDrawings(self, kinds: list, prtList: list, prefixName: str = '', suffixName: str = '',
                       folder: str = '', writeMsg=None, progress=None, skipExisting: bool = False) -> dict:
        """
        批量导出图纸（PDF / DWG，在后台 NX 进程中执行）

        Args:
            kinds (list[str]): 导出格式列表（'pdf' / 'dwg' 的子集，按顺序执行）
            prtList (list[str]): NX 图纸文件路径列表
            prefixName (str): 文件名前缀
            suffixName (str): 文件名后缀
            folder (str): 输出文件夹
            writeMsg (function): 消息输出函数
            progress (function): 进度回调
            skipExisting (bool): 是否跳过已存在的同名文件

        Returns:
            dict: 任务统计结果
        """
        job = {
            'kind': 'drawings',
            'kinds': [str(kind) for kind in (kinds or [])],
            'files': [os.path.normpath(path) for path in (prtList or [])],
            'prefix': prefixName,
            'suffix': suffixName,
            'folder': folder,
            'skipExisting': bool(skipExisting),
        }
        return self._runJobAuto(job, writeMsg, progress)

    def exportModels(self, prtList: list, prefixName: str = '', suffixName: str = '',
                     folder: str = '', options=None, writeMsg=None, progress=None) -> dict:
        """
        批量导出模型（XT / STP，在后台 NX 进程中执行）

        Args:
            prtList (list[str]): 部件文件路径列表
            prefixName (str): 文件名前缀
            suffixName (str): 文件名后缀
            folder (str): 输出文件夹
            options (ModelExportOptions): 导出选项
            writeMsg (function): 消息输出函数
            progress (function): 进度回调

        Returns:
            dict: 任务统计结果
        """
        job = {
            'kind': 'models',
            'files': [os.path.normpath(path) for path in (prtList or [])],
            'prefix': prefixName,
            'suffix': suffixName,
            'folder': folder,
            'options': {
                'formats': list(getattr(options, 'formats', []) or []),
                'stepSchema': getattr(options, 'stepSchema', 'ap214'),
                'xtVersion': getattr(options, 'xtVersion', 'current'),
                'flattenAssembly': bool(getattr(options, 'flattenAssembly', False)),
                'skipExisting': bool(getattr(options, 'skipExisting', False)),
            },
        }
        return self._runJobAuto(job, writeMsg, progress)

    def runJobAuto(self, job: dict, writeMsg=None, progress=None) -> dict:
        """
        公开的任务执行入口：优先常驻暖机引擎，失败自动回退一次性启动（供 CLI 等调用）

        Args:
            job (dict): 作业描述
            writeMsg (function): 消息回调
            progress (function): 进度回调

        Returns:
            dict: 任务统计结果
        """
        return self._runJobAuto(job, writeMsg, progress)

    def _runJobAuto(self, job: dict, writeMsg=None, progress=None) -> dict:
        """
        执行后台作业：优先使用常驻暖机引擎；未启用或不可用时回退一次性启动

        Args:
            job (dict): 作业描述
            writeMsg (function): 消息回调
            progress (function): 进度回调

        Returns:
            dict: 任务统计结果
        """
        if writeMsg is None:
            def writeMsg(msg, level='info'):
                pass

        if not self.warmEngineEnabled:
            return self.runJob(job, writeMsg, progress)

        result = self.warmServer.submit(job, writeMsg, progress)
        if result is not None:
            return result
        writeMsg('  [!] 常驻 NX 转换引擎不可用，改为临时启动 NX 后台进程（本次会更慢）', 'warn')
        return self.runJob(job, writeMsg, progress)

    def mergePdfs(self, outputFilename: str, inputFiles: list, writeMsg=None):
        """
        合并 PDF（本地完成，无需 NX）

        Args:
            outputFilename (str): 输出文件名
            inputFiles (list[str]): 输入 PDF 文件列表
            writeMsg (function): 消息输出函数
        """
        from pdfmodules import PdfModules
        return PdfModules.mergePdfs(outputFilename, inputFiles, writeMsg)

    # ------------------------- 后台作业执行 -------------------------

    def runJob(self, job: dict, writeMsg=None, progress=None) -> dict:
        """
        启动后台 NX 进程执行导出作业，并实时回传日志/进度

        Args:
            job (dict): 作业描述（见 exportDrawings / exportModels）
            writeMsg (function): 消息输出函数，签名 writeMsg(msg, level='info')
            progress (function): 进度回调，签名 progress(done, total)

        Returns:
            dict: {'success': int, 'failed': int, 'skipped': int, 'total': int, 'elapsed': float}
        """
        emptyResult = {'success': 0, 'failed': 0, 'skipped': 0, 'total': 0, 'elapsed': 0.0}
        if writeMsg is None:
            def writeMsg(msg, level='info'):
                pass
        if not self.isAvailable():
            writeMsg('  [✘] 未找到 NX2412。请确认已安装 NX 2412，或在状态栏中手动选择 NX 安装目录', 'error')
            return emptyResult

        jobDir = tempfile.mkdtemp(prefix='nx_batch_export_')
        jobPath = os.path.join(jobDir, 'job.json')
        logPath = os.path.join(jobDir, 'worker.log')
        job = dict(job)
        job['pluginDir'] = self.pluginDir
        job['nxRoot'] = self.nxRoot
        try:
            with open(jobPath, 'w', encoding='utf-8') as f:
                json.dump(job, f, ensure_ascii=False)
            with open(logPath, 'w', encoding='utf-8') as f:
                f.write('')
        except Exception as e:
            writeMsg('  [✘] 无法创建后台任务文件：{0}'.format(e), 'error')
            return emptyResult

        env = os.environ.copy()
        env['DSH_NX_JOB'] = jobPath
        env['DSH_NX_LOG'] = logPath
        env['DSH_PLUGIN_DIR'] = self.pluginDir
        env['UGII_BASE_DIR'] = self.nxRoot

        writeMsg('  [i] 正在临时启动 NX2412 后台转换引擎（约 10~25 秒；勾选「使用 NX 后台转换引擎」可复用常驻进程，避免每次等待）...')
        try:
            process = subprocess.Popen(
                [self.runJournalPath, self.workerScript],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW)
        except Exception as e:
            writeMsg('  [✘] 无法启动 NX2412 后台进程：{0}'.format(e), 'error')
            return emptyResult

        result = emptyResult
        lineIndex = 0
        startTime = time.time()
        returnCode = None
        done = False

        while True:
            lines = self._readLogLines(logPath)
            for line in lines[lineIndex:]:
                line = line.strip()
                if not line:
                    continue
                if line.startswith('[MSG] '):
                    payload = self._safeJson(line[6:])
                    if isinstance(payload, dict):
                        writeMsg(str(payload.get('msg', '')), str(payload.get('level', 'info')))
                elif line.startswith('[PROGRESS] '):
                    payload = self._safeJson(line[11:])
                    if isinstance(payload, dict) and progress is not None:
                        try:
                            progress(int(payload.get('done', 0)), int(payload.get('total', 0)))
                        except Exception:
                            pass
                elif line.startswith('[RESULT] '):
                    payload = self._safeJson(line[9:])
                    if isinstance(payload, dict):
                        result = payload
                elif line.startswith('[DONE]'):
                    done = True
            lineIndex = len(lines)

            returnCode = process.poll()
            if returnCode is not None:
                # 进程已退出，再读一次日志确保收尾消息完整
                lines = self._readLogLines(logPath)
                for line in lines[lineIndex:]:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith('[MSG] '):
                        payload = self._safeJson(line[6:])
                        if isinstance(payload, dict):
                            writeMsg(str(payload.get('msg', '')), str(payload.get('level', 'info')))
                    elif line.startswith('[RESULT] '):
                        payload = self._safeJson(line[9:])
                        if isinstance(payload, dict):
                            result = payload
                    elif line.startswith('[DONE]'):
                        done = True
                break

            if time.time() - startTime > JOB_TIMEOUT_SECONDS:
                writeMsg('  [✘] 后台 NX 任务超时，已终止', 'error')
                try:
                    process.kill()
                except Exception:
                    pass
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        if returnCode not in (None, 0):
            writeMsg('  [✘] NX 后台进程异常退出（返回码 {0}），请检查是否已安装/授权 NX2412'.format(returnCode), 'error')
        if not done and returnCode == 0:
            writeMsg('  [!] NX 后台进程已退出，但未收到任务完成标记，结果可能不完整', 'warn')

        try:
            os.remove(jobPath)
        except Exception:
            pass
        return result

    @staticmethod
    def _safeJson(text: str):
        """
        安全解析 JSON

        Args:
            text (str): JSON 文本

        Returns:
            dict | None: 解析结果，失败返回 None
        """
        try:
            return json.loads(text)
        except Exception:
            return None

    @staticmethod
    def _readLogLines(logPath: str) -> list:
        """
        读取后台日志全部行

        Args:
            logPath (str): 日志文件路径

        Returns:
            list[str]: 日志行列表
        """
        try:
            with open(logPath, 'r', encoding='utf-8', errors='replace') as f:
                return f.read().splitlines()
        except Exception:
            return []
