"""端口检查模块 - 检查端口占用情况并提供清理功能"""

import json
import re
import subprocess
import sys
from pathlib import Path


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
