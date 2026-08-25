"""启动脚本 - 运行斑图形成可视化系统的Web服务器"""

import sys
import os
import signal
import gc
import subprocess
import socket
import shutil
import threading
import time
import webbrowser
import winreg

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

from version import VERSION
from port_check import get_port_pids, show_port_status, kill_port_processes
from settings import load_settings, update_settings

# 服务端口
startup_settings = load_settings()
PORT = startup_settings['port']
AUTO_OPEN_BROWSER = startup_settings['auto_open_browser']
AUTO_OPEN_BROWSER_CONFIGURED = startup_settings['auto_open_browser_configured']

# 全局缓存清理标记
_cleaned = False


def open_browser_when_ready(url):
    """等待本地服务就绪后打开浏览器"""
    for _ in range(50):
        try:
            with socket.create_connection(('127.0.0.1', PORT), timeout=0.2):
                open_browser_new_window(url)
                return
        except OSError:
            time.sleep(0.1)


def open_browser_new_window(url):
    """使用默认浏览器的新窗口打开地址"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice',
        ) as key:
            prog_id = str(winreg.QueryValueEx(key, 'ProgId')[0]).lower()
    except OSError:
        prog_id = ''

    browser_paths = {
        'chrome': [
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
        ],
        'edge': [
            os.path.join(os.environ.get('PROGRAMFILES', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
        ],
        'firefox': [
            os.path.join(os.environ.get('PROGRAMFILES', ''), 'Mozilla Firefox', 'firefox.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Mozilla Firefox', 'firefox.exe'),
        ],
        'brave': [
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe'),
            os.path.join(os.environ.get('PROGRAMFILES', ''), 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe'),
        ],
        'opera': [
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Opera', 'opera.exe'),
            os.path.join(os.environ.get('PROGRAMFILES', ''), 'Opera', 'launcher.exe'),
        ],
    }
    browser_path = next(
        (
            path for name, paths in browser_paths.items()
            if name in prog_id
            for path in paths
            if path and os.path.isfile(path)
        ),
        None,
    )

    try:
        if browser_path:
            subprocess.Popen([browser_path, '--new-window', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            webbrowser.open_new(url)
    except OSError:
        webbrowser.open_new(url)

def cleanup_on_exit():
    """清理缓存和内存"""
    global _cleaned
    if _cleaned:
        return
    _cleaned = True
    os.system('cls')
    print("正在清理缓存...")
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
            while True:
                new_port = input("请输入新的端口号（1024-65535）：").strip()
                try:
                    candidate_port = int(new_port)
                except ValueError:
                    print("端口号必须是数字，请重新输入。")
                    continue
                if not 1024 <= candidate_port <= 65535:
                    print("端口号范围必须为1024-65535，请重新输入。")
                    continue
                if get_port_pids(candidate_port):
                    print(f"端口 {candidate_port} 已被占用，请输入其他端口号。")
                    continue
                PORT = candidate_port
                update_settings(port=PORT)
                print(f"端口 {PORT} 未被占用，将使用该端口启动。")
                break

    # 端口页确认后清屏，首次运行时设置浏览器启动方式
    input("按回车继续启动...")
    os.system('cls')

    if not AUTO_OPEN_BROWSER_CONFIGURED:
        print("=" * 60)
        print("  自动打开浏览器设置")
        print("=" * 60)
        while True:
            browser_choice = input("是否自动打开浏览器？(y/n): ").strip().lower()
            if browser_choice in ('y', 'n'):
                break
            print("请输入 y 或 n。")
        AUTO_OPEN_BROWSER = browser_choice == 'y'
        update_settings(
            auto_open_browser=AUTO_OPEN_BROWSER,
            auto_open_browser_configured=True,
        )
        os.system('cls')

    # 端口确认后再初始化模拟器，确保设备信息晚于端口提示输出
    from web.server import app, client_cache, simulator
    from waitress import serve

    # 注册退出信号处理
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 60)
    print(f"  斑图形成可视化系统 v{VERSION}")
    print(f"  使用设备: {'CUDA' if simulator.use_cuda else 'CPU'}")
    print(f"  计算硬件: {simulator.hardware_info}")
    print(f"  局域网访问: http://{lan_ip}:{PORT}")
    print("  按 Ctrl+C 停止服务器")
    print("=" * 60)

    # 服务开始监听后按设置自动打开系统浏览器
    if AUTO_OPEN_BROWSER:
        lan_url = f'http://{lan_ip}:{PORT}'
        threading.Thread(target=open_browser_when_ready, args=(lan_url,), daemon=True).start()

    try:
        # threads=8 支持多用户同时访问，计算由锁串行
        serve(app, host='0.0.0.0', port=PORT, threads=8)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_on_exit()
