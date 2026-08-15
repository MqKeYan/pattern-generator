"""端口检查模块 - 检查端口占用情况并提供清理功能"""

import json
import subprocess


def get_port_pids(port):
    """获取监听指定端口的进程PID列表"""
    out = subprocess.run(['netstat', '-ano'], capture_output=True, text=True,
                         encoding='gbk', errors='ignore').stdout
    pids = []
    for line in out.split('\n'):
        if f':{port}' in line and 'LISTENING' in line:
            parts = line.split()
            if parts:
                pid = parts[-1]
                if pid.isdigit() and pid not in pids:
                    pids.append(pid)
    return pids


def get_process_details(pids):
    """批量查询进程的进程名和命令行"""
    if not pids:
        return []
    # PowerShell 一次查询所有进程
    ps_filter = ' or '.join(f"ProcessId={p}" for p in pids)
    script = (f"$r = @(Get-CimInstance Win32_Process -Filter \"{ps_filter}\" "
              f"-ErrorAction SilentlyContinue | Select-Object ProcessId,Name,CommandLine); "
              f"$r | ConvertTo-Json -Compress")
    result = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                            capture_output=True, text=True,
                            encoding='utf-8', errors='ignore')
    if result.returncode != 0 or not result.stdout.strip():
        # 查询失败时仅返回PID，进程名未知
        return [{'ProcessId': int(p), 'Name': '(未知)', 'CommandLine': None} for p in pids]
    data = json.loads(result.stdout)
    if isinstance(data, dict):
        data = [data]
    return data


def show_port_status(port):
    """打印端口占用情况，返回占用进程列表"""
    pids = get_port_pids(port)
    if not pids:
        print(f"端口 {port} 未被占用，可以正常启动")
        return []
    processes = get_process_details(pids)
    print(f"端口 {port} 被以下进程占用：")
    for p in processes:
        cmdline = p.get('CommandLine') or '(未知命令行)'
        print(f"  PID {p.get('ProcessId')}  {p.get('Name')}  {cmdline}")
    return processes


def kill_port_processes(processes):
    """强制清理占用端口的进程"""
    for p in processes:
        pid = p.get('ProcessId')
        result = subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                                capture_output=True, text=True,
                                encoding='gbk', errors='ignore')
        if result.returncode == 0:
            print(f"  已清理: PID {pid} ({p.get('Name')})")
        else:
            msg = (result.stdout.strip() or result.stderr.strip() or '未知错误')
            print(f"  清理失败: PID {pid} ({msg})")
