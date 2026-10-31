"""
file: batchmodules.py
description: 批量处理引擎：部件打开/复用/关闭、进度回调、结果统计
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
import os
import time
from typing import Callable, Optional

import NXOpen

# Windows 文件名非法字符
_INVALID_NAME_CHARS = '<>:"/\\|?*'


class BatchModules:
    """
    批量处理 NX 部件的通用引擎。

    worker 约定：
        worker(part) -> bool | None
            True  : 本文件处理成功
            False : 本文件处理失败
            None  : 本文件被跳过（不计入成功/失败，计入跳过）
    """

    @staticmethod
    def sanitizeNamePart(name: str) -> str:
        """
        清理文件名前缀/后缀中的非法字符（Windows）

        Args:
            name (str): 用户输入的前缀/后缀

        Returns:
            str: 清理后的字符串
        """
        if not name:
            return ''
        result = ''.join('_' if c in _INVALID_NAME_CHARS or ord(c) < 32 else c for c in name)
        # Windows 文件名不能以空格或点结尾
        return result.rstrip(' .')

    @staticmethod
    def buildOutputPath(part: NXOpen.Part, prefixName: str, suffixName: str, folder: str, extension: str) -> str:
        """
        构建输出文件路径

        Args:
            part (NXOpen.Part): NX 部件
            prefixName (str): 文件名前缀
            suffixName (str): 文件名后缀
            folder (str): 输出文件夹，为空时使用部件所在文件夹
            extension (str): 扩展名（不含点），如 pdf、x_t

        Returns:
            str: 完整输出路径
        """
        targetFolder = folder if folder else os.path.dirname(part.FullPath)
        prefixName = BatchModules.sanitizeNamePart(prefixName)
        suffixName = BatchModules.sanitizeNamePart(suffixName)
        fileName = f'{prefixName}{part.Leaf}{suffixName}.{extension}'
        return os.path.join(targetFolder, fileName)

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
        try:
            # 只读文件在 Windows 下无法直接删除，先尝试去除只读属性
            try:
                os.chmod(filePath, 0o666)
            except Exception:
                pass
            os.remove(filePath)
            return True
        except Exception as e:
            msg = _('  [✘] 无法覆盖已存在的文件（可能被占用）：{file_path} - {e}')
            writeMsg(msg.format(file_path=filePath, e=str(e)), 'error')
            return False

    @staticmethod
    def waitOutputFile(filePath: str, timeout: float = 60.0, interval: float = 0.25) -> int:
        """
        等待转换进程生成输出文件（NX 部分转换器异步写盘，Commit 返回时文件可能尚未生成）

        Args:
            filePath (str): 输出文件路径
            timeout (float): 最长等待秒数
            interval (float): 轮询间隔（秒）

        Returns:
            int: 文件大小（字节），超时或文件无效时返回 0
        """
        startTime = time.time()
        while time.time() - startTime < timeout:
            try:
                size = os.path.getsize(filePath)
            except Exception:
                size = 0
            if size > 0:
                return size
            time.sleep(interval)
        return 0

    @staticmethod
    def findOpenedPart(session: NXOpen.Session, prtPath: str) -> Optional[NXOpen.BasePart]:
        """
        在会话中查找已经打开（加载）的部件

        Args:
            session (NXOpen.Session): NX 会话
            prtPath (str): 部件路径

        Returns:
            NXOpen.BasePart | None: 找到的部件，未找到返回 None
        """
        try:
            target = os.path.normcase(os.path.normpath(prtPath))
        except Exception:
            return None

        try:
            parts = session.Parts
        except Exception:
            return None

        try:
            for part in parts:
                try:
                    if part is None:
                        continue
                    fullPath = part.FullPath
                    if fullPath and os.path.normcase(os.path.normpath(fullPath)) == target:
                        return part
                except Exception:
                    continue
        except Exception:
            return None
        return None

    @staticmethod
    def openPart(prtPath: str, writeMsg: Callable) -> tuple:
        """
        打开部件（若已在内存中则复用并激活显示）

        Args:
            prtPath (str): 部件路径
            writeMsg (function): 消息输出函数

        Returns:
            tuple: (part, opened, loadStatus)
                part: NXOpen.BasePart | None
                opened (bool): True 表示由本函数打开，需要任务结束时关闭
                loadStatus: NXOpen.PartLoadStatus | None
        """
        session = NXOpen.Session.GetSession()
        shortName = os.path.basename(prtPath)

        # 已经在内存中的文件直接复用，避免重复打开报错
        openedPart = BatchModules.findOpenedPart(session, prtPath)
        if openedPart is not None:
            try:
                session.Parts.SetActiveDisplay(
                    openedPart,
                    NXOpen.DisplayPartOption.AllowAdditional,
                    NXOpen.PartDisplayPartWorkPartOption.UseLast)
            except Exception:
                pass
            msg = _('  [!] 提示：{short_name} 已经在内存中，直接复用')
            writeMsg(msg.format(short_name=shortName), 'warn')
            return openedPart, False, None

        try:
            part, loadStatus = session.Parts.OpenActiveDisplay(prtPath, NXOpen.DisplayPartOption.AllowAdditional)
            return part, True, loadStatus
        except NXOpen.NXException as e:
            # 兼容不同 NX 语言/时序：打开报错后再确认一次部件是否已进入会话
            openedPart = BatchModules.findOpenedPart(session, prtPath)
            if openedPart is not None:
                try:
                    session.Parts.SetActiveDisplay(
                        openedPart,
                        NXOpen.DisplayPartOption.AllowAdditional,
                        NXOpen.PartDisplayPartWorkPartOption.UseLast)
                except Exception:
                    pass
                msg = _('  [!] 提示：{short_name} 已经在内存中，直接复用')
                writeMsg(msg.format(short_name=shortName), 'warn')
                return openedPart, False, None
            msg = _('  [✘] 错误：无法打开文件 - {e}')
            writeMsg(msg.format(e=str(e)), 'error')
            return None, False, None

    @staticmethod
    def ensureWorkPart(part: NXOpen.Part) -> bool:
        """
        将部件设置为工作部件（NX 的导出功能要求工作部件存在于会话中）

        Args:
            part (NXOpen.Part): NX 部件

        Returns:
            bool: 是否设置成功
        """
        try:
            session = NXOpen.Session.GetSession()
            if session.Parts.Work is not part:
                session.Parts.SetWork(part)
            return True
        except Exception:
            return False

    @staticmethod
    def closePart(part: NXOpen.BasePart, loadStatus, writeMsg: Callable):
        """
        关闭本工具打开的部件并释放加载状态

        Args:
            part (NXOpen.BasePart): NX 部件
            loadStatus: NXOpen.PartLoadStatus | None
            writeMsg (function): 消息输出函数
        """
        shortName = os.path.basename(part.FullPath) if part and part.FullPath else ''
        try:
            part.Close(NXOpen.BasePart.CloseWholeTree.FalseValue, NXOpen.BasePart.CloseModified.CloseModified, None)
            if loadStatus is not None:
                loadStatus.Dispose()
            msg = _('  [➔] 资源释放：{short_name} 已关闭')
            writeMsg(msg.format(short_name=shortName))
        except Exception as e:
            msg = _('  [!] 关闭部件失败（不影响已导出文件）：{e}')
            writeMsg(msg.format(e=str(e)), 'warn')

    @staticmethod
    def foreachPart(prtList: list, worker: Callable, writeMsg: Callable,
                    progress: Optional[Callable] = None, actionName: str = '') -> dict:
        """
        对每个 NX 文件执行 worker

        Args:
            prtList (list[str]): NX 文件路径列表
            worker (function): worker(part) -> bool | None
            writeMsg (function): 消息输出函数
            progress (function, optional): progress(done, total) 进度回调
            actionName (str, optional): 任务名称，用于日志

        Returns:
            dict: {'success': int, 'failed': int, 'skipped': int, 'total': int, 'elapsed': float}
        """
        session = NXOpen.Session.GetSession()
        total = len(prtList)
        success = 0
        failed = 0
        skipped = 0
        startTime = time.time()

        writeMsg('=' * 50)
        if actionName:
            msg = _('🚀 开始批量任务：{action_name} | 共计: {total} 个文件')
        else:
            msg = _('🚀 开始批量任务 | 共计: {total} 个文件')
        writeMsg(msg.format(action_name=actionName, total=total))
        writeMsg('=' * 50)

        if progress is not None:
            progress(0, total)

        for index, prtPath in enumerate(prtList, 1):
            shortName = os.path.basename(prtPath)
            msg = _('\n[{index}/{total}] 正在处理: {short_name}')
            writeMsg(msg.format(index=index, total=total, short_name=shortName))

            fileStart = time.time()
            part = None
            opened = False
            loadStatus = None
            try:
                part, opened, loadStatus = BatchModules.openPart(prtPath, writeMsg)
                if part is None:
                    failed += 1
                else:
                    result = worker(part)
                    if result is True:
                        success += 1
                    elif result is False:
                        failed += 1
                    else:
                        skipped += 1
            except Exception as e:
                failed += 1
                msg = _('  [✘] 处理异常: {e}')
                writeMsg(msg.format(e=str(e)), 'error')
            finally:
                # 只关闭本工具打开的部件，用户原本已打开的部件保持原样
                if opened and part is not None:
                    BatchModules.closePart(part, loadStatus, writeMsg)
                msg = _('  ⏱ 耗时: {elapsed:.2f} 秒')
                writeMsg(msg.format(elapsed=time.time() - fileStart))
                if progress is not None:
                    progress(index, total)

        elapsed = time.time() - startTime
        writeMsg('\n' + '=' * 50)
        if total > 0 and success == total:
            level = 'success'
        elif total > 0 and skipped == total:
            # 全部跳过（例如都命中「跳过已存在的同名文件」）属于正常情况
            level = 'warn'
        elif success > 0:
            level = 'warn'
        else:
            level = 'error'
        msg = _('✨ 任务完成！成功: {success} / {total}，失败: {failed}，跳过: {skipped}，总耗时: {elapsed:.2f} 秒')
        writeMsg(msg.format(success=success, total=total, failed=failed,
                            skipped=skipped, elapsed=elapsed), level)
        writeMsg('=' * 50)

        return {
            'success': success,
            'failed': failed,
            'skipped': skipped,
            'total': total,
            'elapsed': elapsed,
        }
