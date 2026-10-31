"""
file: remote_worker.py
description: 免安装版一次性后台 worker —— 由 run_journal.exe 调起，在 NX 内置 Python 中执行单个导出作业
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.

本脚本不是给用户直接运行的，而是由 remote_backend.py 通过 NX 的 run_journal.exe 启动。
作业参数通过环境变量传入：
    DSH_NX_JOB     作业 JSON 文件路径
    DSH_NX_LOG     日志输出文件路径（JSON 行格式，供界面实时读取）
    DSH_PLUGIN_DIR 插件后端源码目录（加入 sys.path）

注意：常驻暖机模式使用 remote_server.py，本脚本仅用于「不使用常驻引擎」时的一次性导出
（以及常驻服务启动失败时的兜底）。
"""
import json
import os
import sys
import traceback

JOB_PATH = os.environ.get('DSH_NX_JOB', '')
LOG_PATH = os.environ.get('DSH_NX_LOG', '')
PLUGIN_DIR = os.environ.get('DSH_PLUGIN_DIR', '')

if PLUGIN_DIR and PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)


def emit(payload: dict):
    """
    向日志文件追加一行记录（与 remote_backend.py 的解析严格对应）

    日志格式：
        [MSG] {"level": "info", "msg": "..."}
        [PROGRESS] {"done": 1, "total": 3}
        [RESULT] {"success": 1, "failed": 0, "skipped": 0, "total": 1, "elapsed": 6.7}
        [DONE]

    Args:
        payload (dict): 记录内容
    """
    try:
        payloadType = payload.get('type')
        if payloadType == 'msg':
            line = '[MSG] ' + json.dumps(
                {'level': payload.get('level', 'info'), 'msg': payload.get('msg', '')},
                ensure_ascii=False)
        elif payloadType == 'progress':
            line = '[PROGRESS] ' + json.dumps(
                {'done': payload.get('done', 0), 'total': payload.get('total', 0)},
                ensure_ascii=False)
        elif payloadType == 'result':
            line = '[RESULT] ' + json.dumps(payload.get('result') or {}, ensure_ascii=False)
        elif payloadType == 'done':
            line = '[DONE]'
        else:
            line = '[MSG] ' + json.dumps(
                {'level': 'info', 'msg': json.dumps(payload, ensure_ascii=False)},
                ensure_ascii=False)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def writeMsg(msg, level: str = 'info'):
    """
    消息输出回调（供导出模块调用）

    Args:
        msg (str): 消息内容
        level (str): 消息级别
    """
    emit({'type': 'msg', 'level': str(level), 'msg': '' if msg is None else str(msg)})


def progress(done: int, total: int):
    """
    进度回调（供导出模块调用）

    Args:
        done (int): 已完成数量
        total (int): 总数量
    """
    emit({'type': 'progress', 'done': int(done), 'total': int(total)})


def main():
    """执行一次性后台导出作业"""
    result = {'success': 0, 'failed': 0, 'skipped': 0, 'total': 0, 'elapsed': 0.0}
    try:
        # 兼容带 BOM 的 UTF-8（部分外部工具生成的 job 文件可能带 BOM）
        with open(JOB_PATH, 'r', encoding='utf-8-sig') as f:
            job = json.load(f)

        # 初始化界面/日志文本的多语言（无 mo 文件时回退中文）
        try:
            from language import init_i18n
            init_i18n()
        except Exception:
            pass

        from remote_jobs import executeJob
        result = executeJob(job, writeMsg, progress)
    except Exception:
        writeMsg('  [✘] 后台转换异常:\n{0}'.format(traceback.format_exc()), 'error')
    finally:
        emit({'type': 'result', 'result': result})
        emit({'type': 'done'})


main()
