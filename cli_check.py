"""
命令行批量检测工具 (CLI)
用法:
  python cli_check.py --input links.txt --output valid_links.txt
  python cli_check.py "https://serviceactivation.google.com/subscription/new/AQCpiI..."
"""
import os
import sys
import io
import argparse

# 确保在 Windows 终端正确输出 UTF-8
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config import load_config
from checker import (
    LinkChecker, BatchChecker,
    STATUS_ACTIVE, STATUS_USED, STATUS_INVALID, STATUS_NEED_AUTH, STATUS_ERROR
)

def main():
    parser = argparse.ArgumentParser(description="Google One Jio 18个月 AI Pro 激活链接活性批量检测工具 (CLI)")
    parser.add_argument("links", nargs="*", help="待检测的单个或多个激活链接")
    parser.add_argument("-i", "--input", help="包含激活链接的输入文件 (.txt / .csv)")
    parser.add_argument("-o", "--output", help="保存有效链接的输出文件 (.txt)")
    parser.add_argument("-p", "--proxy", help="指定代理地址，如 http://127.0.0.1:7890")
    parser.add_argument("-c", "--cookie", help="指定 Google Cookie 字符串")
    parser.add_argument("-t", "--threads", type=int, default=5, help="并发检测线程数 (默认 5)")
    args = parser.parse_args()

    cfg = load_config()
    proxy = args.proxy or cfg.get("proxy")
    cookie = args.cookie or cfg.get("cookie")
    threads = args.threads or cfg.get("threads", 5)

    all_links = []
    if args.links:
        all_links.extend(args.links)

    if args.input:
        if not os.path.exists(args.input):
            print(f"[错误] 输入文件不存在: {args.input}")
            sys.exit(1)
        with open(args.input, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                l = line.strip()
                if l:
                    all_links.append(l)

    if not all_links:
        print("[提示] 未指定链接，请输入链接或使用 -i links.txt 指定文件。")
        print("示例: python cli_check.py \"https://serviceactivation.google.com/subscription/new/...\"")
        sys.exit(0)

    print("=" * 65)
    print("  Google One / Jio 18个月 AI Pro 激活链接活性检测器 (CLI)")
    print(f"  代理设置: {proxy or '无'}")
    print(f"  Cookie配置: {'已设置 (' + str(len(cookie)) + ' chars)' if cookie else '未设置 (提示: 未登录状态将无法获取套餐详情)'}")
    print(f"  待测链接数: {len(all_links)} | 并发线程: {threads}")
    print("=" * 65)

    batch_checker = BatchChecker(proxy=proxy, cookie=cookie, max_workers=threads)

    active_links = []
    def on_progress(current, total, item_res):
        badge = item_res.get("status_badge", item_res.get("status"))
        remain = item_res.get("remaining_time", "-")
        deadline = item_res.get("expire_deadline", "-")
        snip = item_res.get("token_snippet", "-")
        plan = item_res.get("plan_info", "-")
        dur = item_res.get("duration_ms", 0)
        idx = item_res.get("index", current)
        print(f"[第 {idx} 条] {badge} | ⏳ 剩余时效: {remain} (截止: {deadline}) | 套餐: {plan} | 码: {snip} | 耗时: {dur}ms")
        if item_res.get("status") == STATUS_ACTIVE:
            active_links.append(f"第 {idx} 条 ({remain} | 截止: {deadline}): " + (item_res.get("url") or item_res.get("raw_input")))


    results = batch_checker.run(all_links, progress_callback=on_progress)

    active_cnt = sum(1 for r in results if r.get("status") == STATUS_ACTIVE)
    used_cnt = sum(1 for r in results if r.get("status") == STATUS_USED)
    other_cnt = len(results) - active_cnt - used_cnt

    print("\n" + "=" * 65)
    print(f"  检测总结: 总数 {len(results)} | 有效: {active_cnt} | 已失效: {used_cnt} | 异常/需Cookie: {other_cnt}")
    print("=" * 65)

    if args.output and active_links:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(active_links))
        print(f"[成功] 已将 {len(active_links)} 条有效链接保存至: {args.output}")

if __name__ == "__main__":
    main()
