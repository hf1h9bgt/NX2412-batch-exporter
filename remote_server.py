"""
file: remote_server.py
description: 免安装版常驻后台转换服务 —— 由 run_journal.exe 启动后在 NX 内置 Python 中循环执行导出作业
author: IYATT-yx
repository: https://github.com/IYATT-yx/NX-batch-PDF-exporter
copyright:  Copyright (c) 2026 IYATT-yx.
            Licensed under the MIT License. See LICENSE file in the project root for full license information.

工作方式：
- remote_backend.py 通过 NX 的 run_journal.exe 启动本脚本，本脚本保持 NX 进程常驻；
- 外部界面把作业 JSON 写入（环境变量 DSH_NX_JOB_DIR 指定的）jobs 子目录；
- 本脚本轮询 jobs 目录，逐个执行（调用 remote_jobs.executeJob），并把日志/进度/结果以 JSON 行
  写入 logs/<作业ID>.jsonl，外部界面实时读取；
- 空闲超过 DSH_SERVER_IDLE_TIMEOUT 秒（默认 1800）或检测到 stop 文件时，退出循环并释放 NX 进程。

环境变量：
    DSH_NX_JOB_DIR    作业目录（必须）
    DSH_PLUGIN_DIR    插件后端源码目录（加入 sys.path）
    DSH_SERVER_IDLE_TIMEOUT  空闲退出秒数（默认 1800）
"""
import glob
import json
import os
import sys
import time
import traceback

JOB_DIR = os.environ.get('DSH_NX_JOB_DIR', '')
PLUGIN_DIR = os.environ.get('DSH_PLUGIN_DIR', '')
IDLE_TIMEOUT = float(os.environ.get('DSH_SERVER_IDLE_TIMEOUT', '1800'))
POLL_INTERVAL = 0.3

JOBS_DIR = os.path.join(JOB_DIR, 'jobs')
LOGS_DIR = os.path.join(JOB_DIR, 'logs')
READY_FILE = os.path.join(JOB_DIR, 'server_ready.json')
ERROR_FILE = os.path.join(JOB_DIR, 'server_error.txt')
EXITED_FILE = os.path.join(JOB_DIR, 'server_exited.json')
STOP_FILE = os.path.join(JOB_DIR, 'stop')


def emit(logPath: str, payload: dict):
    """
    向作业日志文件追加一行记录（外部界面实时读取）

    日志格式必须与 remote_backend.py 的解析严格对应：
        [MSG] {"level": "info", "msg": "..."}
        [PROGRESS] {"done": 1, "total": 3}
        [RESULT] {"success": 1, ...}
        [DONE]

    Args:
        logPath (str): 日志文件路径
        payload (dict): 记录内容（含 type 字段）
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
        with open(logPath, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def writeReady():
    """写入服务就绪标记（包含进程与 NX 版本信息）"""
    info = {
        'pid': os.getpid(),
        'startTime': time.time(),
        'nxVersion': '',
    }
    try:
        import NXOpen
        session = NXOpen.Session.GetSession()
        info['nxVersion'] = str(session.GetEnvironmentVariableValue('UGII_VERSION'))
    except Exception:
        pass
    try:
        with open(READY_FILE, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False)
    except Exception:
        pass


def processJob(jobPath: str):
    """
    处理一个作业文件

    Args:
        jobPath (str): 作业 JSON 文件路径
    """
    jobId = os.path.splitext(os.path.basename(jobPath))[0]
    logPath = os.path.join(LOGS_DIR, jobId + '.jsonl')

    def writeMsg(msg, level: str = 'info'):
        emit(logPath, {'type': 'msg', 'level': str(level), 'msg': '' if msg is None else str(msg)})

    def progress(done, total):
        emit(logPath, {'type': 'progress', 'done': int(done), 'total': int(total)})

    result = {'success': 0, 'failed': 0, 'skipped': 0, 'total': 0, 'elapsed': 0.0}
    try:
        with open(jobPath, 'r', encoding='utf-8-sig') as f:
            job = json.load(f)
        from remote_jobs import executeJob
        result = executeJob(job, writeMsg, progress)
    except Exception:
        writeMsg('  [✘] 后台转换异常:\n' + traceback.format_exc(), 'error')
    finally:
        emit(logPath, {'type': 'result', 'result': result})
        emit(logPath, {'type': 'done'})
        try:
            os.remove(jobPath)
        except Exception:
            try:
                os.rename(jobPath, jobPath + '.done')
            except Exception:
                pass


def main():
    """常驻服务主循环"""
    try:
        if PLUGIN_DIR and PLUGIN_DIR not in sys.path:
            sys.path.insert(0, PLUGIN_DIR)
        os.makedirs(JOBS_DIR, exist_ok=True)
        os.makedirs(LOGS_DIR, exist_ok=True)

        # 初始化多语言（无 mo 文件时回退中文）
        try:
            from language import init_i18n
            init_i18n()
        except Exception:
            pass

        # 确认 NX 会话已就绪（此时 run_journal 已完成 NX 初始化）
        import NXOpen  # noqa: F401
        session = NXOpen.Session.GetSession()  # noqa: F841

        writeReady()

        lastActivity = time.time()
        while True:
            if os.path.exists(STOP_FILE):
                break
            jobFiles = sorted(glob.glob(os.path.join(JOBS_DIR, '*.json')))
            if jobFiles:
                for jobFile in jobFiles:
                    processJob(jobFile)
                    lastActivity = time.time()
                continue
            if time.time() - lastActivity > IDLE_TIMEOUT:
                break
            time.sleep(POLL_INTERVAL)
    except Exception:
        try:
            with open(ERROR_FILE, 'w', encoding='utf-8') as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
    finally:
        try:
            with open(EXITED_FILE, 'w', encoding='utf-8') as f:
                json.dump({'pid': os.getpid(), 'exitTime': time.time()}, f, ensure_ascii=False)
        except Exception:
            pass
        try:
            if os.path.exists(READY_FILE):
                os.remove(READY_FILE)
        except Exception:
            pass


main()
