"""
file: nxmodules.py
description: NX 相关调用功能模块
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
from tkinter import filedialog

import NXOpen

from typing import Callable, Optional
import os
import time

from batchmodules import BatchModules


class NxModules:
    # 输出文件等待超时（秒）：NX 的 DWG 转换器异步写盘，实测单张图纸可能需要 40~60 秒；
    # PDF 一般较快，复杂图纸也可能需要较长时间。
    PDF_WAIT_TIMEOUT = 180.0
    DWG_WAIT_TIMEOUT = 300.0

    @staticmethod
    def selectPrts() -> list[str]:
        """
        选择 NX 文件

        Returns:
            list[str]: NX 文件路径列表
        """
        prts = filedialog.askopenfilenames(
            title=_('选择 NX 文件'),
            filetypes=[(_('NX 文件'), '*.prt')]
        )
        return prts

    @staticmethod
    def getOpenedPrts() -> list[str]:
        """
        获取已打开的 NX 文件

        Returns:
            list[str]: NX 文件路径列表
        """
        session = NXOpen.Session.GetSession()
        return [prt.FullPath for prt in session.Parts]

    @staticmethod
    def getPrtsFromSelectedFolder(recursive: bool = False) -> list[str]:
        """
        从指定文件夹获取 NX 文件

        Args:
            recursive (bool, optional): 是否递归获取子文件夹中的文件。默认不递归。

        Returns:
            list[str]: NX 文件路径列表
        """
        folder = filedialog.askdirectory(title=_('选择包含 NX 文件的文件夹'))
        if not folder:
            # 用户取消选择
            return []

        prts = []
        try:
            if recursive:
                for root, dirs, files in os.walk(folder):
                    for file in files:
                        if file.lower().endswith('.prt'):
                            prts.append(os.path.join(root, file))
            else:
                for file in os.listdir(folder):
                    if file.lower().endswith('.prt'):
                        prts.append(os.path.join(folder, file))
        except Exception:
            return []
        return prts

    @staticmethod
    def getWorkPrt() -> list[str]:
        """
        获取当前工作部件

        Returns:
            list[str]: NX 文件路径列表
        """
        try:
            workPrt = NXOpen.Session.GetSession().Parts.Work
        except NXOpen.NXException as e:
            msg: str = _('获取当前工作部件失败: {e}')
            NxModules.printMsg(msg.format(e=str(e)))
            return []

        if workPrt is None:
            NxModules.printMsg(_('当前没有工作部件'))
            return []

        return [workPrt.FullPath]

    @staticmethod
    def printMsg(msg: str):
        """
        仅用于无界面消息输出（保持向后兼容）

        Args:
            msg (str): 消息内容
        """
        print(msg)

    @staticmethod
    def normalizeKinds(kinds) -> list:
        """
        归一化导出格式列表（兼容单个字符串，按 PDF、DWG 顺序去重）

        Args:
            kinds (str | list[str]): 导出格式（'pdf' / 'dwg'）

        Returns:
            list[str]: 归一化后的格式列表；包含非法格式时该项以 '__invalid__' 开头
        """
        if isinstance(kinds, str):
            kinds = [kinds]
        result = []
        invalid = []
        for kind in kinds or []:
            kind = str(kind).strip().lower()
            if not kind:
                continue
            if kind not in ('pdf', 'dwg'):
                invalid.append(kind)
                continue
            if kind not in result:
                result.append(kind)
        ordered = [kind for kind in ('pdf', 'dwg') if kind in result]
        return ordered + ['__invalid__' + kind for kind in invalid]

    @staticmethod
    def exportDrawings(kinds, prtList: list, prefixName: str = '', suffixName: str = '',
                       folder: str = '', writeMsg: Optional[Callable] = None,
                       progress: Optional[Callable] = None, skipExisting: bool = False) -> dict:
        """
        批量导出图纸（PDF / DWG，可同时选择多种格式，逐个文件依次导出）

        Args:
            kinds (str | list[str]): 导出格式（'pdf' / 'dwg' 的单个或列表）
            prtList (list[str]): NX 图纸文件路径列表
            prefixName (str, optional): 文件名前缀
            suffixName (str, optional): 文件名后缀
            folder (str, optional): 输出文件夹，为空时输出到源文件所在文件夹
            writeMsg (function): 消息输出函数，签名 writeMsg(msg, level='info')
            progress (function, optional): 进度回调，签名 progress(done, total)
            skipExisting (bool, optional): 是否跳过已存在的同名文件

        Returns:
            dict: 任务统计结果，见 BatchModules.foreachPart
        """
        emptyResult = {'success': 0, 'failed': 0, 'skipped': 0, 'total': 0, 'elapsed': 0.0}
        if writeMsg is None:
            writeMsg = NxModules.printMsg
        if not prtList:
            writeMsg(_('  [!] 没有需要导出的图纸文件'), 'warn')
            return emptyResult

        kindList = NxModules.normalizeKinds(kinds)
        invalid = [kind for kind in kindList if kind.startswith('__invalid__')]
        if invalid:
            msg = _('  [✘] 不支持的导出格式: {kind}')
            writeMsg(msg.format(kind=invalid[0][len('__invalid__'):]), 'error')
            return emptyResult
        if not kindList:
            writeMsg(_('  [!] 请至少选择一种导出格式（PDF / DWG）'), 'warn')
            return emptyResult

        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                msg = _('  [✘] 无法创建导出文件夹：{e}')
                writeMsg(msg.format(e=str(e)), 'error')
                return emptyResult

        formatText = ' + '.join(kind.upper() for kind in kindList)
        writeMsg(_('  导出格式: {formats}').format(formats=formatText))

        def worker(part) -> Optional[bool]:
            return NxModules.exportDrawing(part, kindList, prefixName, suffixName, folder, writeMsg, skipExisting)

        actionName = _('图纸导出') + f' [{formatText}]'
        return BatchModules.foreachPart(prtList, worker, writeMsg, progress, actionName=actionName)

    @staticmethod
    def getDrawingSheets(part: NXOpen.Part) -> tuple:
        """
        获取图纸页并区分「有视图的图纸页」与「空白图纸页」

        NX 2412 主模型出图时，零件里常会额外带一个没有视图的默认图纸页（如 Sheet 1），
        导出 DWG/PDF 时应跳过这类空白页，避免产生多余文件/空白页。

        Args:
            part (NXOpen.Part): NX 部件

        Returns:
            tuple: (全部图纸页列表, 有视图的图纸页列表, 空白图纸页名称列表)
        """
        try:
            allSheets = list(part.DrawingSheets)
        except Exception:
            allSheets = []
        drawable = []
        skippedNames = []
        for sheet in allSheets:
            hasViews = True
            try:
                hasViews = bool(sheet.GetDraftingViews())
            except Exception:
                hasViews = True
            if hasViews:
                drawable.append(sheet)
            else:
                try:
                    skippedNames.append(str(sheet.Name))
                except Exception:
                    skippedNames.append('')
        return allSheets, drawable, skippedNames

    @staticmethod
    def getDrawingOutputPaths(part: NXOpen.Part, prefixName: str, suffixName: str,
                              folder: str, kind: str, drawableSheets: list) -> list:
        """
        计算图纸导出后的输出文件路径（DWG 多图纸时 NX 会按图纸名拆分文件）

        Args:
            part (NXOpen.Part): NX 部件
            prefixName (str): 文件名前缀
            suffixName (str): 文件名后缀
            folder (str): 输出文件夹
            kind (str): 导出格式（'pdf' / 'dwg'）
            drawableSheets (list): 有视图的图纸页列表

        Returns:
            list[str]: 期望生成的输出文件路径列表
        """
        extension = 'pdf' if kind == 'pdf' else 'dwg'
        basePath = BatchModules.buildOutputPath(part, prefixName, suffixName, folder, extension)
        if kind == 'pdf' or len(drawableSheets) <= 1:
            return [basePath]

        # DWG 多图纸：NX 实际输出 <OutputFile去扩展名>_<图纸名>.dwg
        targetDir = os.path.dirname(basePath)
        baseName = os.path.splitext(os.path.basename(basePath))[0]
        paths = []
        for sheet in drawableSheets:
            sheetName = str(sheet.Name)
            paths.append(os.path.join(targetDir, f'{baseName}_{sheetName}.{extension}'))
        return paths

    @staticmethod
    def getDwgSettingsFile() -> str:
        """
        获取 DXF/DWG 转换器设置文件路径（与 NX 导出界面默认行为保持一致）

        Returns:
            str: 设置文件路径，未找到时返回空字符串
        """
        candidates = []
        envDir = os.environ.get('DXFDWG_DIR', '')
        if envDir:
            candidates.append(os.path.join(envDir, 'dxfdwg.def'))
        baseDir = os.environ.get('UGII_BASE_DIR', '')
        if baseDir:
            candidates.append(os.path.join(baseDir, 'DXFDWG', 'dxfdwg.def'))
        for filePath in candidates:
            try:
                if os.path.isfile(filePath):
                    return filePath
            except Exception:
                continue
        return ''

    @staticmethod
    def exportDrawing(part: NXOpen.Part, kinds, prefixName: str, suffixName: str,
                      folder: str, writeMsg: Callable, skipExisting: bool = False) -> Optional[bool]:
        """
        导出单个部件的图纸（可同时导出多种格式）

        Args:
            part (NXOpen.Part): NX 部件
            kinds (str | list[str]): 导出格式（'pdf' / 'dwg' 的单个或列表）
            prefixName (str): 文件名前缀
            suffixName (str): 文件名后缀
            folder (str): 输出文件夹
            writeMsg (function): 消息输出函数
            skipExisting (bool, optional): 是否跳过已存在的同名文件

        Returns:
            bool | None: True 成功，False 失败，None 跳过（无图纸页/全是空白页/全部已存在）
        """
        if isinstance(kinds, str):
            kinds = [kinds]
        kindList = [str(kind).lower() for kind in (kinds or []) if str(kind).strip()]

        allSheets, drawableSheets, skippedSheetNames = NxModules.getDrawingSheets(part)
        if not allSheets:
            writeMsg(_('  [!] 跳过: 该部件未发现任何图纸页'), 'warn')
            return None
        if skippedSheetNames:
            msg = _('  [i] 跳过空白图纸页: {sheets}')
            writeMsg(msg.format(sheets=', '.join(name for name in skippedSheetNames if name)))
        if not drawableSheets:
            writeMsg(_('  [!] 跳过: 该部件的图纸页均没有视图（空白图纸）'), 'warn')
            return None

        success = True
        attempted = False
        for kind in kindList:
            expectedPaths = NxModules.getDrawingOutputPaths(
                part, prefixName, suffixName, folder, kind, drawableSheets)
            extension = 'pdf' if kind == 'pdf' else 'dwg'
            # 传给转换器的输出路径始终是「基础文件名」；多图纸 DWG 由 NX 按图纸名拆分
            baseFilePath = BatchModules.buildOutputPath(
                part, prefixName, suffixName, folder, extension)

            # 全部输出都已存在时才跳过，避免多图纸 DWG 只导出部分文件
            if skipExisting and expectedPaths and all(os.path.exists(path) for path in expectedPaths):
                for path in expectedPaths:
                    msg = _('  [➭] 跳过已存在: {file_path}')
                    writeMsg(msg.format(file_path=path), 'warn')
                continue

            attempted = True
            removeOk = True
            for path in expectedPaths:
                if os.path.exists(path):
                    if not BatchModules.removeExisting(path, writeMsg):
                        removeOk = False
            # 清理上一次转换残留的 .log（转换器生成，属于中间文件）
            for logPath in NxModules.getDrawingLogPaths(part, prefixName, suffixName, folder, kind,
                                                        drawableSheets, expectedPaths):
                try:
                    if os.path.exists(logPath):
                        os.remove(logPath)
                except Exception:
                    pass
            if not removeOk:
                success = False
                continue

            if kind == 'pdf':
                result = NxModules.exportPdf(part, baseFilePath, writeMsg, drawableSheets)
            else:
                result = NxModules.exportDwg(part, baseFilePath, writeMsg, drawableSheets)
            if result is False:
                success = False

        if not attempted:
            return None
        return success

    @staticmethod
    def getDrawingLogPaths(part: NXOpen.Part, prefixName: str, suffixName: str, folder: str,
                           kind: str, drawableSheets: list, expectedPaths: list) -> list:
        """
        计算导出过程中可能生成的转换日志文件路径（用于清理）

        Args:
            part (NXOpen.Part): NX 部件
            prefixName (str): 文件名前缀
            suffixName (str): 文件名后缀
            folder (str): 输出文件夹
            kind (str): 导出格式
            drawableSheets (list): 有视图的图纸页列表
            expectedPaths (list[str]): 期望输出文件路径列表

        Returns:
            list[str]: 可能存在的 .log 文件路径列表
        """
        extension = 'pdf' if kind == 'pdf' else 'dwg'
        basePath = BatchModules.buildOutputPath(part, prefixName, suffixName, folder, extension)
        baseName = os.path.splitext(basePath)[0]
        paths = [baseName + '.log']
        for path in expectedPaths:
            paths.append(os.path.splitext(path)[0] + '.log')
        return paths

    @staticmethod
    def exportPdf(part: NXOpen.Part, filename: str, writeMsg: Callable,
                  sheets: Optional[list] = None) -> Optional[bool]:
        """
        导出 PDF 图纸

        Args:
            part (NXOpen.Part): NX 部件
            filename (str): 输出文件完整路径
            writeMsg (function): 消息输出函数
            sheets (list, optional): 需要导出的图纸页列表（默认导出全部有视图的图纸页）

        Returns:
            bool | None: True 成功，False 失败，None 跳过（无图纸页）
        """
        pdfbuilder = None
        try:
            if sheets is None:
                allSheets, sheets, skippedNames = NxModules.getDrawingSheets(part)
                if not allSheets:
                    writeMsg(_('  [!] 跳过: 该部件未发现任何图纸页'), 'warn')
                    return None
                if not sheets:
                    writeMsg(_('  [!] 跳过: 该部件的图纸页均没有视图（空白图纸）'), 'warn')
                    return None
                if skippedNames:
                    msg = _('  [i] 跳过空白图纸页: {sheets}')
                    writeMsg(msg.format(sheets=', '.join(name for name in skippedNames if name)))
            if not sheets:
                writeMsg(_('  [!] 跳过: 该部件未发现任何图纸页'), 'warn')  # 警告色
                return None

            for sheet in sheets:
                sheet.Open()

            pdfbuilder = part.PlotManager.CreatePrintPdfbuilder()
            pdfbuilder.Filename = filename
            pdfbuilder.SourceBuilder.SetSheets(sheets)
            pdfbuilder.Commit()

            # 等待输出文件生成（部分 NX 版本的转换器可能异步写盘）
            size = BatchModules.waitOutputFile(filename, NxModules.PDF_WAIT_TIMEOUT)
            if size <= 0:
                writeMsg(_('  [✘] PDF 导出失败: 未生成有效文件'), 'error')
                return False

            writeMsg(_('  [✓] PDF 导出成功'), 'success')  # 成功色
            msg: str = _('      📍 路径: {filename}')
            writeMsg(msg.format(filename=filename))
            return True
        except Exception as e:
            msg: str = _('  [✘] PDF 导出异常: {e}')
            writeMsg(msg.format(e=str(e)), 'error')  # 错误色
            return False
        finally:
            if pdfbuilder is not None:
                try:
                    pdfbuilder.Destroy()
                except Exception:
                    pass

    @staticmethod
    def waitDwgOutputs(expectedPaths: list, baseFilePath: str, sheetCount: int,
                       timeout: float = None) -> list:
        """
        等待 DWG 输出文件全部生成

        NX 多图纸导出时会按图纸名拆分文件，个别情况下文件名可能与预期略有差异，
        因此在等待预期文件的同时，会用「前缀匹配 + 数量」做兜底识别。

        Args:
            expectedPaths (list[str]): 预期输出文件路径列表
            baseFilePath (str): 输出文件完整路径（用于兜底扫描）
            sheetCount (int): 图纸数量
            timeout (float, optional): 超时秒数，默认为 DWG_WAIT_TIMEOUT

        Returns:
            list[str]: 实际生成的有效输出文件列表；超时返回空列表
        """
        if timeout is None:
            timeout = NxModules.DWG_WAIT_TIMEOUT
        targetDir = os.path.dirname(baseFilePath)
        baseName = os.path.splitext(os.path.basename(baseFilePath))[0]
        expected = [os.path.normpath(path) for path in expectedPaths]

        startTime = time.time()
        while time.time() - startTime < timeout:
            valid = []
            for path in expected:
                try:
                    if os.path.getsize(path) > 0:
                        valid.append(path)
                except Exception:
                    continue
            if len(valid) == len(expected):
                return valid

            # 兜底：按 "输出名_图纸名.dwg" 前缀扫描，数量满足即认为完成
            actual = []
            try:
                for fileName in os.listdir(targetDir):
                    lowerName = fileName.lower()
                    if not lowerName.endswith('.dwg'):
                        continue
                    if not lowerName.startswith(baseName.lower() + '_'):
                        continue
                    path = os.path.join(targetDir, fileName)
                    try:
                        if os.path.getsize(path) > 0:
                            actual.append(path)
                    except Exception:
                        continue
            except Exception:
                actual = []
            if len(actual) >= sheetCount:
                return sorted(actual)
            time.sleep(0.25)
        return []

    @staticmethod
    def exportDwg(part: NXOpen.Part, filename: str, writeMsg: Callable,
                  sheets: Optional[list] = None) -> Optional[bool]:
        """
        导出 AutoCAD DWG 图纸

        注意：NX 2412 在多图纸导出时会按图纸名把输出拆分为
        `<输出文件名>_<图纸名>.dwg` 多个文件；单图纸时输出为指定的文件名。
        本方法会等待全部输出生成、打印实际路径，并清理转换器生成的 .log。

        Args:
            part (NXOpen.Part): NX 部件
            filename (str): 输出文件完整路径
            writeMsg (function): 消息输出函数
            sheets (list, optional): 需要导出的图纸页列表（默认导出全部有视图的图纸页）

        Returns:
            bool | None: True 成功，False 失败，None 跳过（无图纸页/全部图纸页空白）
        """
        dxfdwgCreator = None
        try:
            if sheets is None:
                allSheets, sheets, skippedNames = NxModules.getDrawingSheets(part)
                if not allSheets:
                    writeMsg(_('  [!] 跳过: 该部件未发现任何图纸页'), 'warn')  # 警告色
                    return None
                if not sheets:
                    writeMsg(_('  [!] 跳过: 该部件的图纸页均没有视图（空白图纸）'), 'warn')
                    return None
                if skippedNames:
                    msg = _('  [i] 跳过空白图纸页: {sheets}')
                    writeMsg(msg.format(sheets=', '.join(name for name in skippedNames if name)))
            if not sheets:
                writeMsg(_('  [!] 跳过: 该部件未发现任何图纸页'), 'warn')  # 警告色
                return None

            targetDir = os.path.dirname(filename)
            baseName = os.path.splitext(os.path.basename(filename))[0]
            if len(sheets) <= 1:
                expectedPaths = [filename]
            else:
                expectedPaths = [
                    os.path.join(targetDir, f'{baseName}_{str(sheet.Name)}.dwg') for sheet in sheets
                ]

            theSession = NXOpen.Session.GetSession()
            dxfdwgCreator = theSession.DexManager.CreateDxfdwgCreator()
            dxfdwgCreator.InputFile = part.FullPath
            dxfdwgCreator.OutputFile = filename
            dxfdwgCreator.ExportData = NXOpen.DxfdwgCreator.ExportDataOption.Drawing
            dxfdwgCreator.AutoCADRevision = NXOpen.DxfdwgCreator.AutoCADRevisionOptions.R2004
            dxfdwgCreator.OutputFileType = NXOpen.DxfdwgCreator.OutputFileTypeOption.Dwg
            # 只导出有视图的图纸页，避免产生空白图纸文件；必须带引号，否则 NX 不输出
            dxfdwgCreator.DrawingList = ",".join([f'"{sheet.Name}"' for sheet in sheets])
            settingsFile = NxModules.getDwgSettingsFile()
            if settingsFile:
                try:
                    dxfdwgCreator.SettingsFile = settingsFile
                except Exception:
                    pass
            # 等待转换进程完成，保证 Commit 返回时输出已经处理完毕
            try:
                dxfdwgCreator.ProcessHoldFlag = True
            except Exception:
                pass
            dxfdwgCreator.Commit()

            # 等待实际输出文件（多图纸时 NX 会拆成多个文件，需按预期/前缀识别）
            outputs = NxModules.waitDwgOutputs(expectedPaths, filename, len(sheets))
            if not outputs:
                msg = _('  [✘] DWG 导出失败: 等待 {timeout:.0f} 秒仍未生成有效文件')
                writeMsg(msg.format(timeout=NxModules.DWG_WAIT_TIMEOUT), 'error')
                return False

            msg: str = _('  [✓] DWG 导出成功 ({len_of_sheets} 张图纸，{len_of_files} 个文件)')
            writeMsg(msg.format(len_of_sheets=len(sheets), len_of_files=len(outputs)), 'success')  # 成功色
            for output in outputs:
                try:
                    size = os.path.getsize(output) / 1024.0
                except Exception:
                    size = 0.0
                writeMsg(_('      📍 路径: {file_path}（{size:.1f} KB）').format(
                    file_path=output, size=size))

            # 清理转换器生成的 .log 文件（属于中间文件），保持输出目录整洁
            logPaths = [os.path.splitext(filename)[0] + '.log']
            for output in outputs:
                logPaths.append(os.path.splitext(output)[0] + '.log')
            for logPath in logPaths:
                try:
                    if os.path.exists(logPath):
                        os.remove(logPath)
                except Exception:
                    pass
            return True

        except Exception as e:
            msg: str = _('  [✘] DWG 导出异常: {e}')
            writeMsg(msg.format(e=str(e)), 'error')  # 错误色
            return False
        finally:
            if dxfdwgCreator is not None:
                try:
                    dxfdwgCreator.Destroy()
                except Exception:
                    pass

    @staticmethod
    def setFileReadOnly(filePath: str, readonly: bool = True):
        """
        设置文件只读属性

        Args:
            filePath(str): 文件路径
            readonly(bool): True 设置只读，False 取消只读
        """
        if readonly:
            os.chmod(filePath, 0o444)
        else:
            os.chmod(filePath, 0o777)
