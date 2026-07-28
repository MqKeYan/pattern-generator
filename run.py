"""启动脚本 - 运行斑图形成可视化系统的Web服务器"""

import sys
import os
import signal
import gc
import subprocess

# 将app文件夹加入模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from server import app, client_cache, simulator
from waitress import serve
from version import VERSION

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
    out = subprocess.run(['ipconfig'], capture_output=True, text=True, encoding='gbk').stdout
    ips = [w for l in out.split('\n') for w in l.split() if w.count('.') == 3]
    lan_ip = next((ip for ip in ips if ip.startswith(('192.168.', '10.'))
                   or (ip.startswith('172.') and 16 <= int(ip.split('.')[1]) <= 31)), '未知')

    print("=" * 60)
    print(f"  斑图形成可视化系统 v{VERSION}")
    print(f"  本机访问: http://localhost:5000")
    print(f"  局域网访问: http://{lan_ip}:5000")
    print("  按 Ctrl+C 停止服务器")
    print("=" * 60)

    try:
        # threads=8 支持多用户同时访问，计算由锁串行
        serve(app, host='0.0.0.0', port=5000, threads=8)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_on_exit()