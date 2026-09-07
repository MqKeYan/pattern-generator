"""报表导出 - 客户端活动/任务执行/系统资源峰值/访问控制事件/告警事件

格式：CSV / XLSX / JSON。
数据来源：内存数据（任务历史、被拒记录、告警缓冲）+ stats.json（客户端统计、资源峰值）+ 当日日志。
"""

import csv
import io
import json
import time


REPORT_TYPES = ('clients', 'tasks', 'system', 'access', 'alerts')
FORMATS = ('csv', 'xlsx', 'json')

_HEADERS = {
    'clients': ['client_id', 'client_name', 'ip', 'status', 'total_requests', 'total_tasks',
                'success_count', 'failed_count', 'cancelled_count', 'total_compute_time',
                'online_duration_seconds', 'tags', 'remark'],
    'tasks': ['task_id', 'client_id', 'type', 'model', 'iterations', 'frames', 'status',
              'progress', 'retry_count', 'gpu_id', 'created_at', 'started_at', 'completed_at',
              'completed_at_h', 'error'],
    'system': ['metric', 'value'],
    'access': ['time', 'ip', 'client_id', 'reason'],
    'alerts': ['time', 'event', 'detail'],
}


def _fmt_time(ts):
    if not ts:
        return ''
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))


def _safe_spreadsheet_cell(value):
    """将可能被表格软件解释为公式的文本转为纯文本。"""
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        return f"'{value}"
    return value


def _safe_spreadsheet_rows(rows):
    """统一保护 CSV 与 XLSX 的所有数据单元格。"""
    return [[_safe_spreadsheet_cell(value) for value in row] for row in rows]


def _rows_for(report_type, clients_list, tasks_list, peaks, denied, alerts):
    if report_type == 'clients':
        rows = []
        for c in clients_list:
            row = []
            for h in _HEADERS['clients']:
                val = c.get(h, '')
                if isinstance(val, (list, tuple)):
                    val = ', '.join(str(v) for v in val)
                row.append(val)
            rows.append(row)
        return rows
    if report_type == 'tasks':
        rows = []
        for t in tasks_list:
            rows.append([t.get(h, '') for h in _HEADERS['tasks'][:13]] +
                        [_fmt_time(t.get('completed_at')), t.get('error') or ''])
        return rows
    if report_type == 'system':
        rows = [[k, v] for k, v in (peaks or {}).items()]
        rows.append(['generated_at', _fmt_time(time.time())])
        return rows
    if report_type == 'access':
        return [[d.get(h, '') for h in _HEADERS['access']] for d in denied]
    if report_type == 'alerts':
        return [[a.get(h, '') for h in _HEADERS['alerts']] for a in alerts]
    raise ValueError(f'未知报表类型: {report_type}')


def _to_csv(headers, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(_safe_spreadsheet_rows(rows))
    return buf.getvalue().encode('utf-8-sig')  # BOM 便于 Excel 打开


def _to_xlsx(headers, rows):
    try:
        from openpyxl import Workbook
    except ImportError:
        raise RuntimeError('openpyxl 未安装，无法导出 XLSX')
    wb = Workbook()
    ws = wb.active
    ws.title = 'report'
    ws.append(headers)
    for row in _safe_spreadsheet_rows(rows):
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_report(report_type, fmt, clients_list, tasks_list, peaks, denied, alerts):
    """生成报表，返回 (filename, bytes)"""
    if report_type not in REPORT_TYPES:
        raise ValueError(f'未知报表类型: {report_type}')
    if fmt not in FORMATS:
        raise ValueError(f'未知导出格式: {fmt}')

    headers = _HEADERS[report_type]
    rows = _rows_for(report_type, clients_list, tasks_list, peaks, denied, alerts)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    filename = f'report_{report_type}_{stamp}.{fmt}'

    if fmt == 'csv':
        return filename, _to_csv(headers, rows)
    if fmt == 'xlsx':
        return filename, _to_xlsx(headers, rows)
    data = [dict(zip(headers, row)) for row in rows]
    return filename, json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
