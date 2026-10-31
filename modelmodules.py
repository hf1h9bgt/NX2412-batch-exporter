"""
file: modelmodules.py
description: NX 模型导出模块（Parasolid XT / STEP STP），支持单个部件与装配体
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
import os
import time
from typing import Callable, Optional

import NXOpen

from batchmodules import BatchModules
from pluginoptions import ModelExportOptions, ModelFormat, StepSchema, XtVersion

# 兼容旧调用：模型导出选项定义已迁移到 pluginoptions（纯 Python，界面/免安装版可安全导入）
__all__ = ['ModelFormat', 'StepSchema', 'XtVersion', 'ModelExportOptions', 'ModelModules']


class ModelModules:
    """NX 模型导出功能模块"""

    XT_EXTENSION = 'x_t'
    STP_EXTENSION = 'stp'

    # 导出转换进程等待超时（秒）：NX 的 STP 转换有时在 Commit 后数秒才落盘，需要轮询等待
    WAIT_FILE_TIMEOUT_XT = 30.0
    WAIT_FILE_TIMEOUT_STP = 120.0

    # Parasolid 版本选项映射（NXOpen.ParasolidExporter.ParasolidVersionOption）
    _XT_VERSION_OPTIONS = {
        XtVersion.CURRENT.value: 'Current',
        XtVersion.NX2406.value: 'Ps361Nx2406',
        XtVersion.NX2306.value: 'Ps351Nx2306',
        XtVersion.NX2206.value: 'Ps341Nx2206',
        XtVersion.NX2007.value: 'Ps340Nx2007',
        XtVersion.NX12.value: 'Ps301Nx120',
    }

    # STEP 协议映射（NXOpen.StepCreator.ExportAsOption）
    _STEP_SCHEMA_OPTIONS = {
        StepSchema.AP203.value: 'Ap203',
        StepSchema.AP214.value: 'Ap214',
        StepSchema.AP242.value: 'Ap242',
    }

    _XT_VERSION_LABELS = {
        XtVersion.CURRENT.value: '当前版本',
        XtVersion.NX2406.value: 'NX 2406',
        XtVersion.NX2306.value: 'NX 2306',
        XtVersion.NX2206.value: 'NX 2206',
        XtVersion.NX2007.value: 'NX 2007',
        XtVersion.NX12.value: 'NX 12',
    }

    _STEP_SCHEMA_LABELS = {
        StepSchema.AP203.value: 'AP203',
        StepSchema.AP214.value: 'AP214',
        StepSchema.AP242.value: 'AP242',
    }

    @staticmethod
    def exportModels(prtList: list, prefixName: str, suffixName: str, folder: str,
                     options: ModelExportOptions, writeMsg: Callable,
                     progress: Optional[Callable] = None) -> dict:
        """
        批量导出模型（XT / STP），单个部件与装配体均支持

        Args:
            prtList (list[str]): 部件文件路径列表
            prefixName (str): 文件名前缀
            suffixName (str): 文件名后缀
            folder (str): 输出文件夹，为空时输出到源文件所在文件夹
            options (ModelExportOptions): 导出选项
            writeMsg (function): 消息输出函数，签名 writeMsg(msg, level='info')
            progress (function, optional): 进度回调，签名 progress(done, total)

        Returns:
            dict: 任务统计结果，见 BatchModules.foreachPart
        """
        if not prtList:
            writeMsg(_('  [!] 没有需要导出的模型文件'), 'warn')
            return {'success': 0, 'failed': 0, 'skipped': 0, 'total': 0, 'elapsed': 0.0}

        formats = [fmt.value for fmt in (ModelFormat.XT, ModelFormat.STP)
                   if fmt.value in (options.formats or [])]
        if not formats:
            writeMsg(_('  [!] 请至少选择一种导出格式（XT / STP）'), 'warn')
            return {'success': 0, 'failed': 0, 'skipped': 0, 'total': 0, 'elapsed': 0.0}

        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                msg = _('  [✘] 无法创建输出文件夹：{e}')
                writeMsg(msg.format(e=str(e)), 'error')
                return {'success': 0, 'failed': 0, 'skipped': 0, 'total': 0, 'elapsed': 0.0}

        # 输出格式与选项提示
        formatText = ' + '.join('XT' if fmt == ModelFormat.XT.value else 'STP' for fmt in formats)
        writeMsg(_('  导出格式: {formats}').format(formats=formatText))
        if ModelFormat.XT.value in formats:
            msg = _('  XT 版本: {version}，装配体扁平化: {flatten}')
            writeMsg(msg.format(
                version=ModelModules._XT_VERSION_LABELS.get(options.xtVersion, options.xtVersion),
                flatten=_('是') if options.flattenAssembly else _('否')))
        if ModelFormat.STP.value in formats:
            msg = _('  STEP 协议: {schema}')
            writeMsg(msg.format(
                schema=ModelModules._STEP_SCHEMA_LABELS.get(options.stepSchema, options.stepSchema)))
        if options.skipExisting:
            writeMsg(_('  跳过已存在的同名文件: 是'), 'warn')

        def worker(part) -> Optional[bool]:
            return ModelModules.exportPart(part, prefixName, suffixName, folder, options, formats, writeMsg)

        actionName = _('模型导出') + f' [{formatText}]'
        return BatchModules.foreachPart(prtList, worker, writeMsg, progress, actionName=actionName)

    @staticmethod
    def describePart(part: NXOpen.Part) -> dict:
        """
        获取部件信息：是否装配体、组件数、实体数

        Args:
            part (NXOpen.Part): NX 部件

        Returns:
            dict: {'isAssembly': bool, 'componentCount': int, 'bodyCount': int}
        """
        info = {'isAssembly': False, 'componentCount': 0, 'bodyCount': 0}
        try:
            info['bodyCount'] = len([body for body in part.Bodies])
        except Exception:
            pass

        try:
            rootComponent = part.ComponentAssembly.RootComponent
        except Exception:
            rootComponent = None

        if rootComponent is not None:
            info['isAssembly'] = True
            try:
                info['componentCount'] = ModelModules.countComponents(rootComponent)
            except Exception:
                info['componentCount'] = 0
        return info

    @staticmethod
    def countComponents(component) -> int:
        """
        递归统计装配体组件数量

        Args:
            component (NXOpen.Assemblies.Component): 组件

        Returns:
            int: 组件总数（含所有层级）
        """
        count = 0
        try:
            children = component.GetChildren()
        except Exception:
            return count
        for child in children or []:
            count += 1 + ModelModules.countComponents(child)
        return count

    @staticmethod
    def exportPart(part: NXOpen.Part, prefixName: str, suffixName: str, folder: str,
                   options: ModelExportOptions, formats: list, writeMsg: Callable) -> Optional[bool]:
        """
        导出单个部件的全部所选格式

        Args:
            part (NXOpen.Part): NX 部件
            prefixName (str): 文件名前缀
            suffixName (str): 文件名后缀
            folder (str): 输出文件夹
            options (ModelExportOptions): 导出选项
            formats (list[str]): 需要导出的格式（'xt' / 'stp'）
            writeMsg (function): 消息输出函数

        Returns:
            bool | None: True 成功，False 失败，None 全部跳过
        """
        info = ModelModules.describePart(part)
        if info['isAssembly']:
            msg = _('  [i] 装配体：共 {count} 个组件')
            writeMsg(msg.format(count=info['componentCount']))
        else:
            msg = _('  [i] 单个部件：共 {count} 个实体')
            writeMsg(msg.format(count=info['bodyCount']))
            if info['bodyCount'] == 0:
                writeMsg(_('  [!] 提示：该部件没有实体，导出的模型可能为空'), 'warn')

        success = True
        allSkipped = True

        # 导出前确保部件是工作部件（NX 导出功能要求工作部件存在于会话中）
        if not BatchModules.ensureWorkPart(part):
            writeMsg(_('  [!] 提示：未能将部件设置为工作部件，导出可能失败'), 'warn')

        for formatType in formats:
            if formatType == ModelFormat.XT.value:
                extension = ModelModules.XT_EXTENSION
            else:
                extension = ModelModules.STP_EXTENSION

            filePath = BatchModules.buildOutputPath(part, prefixName, suffixName, folder, extension)

            if options.skipExisting and os.path.exists(filePath):
                msg = _('  [➭] 跳过已存在: {file_path}')
                writeMsg(msg.format(file_path=filePath), 'warn')
                continue

            allSkipped = False
            if os.path.exists(filePath) and not ModelModules.removeExisting(filePath, writeMsg):
                success = False
                continue

            if formatType == ModelFormat.XT.value:
                msg = _('  [➜] 正在导出 XT（Parasolid）...')
                writeMsg(msg)
                result = ModelModules.exportXt(part, filePath, options, writeMsg, info['isAssembly'])
            else:
                msg = _('  [➜] 正在导出 STP（STEP），转换耗时较长，请稍候...')
                writeMsg(msg)
                result = ModelModules.exportStp(part, filePath, options, writeMsg, info['isAssembly'])
            if not result:
                success = False

        if allSkipped:
            return None
        return success

    @staticmethod
    def removeExisting(filePath: str, writeMsg: Callable) -> bool:
        """
        覆盖导出前删除已存在的旧文件（自动处理只读属性）

        Args:
            filePath (str): 文件路径
            writeMsg (function): 消息输出函数

        Returns:
            bool: 是否可以继续导出
        """
        return BatchModules.removeExisting(filePath, writeMsg)

    @staticmethod
    def checkOutputFile(filePath: str, writeMsg: Callable, formatName: str,
                        timeout: float = 30.0) -> bool:
        """
        等待并校验导出结果文件（NX 的转换进程可能异步写盘，需要轮询等待）

        Args:
            filePath (str): 输出文件路径
            writeMsg (function): 消息输出函数
            formatName (str): 格式名称，用于日志
            timeout (float): 等待输出的最长秒数

        Returns:
            bool: 文件是否有效
        """
        startTime = time.time()
        size = BatchModules.waitOutputFile(filePath, timeout=timeout)
        if size <= 0:
            msg = _('  [✘] {format_name} 导出失败：等待 {timeout:.0f} 秒仍未生成输出文件')
            writeMsg(msg.format(format_name=formatName, timeout=timeout), 'error')
            return False
        msg = _('  [✓] {format_name} 导出成功：{file_path}（{size:.1f} KB）')
        writeMsg(msg.format(format_name=formatName, file_path=filePath, size=size / 1024.0), 'success')
        return True

    @staticmethod
    def getStepSettingsFile(schema: str) -> str:
        """
        获取 STEP 转换器设置文件路径。

        NX 的 STEP 转换必须指定设置文件（.def），否则可能导出不含任何几何数据
        （只有产品结构）的空 STEP 文件。设置文件位于 NX 安装目录下：

        - AP203: <NX>/STEP203UG/ugstep203.def
        - AP214: <NX>/STEP214UG/ugstep214.def
        - AP242: <NX>/STEP214UG/ugstep214.def（实测 NX 2412 下用 STEP242 自带 def 会丢失实体几何，
                  使用 STEP214 的 def 搭配 ExportAs=Ap242 可导出含几何的 AP242 文件）

        Args:
            schema (str): STEP 协议（'ap203' / 'ap214' / 'ap242'）

        Returns:
            str: 设置文件路径，未找到时返回空字符串
        """
        baseDir = os.environ.get('UGII_BASE_DIR', '')
        candidates = []
        if schema == StepSchema.AP203.value:
            envDir = os.environ.get('STEP203UG_DIR', '')
            if envDir:
                candidates.append(os.path.join(envDir, 'ugstep203.def'))
            if baseDir:
                candidates.append(os.path.join(baseDir, 'STEP203UG', 'ugstep203.def'))
        else:
            # AP214 与 AP242 使用 STEP214 转换器设置文件（实测 AP242 用 step242 自带 def 会丢几何）
            envDir = os.environ.get('STEP214UG_DIR', '')
            if envDir:
                candidates.append(os.path.join(envDir, 'ugstep214.def'))
            if baseDir:
                candidates.append(os.path.join(baseDir, 'STEP214UG', 'ugstep214.def'))

        for filePath in candidates:
            try:
                if os.path.isfile(filePath):
                    return filePath
            except Exception:
                continue
        return ''

    @staticmethod
    def setOptionalCreatorProperty(creator, propertyName: str, value):
        """
        设置导出创建器的可选属性（不同 NX 版本可能存在差异，失败时忽略）

        Args:
            creator: NXOpen 导出创建器
            propertyName (str): 属性名
            value: 属性值
        """
        try:
            setattr(creator, propertyName, value)
        except Exception:
            pass

    @staticmethod
    def configureSelection(creator, isAssembly: bool):
        """
        配置导出对象范围与过滤类型（不配置时 NX 会报「没有可导出的对象」）

        Args:
            creator: NXOpen 导出创建器（ParasolidExporter / StepCreator）
            isAssembly (bool): 是否为装配体
        """
        try:
            if isAssembly:
                creator.ExportSelectionBlock.SelectionScope = NXOpen.ObjectSelector.Scope.EntireAssembly
            else:
                creator.ExportSelectionBlock.SelectionScope = NXOpen.ObjectSelector.Scope.EntirePart
        except Exception:
            # 老版本兼容：默认即为整个部件
            pass
        try:
            creator.ObjectTypes.Solids = True
            creator.ObjectTypes.Surfaces = True
            creator.ObjectTypes.ConvergentBodies = True
        except Exception:
            pass

    @staticmethod
    def exportXt(part: NXOpen.Part, filePath: str, options: ModelExportOptions, writeMsg: Callable,
                 isAssembly: bool = False) -> bool:
        """
        导出 Parasolid 文本文件（.x_t）

        Args:
            part (NXOpen.Part): NX 部件
            filePath (str): 输出文件路径
            options (ModelExportOptions): 导出选项
            writeMsg (function): 消息输出函数
            isAssembly (bool): 是否为装配体

        Returns:
            bool: 是否成功
        """
        exporter = None
        try:
            session = NXOpen.Session.GetSession()
            exporter = session.DexManager.CreateParasolidExporter()
            exporter.ExportDestination = NXOpen.BaseCreator.ExportDestinationOption.NativeFileSystem
            exporter.ExportFrom = NXOpen.ParasolidExporter.ExportFromOption.DisplayedPart
            exporter.InputFile = part.FullPath
            exporter.OutputFile = filePath
            exporter.OutputFileExtension = ModelModules.XT_EXTENSION
            # 关键：必须指定导出范围与对象类型，否则 NX 报「没有可导出的对象」
            ModelModules.configureSelection(exporter, isAssembly)
            versionName = ModelModules._XT_VERSION_OPTIONS.get(options.xtVersion, 'Current')
            exporter.ParasolidVersion = getattr(
                NXOpen.ParasolidExporter.ParasolidVersionOption, versionName,
                NXOpen.ParasolidExporter.ParasolidVersionOption.Current)
            exporter.FlattenAssembly = bool(options.flattenAssembly)
            # 等待转换进程完成，确保 Commit 返回前文件已处理完毕
            ModelModules.setOptionalCreatorProperty(exporter, 'ProcessHoldFlag', True)
            exporter.Commit()
            return ModelModules.checkOutputFile(filePath, writeMsg, 'XT',
                                                timeout=ModelModules.WAIT_FILE_TIMEOUT_XT)
        except Exception as e:
            msg = _('  [✘] XT 导出异常: {e}')
            writeMsg(msg.format(e=str(e)), 'error')
            return False
        finally:
            if exporter is not None:
                try:
                    exporter.Destroy()
                except Exception:
                    pass

    @staticmethod
    def exportStp(part: NXOpen.Part, filePath: str, options: ModelExportOptions, writeMsg: Callable,
                  isAssembly: bool = False) -> bool:
        """
        导出 STEP 文件（.stp）

        Args:
            part (NXOpen.Part): NX 部件
            filePath (str): 输出文件路径
            options (ModelExportOptions): 导出选项
            writeMsg (function): 消息输出函数
            isAssembly (bool): 是否为装配体

        Returns:
            bool: 是否成功
        """
        creator = None
        logFile = os.path.splitext(filePath)[0] + '.log'
        try:
            session = NXOpen.Session.GetSession()
            creator = session.DexManager.CreateStepCreator()
            creator.ExportDestination = NXOpen.BaseCreator.ExportDestinationOption.NativeFileSystem
            creator.ExportFrom = NXOpen.StepCreator.ExportFromOption.DisplayPart
            creator.InputFile = part.FullPath
            creator.OutputFile = filePath
            # 关键：必须指定导出范围与对象类型，否则 NX 报「没有可导出的对象」
            ModelModules.configureSelection(creator, isAssembly)
            # 关键：必须指定转换器设置文件，否则导出的 STEP 可能丢失几何数据
            settingsFile = ModelModules.getStepSettingsFile(options.stepSchema)
            if settingsFile:
                creator.SettingsFile = settingsFile
            else:
                writeMsg(_('  [!] 警告：未找到 STEP 转换设置文件，导出的 STEP 可能缺少几何数据'), 'warn')
            # 先设置设置文件，再设置协议等属性，避免被设置文件中的默认值覆盖
            schemaName = ModelModules._STEP_SCHEMA_OPTIONS.get(options.stepSchema, 'Ap214')
            creator.ExportAs = getattr(
                NXOpen.StepCreator.ExportAsOption, schemaName,
                NXOpen.StepCreator.ExportAsOption.Ap214)
            creator.ExportSolidsAndSurfacesAs = NXOpen.StepCreator.ExportSolidsAndSurfacesAsOption.Precise
            creator.ColorAndLayers = True
            # 导出全部图层上的对象（与 NX 导出界面默认值一致）
            ModelModules.setOptionalCreatorProperty(creator, 'LayerMask', '1-256')
            # 文件导出场景（非保存场景）；设为 True 时不会产生输出文件
            creator.FileSaveFlag = False
            # 等待转换进程完成（STEP 转换在后台异步进行，设为 True 后 Commit 会阻塞到转换结束）
            ModelModules.setOptionalCreatorProperty(creator, 'ProcessHoldFlag', True)
            creator.Commit()
            result = ModelModules.checkOutputFile(filePath, writeMsg, 'STP',
                                                  timeout=ModelModules.WAIT_FILE_TIMEOUT_STP)
            # NX 转换过程会生成同名 .log 文件，成功后清理以保持输出目录整洁
            if result:
                try:
                    if os.path.exists(logFile):
                        os.remove(logFile)
                except Exception:
                    pass
            return result
        except Exception as e:
            msg = _('  [✘] STP 导出异常: {e}')
            writeMsg(msg.format(e=str(e)), 'error')
            return False
        finally:
            if creator is not None:
                try:
                    creator.Destroy()
                except Exception:
                    pass
