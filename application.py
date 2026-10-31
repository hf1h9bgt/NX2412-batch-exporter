"""
file: application.py
description: 图形界面
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
import builtins
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# 兼容独立运行（免安装 exe / 系统 Python 直接 import application）：
# 在 NX 内由 NX-batch-PDF-exporter.py 先调用 language.init_i18n()，此处不会重复初始化。
if not hasattr(builtins, '_'):
    try:
        from language import init_i18n
        init_i18n()
    except Exception:
        builtins._ = lambda msg: msg

from listshow import ListShow
from pluginoptions import ModelExportOptions, ModelFormat, StepSchema, XtVersion, filterPrts
from backend_direct import DirectBackend
from remote_backend import RemoteBackend
import version

programName = _('Siemens NX2412 批量导出工具')
baseDir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
tclDir = os.path.join(baseDir, 'tcl', 'tcl8.6')


def _isRunningInNx() -> bool:
    """
    判断当前是否运行在 NX 内置 Python 中

    插件目录自带的 tcl（8.6.12，提取自 NX）只适用于 NX 内置的 Tk；
    便携版/系统 Python 的 Tk 版本不同（如 8.6.15），若强行设置 TCL_LIBRARY
    会与插件目录的 tcl 版本冲突导致 tkinter 启动失败，因此只在 NX 中设置。

    Returns:
        bool: 是否运行在 NX 内置 Python 中
    """
    try:
        exeName = os.path.basename(sys.executable).lower()
        exeDir = os.path.dirname(os.path.abspath(sys.executable)).lower()
        return exeName in ('ugraf.exe', 'run_journal.exe', 'nx.exe') or 'nxbin' in exeDir
    except Exception:
        return False


if os.path.isdir(tclDir) and _isRunningInNx():
    # 插件目录内置的 tcl 供 NX 内置 Python 使用；便携版/冻结 exe 使用自带的 Tcl
    os.environ["TCL_LIBRARY"] = tclDir

# 界面字体（Windows 自带中文字体，保证中英文混排清晰）
uiFontFamily = 'Microsoft YaHei UI'
uiFontSize = 9

# 日志消息级别
logLevels = ('info', 'success', 'warn', 'error')

# XT 版本选项（显示文本, XtVersion 枚举值）
xtVersionOptions = [
    (_('当前版本 (推荐)'), XtVersion.CURRENT.value),
    (_('NX 2406'), XtVersion.NX2406.value),
    (_('NX 2306'), XtVersion.NX2306.value),
    (_('NX 2206'), XtVersion.NX2206.value),
    (_('NX 2007'), XtVersion.NX2007.value),
    (_('NX 12'), XtVersion.NX12.value),
]

# STP 协议选项（显示文本, StepSchema 枚举值）
stepSchemaOptions = [
    (_('AP203'), StepSchema.AP203.value),
    (_('AP214 (推荐)'), StepSchema.AP214.value),
    (_('AP242'), StepSchema.AP242.value),
]

# 启动横幅（三个页签日志各写一份，版本号取 version.V）
bannerLines = [
    _('{programName} {version}'),
    _('本工具参考开源项目，发布地址：https://github.com/IYATT-yx/NX-batch-PDF-exporter；在该项目基础上进行修改，新增批量导出 xt/stp 功能、更改 UI 界面及部分优化；'),
    _('修改用 AI 智能体为 DEEPSEEK HARNESS  DEEPSEEK-V4.1 Flash1017 创造模式；'),
]


class Application(tk.Frame):
    def __init__(self, root: tk.Tk, backend=None):
        """
        图形界面

        Args:
            root (tk.Tk): 根窗口
            backend (optional): 导出后端（backend_direct.DirectBackend / remote_backend.RemoteBackend），
                为空时默认使用 NX 内直连后端
        """
        super().__init__(root)
        self.root = root
        self.pack(fill=tk.BOTH, expand=True)

        # 后端注入：NX 内默认直连；若直连不可用（如系统 Python 无 NXOpen）则退回后台转换模式
        self.backendFallbackError = ''
        if backend is None:
            try:
                self.backend = DirectBackend()
            except Exception as e:
                self.backendFallbackError = str(e)
                self.backend = RemoteBackend()
        else:
            self.backend = backend
        self.supportsOpenedFiles = bool(getattr(self.backend, 'supportsOpenedFiles', True))
        # 是否支持「常驻暖机 NX 后台转换引擎」（免安装版支持；NX 内直连不支持）
        self.supportsWarmEngine = bool(getattr(self.backend, 'supportsWarmEngine', False))

        self.msgText = None
        self.lastOutputFolder = ''  # 最近一次的输出文件夹，用于「打开输出文件夹」
        self.taskTotal = 1
        self.tabMsgTexts = {}
        self.openedFilesButtons = []  # 「所有打开文件」按钮
        self.workFileButtons = []     # 「工作部件」按钮
        self.panelCanvases = []       # 三个页签右侧滚动控制区的 Canvas
        self.panelScrollbars = []     # 三个页签右侧滚动控制区的垂直滚动条

        # 免安装版「使用 NX 后台转换引擎」选项
        self.warmEngineValue = tk.BooleanVar(self, value=True)
        self.warmEngineFrame = None
        self.warmEngineCheckbutton = None
        self.warmEngineNoteLabel = None
        self._prewarmDone = False
        self._enginePollAfterId = None
        self._lastBackendStatus = ''

        # 下拉框显示文本 <-> 枚举值
        self.xtVersionLabels = [label for label, value in xtVersionOptions]
        self.xtVersionValues = {label: value for label, value in xtVersionOptions}
        self.stpSchemaLabels = [label for label, value in stepSchemaOptions]
        self.stpSchemaValues = {label: value for label, value in stepSchemaOptions}

        self.initStyle()
        self.createWidgets()

        self._lastBackendStatus = self._getBackendStatusText()

        # 窗口关闭时先释放常驻后台转换引擎，再销毁窗口
        try:
            self.root.protocol('WM_DELETE_WINDOW', self.onCloseWindow)
        except tk.TclError:
            pass

        # 免安装版：延迟预热常驻 NX 转换引擎 + 定时刷新转换引擎状态
        if self.supportsWarmEngine:
            self.after(300, self._prewarmEngine)
            self.after(800, self._pollEngineState)

    def initStyle(self):
        """
        初始化界面风格
        """
        self.style = ttk.Style(self)
        for themeName in ('vista', 'winnative', 'clam'):
            try:
                self.style.theme_use(themeName)
                break
            except tk.TclError:
                continue

        self.uiFont = (uiFontFamily, uiFontSize)
        self.logFont = (uiFontFamily, uiFontSize)
        self.style.configure('.', font=self.uiFont)
        self.style.configure('TButton', padding=(6, 2))
        self.style.configure('Accent.TButton', font=(uiFontFamily, uiFontSize + 1, 'bold'), padding=(8, 5))
        self.style.configure('Treeview', rowheight=24)
        self.style.configure('Treeview.Heading', font=(uiFontFamily, uiFontSize, 'bold'))

    def createWidgets(self):
        """
        创建组件
        """
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky=tk.NSEW, padx=8, pady=(5, 0))

        # 图纸导出页
        self.drawingTab = ttk.Frame(self.notebook, padding=6)
        self.createDrawingTab(self.drawingTab)
        self.notebook.add(self.drawingTab, text=_('图纸导出 (PDF/DWG)'))

        # 模型导出页
        self.modelTab = ttk.Frame(self.notebook, padding=6)
        self.createModelTab(self.modelTab)
        self.notebook.add(self.modelTab, text=_('模型导出 (XT/STP)'))

        # 合并 PDF 页
        self.mergePdfTab = ttk.Frame(self.notebook, padding=6)
        self.createMergePdfTab(self.mergePdfTab)
        self.notebook.add(self.mergePdfTab, text=_('合并 PDF'))

        # 各页日志文本框与消息路由
        self.tabMsgTexts = {
            self.drawingTab: self.prtMsgText,
            self.modelTab: self.modelMsgText,
            self.mergePdfTab: self.pdfMsgText,
        }
        self.msgText = self.prtMsgText
        self.notebook.bind('<<NotebookTabChanged>>', self.onTabChanged)

        # 每个页签的日志区都写入启动横幅，避免切换页签后日志区空白
        banner = '\n'.join(line.format(programName=programName, version=version.V) for line in bannerLines)
        for textWidget in self.tabMsgTexts.values():
            self._appendText(textWidget, banner)

        # 免安装版「使用 NX 后台转换引擎」全局选项（NX 内直连模式不显示）
        self.createWarmEngineOption()

        # 底部全局状态栏
        self.createStatusBar()

        # 刷新转换引擎状态与启动提示（已打开文件/工作部件按钮保持可点击，点击时提示）
        self._updateBackendStatus()
        self._writeBackendStartupLog()

    def _createTabSkeleton(self, parent: ttk.Frame):
        """
        创建页面骨架：左侧文件列表区 + 右侧可滚动操作区 + 底部日志区

        Args:
            parent (ttk.Frame): 页面容器

        Returns:
            tuple: (列表容器, 操作区内部容器, 操作区 Canvas, 日志文本框)
        """
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=3)
        parent.rowconfigure(1, weight=1)

        listFrame = ttk.LabelFrame(parent, text=_('文件列表'), padding=4)
        listFrame.grid(row=0, column=0, sticky=tk.NSEW)
        listFrame.rowconfigure(0, weight=1)
        listFrame.columnconfigure(0, weight=1)

        controlFrame, controlCanvas = self._createScrollablePanel(parent)

        logFrame = ttk.LabelFrame(parent, text=_('运行日志'), padding=4)
        logFrame.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW, pady=(5, 0))
        logFrame.rowconfigure(0, weight=1)
        logFrame.columnconfigure(0, weight=1)

        logText = tk.Text(logFrame, wrap=tk.CHAR, height=7, state=tk.DISABLED, font=self.logFont, bd=1, relief=tk.SOLID, padx=4, pady=2)
        logText.grid(row=0, column=0, sticky=tk.NSEW)
        logScrollbar = ttk.Scrollbar(logFrame, orient=tk.VERTICAL, command=logText.yview)
        logText.configure(yscrollcommand=logScrollbar.set)
        logScrollbar.grid(row=0, column=1, sticky=tk.NS)
        self._config_text_tags(logText)

        return listFrame, controlFrame, controlCanvas, logText

    def _createScrollablePanel(self, parent: ttk.Frame):
        """
        创建可滚动的右侧操作区（Canvas + 内部 Frame + 垂直滚动条 + 鼠标滚轮）

        Args:
            parent (ttk.Frame): 页面容器

        Returns:
            tuple: (内部容器 Frame, Canvas)
        """
        wrapper = ttk.Frame(parent)
        wrapper.grid(row=0, column=1, sticky=tk.NS, padx=(8, 0))
        wrapper.rowconfigure(0, weight=1)
        wrapper.columnconfigure(0, weight=1)

        canvasBackground = '#F0F0F0'
        try:
            canvasBackground = self.style.lookup('TFrame', 'background') or canvasBackground
        except tk.TclError:
            pass

        canvas = tk.Canvas(wrapper, width=370, highlightthickness=0, bd=0, background=canvasBackground, yscrollincrement=20)
        canvas.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar = ttk.Scrollbar(wrapper, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        canvas.configure(yscrollcommand=scrollbar.set)

        innerFrame = ttk.Frame(canvas)
        innerFrame.columnconfigure(0, weight=1)
        windowId = canvas.create_window((0, 0), window=innerFrame, anchor=tk.NW, width=370)

        def onInnerConfigure(event):
            canvas.configure(scrollregion=canvas.bbox('all'))
            self._updatePanelScrollbar(canvas, scrollbar, innerFrame)

        def onCanvasConfigure(event):
            canvas.itemconfigure(windowId, width=event.width)
            self._updatePanelScrollbar(canvas, scrollbar, innerFrame)

        innerFrame.bind('<Configure>', onInnerConfigure)
        canvas.bind('<Configure>', onCanvasConfigure)

        self.panelCanvases.append(canvas)
        self.panelScrollbars.append(scrollbar)
        return innerFrame, canvas

    def _updatePanelScrollbar(self, canvas: tk.Canvas, scrollbar: ttk.Scrollbar, innerFrame: ttk.Frame):
        """
        根据内容高度显示/隐藏滚动条；内容不超出时隐藏滚动条并回到顶部

        Args:
            canvas (tk.Canvas): 滚动区 Canvas
            scrollbar (ttk.Scrollbar): 垂直滚动条
            innerFrame (ttk.Frame): 内部容器
        """
        visibleHeight = canvas.winfo_height()
        if visibleHeight <= 1:
            return
        if innerFrame.winfo_reqheight() > visibleHeight:
            scrollbar.grid()
        else:
            scrollbar.grid_remove()
            canvas.yview_moveto(0)

    def _bindPanelMouseWheel(self, canvas: tk.Canvas, widget):
        """
        给滚动控制区及其所有子组件绑定鼠标滚轮事件

        Args:
            canvas (tk.Canvas): 滚动区 Canvas
            widget: 需要绑定事件的组件
        """
        widget.bind('<MouseWheel>', lambda event, canvas=canvas: self._onPanelMouseWheel(event, canvas))
        for child in widget.winfo_children():
            self._bindPanelMouseWheel(canvas, child)

    def _onPanelMouseWheel(self, event: tk.Event, canvas: tk.Canvas):
        """
        控制区鼠标滚轮事件：滚动右侧操作区

        Args:
            event (tk.Event): 事件对象
            canvas (tk.Canvas): 滚动区 Canvas

        Returns:
            str: 'break'，阻止 Combobox 等组件响应滚轮
        """
        delta = getattr(event, 'delta', 0)
        if delta == 0:
            return 'break'
        notches = int(delta / 120)
        if notches == 0:
            notches = 1 if delta > 0 else -1
        canvas.yview_scroll(-notches, 'units')
        return 'break'

    def _config_text_tags(self, textWidget: tk.Text):
        """
        配置 Text 组件的颜色标签

        Args:
            textWidget (tk.Text): 日志文本框
        """
        textWidget.tag_config('info', foreground='#202020')     # 普通消息
        textWidget.tag_config('success', foreground='#0E7A0D')  # 成功消息
        textWidget.tag_config('warn', foreground='#B36B00')     # 警告消息
        textWidget.tag_config('error', foreground='#C00000')    # 错误消息

    def createDrawingTab(self, parent: ttk.Frame):
        """
        创建图纸导出页面（PDF / DWG）

        Args:
            parent (ttk.Frame): 父组件
        """
        listFrame, controlFrame, controlCanvas, prtMsgText = self._createTabSkeleton(parent)
        self.prtMsgText = prtMsgText

        self.prtListShow = ListShow(listFrame, heading3=_('NX 文件路径'))
        self.prtListShow.grid(row=0, column=0, sticky=tk.NSEW)

        # ---- 文件收集 ----
        collectFrame = ttk.LabelFrame(controlFrame, text=_('文件收集'), padding=(6, 3))
        collectFrame.grid(row=0, column=0, sticky=tk.EW)
        for column in range(3):
            collectFrame.columnconfigure(column, weight=1)

        self.prtRecursiveValue = tk.BooleanVar(parent, value=False)
        ttk.Button(collectFrame, text=_('选择文件'), command=self.onGetSelectedPrts).grid(row=0, column=0, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Button(collectFrame, text=_('选择文件夹'), command=self.onGetPrtsFromSelectedFolder).grid(row=0, column=1, sticky=tk.EW, padx=(0, 4), pady=1)
        self.openedFilesButtons.append(ttk.Button(collectFrame, text=_('所有打开文件'), command=self.onGetOpenedPrts))
        self.openedFilesButtons[-1].grid(row=0, column=2, sticky=tk.EW, pady=1)
        self.workFileButtons.append(ttk.Button(collectFrame, text=_('工作部件'), command=self.onWorkPrt))
        self.workFileButtons[-1].grid(row=1, column=0, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Button(collectFrame, text=_('移除选中'), command=self.onRemoveSelectedPrts).grid(row=1, column=1, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Button(collectFrame, text=_('清空显示'), command=self.onClearPrts).grid(row=1, column=2, sticky=tk.EW, pady=1)
        ttk.Checkbutton(collectFrame, text=_('递归子文件夹'), variable=self.prtRecursiveValue).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(1, 0))

        self.drawingFilterValue = tk.BooleanVar(parent, value=True)
        ttk.Checkbutton(collectFrame, text=_('仅添加文件名含 dwg 的图纸文件'), variable=self.drawingFilterValue).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(1, 0))

        # ---- 导出状态设置 ----
        statusFrame = ttk.LabelFrame(controlFrame, text=_('导出状态设置'), padding=(6, 3))
        statusFrame.grid(row=1, column=0, sticky=tk.EW, pady=(5, 0))
        statusFrame.columnconfigure(0, weight=1)
        statusFrame.columnconfigure(2, weight=1)

        self.selectedPrtStatusValue = tk.BooleanVar(parent, value=True)
        ttk.Button(statusFrame, text=_('设置选中项'), command=self.onSetSelectedPrtStatus).grid(row=0, column=0, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Checkbutton(statusFrame, text=_('导出'), variable=self.selectedPrtStatusValue).grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
        self.allPrtStatusValue = tk.BooleanVar(parent, value=True)
        ttk.Button(statusFrame, text=_('设置所有'), command=self.onSetAllPrtStatus).grid(row=0, column=2, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Checkbutton(statusFrame, text=_('导出'), variable=self.allPrtStatusValue).grid(row=0, column=3, sticky=tk.W)

        # ---- 输出选项 ----
        outputFrame = ttk.LabelFrame(controlFrame, text=_('输出选项（文件夹留空 = 输出到源文件所在目录）'), padding=(6, 3))
        outputFrame.grid(row=2, column=0, sticky=tk.EW, pady=(5, 0))
        outputFrame.columnconfigure(1, weight=1)

        self.exportFolderValue = tk.StringVar(parent, value='')
        ttk.Label(outputFrame, text=_('导出文件夹')).grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(outputFrame, textvariable=self.exportFolderValue, width=22).grid(row=0, column=1, sticky=tk.EW, padx=4)
        ttk.Button(outputFrame, text=_('选择'), command=self.onSelectExportFolder).grid(row=0, column=2, sticky=tk.E)

        self.prefixNameValue = tk.StringVar(parent, value='')
        ttk.Label(outputFrame, text=_('文件名前缀')).grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(outputFrame, textvariable=self.prefixNameValue, width=22).grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=4)

        self.suffixNameValue = tk.StringVar(parent, value='')
        ttk.Label(outputFrame, text=_('文件名后缀')).grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(outputFrame, textvariable=self.suffixNameValue, width=22).grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=4)

        self.skipExistingValue = tk.BooleanVar(parent, value=False)
        ttk.Checkbutton(outputFrame, text=_('跳过已存在的同名文件'), variable=self.skipExistingValue).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(1, 0))

        # ---- 导出格式（PDF / DWG 可同时勾选） ----
        formatFrame = ttk.LabelFrame(controlFrame, text=_('导出格式（可同时勾选）'), padding=(6, 3))
        formatFrame.grid(row=3, column=0, sticky=tk.EW, pady=(5, 0))
        self.pdfFormatValue = tk.BooleanVar(parent, value=True)
        self.dwgFormatValue = tk.BooleanVar(parent, value=True)
        ttk.Checkbutton(formatFrame, text=_('PDF(.pdf)'), variable=self.pdfFormatValue).grid(row=0, column=0, sticky=tk.W, padx=(0, 16))
        ttk.Checkbutton(formatFrame, text=_('DWG(.dwg)'), variable=self.dwgFormatValue).grid(row=0, column=1, sticky=tk.W)

        # ---- 导出按钮 ----
        self.exportButton = ttk.Button(controlFrame, text=_('开始导出'), command=self.onExport, style='Accent.TButton')
        self.exportButton.grid(row=4, column=0, sticky=tk.EW, pady=(8, 0))

        self._bindPanelMouseWheel(controlCanvas, controlFrame)

    def createModelTab(self, parent: ttk.Frame):
        """
        创建模型导出页面（XT / STP）

        Args:
            parent (ttk.Frame): 父组件
        """
        listFrame, controlFrame, controlCanvas, modelMsgText = self._createTabSkeleton(parent)
        self.modelMsgText = modelMsgText

        self.modelListShow = ListShow(listFrame, heading3=_('模型文件路径'))
        self.modelListShow.grid(row=0, column=0, sticky=tk.NSEW)

        # ---- 文件收集 ----
        collectFrame = ttk.LabelFrame(controlFrame, text=_('文件收集'), padding=(6, 3))
        collectFrame.grid(row=0, column=0, sticky=tk.EW)
        for column in range(3):
            collectFrame.columnconfigure(column, weight=1)

        self.modelRecursiveValue = tk.BooleanVar(parent, value=False)
        ttk.Button(collectFrame, text=_('选择文件'), command=self.onGetSelectedModelPrts).grid(row=0, column=0, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Button(collectFrame, text=_('选择文件夹'), command=self.onGetModelPrtsFromSelectedFolder).grid(row=0, column=1, sticky=tk.EW, padx=(0, 4), pady=1)
        self.openedFilesButtons.append(ttk.Button(collectFrame, text=_('所有打开文件'), command=self.onGetOpenedModelPrts))
        self.openedFilesButtons[-1].grid(row=0, column=2, sticky=tk.EW, pady=1)
        self.workFileButtons.append(ttk.Button(collectFrame, text=_('工作部件'), command=self.onWorkModelPrt))
        self.workFileButtons[-1].grid(row=1, column=0, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Button(collectFrame, text=_('移除选中'), command=self.onRemoveSelectedModelPrts).grid(row=1, column=1, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Button(collectFrame, text=_('清空显示'), command=self.onClearModelPrts).grid(row=1, column=2, sticky=tk.EW, pady=1)
        ttk.Checkbutton(collectFrame, text=_('递归子文件夹'), variable=self.modelRecursiveValue).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(1, 0))

        self.modelFilterValue = tk.BooleanVar(parent, value=True)
        ttk.Checkbutton(collectFrame, text=_('排除文件名含 dwg 的图纸文件'), variable=self.modelFilterValue).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(1, 0))

        # ---- 导出状态设置 ----
        statusFrame = ttk.LabelFrame(controlFrame, text=_('导出状态设置'), padding=(6, 3))
        statusFrame.grid(row=1, column=0, sticky=tk.EW, pady=(5, 0))
        statusFrame.columnconfigure(0, weight=1)
        statusFrame.columnconfigure(2, weight=1)

        self.selectedModelStatusValue = tk.BooleanVar(parent, value=True)
        ttk.Button(statusFrame, text=_('设置选中项'), command=self.onSetSelectedModelStatus).grid(row=0, column=0, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Checkbutton(statusFrame, text=_('导出'), variable=self.selectedModelStatusValue).grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
        self.allModelStatusValue = tk.BooleanVar(parent, value=True)
        ttk.Button(statusFrame, text=_('设置所有'), command=self.onSetAllModelStatus).grid(row=0, column=2, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Checkbutton(statusFrame, text=_('导出'), variable=self.allModelStatusValue).grid(row=0, column=3, sticky=tk.W)

        # ---- 输出选项 ----
        outputFrame = ttk.LabelFrame(controlFrame, text=_('输出选项（文件夹留空 = 输出到源文件所在目录）'), padding=(6, 3))
        outputFrame.grid(row=2, column=0, sticky=tk.EW, pady=(5, 0))
        outputFrame.columnconfigure(1, weight=1)

        self.modelExportFolderValue = tk.StringVar(parent, value='')
        ttk.Label(outputFrame, text=_('导出文件夹')).grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(outputFrame, textvariable=self.modelExportFolderValue, width=22).grid(row=0, column=1, sticky=tk.EW, padx=4)
        ttk.Button(outputFrame, text=_('选择'), command=self.onSelectModelExportFolder).grid(row=0, column=2, sticky=tk.E)

        self.modelPrefixNameValue = tk.StringVar(parent, value='')
        ttk.Label(outputFrame, text=_('文件名前缀')).grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(outputFrame, textvariable=self.modelPrefixNameValue, width=22).grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=4)

        self.modelSuffixNameValue = tk.StringVar(parent, value='')
        ttk.Label(outputFrame, text=_('文件名后缀')).grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(outputFrame, textvariable=self.modelSuffixNameValue, width=22).grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=4)

        self.modelSkipExistingValue = tk.BooleanVar(parent, value=False)
        ttk.Checkbutton(outputFrame, text=_('跳过已存在的同名文件'), variable=self.modelSkipExistingValue).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(1, 0))

        # ---- 导出格式 ----
        formatFrame = ttk.LabelFrame(controlFrame, text=_('导出格式'), padding=(6, 3))
        formatFrame.grid(row=3, column=0, sticky=tk.EW, pady=(5, 0))
        formatFrame.columnconfigure(2, weight=1)

        self.xtFormatValue = tk.BooleanVar(parent, value=True)
        self.stpFormatValue = tk.BooleanVar(parent, value=True)
        self.xtVersionValue = tk.StringVar(parent, value=xtVersionOptions[0][0])
        self.stpSchemaValue = tk.StringVar(parent, value=stepSchemaOptions[1][0])

        ttk.Checkbutton(formatFrame, text=_('XT (.x_t)'), variable=self.xtFormatValue).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(formatFrame, text=_('XT 版本')).grid(row=0, column=1, sticky=tk.E, padx=(8, 4))
        ttk.Combobox(formatFrame, textvariable=self.xtVersionValue, values=self.xtVersionLabels, state='readonly', width=16).grid(row=0, column=2, sticky=tk.EW)

        ttk.Checkbutton(formatFrame, text=_('STP (.stp)'), variable=self.stpFormatValue).grid(row=1, column=0, sticky=tk.W)
        ttk.Label(formatFrame, text=_('STP 协议')).grid(row=1, column=1, sticky=tk.E, padx=(8, 4))
        ttk.Combobox(formatFrame, textvariable=self.stpSchemaValue, values=self.stpSchemaLabels, state='readonly', width=16).grid(row=1, column=2, sticky=tk.EW)

        self.flattenAssemblyValue = tk.BooleanVar(parent, value=False)
        ttk.Checkbutton(formatFrame, text=_('装配体扁平化（导出为单一实体）'), variable=self.flattenAssemblyValue).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(1, 0))

        # ---- 导出按钮 ----
        self.modelExportButton = ttk.Button(controlFrame, text=_('开始导出模型'), command=self.onExportModels, style='Accent.TButton')
        self.modelExportButton.grid(row=4, column=0, sticky=tk.EW, pady=(8, 0))

        self._bindPanelMouseWheel(controlCanvas, controlFrame)

    def createMergePdfTab(self, parent: ttk.Frame):
        """
        创建合并 PDF 页面

        Args:
            parent (ttk.Frame): 父组件
        """
        listFrame, controlFrame, controlCanvas, pdfMsgText = self._createTabSkeleton(parent)
        self.pdfMsgText = pdfMsgText

        self.pdfListShow = ListShow(listFrame, heading2=_('合并'), heading3=_('PDF 文件路径'))
        self.pdfListShow.grid(row=0, column=0, sticky=tk.NSEW)

        # ---- 文件收集 ----
        collectFrame = ttk.LabelFrame(controlFrame, text=_('文件收集'), padding=(6, 3))
        collectFrame.grid(row=0, column=0, sticky=tk.EW)
        collectFrame.columnconfigure(0, weight=1)
        collectFrame.columnconfigure(1, weight=1)

        ttk.Button(collectFrame, text=_('打开文件'), command=self.onOpenPdfs).grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=1)
        ttk.Button(collectFrame, text=_('移除选中'), command=self.onRemoveSelectedPdfs).grid(row=1, column=0, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Button(collectFrame, text=_('清空显示'), command=self.onClearPdfs).grid(row=1, column=1, sticky=tk.EW, pady=1)

        # ---- 合并状态设置 ----
        statusFrame = ttk.LabelFrame(controlFrame, text=_('合并状态设置'), padding=(6, 3))
        statusFrame.grid(row=1, column=0, sticky=tk.EW, pady=(5, 0))
        statusFrame.columnconfigure(0, weight=1)
        statusFrame.columnconfigure(2, weight=1)

        self.selectedPdfStatusValue = tk.BooleanVar(parent, value=True)
        ttk.Button(statusFrame, text=_('设置选中项'), command=self.onSetSelectedPdfStatus).grid(row=0, column=0, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Checkbutton(statusFrame, text=_('合并'), variable=self.selectedPdfStatusValue).grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
        self.allPdfStatusValue = tk.BooleanVar(parent, value=True)
        ttk.Button(statusFrame, text=_('设置所有'), command=self.onSetAllPdfStatus).grid(row=0, column=2, sticky=tk.EW, padx=(0, 4), pady=1)
        ttk.Checkbutton(statusFrame, text=_('合并'), variable=self.allPdfStatusValue).grid(row=0, column=3, sticky=tk.W)

        # ---- 输出选项 ----
        outputFrame = ttk.LabelFrame(controlFrame, text=_('输出选项'), padding=(6, 3))
        outputFrame.grid(row=2, column=0, sticky=tk.EW, pady=(5, 0))
        outputFrame.columnconfigure(1, weight=1)

        # 保存路径默认为第一个被合并 PDF 所在文件夹；用户自选/手输后不再自动覆盖
        self._mergeFolderAuto = True

        self.mergeSaveFolderValue = tk.StringVar(parent, value='')
        ttk.Label(outputFrame, text=_('保存路径')).grid(row=0, column=0, sticky=tk.W)
        self.mergeSaveFolderEntry = ttk.Entry(outputFrame, textvariable=self.mergeSaveFolderValue, width=22)
        self.mergeSaveFolderEntry.grid(row=0, column=1, sticky=tk.EW, padx=4)
        self.mergeSaveFolderEntry.bind('<KeyRelease>', self._onMergeFolderTyped)
        ttk.Button(outputFrame, text=_('选择'), command=self.onSelectMergeFolder).grid(row=0, column=2, sticky=tk.E)

        self.mergeSaveNameValue = tk.StringVar(parent, value=_('组合1'))
        ttk.Label(outputFrame, text=_('文件名')).grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(outputFrame, textvariable=self.mergeSaveNameValue, width=22).grid(row=1, column=1, sticky=tk.EW, padx=4)
        ttk.Label(outputFrame, text=_('（自动加 .pdf）'), foreground='#606060').grid(row=1, column=2, sticky=tk.W)

        self.mergeRenameOnSaveValue = tk.BooleanVar(parent, value=False)
        ttk.Checkbutton(outputFrame, text=_('保存时重命名（合并前弹出另存为对话框）'), variable=self.mergeRenameOnSaveValue).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(1, 0))

        # ---- 使用说明 ----
        tipFrame = ttk.LabelFrame(controlFrame, text=_('使用说明'), padding=(6, 3))
        tipFrame.grid(row=3, column=0, sticky=tk.EW, pady=(5, 0))
        tipText: str = _('按列表顺序（序号从小到大）依次合并，可通过「设置选中项 / 设置所有」调整参与合并的文件。\n保存路径默认为第一个 PDF 所在文件夹，文件名默认「组合1」；也可勾选「保存时重命名」在合并前选择最终路径与文件名。')
        ttk.Label(tipFrame, text=tipText, wraplength=330, justify=tk.LEFT, foreground='#404040').grid(row=0, column=0, sticky=tk.W)

        # ---- 合并按钮 ----
        self.mergeButton = ttk.Button(controlFrame, text=_('开始合并'), command=self.onMergePdf, style='Accent.TButton')
        self.mergeButton.grid(row=4, column=0, sticky=tk.EW, pady=(8, 0))

        self._bindPanelMouseWheel(controlCanvas, controlFrame)

    def createStatusBar(self):
        """
        创建底部全局状态栏（进度条 + 状态文字 + 转换引擎状态 + 打开输出文件夹）
        """
        ttk.Separator(self, orient=tk.HORIZONTAL).grid(row=2, column=0, sticky=tk.EW, padx=8)
        statusBar = ttk.Frame(self)
        statusBar.grid(row=3, column=0, sticky=tk.EW, padx=8, pady=4)
        statusBar.columnconfigure(0, weight=1)

        self.progressBar = ttk.Progressbar(statusBar, mode='determinate', maximum=100, value=0)
        self.progressBar.grid(row=0, column=0, sticky=tk.EW, padx=(0, 10))

        self.statusLabel = ttk.Label(statusBar, text=_('就绪'), width=22, anchor=tk.W)
        self.statusLabel.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))

        self.backendStatusLabel = ttk.Label(statusBar, text='', width=40, anchor=tk.W)
        self.backendStatusLabel.grid(row=0, column=2, sticky=tk.W, padx=(0, 10))
        self.backendStatusLabel.bind('<Button-1>', self.onBackendStatusClick)

        self.openOutputFolderButton = ttk.Button(statusBar, text=_('打开输出文件夹'), command=self.onOpenOutputFolder, state=tk.DISABLED)
        self.openOutputFolderButton.grid(row=0, column=3, sticky=tk.E)

    def _getBackendStatusText(self) -> str:
        """
        获取后端状态描述文字（优先使用后端的 statusText()）

        Returns:
            str: 后端状态描述
        """
        statusText = getattr(self.backend, 'statusText', None)
        if callable(statusText):
            try:
                text = str(statusText() or '')
                if text:
                    return text
            except Exception:
                pass
        name = getattr(self.backend, 'displayName', '')
        return str(name) if name else _('未知')

    def _isBackendAvailable(self) -> bool:
        """
        后端是否可用

        Returns:
            bool: 是否可用
        """
        try:
            return bool(self.backend.isAvailable())
        except Exception:
            return False

    def _backendSupportsNxRoot(self) -> bool:
        """
        后端是否支持手动指定 NX 安装目录（免安装版）

        Returns:
            bool: 是否支持
        """
        return callable(getattr(self.backend, 'setNxRoot', None))

    def createWarmEngineOption(self):
        """
        创建免安装版「使用 NX 后台转换引擎」选项行（NX 内直连模式不显示）

        勾选时使用常驻暖机后台引擎（启动即预热、导出复用）；取消勾选时每次导出临时启动 NX。
        """
        if not self.supportsWarmEngine:
            return

        try:
            initialEnabled = bool(self.backend.isWarmEngineEnabled())
        except Exception:
            initialEnabled = True
        self.warmEngineValue.set(initialEnabled)

        optionFrame = ttk.Frame(self)
        optionFrame.grid(row=1, column=0, sticky=tk.EW, padx=8, pady=(2, 0))
        optionFrame.columnconfigure(0, weight=1)
        self.warmEngineFrame = optionFrame

        self.warmEngineCheckbutton = ttk.Checkbutton(
            optionFrame,
            text=_('使用 NX 后台转换引擎'),
            variable=self.warmEngineValue,
            command=self.onToggleWarmEngine,
        )
        self.warmEngineCheckbutton.grid(row=0, column=0, sticky=tk.W)

        noteText: str = _('勾选：无需打开 NX，首次约 10~20 秒启动，之后自动复用、转换更快；取消勾选：每次导出临时启动 NX（较慢，不在后台常驻）。两种方式都无需打开 NX；如需使用已打开的 NX 以及「已打开文件 / 工作部件」，请在 NX 中运行插件（Alt+F8 运行 NX-batch-PDF-exporter.py）。')
        self.warmEngineNoteLabel = ttk.Label(
            optionFrame,
            text=noteText,
            foreground='#606060',
            wraplength=1080,
            justify=tk.LEFT,
            font=(uiFontFamily, uiFontSize - 1),
        )
        self.warmEngineNoteLabel.grid(row=1, column=0, sticky=tk.W, pady=(1, 0))

        def onOptionFrameConfigure(event):
            # 让备注随窗口宽度自动换行（初始约 1080，窗口变窄时同步收缩）
            wrapLength = max(320, event.width - 8)
            try:
                current = int(float(self.warmEngineNoteLabel.cget('wraplength')))
                if current != wrapLength:
                    self.warmEngineNoteLabel.configure(wraplength=wrapLength)
            except tk.TclError:
                pass

        optionFrame.bind('<Configure>', onOptionFrameConfigure)

    def onToggleWarmEngine(self):
        """
        勾选/取消「使用 NX 后台转换引擎」
        """
        enabled = bool(self.warmEngineValue.get())
        try:
            self.backend.setWarmEngineEnabled(enabled)
        except Exception as e:
            msg: str = _('设置后台转换引擎模式失败: {e}')
            self.writeMsg(msg.format(e=str(e)), 'error')
            return

        if enabled:
            try:
                self.backend.prewarm()
            except Exception as e:
                msg = _('预热后台转换引擎失败: {e}')
                self.writeMsg(msg.format(e=str(e)), 'error')
            self.writeMsg(_('已启用常驻 NX 转换引擎（首次启动约 10~20 秒）'))
        else:
            try:
                self.backend.shutdown()
            except Exception as e:
                msg = _('关闭常驻转换引擎失败: {e}')
                self.writeMsg(msg.format(e=str(e)), 'error')
            self.writeMsg(_('已关闭常驻引擎，下次导出将临时启动 NX（耗时增加）'))

        self._updateBackendStatus()

    def _prewarmEngine(self):
        """
        启动后延迟预热常驻 NX 转换引擎（只执行一次，期间界面可正常操作）
        """
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if self._prewarmDone or not self.supportsWarmEngine:
            return
        if not self.warmEngineValue.get():
            return

        self._prewarmDone = True
        msg: str = _('[i] 正在后台预热 NX 转换引擎（首次约 10~20 秒，期间可正常操作界面）...')
        for textWidget in self.tabMsgTexts.values():
            self._appendText(textWidget, msg)
        try:
            self.backend.prewarm()
        except Exception as e:
            errorMsg: str = _('后台预热 NX 转换引擎失败: {e}')
            self.writeMsg(errorMsg.format(e=str(e)), 'error')
        self._updateBackendStatus()

    def _pollEngineState(self):
        """
        定时轮询转换引擎状态并刷新状态栏（窗口销毁后停止调度）
        """
        try:
            if not self.winfo_exists():
                return
            self._updateBackendStatus()
            status = self._getBackendStatusText()
            if status != self._lastBackendStatus:
                self._lastBackendStatus = status
                msg: str = _('转换引擎状态: {status}')
                self.writeMsg(msg.format(status=status))
        except tk.TclError:
            return

        try:
            if self.winfo_exists():
                self._enginePollAfterId = self.after(800, self._pollEngineState)
        except tk.TclError:
            pass

    def onCloseWindow(self):
        """
        窗口关闭：取消状态轮询并释放常驻后台转换引擎，然后销毁窗口
        """
        if self._enginePollAfterId is not None:
            try:
                self.after_cancel(self._enginePollAfterId)
            except Exception:
                pass
            self._enginePollAfterId = None

        try:
            self.backend.shutdown()
        except Exception:
            pass

        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _needNxPluginHint(self) -> bool:
        """
        免安装版点击「所有打开文件 / 工作部件」时弹提示（需要 NX 内插件）

        Returns:
            bool: True 表示已提示并应中止后续操作
        """
        if self.supportsOpenedFiles:
            return False
        try:
            messagebox.showinfo(
                title=_('需要使用 NX 内插件'),
                message=_('免安装版无法读取另一个 NX 会话中的已打开文件 / 工作部件。\n\n如需该功能，请在 NX 中按 Alt+F8 运行 NX-batch-PDF-exporter.py（NX 内直连模式），或使用原 NX 内插件入口。'),
            )
        except Exception:
            pass
        self.writeMsg(_('该功能需在 NX 内运行插件（免安装版不支持跨会话读取）'), 'warn')
        return True

    def _updateBackendStatus(self):
        """
        刷新状态栏的转换引擎状态文字
        """
        if self._isBackendAvailable():
            msg: str = _('转换引擎: {name}')
            self.backendStatusLabel.configure(text=msg.format(name=self._getBackendStatusText()), foreground='#202020')
        else:
            self.backendStatusLabel.configure(text=_('转换引擎: 未找到 NX2412'), foreground='#B36B00')
        if self._backendSupportsNxRoot():
            self.backendStatusLabel.configure(cursor='hand2')
        else:
            self.backendStatusLabel.configure(cursor='')

    def setBackendStatus(self, text: str, warn: bool = False):
        """
        设置状态栏转换引擎文字（供 standalone 等外部入口调用）

        Args:
            text (str): 状态文字
            warn (bool): 是否使用警告颜色
        """
        self.backendStatusLabel.configure(text=text, foreground='#B36B00' if warn else '#202020')

    def onBackendStatusClick(self, event: tk.Event = None):
        """
        点击状态栏转换引擎：免安装版可手动选择 NX2412 的 run_journal.exe
        """
        if not self._backendSupportsNxRoot():
            return
        filePath = filedialog.askopenfilename(
            title=_('选择 NX2412 的 run_journal.exe'),
            filetypes=[(_('run_journal.exe'), 'run_journal.exe'), (_('可执行文件'), '*.exe'), (_('所有文件'), '*.*')]
        )
        if filePath == '':
            return
        filePath = os.path.normpath(filePath)

        # 依次尝试：NX 安装目录（run_journal.exe 上两级）、所在 NXBIN 目录的上级、所在目录、所选文件本身
        exeDir = os.path.dirname(filePath)
        candidates = []
        if os.path.basename(exeDir).lower() == 'nxbin':
            candidates.append(os.path.dirname(exeDir))
        candidates.append(os.path.dirname(exeDir))
        candidates.append(exeDir)
        candidates.append(filePath)

        nxRoot = ''
        try:
            for candidate in candidates:
                if candidate and self.backend.setNxRoot(candidate):
                    nxRoot = candidate
                    break
        except Exception as e:
            msg: str = _('设置 NX 安装目录失败: {e}')
            self.writeMsg(msg.format(e=str(e)), 'error')
            self._updateBackendStatus()
            return

        self._updateBackendStatus()
        if nxRoot != '':
            msg = _('已设置 NX 安装目录: {path}')
            self.writeMsg(msg.format(path=nxRoot), 'success')
        else:
            self.writeMsg(_('设置 NX 安装目录失败，请确认选择的是 NX2412 的 run_journal.exe'), 'error')

    def _writeBackendStartupLog(self):
        """
        向各页日志写入后端相关的启动提示
        """
        if self.backendFallbackError != '':
            msg: str = _('未检测到 NX 环境，已切换为后台转换模式: {e}')
            for textWidget in self.tabMsgTexts.values():
                self._appendText(textWidget, msg.format(e=self.backendFallbackError), 'warn')

        if not self._isBackendAvailable() and self._backendSupportsNxRoot():
            self._appendText(self.prtMsgText, _('未找到 NX2412：请点击状态栏「转换引擎」选择 NX 安装目录中的 run_journal.exe'), 'warn')
            self._appendText(self.modelMsgText, _('未找到 NX2412：请点击状态栏「转换引擎」选择 NX 安装目录中的 run_journal.exe'), 'warn')

        if not self.supportsOpenedFiles:
            msg = _('免安装版：已打开文件/工作部件需在 NX 内运行插件（点击按钮会提示）')
            self._appendText(self.prtMsgText, msg, 'warn')
            self._appendText(self.modelMsgText, msg, 'warn')

    def onTabChanged(self, event: tk.Event):
        """
        切换标签页事件处理，根据当前标签页设置消息框

        Args:
            event (tk.Event): 事件对象
        """
        currentTabId = self.notebook.select()
        if not currentTabId:
            return

        currentFrame = self.notebook.nametowidget(currentTabId)
        self.msgText = self.tabMsgTexts.get(currentFrame, self.prtMsgText)

    def _appendText(self, textWidget: tk.Text, msg: str, level: str = 'info'):
        """
        向指定日志文本框追加一条消息

        Args:
            textWidget (tk.Text): 日志文本框
            msg (str): 消息内容
            level (str): 消息级别 ('info', 'success', 'warn', 'error')
        """
        if textWidget is None:
            return
        if level not in logLevels:
            level = 'info'

        textWidget.config(state=tk.NORMAL)
        # 在 insert 时传入对应的 tag 名字
        textWidget.insert(tk.END, str(msg) + '\n', level)
        textWidget.config(state=tk.DISABLED)
        textWidget.see(tk.END)
        textWidget.update_idletasks()

    def writeMsg(self, msg: str, level: str = 'info'):
        """
        写消息

        Args:
            msg (str): 消息内容
            level (str): 消息级别 ('info', 'success', 'warn', 'error')
        """
        self._appendText(self.msgText, msg, level)

    def startTask(self, text: str, total: int = 0):
        """
        任务开始：重置进度条与状态文字

        Args:
            text (str): 状态文字
            total (int): 任务总数量
        """
        self.taskTotal = max(total, 1)
        self.progressBar.configure(maximum=self.taskTotal, value=0)
        self.statusLabel.configure(text=text)
        self.update_idletasks()

    def setProgress(self, done: int, total: int):
        """
        更新任务进度（由后端在每处理完一个文件时回调）

        Args:
            done (int): 已完成数量
            total (int): 总数量
        """
        if total is None or total <= 0:
            return
        self.taskTotal = total
        self.progressBar.configure(maximum=total, value=done)
        msg: str = _('正在处理 {done}/{total}')
        self.statusLabel.configure(text=msg.format(done=done, total=total))
        self.update_idletasks()

    def endTask(self):
        """
        任务结束：进度条填满并显示「完成」
        """
        self.progressBar.configure(maximum=self.taskTotal, value=self.taskTotal)
        self.statusLabel.configure(text=_('完成'))
        self.update_idletasks()

    def _setTaskButtonsEnabled(self, enabled: bool):
        """
        启用/禁用任务按钮

        Args:
            enabled (bool): 是否启用
        """
        state = tk.NORMAL if enabled else tk.DISABLED
        for button in (self.exportButton, self.modelExportButton, self.mergeButton):
            button.configure(state=state)

    def _setLastOutputFolder(self, folder: str):
        """
        记录最近一次的输出文件夹并刷新「打开输出文件夹」按钮状态

        Args:
            folder (str): 输出文件夹
        """
        if folder:
            self.lastOutputFolder = os.path.normpath(folder)
        self.updateOutputFolderButton()

    def updateOutputFolderButton(self):
        """
        根据最近一次的输出文件夹刷新「打开输出文件夹」按钮状态
        """
        enabled = self.lastOutputFolder != '' and os.path.isdir(self.lastOutputFolder)
        self.openOutputFolderButton.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def onOpenOutputFolder(self):
        """
        打开最近一次的输出文件夹
        """
        if self.lastOutputFolder == '' or not os.path.isdir(self.lastOutputFolder):
            self.writeMsg(_('暂无可打开的输出文件夹'), 'warn')
            self.updateOutputFolderButton()
            return
        try:
            os.startfile(self.lastOutputFolder)
        except OSError as e:
            msg: str = _('打开输出文件夹失败: {e}')
            self.writeMsg(msg.format(e=str(e)), 'error')

    def _collectPrts(self, listShow: ListShow, getter, filterValue=None, filterMode: str = '', *args):
        """
        通过后端收集文件（按需按文件名过滤）并添加到列表

        Args:
            listShow (ListShow): 目标列表
            getter (function): 后端文件收集方法
            filterValue (tk.BooleanVar, optional): 过滤开关
            filterMode (str): 过滤模式（'drawing' / 'model'）
            *args: 传递给文件收集方法的参数
        """
        try:
            prtList = getter(*args)
        except Exception as e:
            msg: str = _('获取文件列表失败: {e}')
            self.writeMsg(msg.format(e=str(e)), 'error')
            return

        prtList = list(prtList or [])
        if filterValue is not None and filterMode != '' and filterValue.get():
            kept, filteredOut = filterPrts(prtList, filterMode)
            filteredCount = len(filteredOut) if isinstance(filteredOut, (list, tuple, set)) else int(filteredOut)
            if filteredCount > 0:
                if filterMode == 'drawing':
                    msg = _('已过滤 {count} 个文件名不含 dwg 的文件')
                else:
                    msg = _('已排除 {count} 个文件名含 dwg 的图纸文件')
                self.writeMsg(msg.format(count=filteredCount))
            prtList = list(kept)

        self._addPrts(listShow, prtList)

    def _addPrts(self, listShow: ListShow, prtList: list[str]):
        """
        向列表中添加文件并输出日志

        Args:
            listShow (ListShow): 目标列表
            prtList (list[str]): 文件路径列表
        """
        if not prtList:
            return

        beforeCount = listShow.count()
        listShow.insertPrtList(prtList)
        addedCount = listShow.count() - beforeCount
        if addedCount > 0:
            msg: str = _('已添加 {added} 个文件，列表共 {total} 个文件')
            self.writeMsg(msg.format(added=addedCount, total=listShow.count()))
        elif beforeCount > 0:
            self.writeMsg(_('所选文件已全部在列表中'))

    def _removeSelectedFromList(self, listShow: ListShow):
        """
        移除列表中选中的项目并输出日志

        Args:
            listShow (ListShow): 目标列表
        """
        removedCount = listShow.removeSelected()
        if removedCount > 0:
            msg: str = _('已从列表移除 {count} 个文件')
            self.writeMsg(msg.format(count=removedCount))
        else:
            self.writeMsg(_('请先在列表中选择要移除的文件'), 'warn')

    def _clearList(self, listShow: ListShow):
        """
        清空列表并输出日志

        Args:
            listShow (ListShow): 目标列表
        """
        count = listShow.count()
        listShow.clear()
        if count > 0:
            msg: str = _('已清空文件列表（{count} 个文件）')
            self.writeMsg(msg.format(count=count))

    # ---- 图纸导出页 ----

    def onGetSelectedPrts(self):
        """
        获取选择的图纸文件
        """
        self._collectPrts(self.prtListShow, self.backend.selectFiles, self.drawingFilterValue, 'drawing')

    def onGetPrtsFromSelectedFolder(self):
        """
        获取选择的文件夹中的图纸文件
        """
        self._collectPrts(self.prtListShow, self.backend.getFilesFromFolder, self.drawingFilterValue, 'drawing', self.prtRecursiveValue.get())

    def onGetOpenedPrts(self):
        """
        获取已打开的图纸文件（免安装版点击时提示需在 NX 内运行插件）
        """
        if self._needNxPluginHint():
            return
        self._collectPrts(self.prtListShow, self.backend.getOpenedFiles, self.drawingFilterValue, 'drawing')

    def onWorkPrt(self):
        """
        获取工作部件（免安装版点击时提示需在 NX 内运行插件）
        """
        if self._needNxPluginHint():
            return
        self._collectPrts(self.prtListShow, self.backend.getWorkFile, self.drawingFilterValue, 'drawing')

    def onRemoveSelectedPrts(self):
        """
        移除选中的图纸文件
        """
        self._removeSelectedFromList(self.prtListShow)

    def onClearPrts(self):
        """
        清空图纸文件列表
        """
        self._clearList(self.prtListShow)

    def onSetSelectedPrtStatus(self):
        """
        设置 NX 图纸选中项的状态
        """
        self.prtListShow.setSelectedStatus(self.selectedPrtStatusValue.get())

    def onSetAllPrtStatus(self):
        """
        设置所有 NX 图纸的状态
        """
        self.prtListShow.setAllStatus(self.allPrtStatusValue.get())

    def onSelectExportFolder(self):
        """
        选择图纸导出文件夹
        """
        folder = filedialog.askdirectory(title=_('选择导出文件夹'))
        if folder == '':
            return
        folder = os.path.normpath(folder)
        self.exportFolderValue.set(folder)
        self._setLastOutputFolder(folder)

    def onExport(self):
        """
        导出图纸（PDF / DWG，可同时导出）
        """
        prtList = self.prtListShow.getPrtList()
        if not prtList:
            self.writeMsg(_('请先添加需要导出的图纸文件'), 'warn')
            return

        kinds = []
        if self.pdfFormatValue.get():
            kinds.append('pdf')
        if self.dwgFormatValue.get():
            kinds.append('dwg')
        if not kinds:
            self.writeMsg(_('请至少勾选一种图纸导出格式（PDF / DWG）'), 'warn')
            return

        exportFolder = self.exportFolderValue.get().strip()
        if exportFolder != '':
            try:
                os.makedirs(exportFolder, exist_ok=True)
            except OSError as e:
                msg: str = _('无法创建导出文件夹: {e}')
                self.writeMsg(msg.format(e=str(e)), 'error')
                return

        prefixName = self.prefixNameValue.get().strip()
        suffixName = self.suffixNameValue.get().strip()
        skipExisting = self.skipExistingValue.get()

        self._setLastOutputFolder(exportFolder if exportFolder != '' else os.path.dirname(prtList[0]))
        self._setTaskButtonsEnabled(False)
        self.startTask(_('正在导出图纸...'), len(prtList))
        try:
            self.backend.exportDrawings(
                kinds,
                prtList,
                prefixName,
                suffixName,
                exportFolder,
                self.writeMsg,
                progress=self.setProgress,
                skipExisting=skipExisting,
            )
            self.writeMsg(_('图纸导出任务结束'), 'success')
        except Exception as e:
            msg: str = _('图纸导出任务异常终止: {e}')
            self.writeMsg(msg.format(e=str(e)), 'error')
        finally:
            # NX 中执行时有异常，必须执行 update，否则按钮禁用状态下的点击也会留到本轮执行结束后继续触发
            self.update()
            self._setTaskButtonsEnabled(True)
            self.endTask()

    # ---- 模型导出页 ----

    def onGetSelectedModelPrts(self):
        """
        获取选择的模型文件
        """
        self._collectPrts(self.modelListShow, self.backend.selectFiles, self.modelFilterValue, 'model')

    def onGetModelPrtsFromSelectedFolder(self):
        """
        获取选择的文件夹中的模型文件
        """
        self._collectPrts(self.modelListShow, self.backend.getFilesFromFolder, self.modelFilterValue, 'model', self.modelRecursiveValue.get())

    def onGetOpenedModelPrts(self):
        """
        获取已打开的模型文件（免安装版点击时提示需在 NX 内运行插件）
        """
        if self._needNxPluginHint():
            return
        self._collectPrts(self.modelListShow, self.backend.getOpenedFiles, self.modelFilterValue, 'model')

    def onWorkModelPrt(self):
        """
        获取工作部件（免安装版点击时提示需在 NX 内运行插件）
        """
        if self._needNxPluginHint():
            return
        self._collectPrts(self.modelListShow, self.backend.getWorkFile, self.modelFilterValue, 'model')

    def onRemoveSelectedModelPrts(self):
        """
        移除选中的模型文件
        """
        self._removeSelectedFromList(self.modelListShow)

    def onClearModelPrts(self):
        """
        清空模型文件列表
        """
        self._clearList(self.modelListShow)

    def onSetSelectedModelStatus(self):
        """
        设置模型选中项的状态
        """
        self.modelListShow.setSelectedStatus(self.selectedModelStatusValue.get())

    def onSetAllModelStatus(self):
        """
        设置所有模型的状态
        """
        self.modelListShow.setAllStatus(self.allModelStatusValue.get())

    def onSelectModelExportFolder(self):
        """
        选择模型导出文件夹
        """
        folder = filedialog.askdirectory(title=_('选择导出文件夹'))
        if folder == '':
            return
        folder = os.path.normpath(folder)
        self.modelExportFolderValue.set(folder)
        self._setLastOutputFolder(folder)

    def onExportModels(self):
        """
        导出模型（XT / STP）
        """
        prtList = self.modelListShow.getPrtList()
        if not prtList:
            self.writeMsg(_('请先添加需要导出的模型文件'), 'warn')
            return

        formats = []
        if self.xtFormatValue.get():
            formats.append(ModelFormat.XT.value)
        if self.stpFormatValue.get():
            formats.append(ModelFormat.STP.value)
        if not formats:
            self.writeMsg(_('请至少勾选一种导出格式（XT / STP）'), 'warn')
            return

        exportFolder = self.modelExportFolderValue.get().strip()
        if exportFolder != '':
            try:
                os.makedirs(exportFolder, exist_ok=True)
            except OSError as e:
                msg: str = _('无法创建导出文件夹: {e}')
                self.writeMsg(msg.format(e=str(e)), 'error')
                return

        options = ModelExportOptions(
            formats=formats,
            stepSchema=self.stpSchemaValues.get(self.stpSchemaValue.get(), StepSchema.AP214.value),
            xtVersion=self.xtVersionValues.get(self.xtVersionValue.get(), XtVersion.CURRENT.value),
            flattenAssembly=self.flattenAssemblyValue.get(),
            skipExisting=self.modelSkipExistingValue.get(),
        )

        prefixName = self.modelPrefixNameValue.get().strip()
        suffixName = self.modelSuffixNameValue.get().strip()

        self._setLastOutputFolder(exportFolder if exportFolder != '' else os.path.dirname(prtList[0]))
        self._setTaskButtonsEnabled(False)
        self.startTask(_('正在导出模型...'), len(prtList))
        try:
            self.backend.exportModels(
                prtList,
                prefixName,
                suffixName,
                exportFolder,
                options,
                self.writeMsg,
                progress=self.setProgress,
            )
            self.writeMsg(_('模型导出任务结束'), 'success')
        except Exception as e:
            msg: str = _('模型导出任务异常终止: {e}')
            self.writeMsg(msg.format(e=str(e)), 'error')
        finally:
            # NX 中执行时有异常，必须执行 update，否则按钮禁用状态下的点击也会留到本轮执行结束后继续触发
            self.update()
            self._setTaskButtonsEnabled(True)
            self.endTask()

    # ---- 合并 PDF 页 ----

    def _syncMergeDefaultFolder(self):
        """
        自动把保存路径同步为第一个被合并 PDF 所在文件夹（用户自选/手输过则不再覆盖）
        """
        if not self._mergeFolderAuto:
            return
        pdfList = self.pdfListShow.getPrtList()
        if not pdfList:
            # 全部未勾选时退回取列表第一行，保证保存路径仍有合理默认值
            children = self.pdfListShow.tree.get_children()
            if not children:
                return
            pdfList = [self.pdfListShow.tree.set(children[0], 'filePath')]
        folder = os.path.dirname(pdfList[0])
        if folder != '':
            self.mergeSaveFolderValue.set(os.path.normpath(folder))

    def _onMergeFolderTyped(self, event: tk.Event = None):
        """
        用户手动编辑保存路径后，不再自动覆盖该路径
        """
        self._mergeFolderAuto = False

    def onOpenPdfs(self):
        """
        打开要合并的 PDF 文件
        """
        pdfFiles = filedialog.askopenfilenames(
            title=_('选择要合并的 PDF 文件'),
            filetypes=[(_('PDF 文件'), '*.pdf')]
        )
        self._addPrts(self.pdfListShow, pdfFiles)
        self._syncMergeDefaultFolder()

    def onRemoveSelectedPdfs(self):
        """
        移除选中的 PDF 文件
        """
        self._removeSelectedFromList(self.pdfListShow)

    def onClearPdfs(self):
        """
        清空 PDF 文件列表（保存路径恢复自动同步，文件名输入值保留）
        """
        self._clearList(self.pdfListShow)
        self._mergeFolderAuto = True

    def onSelectMergeFolder(self):
        """
        选择合并后 PDF 的保存文件夹
        """
        initialDir = self.mergeSaveFolderValue.get().strip()
        if initialDir == '':
            pdfList = self.pdfListShow.getPrtList()
            if pdfList:
                initialDir = os.path.dirname(pdfList[0])
        kwargs = {'title': _('选择合并后 PDF 的保存文件夹')}
        if initialDir != '' and os.path.isdir(initialDir):
            kwargs['initialdir'] = initialDir
        folder = filedialog.askdirectory(**kwargs)
        if folder == '':
            return
        folder = os.path.normpath(folder)
        self.mergeSaveFolderValue.set(folder)
        self._mergeFolderAuto = False

    def onSetSelectedPdfStatus(self):
        """
        设置 PDF 图纸选中项的状态
        """
        self.pdfListShow.setSelectedStatus(self.selectedPdfStatusValue.get())

    def onSetAllPdfStatus(self):
        """
        设置所有 PDF 图纸的状态
        """
        self.pdfListShow.setAllStatus(self.allPdfStatusValue.get())

    def onMergePdf(self):
        """
        合并 PDF

        保存路径默认为第一个被合并 PDF 所在文件夹，文件名默认「组合1」；
        勾选「保存时重命名」时先弹出另存为对话框，可修改最终路径与文件名。
        """
        pdfList = self.pdfListShow.getPrtList()
        if not pdfList:
            self.writeMsg(_('请先添加要合并的 PDF 文件'), 'warn')
            return

        # 文件名：为空时用「组合1」，自动补 .pdf，并用 basename 防止路径注入
        name = self.mergeSaveNameValue.get().strip() or _('组合1')
        name = os.path.basename(name)
        if not name.lower().endswith('.pdf'):
            name = name + '.pdf'

        # 保存路径：输入框为空时取第一个被合并 PDF 所在目录
        folder = self.mergeSaveFolderValue.get().strip()
        if folder == '':
            folder = os.path.dirname(pdfList[0])
        if folder == '':
            self.writeMsg(_('请设置合并后的 PDF 保存路径'), 'warn')
            return
        folder = os.path.normpath(folder)

        target = ''
        if self.mergeRenameOnSaveValue.get():
            # 勾选「保存时重命名」：合并前弹出另存为对话框，取消则放弃本次合并
            selected = filedialog.asksaveasfilename(
                title=_('保存合并后的 PDF'),
                initialdir=folder,
                initialfile=name,
                defaultextension='.pdf',
                filetypes=[(_('PDF 文件'), '*.pdf')],
            )
            if selected == '':
                self.writeMsg(_('已取消合并'))
                return
            target = os.path.abspath(os.path.normpath(selected))
            if not target.lower().endswith('.pdf'):
                target = target + '.pdf'
            folder = os.path.dirname(target)
            name = os.path.basename(target)
            self.mergeSaveFolderValue.set(folder)
            self.mergeSaveNameValue.set(name)
            self._mergeFolderAuto = False
        else:
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as e:
                msg: str = _('无法创建输出文件夹: {e}')
                self.writeMsg(msg.format(e=str(e)), 'warn')
                return
            target = os.path.join(folder, name)
            if os.path.exists(target):
                overwrite = False
                try:
                    overwrite = bool(messagebox.askyesno(_('文件已存在'), _('{name} 已存在，是否覆盖？').format(name=name)))
                except Exception:
                    overwrite = False
                if not overwrite:
                    self.writeMsg(_('已取消合并（文件已存在，未覆盖）'), 'warn')
                    return

        self._setLastOutputFolder(folder)
        self._setTaskButtonsEnabled(False)
        self.startTask(_('正在合并 PDF...'), len(pdfList))
        try:
            self.backend.mergePdfs(target, pdfList, self.writeMsg)
            self.writeMsg(_('PDF 合并任务结束'), 'success')
        except Exception as e:
            msg: str = _('PDF 合并任务异常终止: {e}')
            self.writeMsg(msg.format(e=str(e)), 'error')
        finally:
            # NX 中执行时有异常，必须执行 update，否则按钮禁用状态下的点击也会留到本轮执行结束后继续触发
            self.update()
            self._setTaskButtonsEnabled(True)
            self.endTask()


def getUiScale() -> float:
    """
    获取 Windows 显示缩放比例。

    NX 内置 Python/tkinter 进程不是 DPI 感知进程，Windows 会把窗口按系统缩放比例
    （例如 150%）放大显示，而 tkinter 仍然按 96 DPI 的坐标计算窗口位置和大小。
    如果不做换算，窗口在高缩放比例的显示器上会超出屏幕（右侧/底部被裁掉）。
    本函数返回 Windows 的缩放比例（100% 返回 1.0，150% 返回 1.5）。

    Returns:
        float: 显示缩放比例
    """
    # 如果进程已经具备 DPI 感知能力，则坐标本身就是物理像素，无需补偿
    try:
        import ctypes
        awareness = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(ctypes.c_void_p(-1), ctypes.byref(awareness))
        if awareness.value != 0:
            return 1.0
    except Exception:
        pass

    # 读取 Windows 系统缩放比例（AppliedDPI：96=100%，120=125%，144=150%，192=200%）
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Control Panel\Desktop\WindowMetrics')
        appliedDpi, _ = winreg.QueryValueEx(key, 'AppliedDPI')
        scale = float(appliedDpi) / 96.0
        if 1.0 <= scale <= 4.0:
            return scale
    except Exception:
        pass
    return 1.0


def run(backend=None):
    """
    启动图形界面

    Args:
        backend (optional): 导出后端；为空时使用 NX 内直连后端（NX-batch-PDF-exporter.py 的调用方式），
            免安装版 standalone.py 会传入 RemoteBackend()
    """
    root = tk.Tk()
    width = 1180
    height = 870

    # 换算到当前显示缩放比例下的逻辑屏幕尺寸，保证窗口完整显示在屏幕内
    scale = getUiScale()
    screenwidth = root.winfo_screenwidth() / scale
    screenheight = root.winfo_screenheight() / scale
    width = min(width, max(920, int(screenwidth - 80)))
    height = min(height, max(680, int(screenheight - 80)))
    x = int((screenwidth - width) / 2)
    y = int((screenheight - height) / 2)

    root.geometry(f'{width}x{height}+{x}+{y}')
    root.minsize(920, 640)
    root.attributes('-topmost', True)
    root.title(f'{programName}')
    try:
        root.iconbitmap(os.path.join(baseDir, 'icon.ico'))
    except tk.TclError:
        pass
    app = Application(root, backend=backend)
    app.mainloop()
