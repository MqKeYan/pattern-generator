"""同软件实例检测 - 启动前检测本软件是否已有其他实例正在运行

多实例并存时会互相覆盖 config/settings.json 中的端口配置，导致先启动
实例对外公布的网址失效，并争抢 GPU 显存、缓存与任务队列。
检测手段（双保险）：
1. 实例锁文件 config/instance.lock：运行实例启动时写入自身 PID 与端口；
2. 进程扫描：打包运行按 exe 进程名匹配，开发运行按 run.py 命令行匹配。
锁文件中的进程已不存在时视为残留，读取时自动清理。
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from persistence import atomic_write_json
from paths import software_root

# 开发模式下命令行中 run.py 的路径边界匹配（python run.py / "..."\...\run.py" 等）
_RUN_PY_RE = re.compile(r'(?:^|[\s"\'\\])run\.py(?:$|[\s"\'])')


def _software_root():
    """软件根目录：打包后为 exe 所在目录，开发时为项目根目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return software_root()


def _lock_path():
    return _software_root() / 'config' / 'instance.lock'


def get_process_list():
    """枚举系统全部进程，返回进程信息列表（查询失败时返回空列表）"""
    script = ('Get-CimInstance Win32_Process | '
              'Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | '
              'ConvertTo-Json -Compress')
    result = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                            capture_output=True, text=True,
                            encoding='utf-8', errors='ignore')
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    return data or []


def _pid_alive(pid):
    """单独探测某个 PID 是否存活（无现成进程列表时使用）"""
    script = (f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
              "if ($p) { 'alive' } else { 'dead' }")
    result = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                            capture_output=True, text=True,
                            encoding='utf-8', errors='ignore')
    return result.stdout.strip() == 'alive'


def read_instance_lock(processes=None):
    """读取实例锁文件；锁归属进程已退出时视为残留并删除，返回 None

    processes 传入 get_process_list() 的结果可避免重复查询。
    """
    path = _lock_path()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    pid = data.get('pid')
    if not isinstance(pid, int) or pid == os.getpid():
        return None
    if processes is not None:
        alive = any(p.get('ProcessId') == pid for p in processes)
    else:
        alive = _pid_alive(pid)
    if not alive:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return data


def write_instance_lock(port, admin_port):
    """登记本实例的运行锁（PID + 端口），供下次启动的实例检测使用"""
    data = {
        'pid': os.getpid(),
        'port': port,
        'admin_port': admin_port,
        'exe': sys.executable if getattr(sys, 'frozen', False) else 'python run.py',
        'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    path = _lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, data)
    except OSError:
        pass


def remove_instance_lock():
    """删除本软件的实例锁文件（文件不存在时静默跳过）"""
    try:
        _lock_path().unlink(missing_ok=True)
    except OSError:
        pass


def _match_own_software(proc):
    """判断进程是否属于本软件：打包运行按 exe 进程名匹配，开发运行按 Python 解释器 + run.py 命令行匹配"""
    name = (proc.get('Name') or '').lower()
    if getattr(sys, 'frozen', False):
        return name == Path(sys.executable).name.lower()
    # 开发模式：仅匹配 Python 解释器进程，避免把命令行里恰好提到 run.py
    # 的编辑器、脚本等无关进程误判为本软件实例
    if not (name.startswith('python') or name == 'py.exe'):
        return False
    cmdline = (proc.get('CommandLine') or '').lower()
    return bool(_RUN_PY_RE.search(cmdline))


def detect_same_software_instances():
    """检测本软件的其他运行实例

    返回实例列表，每个实例为 {'processes': [进程信息...], 'lock': 锁数据或 None}。
    打包引导进程与其子进程会合并为同一实例；锁文件记录了活跃 PID 但进程扫描
    未匹配到时（如 exe 被改名），按锁文件补一条实例记录。
    """
    processes = get_process_list()
    own_pid = os.getpid()
    own_parent = next(
        (p.get('ParentProcessId') for p in processes if p.get('ProcessId') == own_pid),
        None,
    )

    matched = []
    for p in processes:
        pid = p.get('ProcessId')
        if not isinstance(pid, int) or pid == own_pid:
            continue
        # 排除自身进程树：打包引导父进程与本实例派生的同名子进程
        if own_parent is not None and pid == own_parent:
            continue
        if p.get('ParentProcessId') == own_pid:
            continue
        if _match_own_software(p):
            matched.append(p)

    # 父子进程都在列表中时合并为同一实例（打包引导进程 + 实际工作进程）
    matched_ids = {p['ProcessId'] for p in matched}
    instances = []
    for p in sorted(matched, key=lambda x: x['ProcessId']):
        if p.get('ParentProcessId') in matched_ids:
            continue  # 已并入其父进程所在的实例
        group = [p] + [c for c in matched if c.get('ParentProcessId') == p['ProcessId']]
        instances.append({'processes': group, 'lock': None})

    lock = read_instance_lock(processes)
    if lock:
        target = next(
            (inst for inst in instances
             if any(p['ProcessId'] == lock['pid'] for p in inst['processes'])),
            None,
        )
        if target is None:
            target = {'processes': [{'ProcessId': lock['pid'], 'Name': '(锁文件记录)',
                                     'ExecutablePath': lock.get('exe', '')}],
                      'lock': lock}
            instances.append(target)
        else:
            target['lock'] = lock

    return instances
