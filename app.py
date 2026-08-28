"""
Web 端服务入口与 REST API
"""
import os
import sys
import io
import time
import uuid
import threading
from typing import Dict, List
from flask import Flask, render_template, request, jsonify, Response, send_file
import xlsxwriter

from config import load_config, save_config
from checker import (
    LinkChecker, BatchChecker, check_google_cookie_validity,
    STATUS_ACTIVE, STATUS_USED, STATUS_INVALID, STATUS_NEED_AUTH, STATUS_INELIGIBLE, STATUS_ERROR,
    STATUS_LABELS, extract_token_and_normalize_url
)

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# 内存中保存的批量任务
# task_id -> { "is_running": bool, "total": int, "completed": int, "results": list, "checker": BatchChecker }
tasks: Dict[str, dict] = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "POST":
        data = request.get_json() or {}
        save_config(data)
        return jsonify({"success": True, "config": load_config()})
    return jsonify({"success": True, "config": load_config()})


@app.route("/api/test-cookie", methods=["POST"])
def api_test_cookie():
    data = request.get_json() or {}
    cookie_str = data.get("cookie", "")
    proxy_str = data.get("proxy", "")
    if not cookie_str:
        cfg = load_config()
        cookie_str = cfg.get("cookie", "")
        if not proxy_str:
            proxy_str = cfg.get("proxy", "")

    valid, message = check_google_cookie_validity(cookie_str, proxy=proxy_str)
    return jsonify({"success": valid, "message": message})


@app.route("/api/check-single", methods=["POST"])
def api_check_single():
    data = request.get_json() or {}
    link = data.get("link", "").strip()
    if not link:
        return jsonify({"success": False, "error": "链接不能为空"})

    cfg = load_config()
    proxy = data.get("proxy") or cfg.get("proxy")
    cookie = data.get("cookie") or cfg.get("cookie")
    timeout = int(data.get("timeout") or cfg.get("timeout", 15))

    checker = LinkChecker(proxy=proxy, cookie=cookie, timeout=timeout)
    result = checker.check_single_link(link)
    return jsonify({"success": True, "result": result})


@app.route("/api/check-batch-start", methods=["POST"])
def api_check_batch_start():
    data = request.get_json() or {}
    links = data.get("links", [])
    if not links or not isinstance(links, list):
        return jsonify({"success": False, "error": "没有提供待检测的链接列表"})

    cfg = load_config()
    proxy = data.get("proxy") or cfg.get("proxy")
    cookie = data.get("cookie") or cfg.get("cookie")
    threads = int(data.get("threads") or cfg.get("threads", 5))
    timeout = int(data.get("timeout") or cfg.get("timeout", 15))

    task_id = str(uuid.uuid4())
    batch_checker = BatchChecker(proxy=proxy, cookie=cookie, max_workers=threads, timeout=timeout)

    task_data = {
        "is_running": True,
        "total": len(links),
        "completed": 0,
        "results": [],
        "checker": batch_checker,
        "start_time": time.time()
    }
    tasks[task_id] = task_data

    def run_worker():
        def on_progress(current, total, item_result):
            task_data["completed"] = current
            task_data["results"].append(item_result)

        try:
            batch_checker.run(links, progress_callback=on_progress)
        finally:
            task_data["is_running"] = False

    t = threading.Thread(target=run_worker, daemon=True)
    t.start()

    return jsonify({"success": True, "task_id": task_id, "total": len(links)})


@app.route('/api/check-batch-sync', methods=['POST'])
def api_check_batch_sync():
    data = request.get_json() or {}
    links = data.get("links", [])
    if not links:
        return jsonify({"success": False, "error": "没有提供待检测的链接"}), 400

    cfg = load_config()
    req_cookie = data.get("cookie")
    if req_cookie and req_cookie.strip():
        cfg["cookie"] = req_cookie.strip()

    req_proxy = data.get("proxy")
    if req_proxy is not None:
        cfg["proxy"] = req_proxy.strip()

    threads = int(data.get("threads") or cfg.get("threads", 8))
    timeout = int(data.get("timeout") or cfg.get("timeout", 10))

    batch_checker = BatchChecker(
        proxy=cfg.get("proxy"),
        cookie=cfg.get("cookie"),
        max_workers=threads,
        timeout=timeout
    )

    results = batch_checker.run(links)

    stats = {
        "total": len(links),
        "completed": len(results),
        "active": sum(1 for r in results if r.get("status") == STATUS_ACTIVE),
        "used": sum(1 for r in results if r.get("status") == STATUS_USED),
        "invalid": sum(1 for r in results if r.get("status") == STATUS_INVALID),
        "need_auth": sum(1 for r in results if r.get("status") == STATUS_NEED_AUTH),
        "error": sum(1 for r in results if r.get("status") == STATUS_ERROR)
    }

    return jsonify({
        "success": True,
        "results": results,
        "stats": stats
    })


@app.route("/api/check-batch-status/<task_id>", methods=["GET"])
def api_check_batch_status(task_id):
    if task_id not in tasks:
        return jsonify({"success": False, "error": "任务不存在或已过期"}), 404

    task_data = tasks[task_id]
    offset = int(request.args.get("offset", 0))
    new_results = task_data["results"][offset:]

    # 统计数据
    all_results = task_data["results"]
    stats = {
        "total": task_data["total"],
        "completed": task_data["completed"],
        "active": sum(1 for r in all_results if r["status"] == STATUS_ACTIVE),
        "used": sum(1 for r in all_results if r["status"] == STATUS_USED),
        "invalid": sum(1 for r in all_results if r["status"] in (STATUS_INVALID, STATUS_INELIGIBLE)),
        "need_auth": sum(1 for r in all_results if r["status"] == STATUS_NEED_AUTH),
        "error": sum(1 for r in all_results if r["status"] == STATUS_ERROR),
    }

    return jsonify({
        "success": True,
        "task_id": task_id,
        "is_running": task_data["is_running"],
        "total": task_data["total"],
        "completed": task_data["completed"],
        "stats": stats,
        "new_results": new_results,
        "next_offset": len(all_results)
    })


@app.route("/api/check-batch-stop/<task_id>", methods=["POST"])
def api_check_batch_stop(task_id):
    if task_id in tasks:
        tasks[task_id]["checker"].stop_requested = True
        tasks[task_id]["is_running"] = False
        return jsonify({"success": True, "message": "已请求停止任务"})
    return jsonify({"success": False, "error": "任务不存在"}), 404


@app.route("/api/parse-file", methods=["POST"])
def api_parse_file():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "未上传文件"})
    f = request.files["file"]
    filename = f.filename.lower()
    content = f.read()

    links = []
    if filename.endswith(".txt") or filename.endswith(".csv"):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("gbk", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if line:
                # 若为CSV，拆分逗号
                parts = [p.strip() for p in line.split(",")]
                for p in parts:
                    if p.startswith("http") or len(p) > 25:
                        links.append(p)
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        # 简单解析文本内容
        try:
            # 查找所有类似链接的特征
            raw_str = content.decode("utf-8", errors="ignore")
            matches = re.findall(r'https?://[^\s",<>]+', raw_str)
            links.extend(matches)
        except Exception as e:
            pass

    # 去重
    unique_links = []
    seen = set()
    for l in links:
        if l not in seen:
            seen.add(l)
            unique_links.append(l)

    return jsonify({"success": True, "count": len(unique_links), "links": unique_links})


@app.route("/api/export-excel", methods=["POST"])
def api_export_excel():
    data = request.get_json() or {}
    results = data.get("results", [])
    filter_status = data.get("filter_status", "ALL")

    if filter_status != "ALL":
        results = [r for r in results if r.get("status") == filter_status]

    # 按原始输入行号排序
    results.sort(key=lambda x: x.get("index", 0))

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet("检测结果")

    # 样式
    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#1a73e8', 'font_color': 'white', 'align': 'center', 'valign': 'vcenter'})
    active_fmt = workbook.add_format({'bg_color': '#e6f4ea', 'font_color': '#137333', 'bold': True})
    used_fmt = workbook.add_format({'bg_color': '#fce8e6', 'font_color': '#c5221f', 'bold': True})
    cell_fmt = workbook.add_format({'valign': 'vcenter'})
    code_fmt = workbook.add_format({'font_name': 'Consolas', 'valign': 'vcenter'})

    headers = ["输入行号", "状态判定", "剩余时效倒计时", "激活截止日期", "Token特征码", "权益方案", "详细说明", "完整原始链接", "耗时(ms)", "检测时间"]
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header, header_fmt)

    worksheet.set_column(0, 0, 10)
    worksheet.set_column(1, 1, 18)
    worksheet.set_column(2, 2, 22)
    worksheet.set_column(3, 3, 18)
    worksheet.set_column(4, 4, 26)
    worksheet.set_column(5, 5, 36)
    worksheet.set_column(6, 6, 45)
    worksheet.set_column(7, 7, 60)
    worksheet.set_column(8, 8, 12)
    worksheet.set_column(9, 9, 20)

    for row_idx, r in enumerate(results, start=1):
        status = r.get("status", "")
        status_text = r.get("status_badge", r.get("status_label", status))
        row_fmt = active_fmt if status == STATUS_ACTIVE else (used_fmt if status == STATUS_USED else cell_fmt)

        worksheet.write(row_idx, 0, f"第 {r.get('index', row_idx)} 条", cell_fmt)
        worksheet.write(row_idx, 1, status_text, row_fmt)
        worksheet.write(row_idx, 2, r.get("remaining_time", "-"), row_fmt)
        worksheet.write(row_idx, 3, r.get("expire_deadline", "-"), cell_fmt)
        worksheet.write(row_idx, 4, r.get("token_snippet", "-"), code_fmt)
        worksheet.write(row_idx, 5, r.get("plan_info", "-"), cell_fmt)
        worksheet.write(row_idx, 6, r.get("details", ""), cell_fmt)
        worksheet.write(row_idx, 7, r.get("raw_input", ""), code_fmt)
        worksheet.write(row_idx, 8, r.get("duration_ms", 0), cell_fmt)
        worksheet.write(row_idx, 9, r.get("timestamp", ""), cell_fmt)


    workbook.close()
    output.seek(0)

    filename = f"GoogleOne_Jio_Activation_Results_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )



if __name__ == "__main__":
    port = 5000
    print(f"==================================================")
    print(f"  Google One / Jio 18个月 AI Pro 激活链接检测工具")
    print(f"  Web 服务已启动: http://127.0.0.1:{port}")
    print(f"==================================================")
    app.run(host="127.0.0.1", port=port, debug=False)
