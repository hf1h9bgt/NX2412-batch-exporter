"""
file: remote_jobs.py
description: 免安装版后台作业执行逻辑（在 NX 内置 Python 中运行，供 remote_worker / remote_server 复用）
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.
"""


def emptyResult() -> dict:
    """
    构造空的任务结果

    Returns:
        dict: 统计结果
    """
    return {'success': 0, 'failed': 0, 'skipped': 0, 'total': 0, 'elapsed': 0.0}


def executeJob(job: dict, writeMsg, progress=None) -> dict:
    """
    执行一个后台作业（图纸导出 / 模型导出）

    Args:
        job (dict): 作业描述
            kind: 'drawings' 或 'models'
            files: 文件路径列表
            prefix / suffix / folder: 输出选项
            kinds: 图纸导出格式列表（drawings）
            skipExisting: 是否跳过已存在文件（drawings）
            options: 模型导出选项（models）
        writeMsg (function): 消息回调，签名 writeMsg(msg, level='info')
        progress (function, optional): 进度回调，签名 progress(done, total)

    Returns:
        dict: 任务统计结果
    """
    kind = job.get('kind')
    if kind == 'drawings':
        from nxmodules import NxModules
        return NxModules.exportDrawings(
            job.get('kinds') or ['pdf'],
            job.get('files') or [],
            job.get('prefix', ''),
            job.get('suffix', ''),
            job.get('folder', ''),
            writeMsg,
            progress=progress,
            skipExisting=bool(job.get('skipExisting', False)))

    if kind == 'models':
        from modelmodules import ModelModules
        from pluginoptions import ModelExportOptions
        options = ModelExportOptions(**(job.get('options') or {}))
        return ModelModules.exportModels(
            job.get('files') or [],
            job.get('prefix', ''),
            job.get('suffix', ''),
            job.get('folder', ''),
            options,
            writeMsg,
            progress=progress)

    writeMsg('  [✘] 未知的后台任务类型: {0}'.format(kind), 'error')
    return emptyResult()
