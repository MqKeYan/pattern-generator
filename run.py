"""启动脚本 - 运行斑图形成可视化系统的Web服务器"""

import sys
import os
import signal
import gc
import subprocess

# PyInstaller打包后只能看到_internal/目录，需添加系统site-packages
# 以便加载用户自行安装的包（如PyTorch）
if getattr(sys, 'frozen', False):
    # 收集所有包含PyTorch的路径
    torch_paths = []

    # 使用where命令查找所有Python
    try:
        result = subprocess.run(['where', 'python'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                python_path = line.strip()
                if python_path and python_path.lower().endswith('python.exe'):
                    python_dir = os.path.dirname(python_path)
                    for site_path in [os.path.join(python_dir, 'Lib', 'site-packages'), os.path.join(python_dir, 'site-packages')]:
                        if os.path.isdir(os.path.join(site_path, 'torch')) and site_path not in torch_paths:
                            torch_paths.append(site_path)
    except:
        pass

    # 让用户选择PyTorch版本
    if len(torch_paths) > 1:
        print("=" * 60)
        print(f"找到 {len(torch_paths)} 个PyTorch安装：")
        for i, path in enumerate(torch_paths, 1):
            print(f"{i}. {path}")
        print("=" * 60)
        while True:
            choice = input("请选择要使用的PyTorch版本 (输入序号): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(torch_paths):
                selected_path = torch_paths[int(choice) - 1]
                if selected_path not in sys.path:
                    sys.path.insert(0, selected_path)
                break
    elif torch_paths:
        if torch_paths[0] not in sys.path:
            sys.path.insert(0, torch_paths[0])

# 将src文件夹加入模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# 检测PyTorch是否可用
try:
    import torch
except ImportError:
    print("=" * 60)
    print("错误: 未检测到PyTorch！")
    print("请先安装PyTorch后再次运行此程序")
    print("=" * 60)
    input("按回车键退出...")
    sys.exit(1)

from web.server import app, client_cache, simulator
from waitress import serve
from version import VERSION
from port_check import show_port_status, kill_port_processes

# 服务端口
PORT = 5000

# 全局缓存清理标记
_cleaned = False

def cleanup_on_exit():
    """清理缓存和内存"""
    global _cleaned
    if _cleaned:
        return
    _cleaned = True
    print("\n正在清理缓存...")
    try:
        client_cache.clear()
        simulator.clear_memory()
        gc.collect()
        print("缓存清理完毕，服务器已停止")
    except Exception as e:
        print(f"清理时出错: {e}")

def signal_handler(sig, frame):
    """处理退出信号"""
    cleanup_on_exit()
    sys.exit(0)

if __name__ == '__main__':
    # 注册退出信号处理
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)

    # 获取本机局域网IP（匹配RFC 1918私网地址）
    out = subprocess.run(['ipconfig'], capture_output=True, text=True, encoding='gbk', errors='ignore').stdout
    ips = [w for l in (out or '').split('\n') for w in l.split() if w.count('.') == 3]
    lan_ip = next((ip for ip in ips if ip.startswith(('192.168.', '10.'))
                   or (ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31)), '未知')

    # 检查端口占用情况，让用户决定是否清理
    occupied = show_port_status(PORT)
    if occupied:
        choice = input("是否清理这些占用进程后启动？(y/n): ").strip().lower()
        if choice == 'y':
            kill_port_processes(occupied)
        else:
            print("跳过清理，直接启动")

    print("=" * 60)
    print(f"  斑图形成可视化系统 v{VERSION}")
    print(f"  本机访问: http://localhost:{PORT}")
    print(f"  局域网访问: http://{lan_ip}:{PORT}")
    print("  按 Ctrl+C 停止服务器")
    print("=" * 60)

    try:
        # threads=8 支持多用户同时访问，计算由锁串行
        serve(app, host='0.0.0.0', port=PORT, threads=8)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_on_exit()