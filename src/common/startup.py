"""启动检查模块 - 端口占用清理与同软件实例检测

1. 端口检查：检测相应用端口是否被占用，仅允许清理属于本软件的进程；
2. 实例检测：多实例并存时会互相覆盖 config/settings.json 中的端口配置，
   导致先启动实例对外公布的网址失效，并争抢 GPU 显存、缓存与任务队列。
   检测手段（双保险）：实例锁文件 config/instance.lock + 进程扫描。
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from common.config import software_root
from common.persistence import atomic_write_json


# ============================================================
# 端口检查
# ============================================================

def get_port_pids(port):
    """获取监听指定端口的进程PID列表"""
    out = subprocess.run(['netstat', '-ano'], capture_output=True, text=True,
                         encoding='gbk', errors='ignore').stdout
    pids = []
    pattern = re.compile(r'^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$')
    for line in out.splitlines():
        match = pattern.match(line)
        if match and int(match.group(1)) == int(port):
            pid = match.group(2)
            if pid not in pids:
                pids.append(pid)
    return pids


def get_process_details(pids):
    """批量查询进程的进程名"""
    if not pids:
        return []
    # PowerShell 一次查询所有进程
    ps_filter = ' or '.join(f"ProcessId={p}" for p in pids)
    script = (f"$r = @(Get-CimInstance Win32_Process -Filter \"{ps_filter}\" "
              f"-ErrorAction SilentlyContinue | Select-Object ProcessId,Name,ExecutablePath,CommandLine); "
              f"$r | ConvertTo-Json -Compress")
    result = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                            capture_output=True, text=True,
                            encoding='utf-8', errors='ignore')
    if result.returncode != 0 or not result.stdout.strip():
        # 查询失败时仅返回PID，进程名未知
        return [{'ProcessId': int(p), 'Name': '(未知)'} for p in pids]
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [{'ProcessId': int(p), 'Name': '(未知)'} for p in pids]
    if isinstance(data, dict):
        data = [data]
    return data


def show_port_status(port):
    """打印端口占用情况，返回占用进程列表"""
    pids = get_port_pids(port)
    if not pids:
        print(f"  端口 {port} 未被占用，可以正常启动")
        return []
    processes = get_process_details(pids)
    print(f"  端口 {port} 被以下进程占用：")
    for p in processes:
        print(f"    PID {p.get('ProcessId')}  {p.get('Name')}")
    return processes


def _belongs_to_software(process):
    """仅允许终止本软件实例，不误杀其他应用。"""
    name = str(process.get('Name') or '').lower()
    if getattr(sys, 'frozen', False):
        return name == Path(sys.executable).name.lower()
    if not (name.startswith('python') or name == 'py.exe'):
        return False
    return bool(re.search(r'(?:^|[\\/\s\"\'])run\.py(?:$|[\s\"\'])',
                          str(process.get('CommandLine') or '').lower()))


def kill_port_processes(processes, confirmed=False):
    """用户明确确认后，仅清理属于本软件的端口占用进程。"""
    if not confirmed:
        print('  未获得明确确认，未清理任何进程')
        return False
    all_success = True
    for p in processes:
        pid = p.get('ProcessId')
        if not pid or not _belongs_to_software(p):
            print(f"  已跳过非本软件进程: PID {pid} ({p.get('Name')})")
            all_success = False
            continue
        result = subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                                capture_output=True, text=True,
                                encoding='gbk', errors='ignore')
        if result.returncode == 0:
            print(f"  已清理: PID {pid} ({p.get('Name')})")
        else:
            all_success = False
            msg = (result.stdout.strip() or result.stderr.strip() or '未知错误')
            print(f"  清理失败: PID {pid} ({msg})")
    return all_success


# ============================================================
# 实例检测
# ============================================================

# 开发模式下命令行中 run.py 的路径边界匹配（python run.py / "..."\...\run.py" 等）
_RUN_PY_RE = re.compile(r'(?:^|[\s"\'\\])run\.py(?:$|[\s"\'])')

_LOCK_PATH = software_root() / 'config' / 'instance.lock'


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
    try:
        data = json.loads(_LOCK_PATH.read_text(encoding='utf-8'))
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
            _LOCK_PATH.unlink(missing_ok=True)
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
    try:
        _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(_LOCK_PATH, data)
    except OSError:
        pass


def remove_instance_lock():
    """删除本软件的实例锁文件（文件不存在时静默跳过）"""
    try:
        _LOCK_PATH.unlink(missing_ok=True)
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
