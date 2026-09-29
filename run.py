"""启动脚本 - 同时启动主服务（局域网）与后台管理中心（仅本机）

主服务: <局域网IP>:<port>   FastAPI + Uvicorn（单 worker，仅局域网）
后台:   127.0.0.1:<admin_port>  FastAPI + Uvicorn（单 worker，仅本机）
任一服务异常退出或后台触发「停止所有服务」时，整体退出并清理资源。
"""

import sys
import os
import ctypes
import gc
import multiprocessing
import msvcrt
import signal
import subprocess
import socket
import threading
import time
import webbrowser
import winreg

# Compute dependencies are discovered and loaded by external Python workers.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

if __name__ == '__main__' and '--compute-check' in sys.argv:
    import argparse
    from common.compute import ENGINE_NAMES, diagnostics
    parser = argparse.ArgumentParser(description='External compute diagnostics (no service startup)')
    parser.add_argument('--compute-check', required=True, metavar='REPORT_JSON')
    parser.add_argument('--python', default='auto')
    parser.add_argument('--engine', default='auto', choices=('auto', *ENGINE_NAMES))
    args = parser.parse_args()
    diagnostics(args.compute_check, args.python, args.engine)
    sys.exit(0)

if __name__ == '__main__' and '--app-check' in sys.argv:
    # Exercise the full packaged service imports without opening ports or probing GPUs.
    import json
    from common import app_context
    from web.server import app as web_app, templates as web_templates
    from admin.server import create_admin_app
    check_ctx = {
        'settings': app_context.settings,
        'log': app_context.log,
        'monitor': app_context.monitor,
        'clients': app_context.clients,
        'access': app_context.access,
        'task_queue': app_context.task_queue,
        'notifier': app_context.notifier,
        'client_cache': app_context.client_cache,
        'presence_sockets': app_context.presence_sockets,
        'reload_runtime_settings': app_context.reload_runtime_settings,
    }
    admin_app = create_admin_app(check_ctx, threading.Event())
    web_templates.get_template('index.html')
    print(json.dumps({'web_routes': len(web_app.routes),
                      'admin_routes': len(admin_app.routes),
                      'web_template': 'index.html', 'ok': True}))
    sys.exit(0)

from common.config import VERSION, load_settings, software_root, update_settings
from common.startup import (
    detect_same_software_instances,
    write_instance_lock,
    remove_instance_lock,
    get_port_pids,
    show_port_status,
    kill_port_processes,
    cleanup_same_software_instances,
)

startup_settings = load_settings()
PORT = startup_settings['port']
ADMIN_PORT = startup_settings['admin_port']
AUTO_OPEN_BROWSER = startup_settings['auto_open_browser']
AUTO_OPEN_ADMIN_BROWSER = startup_settings['auto_open_admin_browser']
AUTO_OPEN_BROWSER_CONFIGURED = startup_settings['auto_open_browser_configured']

shutdown_event = threading.Event()
_console_handler_ref = None


def install_windows_console_handler():
    """监听 Ctrl+C、窗口关闭及系统注销/关机事件。"""
    global _console_handler_ref
    if os.name != 'nt':
        return

    try:
        from ctypes import wintypes

        handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        def console_handler(ctrl_type):
            if ctrl_type in (0, 1, 2, 5, 6):
                shutdown_event.set()
                return True
            return False

        callback = handler_type(console_handler)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.SetConsoleCtrlHandler.argtypes = [handler_type, wintypes.BOOL]
        kernel32.SetConsoleCtrlHandler.restype = wintypes.BOOL
        if kernel32.SetConsoleCtrlHandler(callback, True):
            _console_handler_ref = callback
    except (AttributeError, OSError):
        _console_handler_ref = None


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


def open_browser_when_ready(url, port, host='127.0.0.1'):
    """等待本地服务就绪后打开浏览器"""
    for _ in range(50):
        try:
            with socket.create_connection((host, port), timeout=0.2):
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


def wait_engine_edit_request(seconds=3, subject='计算引擎'):
    """预检倒计时：n 进入编辑，回车或超时继续启动。"""
    while msvcrt.kbhit():
        key = msvcrt.getwch()
        if key == '\x03':
            raise KeyboardInterrupt
    for remaining in range(seconds, 0, -1):
        print(f"\r  {remaining} 秒后自动继续；回车立即继续，按 n 编辑{subject}...", end='', flush=True)
        deadline = time.time() + 1
        while time.time() < deadline:
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key == '\x03':
                    raise KeyboardInterrupt
                if key in ('\r', '\n'):
                    print()
                    return False
                if key.lower() == 'n':
                    print()
                    return True
            time.sleep(0.05)
    print()
    return False


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
    if ask_yes_no("是否仍要继续启动新实例？(y/n): "):
        return True
    if ask_yes_no("是否清理检测到的已有实例？(y/n): "):
        cleanup_same_software_instances(instances)
    else:
        print("  已保留检测到的已有实例。")
    return False


def show_python_page(settings, manager=None):
    """在引擎探测前确认外部 Python，按 n 才扫描其他安装路径。"""
    from common.compute import discover_pythons, resolve_python
    from common.persistence import atomic_write_json

    state_path = software_root() / 'config' / 'compute-python-state.json'

    def show_current():
        configured = settings.get('compute_python', 'auto')
        try:
            info = resolve_python(configured)
        except (OSError, ValueError) as exc:
            print(f"  当前 Python 不可用：{exc}")
            print(f"  已设置路径：{configured}")
            return None
        mode = '软件自动默认' if configured == 'auto' else '用户指定'
        print(f"  当前 Python：{'.'.join(map(str, info['version']))} · 64 位（{mode}）")
        print(f"  路径：{info['path']}")
        return info

    def edit_python():
        os.system('cls')
        print("=" * 60)
        print("  选择 Python")
        print("  正在扫描可用 Python，请稍候...", end='', flush=True)
        available = discover_pythons()
        print("\r" + " " * 40 + "\r", end='', flush=True)
        print("  0. 软件自动默认")
        for number, info in enumerate(available, 1):
            print(f"  {number}. Python {'.'.join(map(str, info['version']))} · {info['path']}")
        manual_number = len(available) + 1
        print(f"  {manual_number}. 手动输入 Python 绝对路径")
        print("  仅列出通过检查的 64 位 Python 3.13 及以上版本。")
        print("=" * 60)
        while True:
            try:
                choice = input("  输入序号（回车保持当前选择并继续）：").strip()
            except EOFError:
                return
            if not choice:
                return
            if not choice.isdigit() or int(choice) > manual_number:
                print("  请输入列表中的序号。")
                continue
            number = int(choice)
            try:
                if number == manual_number:
                    try:
                        path = input("  输入 Python 可执行文件的绝对路径（回车取消）：").strip().strip('"')
                    except EOFError:
                        return
                    if not path:
                        continue
                    selected = resolve_python(path)
                    configured = selected['path']
                elif number == 0:
                    selected = resolve_python('auto')
                    configured = 'auto'
                else:
                    selected = resolve_python(available[number - 1]['path'])
                    configured = selected['path']
                updated = update_settings(compute_python=configured)
                settings.clear()
                settings.update(updated)
                print("  Python 选择已保存。")
                show_current()
                print("=" * 60)
                wait_countdown(3, 'Python 设置已保存')
                return
            except (OSError, ValueError) as exc:
                print(f"  设置失败：{exc}")

    os.system('cls')
    print("=" * 60)
    print("  Python 环境")
    if not state_path.is_file():
        print("  首次运行：可选择 Python，或沿用软件自动默认。")
    current = show_current()
    preflight = None
    if current and manager and manager.state_path and manager.state_path.is_file():
        from concurrent.futures import ThreadPoolExecutor

        # 利用 Python 页的倒计时提前验证上次引擎，避免下一页再次等待导入。
        executor = ThreadPoolExecutor(max_workers=1)
        preflight = (settings.get('compute_python', 'auto'), executor.submit(manager.prepare_startup))
        executor.shutdown(wait=False)
    print("  按 n 选择 Python；回车可提前继续启动。")
    print("=" * 60)
    if wait_engine_edit_request(subject='Python'):
        if preflight:
            from concurrent.futures import wait
            wait((preflight[1],))
        edit_python()
    atomic_write_json(state_path, {'version': 1})
    return preflight


def show_compute_engine_page(manager, settings, preflight=None):
    """同步验证引擎，倒计时内按 n 才进入编号选择页。"""
    from common.compute import ENGINE_NAMES

    def save_choice(**changes):
        updated = update_settings(**changes)
        settings.clear()
        settings.update(updated)

    def show_status(status):
        selected = status.get('selected')
        if selected:
            mode = '软件自动默认' if settings.get('compute_engine', 'auto') == 'auto' else '用户指定'
            print(f"  当前引擎：{selected['engine_name']} · {selected['device']}（{mode}）")
            print(f"  引擎版本：{selected['version']}")
        else:
            print(f"  当前选择不可用：{status.get('selection_error') or status.get('error') or '没有可用引擎'}")
        print(f"  外部 Python：{settings.get('compute_python', 'auto')}")

    def edit_engine(status):
        os.system('cls')
        print("=" * 60)
        print("  选择计算引擎")
        print("  正在检查可用引擎，请稍候...", end='', flush=True)
        if len(status['engines']) < len(ENGINE_NAMES):
            manager.inventory(refresh=True)
            status = manager.status()
        print("\r" + " " * 40 + "\r", end='', flush=True)
        available = [item for name in ENGINE_NAMES
                     for item in status['engines'] if item['id'] == name and item['usable']]
        print("  0. 软件自动默认（从本机可用引擎中选择）")
        for number, item in enumerate(available, 1):
            devices = item.get('devices', [])
            cpu = any(not device.get('gpu', device['id'].startswith('cuda:'))
                      for device in devices)
            gpu = any(device.get('gpu', device['id'].startswith('cuda:'))
                      for device in devices)
            hardware = 'CPU、GPU' if cpu and gpu else 'GPU' if gpu else 'CPU'
            print(f"  {number}. {item['name']} · {item['version']}（本机可用：{hardware}）")
        if available:
            print("  未列出的引擎可能缺少依赖或驱动。")
        if not available:
            print("  未发现可用引擎；可在后台系统设置中检查外部 Python 路径与依赖。")
        print("=" * 60)
        while True:
            try:
                choice = input("  输入可用引擎序号（回车保持当前选择）：").strip()
            except EOFError:
                return status
            if not choice:
                return status
            if not choice.isdigit() or int(choice) > len(available):
                print("  请输入列表中的序号。")
                continue
            try:
                number = int(choice)
                if number == 0:
                    save_choice(compute_engine='auto', compute_device='auto')
                    status = manager.status(refresh=True)
                else:
                    save_choice(compute_engine=available[number - 1]['id'], compute_device='auto')
                    status = manager.status()
                print("  引擎选择已保存。")
                show_status(status)
                print("=" * 60)
                wait_countdown(3, '引擎设置已保存')
                return status
            except (ValueError, OSError) as exc:
                print(f"  设置失败：{exc}")

    os.system('cls')
    print("=" * 60)
    print("  计算引擎")
    print("  正在检测计算引擎，请稍候...", end='', flush=True)
    if preflight and preflight[0] == settings.get('compute_python', 'auto'):
        result = preflight[1].result()
    else:
        result = manager.prepare_startup()
    print("\r" + " " * 40 + "\r", end='', flush=True)
    status = result['status']
    if result['first_run']:
        print("  首次启动：已全面搜索计算引擎。")
    elif result['rescanned']:
        checked = result['checked'] or {}
        print(f"  上次使用的 {checked.get('name', '计算引擎')} 无法使用，已重新全面搜索。")
        for error in checked.get('errors', []):
            print(f"  原因：{error}")
    else:
        print("  本次仅验证上次使用的计算引擎。")

    show_status(status)
    print("  按 n 编辑计算引擎；回车可提前继续启动。")
    print("=" * 60)
    if wait_engine_edit_request():
        status = edit_engine(status)
    manager.save_startup_selection()
    return status


def main():
    global PORT, ADMIN_PORT, AUTO_OPEN_BROWSER, AUTO_OPEN_ADMIN_BROWSER

    shutdown_event.clear()

    # 获取本机局域网IP（匹配RFC 1918私网地址）
    out = subprocess.run(['ipconfig'], capture_output=True, text=True, encoding='gbk', errors='ignore').stdout
    ips = [w for l in (out or '').split('\n') for w in l.split() if w.count('.') == 3]
    lan_ip = next((ip for ip in ips if ip.startswith(('192.168.', '10.'))
                   or (ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31)), '未知')
    if lan_ip == '未知':
        print("错误：未检测到局域网 IPv4 地址，主服务不会启动。")
        return
    # 启动预检期间只暂存新地址和端口，检测通过后再写入配置。
    # 这样用户选择取消时，不会留下本次未启动实例的配置变更。
    pending_allowed_hosts = [lan_ip]

    # 端口占用检查（单独一页显示）
    os.system('cls')
    print("=" * 60)
    print("  端口占用检测")
    PORT, port_busy = ensure_port_free(PORT, '主服务')
    ADMIN_PORT, admin_busy = ensure_port_free(ADMIN_PORT, '后台服务')
    print("=" * 60)
    if port_busy or admin_busy:
        input("按回车继续启动...")
    else:
        wait_countdown(3)
    os.system('cls')

    # 同软件实例检测（单独一页显示）
    if not show_instance_check_page(lan_ip):
        # 端口检查可能只修改了当前进程中的暂存值，未落盘，不触碰正在运行的旧实例。
        PORT = startup_settings['port']
        ADMIN_PORT = startup_settings['admin_port']
        AUTO_OPEN_BROWSER = startup_settings['auto_open_browser']
        AUTO_OPEN_ADMIN_BROWSER = startup_settings['auto_open_admin_browser']
        print("已取消启动，未运行新实例。")
        time.sleep(1.5)
        return
    # 只有实例检测通过后，才提交本次预检得到的地址和端口。
    update_settings(allowed_hosts=pending_allowed_hosts, port=PORT, admin_port=ADMIN_PORT)
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

    # Python 与计算引擎分别预检；解释器确认后才探测其计算引擎。
    from common import app_context
    preflight = show_python_page(app_context.settings, app_context.compute_manager)
    show_compute_engine_page(app_context.compute_manager, app_context.settings, preflight)
    app_context.initialize_compute_capacity()

    # 登记本实例运行锁，供下次启动的同软件实例检测识别（含端口与网址）
    write_instance_lock(PORT, ADMIN_PORT)

    # 初始化共享上下文与双服务
    import uvicorn
    from web.server import app as web_app
    from admin.server import create_admin_app

    admin_context = {
        'log': app_context.log,
        'settings': app_context.settings,
        'monitor': app_context.monitor,
        'clients': app_context.clients,
        'access': app_context.access,
        'task_queue': app_context.task_queue,
        'notifier': app_context.notifier,
        'client_cache': app_context.client_cache,
        'presence_sockets': app_context.presence_sockets,
        'reload_runtime_settings': app_context.reload_runtime_settings,
        'started_at': None,
        'lan_ip': lan_ip,
    }
    admin_app = create_admin_app(admin_context, shutdown_event)

    web_server = uvicorn.Server(uvicorn.Config(
        web_app, host=lan_ip, port=PORT,
        log_level='warning', access_log=False, timeout_graceful_shutdown=3))
    admin_server = uvicorn.Server(uvicorn.Config(
        admin_app, host='127.0.0.1', port=ADMIN_PORT,
        log_level='warning', access_log=False, timeout_graceful_shutdown=3))

    web_thread = threading.Thread(target=web_server.run, name='web-server', daemon=True)
    admin_thread = threading.Thread(target=admin_server.run, name='admin-server', daemon=True)

    def signal_handler(sig, frame):
        shutdown_event.set()

    install_windows_console_handler()
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, signal_handler)

    # 引擎选择页结束后，清屏再展示独立的主程序页面。
    os.system('cls')
    # 启动检查和倒计时结束后，显示网址时才开始计算后台运行时长。
    admin_context['started_at'] = time.time()
    print("=" * 60)
    print(f"  斑图形成可视化系统 v{VERSION}")
    compute_info = app_context.service_info()
    print(f"  计算引擎: {compute_info['engine']} {compute_info['engine_version']}")
    print(f"  使用设备: {compute_info['hardware']}")
    print(f"  最大并发计算数量: {compute_info['max_compute_concurrency']}")
    print(f"  主界面(局域网): http://{lan_ip}:{PORT}")
    print(f"  后台管理中心(仅本机): http://127.0.0.1:{ADMIN_PORT}")
    print("  按 Ctrl+C 停止服务器")
    print("=" * 60)

    if AUTO_OPEN_BROWSER:
        threading.Thread(target=open_browser_when_ready, args=(f'http://{lan_ip}:{PORT}', PORT, lan_ip), daemon=True).start()
    if AUTO_OPEN_ADMIN_BROWSER:
        threading.Thread(target=open_browser_when_ready, args=(f'http://127.0.0.1:{ADMIN_PORT}', ADMIN_PORT), daemon=True).start()

    cleanup_lock = threading.Lock()
    cleanup_done = False

    def cleanup_services():
        """幂等停止服务并释放本实例资源。"""
        nonlocal cleanup_done
        with cleanup_lock:
            if cleanup_done:
                return
            cleanup_done = True

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
            app_context.release_runtime_memory()
            gc.collect()
            remove_instance_lock()
            app_context.log.shutdown()
            print("缓存清理完毕，服务器已停止")
        except Exception as e:
            print(f"清理时出错: {e}")

    try:
        web_thread.start()
        admin_thread.start()

        # 主线程等待退出信号或任一服务异常退出
        while not shutdown_event.is_set():
            if not web_thread.is_alive() or not admin_thread.is_alive():
                print("检测到服务异常退出，正在停止所有服务...")
                break
            time.sleep(0.5)
    finally:
        cleanup_services()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        main()
    finally:
        # 留出时间看完最后的退出提示，再清屏让系统提示符单独一页显示
        time.sleep(1.5)
        os.system('cls')
