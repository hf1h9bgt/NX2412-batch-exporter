"""
file: backend_direct.py
description: NX 内直连后端（插件在 NX 内运行时使用，直接调用 NXOpen 导出）
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""


class DirectBackend:
    """
    NX 内直连后端。

    本模块顶层不 import NXOpen：只有真正调用导出方法时才按需导入
    nxmodules / modelmodules / pdfmodules，保证界面层可以在没有 NXOpen 的
    独立 Python（免安装版）中安全导入。
    """

    supportsOpenedFiles = True
    supportsWarmEngine = False
    displayName = 'NX 内直连'

    def isAvailable(self) -> bool:
        """当前后端是否可用"""
        try:
            import NXOpen  # noqa: F401
            return True
        except Exception:
            return False

    def statusText(self) -> str:
        """后端状态描述"""
        return self.displayName

    # ---------------- 常驻转换引擎（NX 内直连无需，空实现保持接口一致） ----------------

    def isWarmEngineEnabled(self) -> bool:
        """NX 内直连不需要常驻后台引擎"""
        return False

    def setWarmEngineEnabled(self, enabled: bool):
        """NX 内直连不需要常驻后台引擎（空实现）"""
        return

    def prewarm(self):
        """NX 内直连不需要预热（空实现）"""
        return

    def shutdown(self):
        """NX 内直连无后台进程（空实现）"""
        return

    # ---------------- 文件收集 ----------------

    def selectFiles(self) -> list:
        """
        选择 NX 文件

        Returns:
            list[str]: NX 文件路径列表
        """
        from nxmodules import NxModules
        return NxModules.selectPrts()

    def getFilesFromFolder(self, recursive: bool = False) -> list:
        """
        从选择的文件夹获取 NX 文件

        Args:
            recursive (bool): 是否递归子文件夹

        Returns:
            list[str]: NX 文件路径列表
        """
        from nxmodules import NxModules
        return NxModules.getPrtsFromSelectedFolder(recursive)

    def getOpenedFiles(self) -> list:
        """
        获取已打开的 NX 文件

        Returns:
            list[str]: NX 文件路径列表
        """
        from nxmodules import NxModules
        return NxModules.getOpenedPrts()

    def getWorkFile(self) -> list:
        """
        获取当前工作部件

        Returns:
            list[str]: NX 文件路径列表
        """
        from nxmodules import NxModules
        return NxModules.getWorkPrt()

    # ---------------- 导出 ----------------

    def exportDrawings(self, kinds: list, prtList: list, prefixName: str = '', suffixName: str = '',
                       folder: str = '', writeMsg=None, progress=None, skipExisting: bool = False) -> dict:
        """
        批量导出图纸（PDF / DWG）

        Args:
            kinds (list[str]): 导出格式列表，'pdf' / 'dwg' 的子集（按顺序执行）
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
        from nxmodules import NxModules
        return NxModules.exportDrawings(
            kinds, prtList, prefixName, suffixName, folder, writeMsg,
            progress=progress, skipExisting=skipExisting)

    def exportModels(self, prtList: list, prefixName: str = '', suffixName: str = '',
                     folder: str = '', options=None, writeMsg=None, progress=None) -> dict:
        """
        批量导出模型（XT / STP）

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
        from modelmodules import ModelModules
        return ModelModules.exportModels(
            prtList, prefixName, suffixName, folder, options, writeMsg, progress=progress)

    def mergePdfs(self, outputFilename: str, inputFiles: list, writeMsg=None):
        """
        合并 PDF

        Args:
            outputFilename (str): 输出文件名
            inputFiles (list[str]): 输入 PDF 文件列表
            writeMsg (function): 消息输出函数
        """
        from pdfmodules import PdfModules
        return PdfModules.mergePdfs(outputFilename, inputFiles, writeMsg)
