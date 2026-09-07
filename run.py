"""启动脚本 - 同时启动主服务（局域网）与后台管理中心（仅本机）

主服务: 0.0.0.0:<port>   FastAPI + Uvicorn（单 worker）
后台:   127.0.0.1:<admin_port>  FastAPI + Uvicorn（单 worker，仅本机）
任一服务异常退出或后台触发「停止所有服务」时，整体退出并清理资源。
"""

import sys
import os
import gc
import msvcrt
import signal
import subprocess
import socket
import threading
import time
import webbrowser
import winreg

# PyInstaller打包后只能看到_internal/目录，需添加系统site-packages
# 以便加载用户自行安装的包（如PyTorch）
if getattr(sys, 'frozen', False):
    torch_paths = []
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
    except Exception:
        pass

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

from common.config import VERSION, load_settings, update_settings
from common.startup import (
    detect_same_software_instances,
    write_instance_lock,
    remove_instance_lock,
    get_port_pids,
    show_port_status,
    kill_port_processes,
)

startup_settings = load_settings()
PORT = startup_settings['port']
ADMIN_PORT = startup_settings['admin_port']
AUTO_OPEN_BROWSER = startup_settings['auto_open_browser']
AUTO_OPEN_ADMIN_BROWSER = startup_settings['auto_open_admin_browser']
AUTO_OPEN_BROWSER_CONFIGURED = startup_settings['auto_open_browser_configured']


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
            subprocess.Popen(
                [browser_path, '--new-window', '--start-maximized', url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            webbrowser.open_new(url)
    except OSError:
        webbrowser.open_new(url)


def open_browser_when_ready(url, port):
    """等待本地服务就绪后打开浏览器"""
    for _ in range(50):
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                open_browser_new_window(url)
                return
        except OSError:
            time.sleep(0.1)


def ensure_port_free(port, name):
    """检查端口占用，返回 (用户确认后的最终端口, 是否出现过占用)"""
    occupied = show_port_status(port)
    if not occupied:
        return port, False
    choice = input(f"是否清理这些占用 {name}({port}) 的进程后启动？(y/n): ").strip().lower()
    if choice == 'y':
        if kill_port_processes(occupied, confirmed=True) and not get_port_pids(port):
            return port, True
        print(f"  端口 {port} 仍被占用，请改用其他端口。")
    while True:
        new_port = input(f"请输入新的{name}端口号（1024-65535）：").strip()
        try:
            candidate = int(new_port)
        except ValueError:
            print("端口号必须是数字，请重新输入。")
            continue
        if not 1024 <= candidate <= 65535:
            print("端口号范围必须为1024-65535，请重新输入。")
            continue
        if get_port_pids(candidate):
            print(f"端口 {candidate} 已被占用，请输入其他端口号。")
            continue
        return candidate, True


def ask_yes_no(prompt):
    while True:
        choice = input(prompt).strip().lower()
        if choice in ('y', 'n'):
            return choice == 'y'
        print("请输入 y 或 n。")


def wait_countdown(seconds, message='端口检测通过'):
    """倒计时等待，按回车立即跳过，其他按键忽略"""
    # 清空检测/扫描期间残留的按键缓冲：只有结果出现后新按下的回车才能跳过倒计时
    while msvcrt.kbhit():
        key = msvcrt.getwch()
        if key == '\x03':  # Ctrl+C
            raise KeyboardInterrupt
    for i in range(seconds, 0, -1):
        print(f"\r{message}，{i} 秒后自动启动，按回车立即启动...", end='', flush=True)
        deadline = time.time() + 1
        while time.time() < deadline:
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key == '\x03':  # Ctrl+C
                    raise KeyboardInterrupt
                if key in ('\r', '\n'):
                    return
            time.sleep(0.05)


def show_instance_check_page(lan_ip):
    """同软件实例检测（单独一页显示），返回用户是否选择继续启动"""
    print("=" * 60)
    print("  同软件实例检测")
    # 进程枚举需 1~3 秒，先给出行内提示，扫描完成后原地清除再输出结果
    print("  正在扫描系统进程，请稍候...", end='', flush=True)
    instances = detect_same_software_instances()
    print("\r" + " " * 40 + "\r", end='', flush=True)
    if not instances:
        print("  未检测到本软件的其他运行实例，可正常启动")
        print("=" * 60)
        wait_countdown(3, '实例检测通过')
        return True

    print(f"  检测到 {len(instances)} 个本软件实例正在运行：")
    for i, inst in enumerate(instances, 1):
        for p in inst['processes']:
            source = p.get('ExecutablePath') or p.get('CommandLine') or '(来源未知)'
            print(f"    实例{i}  PID {p.get('ProcessId')}  {p.get('Name')}  {source}")
        lock = inst.get('lock')
        if lock:
            if isinstance(lock.get('port'), int):
                print(f"           主界面网址: http://{lan_ip}:{lock['port']}")
            if isinstance(lock.get('admin_port'), int):
                print(f"           后台管理网址: http://127.0.0.1:{lock['admin_port']}")
    print("  多实例同时运行会互相覆盖端口设置，导致先启动实例的网址失效，")
    print("  并可能争抢 GPU 显存、缓存与任务队列。")
    print("=" * 60)
    return ask_yes_no("是否仍要继续启动新实例？(y/n): ")


def main():
    global PORT, ADMIN_PORT, AUTO_OPEN_BROWSER, AUTO_OPEN_ADMIN_BROWSER

    # 获取本机局域网IP（匹配RFC 1918私网地址）
    out = subprocess.run(['ipconfig'], capture_output=True, text=True, encoding='gbk', errors='ignore').stdout
    ips = [w for l in (out or '').split('\n') for w in l.split() if w.count('.') == 3]
    lan_ip = next((ip for ip in ips if ip.startswith(('192.168.', '10.'))
                   or (ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31)), '未知')
    # 首次启动自动登记当前局域网地址；其他 Host 必须由用户显式加入配置。
    if lan_ip != '未知' and not startup_settings.get('allowed_hosts'):
        update_settings(allowed_hosts=[lan_ip])

    # 端口占用检查（单独一页显示）
    os.system('cls')
    print("=" * 60)
    print("  端口占用检测")
    PORT, port_busy = ensure_port_free(PORT, '主服务')
    ADMIN_PORT, admin_busy = ensure_port_free(ADMIN_PORT, '后台服务')
    update_settings(port=PORT, admin_port=ADMIN_PORT)
    print("=" * 60)
    if port_busy or admin_busy:
        input("按回车继续启动...")
    else:
        wait_countdown(3)
    os.system('cls')

    # 同软件实例检测（单独一页显示）
    if not show_instance_check_page(lan_ip):
        print("已取消启动，未运行新实例。")
        time.sleep(1.5)
        return
    os.system('cls')

    # 首次运行时设置浏览器启动方式
    if not AUTO_OPEN_BROWSER_CONFIGURED:
        print("=" * 60)
        print("  自动打开浏览器设置")
        AUTO_OPEN_BROWSER = ask_yes_no("是否自动打开主界面浏览器？(y/n): ")
        AUTO_OPEN_ADMIN_BROWSER = ask_yes_no("是否自动打开后台管理中心浏览器？(y/n): ")
        print("=" * 60)
        update_settings(
            auto_open_browser=AUTO_OPEN_BROWSER,
            auto_open_admin_browser=AUTO_OPEN_ADMIN_BROWSER,
            auto_open_browser_configured=True,
        )
        os.system('cls')

    # 登记本实例运行锁，供下次启动的同软件实例检测识别（含端口与网址）
    write_instance_lock(PORT, ADMIN_PORT)

    # 初始化共享上下文与双服务
    import uvicorn
    from common import app_context
    from web.server import app as web_app
    from admin.server import create_admin_app

    shutdown_event = threading.Event()
    admin_app = create_admin_app({
        'log': app_context.log,
        'settings': app_context.settings,
        'monitor': app_context.monitor,
        'clients': app_context.clients,
        'access': app_context.access,
        'task_queue': app_context.task_queue,
        'notifier': app_context.notifier,
        'client_cache': app_context.client_cache,
        'presence_sockets': app_context.presence_sockets,
        'simulator': app_context.simulator,
        'reload_runtime_settings': app_context.reload_runtime_settings,
    }, shutdown_event)

    web_server = uvicorn.Server(uvicorn.Config(
        web_app, host='0.0.0.0', port=PORT,
        log_level='warning', access_log=False, timeout_graceful_shutdown=3))
    admin_server = uvicorn.Server(uvicorn.Config(
        admin_app, host='127.0.0.1', port=ADMIN_PORT,
        log_level='warning', access_log=False, timeout_graceful_shutdown=3))

    web_thread = threading.Thread(target=web_server.run, name='web-server', daemon=True)
    admin_thread = threading.Thread(target=admin_server.run, name='admin-server', daemon=True)

    def signal_handler(sig, frame):
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 60)
    print(f"  斑图形成可视化系统 v{VERSION}")
    print(f"  使用设备: {'CUDA' if app_context.simulator.use_cuda else 'CPU'}")
    print(f"  计算硬件: {app_context.simulator.hardware_info}")
    print(f"  主界面(局域网): http://{lan_ip}:{PORT}")
    print(f"  后台管理中心(仅本机): http://127.0.0.1:{ADMIN_PORT}")
    print("  按 Ctrl+C 停止服务器")
    print("=" * 60)

    if AUTO_OPEN_BROWSER:
        threading.Thread(target=open_browser_when_ready, args=(f'http://{lan_ip}:{PORT}', PORT), daemon=True).start()
    if AUTO_OPEN_ADMIN_BROWSER:
        threading.Thread(target=open_browser_when_ready, args=(f'http://127.0.0.1:{ADMIN_PORT}', ADMIN_PORT), daemon=True).start()

    web_thread.start()
    admin_thread.start()

    # 主线程等待退出信号或任一服务异常退出
    while not shutdown_event.is_set():
        if not web_thread.is_alive() or not admin_thread.is_alive():
            print("检测到服务异常退出，正在停止所有服务...")
            break
        time.sleep(0.5)

    # 优雅停止：通知两个 server 退出事件循环
    web_server.should_exit = True
    admin_server.should_exit = True
    web_thread.join(timeout=6)
    admin_thread.join(timeout=6)

    # 统一清理：取消任务、落盘统计、释放缓存
    try:
        print("正在清理缓存与统计落盘...")
        app_context.task_queue.stop()
        app_context.monitor.stop()
        app_context.clients.stop()
        app_context.clients.save(peaks=app_context.monitor.get_peaks())
        app_context.client_cache.clear()
        app_context.client_cache.stop()
        app_context.simulator.clear_memory()
        gc.collect()
        remove_instance_lock()
        app_context.log.shutdown()
        print("缓存清理完毕，服务器已停止")
    except Exception as e:
        print(f"清理时出错: {e}")


if __name__ == '__main__':
    try:
        main()
    finally:
        # 留出时间看完最后的退出提示，再清屏让系统提示符单独一页显示
        time.sleep(1.5)
        os.system('cls')
