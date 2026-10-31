"""
file: pluginoptions.py
description: 导出选项与文件名过滤工具（纯 Python，不依赖 NXOpen，可在免安装版/界面层使用）
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""
import os
from dataclasses import dataclass
from enum import Enum


class ModelFormat(Enum):
    """模型导出格式"""
    XT = 'xt'
    STP = 'stp'


class StepSchema(Enum):
    """STEP 协议"""
    AP203 = 'ap203'
    AP214 = 'ap214'
    AP242 = 'ap242'


class XtVersion(Enum):
    """Parasolid（XT）版本"""
    CURRENT = 'current'
    NX2406 = 'nx2406'
    NX2306 = 'nx2306'
    NX2206 = 'nx2206'
    NX2007 = 'nx2007'
    NX12 = 'nx12'


@dataclass
class ModelExportOptions:
    """模型导出选项"""
    formats: list
    stepSchema: str = StepSchema.AP214.value
    xtVersion: str = XtVersion.CURRENT.value
    flattenAssembly: bool = False
    skipExisting: bool = False


def nameContainsDwg(prtPath: str) -> bool:
    """
    判断文件名（不含目录）中是否包含 dwg（不区分大小写）

    NX 2412 主模型出图时，同一零件会生成两个文件：模型文件与图纸文件，
    图纸文件名中带 dwg 字样（如「零件_dwg1.prt」）。

    Args:
        prtPath (str): 文件路径

    Returns:
        bool: 文件名是否包含 dwg
    """
    try:
        fileName = os.path.basename(prtPath)
    except Exception:
        return False
    return 'dwg' in fileName.lower()


def filterPrts(prtList: list, mode: str = 'all') -> tuple:
    """
    按文件名过滤 NX 文件列表

    Args:
        prtList (list[str]): 文件路径列表
        mode (str): 过滤模式
            'drawing' -> 只保留文件名含 dwg 的（图纸文件）
            'model'   -> 去掉文件名含 dwg 的（只保留模型文件）
            'all'     -> 不过滤

    Returns:
        tuple: (保留的文件列表, 被过滤掉的文件列表)
    """
    kept = []
    filtered = []
    for prtPath in prtList or []:
        hasDwg = nameContainsDwg(prtPath)
        if mode == 'drawing':
            keep = hasDwg
        elif mode == 'model':
            keep = not hasDwg
        else:
            keep = True
        if keep:
            kept.append(prtPath)
        else:
            filtered.append(prtPath)
    return kept, filtered
