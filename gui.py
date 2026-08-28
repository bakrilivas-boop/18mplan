"""
桌面版图形界面客户端 (Tkinter GUI)
"""
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser

from config import load_config, save_config
from checker import (
    LinkChecker, BatchChecker, check_google_cookie_validity,
    STATUS_ACTIVE, STATUS_USED, STATUS_INVALID, STATUS_NEED_AUTH, STATUS_INELIGIBLE, STATUS_ERROR,
    STATUS_LABELS, extract_token_and_normalize_url, get_token_snippet
)

class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Google One / Jio 18个月 AI Pro 激活链接活性检测工具 (桌面版)")
        self.root.geometry("1180x740")
        self.root.minsize(950, 600)

        self.config = load_config()
        self.results = []
        self.is_checking = False
        self.batch_checker = None

        self._setup_style()
        self._build_ui()

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass

        style.configure("Treeview.Heading", font=("Microsoft YaHei", 9, "bold"), background="#f1f5f9")
        style.configure("Treeview", font=("Microsoft YaHei", 9), rowheight=28)
        style.map("Treeview", background=[('selected', '#e2e8f0')])

    def _build_ui(self):
        # 顶部工具栏与状态
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        title_lbl = ttk.Label(top_frame, text="Google One 激活链接活性检测器 (带时效倒计时)", font=("Microsoft YaHei", 12, "bold"))
        title_lbl.pack(side=tk.LEFT)

        btn_settings = ttk.Button(top_frame, text="⚙️ 代理/Cookie配置", command=self.open_settings_dialog)
        btn_settings.pack(side=tk.RIGHT, padx=5)

        btn_help = ttk.Button(top_frame, text="📖 Cookie获取教程", command=self.open_help_dialog)
        btn_help.pack(side=tk.RIGHT, padx=5)

        # 统计面板
        stats_frame = ttk.LabelFrame(self.root, text="检测统计", padding=8)
        stats_frame.pack(fill=tk.X, padx=10, pady=2)

        self.lbl_total = ttk.Label(stats_frame, text="总检测: 0", font=("Microsoft YaHei", 9))
        self.lbl_total.pack(side=tk.LEFT, padx=15)

        self.lbl_active = ttk.Label(stats_frame, text="🟢 有效(未激活): 0", foreground="#16a34a", font=("Microsoft YaHei", 9, "bold"))
        self.lbl_active.pack(side=tk.LEFT, padx=15)

        self.lbl_used = ttk.Label(stats_frame, text="🔴 已失效(已使用): 0", foreground="#dc2626", font=("Microsoft YaHei", 9, "bold"))
        self.lbl_used.pack(side=tk.LEFT, padx=15)

        self.lbl_invalid = ttk.Label(stats_frame, text="⚠️ 异常/过期/需Cookie: 0", foreground="#d97706", font=("Microsoft YaHei", 9))
        self.lbl_invalid.pack(side=tk.LEFT, padx=15)

        self.lbl_status = ttk.Label(stats_frame, text="状态: 就绪", foreground="#475569", font=("Microsoft YaHei", 9))
        self.lbl_status.pack(side=tk.RIGHT, padx=15)

        # 中部区域: 输入框 + 控制按钮
        mid_pane = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        mid_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 输入区域 Frame
        input_frame = ttk.LabelFrame(mid_pane, text="待检测链接列表 (严格按顺序对应: 第1行对应结果第1条，并计算剩余时效)", padding=5)
        mid_pane.add(input_frame, weight=1)

        btn_bar = ttk.Frame(input_frame)
        btn_bar.pack(fill=tk.X, pady=2)

        ttk.Button(btn_bar, text="📁 导入文件 (.txt/.csv)", command=self.import_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="🎲 填入示例", command=self.fill_sample).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text="🧹 清空输入", command=self.clear_input).pack(side=tk.LEFT, padx=2)

        self.btn_start = tk.Button(btn_bar, text="🚀 开始批量检测 (计算时效)", bg="#1a73e8", fg="white", font=("Microsoft YaHei", 9, "bold"), relief="flat", padx=10, command=self.start_check)
        self.btn_start.pack(side=tk.RIGHT, padx=2)

        self.btn_stop = ttk.Button(btn_bar, text="⏹️ 停止", command=self.stop_check, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.RIGHT, padx=2)

        self.txt_input = tk.Text(input_frame, height=5, font=("Consolas", 9), wrap=tk.NONE)
        txt_scroll = ttk.Scrollbar(input_frame, orient=tk.VERTICAL, command=self.txt_input.yview)
        self.txt_input.configure(yscrollcommand=txt_scroll.set)
        self.txt_input.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        txt_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 结果表格 Frame
        table_frame = ttk.LabelFrame(mid_pane, text="检测结果明细 (按输入行号严格对齐，含倒计时)", padding=5)
        mid_pane.add(table_frame, weight=2)

        # 表格操作栏
        tab_bar = ttk.Frame(table_frame)
        tab_bar.pack(fill=tk.X, pady=2)

        ttk.Button(tab_bar, text="📋 复制所有有效链接", command=self.copy_active_links).pack(side=tk.LEFT, padx=2)
        ttk.Button(tab_bar, text="📥 导出有效链接 (.txt)", command=self.export_active_txt).pack(side=tk.LEFT, padx=2)
        ttk.Button(tab_bar, text="📊 导出完整报告 (.xlsx)", command=self.export_excel).pack(side=tk.LEFT, padx=2)

        # Treeview 表格
        cols = ("idx", "status", "remain", "deadline", "snip", "plan", "details", "duration", "url")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        
        self.tree.heading("idx", text="输入行号")
        self.tree.heading("status", text="状态判定")
        self.tree.heading("remain", text="⏳ 剩余时效")
        self.tree.heading("deadline", text="截止日期")
        self.tree.heading("snip", text="Token特征码")
        self.tree.heading("plan", text="权益套餐")
        self.tree.heading("details", text="判定说明 / 到期时间")
        self.tree.heading("duration", text="耗时")
        self.tree.heading("url", text="完整链接 / Token")

        self.tree.column("idx", width=70, anchor=tk.CENTER)
        self.tree.column("status", width=130, anchor=tk.CENTER)
        self.tree.column("remain", width=140, anchor=tk.CENTER)
        self.tree.column("deadline", width=120, anchor=tk.CENTER)
        self.tree.column("snip", width=160, anchor=tk.CENTER)
        self.tree.column("plan", width=180, anchor=tk.W)
        self.tree.column("details", width=220, anchor=tk.W)
        self.tree.column("duration", width=65, anchor=tk.E)
        self.tree.column("url", width=220, anchor=tk.W)

        tree_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.tree.bind("<Double-1>", self.on_double_click_row)

        # 底部进度条
        self.progress_bar = ttk.Progressbar(self.root, mode='determinate')
        self.progress_bar.pack(fill=tk.X, padx=10, pady=5)

    def fill_sample(self):
        sample = (
            "https://serviceactivation.google.com/subscription/new/AQCpiIHej8nqT7bayckk8a6QsgOuffjUBADAo-4A8Ia3TsfCNYphRcd0hE5zILnOOq9HRDQiSInJosMvZnBuT2ExTq5s2fmevPRpZAoKjmIOr9_GiavfPjcw-AHoHB8yOT48znWhbKwS-2DacScVyxwfsT9xNtu_MEXCLa8wR4cahayECj1Bx1nERrOw4MFjriA0calOqMuzsYhbjXlEosZ2oCf2MDsIbUb0_h6WxrQXZZASnDjpqe4uCeLvTrOFuz31RO3skeK2Eap7Fg==\n"
            "https://serviceactivation.google.com/subscription/new/AQCPiiH3Zc2aLnxLQkIAYVANazjvAK6pHpcG9JtkCYazlAhCE3XY7J4HM8luA8chZMfFepePNNRUmFWHnJdtnb_DF3IiQM009vbTKpXPrzJ6XskoAy1mqznz4TxvatWErMwtBAPS-vGffWiUfcS-e8dOe_fELJWZB6jjmnFO7MVdlGIJfkogsipNK5U0vmdei2Kj6gJWJ-zgpvtEJjnaOMCJBlzvoQybbZMFW1162O-pijWfY3TEcwyHWnZTXrGyKFJEmbZBrEhnipZPNQ=="
        )
        self.txt_input.delete("1.0", tk.END)
        self.txt_input.insert(tk.END, sample)

    def clear_input(self):
        self.txt_input.delete("1.0", tk.END)

    def import_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("All files", "*.*")])
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="gbk", errors="ignore") as f:
                content = f.read()
        
        self.txt_input.insert(tk.END, ("\n" if self.txt_input.get("1.0", tk.END).strip() else "") + content.strip())
        messagebox.showinfo("导入成功", f"已成功从 {os.path.basename(file_path)} 导入内容！")

    def start_check(self):
        raw_text = self.txt_input.get("1.0", tk.END).strip()
        if not raw_text:
            messagebox.showwarning("提示", "请先输入待检测的链接！")
            return

        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        if not lines:
            messagebox.showwarning("提示", "没有可检测的有效内容！")
            return

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.results = []

        self.is_checking = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = len(lines)
        self.lbl_status.config(text=f"状态: 按序检测中 (0/{len(lines)})...")

        cfg = load_config()
        self.batch_checker = BatchChecker(
            proxy=cfg.get("proxy"),
            cookie=cfg.get("cookie"),
            max_workers=int(cfg.get("threads", 5)),
            timeout=int(cfg.get("timeout", 15))
        )

        def worker():
            def on_progress(current, total, item_res):
                self.root.after(0, self._append_result, current, total, item_res)

            res_list = self.batch_checker.run(lines, progress_callback=on_progress)
            self.root.after(0, self._finish_check, res_list)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _append_result(self, current, total, item_res):
        self.results.append(item_res)
        self.results.sort(key=lambda x: x.get("index", 0))

        for item in self.tree.get_children():
            self.tree.delete(item)

        for r in self.results:
            idx = f"第 {r.get('index', 1)} 条"
            status = r.get("status_badge", r.get("status"))
            remain = r.get("remaining_time", "-")
            deadline = r.get("expire_deadline", "-")
            snip = r.get("token_snippet", "-")
            plan = r.get("plan_info", "-")
            details = r.get("details", "")
            duration = f"{r.get('duration_ms', 0)}ms"
            url = r.get("url") or r.get("raw_input")
            self.tree.insert("", tk.END, values=(idx, status, remain, deadline, snip, plan, details, duration, url))

        self.progress_bar['value'] = current
        self.lbl_status.config(text=f"状态: 检测中 ({current}/{total})...")
        self._update_stats_label()

    def _finish_check(self, res_list=None):
        self.is_checking = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_status.config(text="状态: 检测完成 ✅ (已按序排列)")
        self._update_stats_label()

    def stop_check(self):
        if self.batch_checker:
            self.batch_checker.stop_requested = True
        self.lbl_status.config(text="状态: 已停止 ⏹️")
        self._finish_check()

    def _update_stats_label(self):
        total = len(self.results)
        active = sum(1 for r in self.results if r.get("status") == STATUS_ACTIVE)
        used = sum(1 for r in self.results if r.get("status") == STATUS_USED)
        invalid = sum(1 for r in self.results if r.get("status") not in (STATUS_ACTIVE, STATUS_USED))

        self.lbl_total.config(text=f"总检测: {total}")
        self.lbl_active.config(text=f"🟢 有效(未激活): {active}")
        self.lbl_used.config(text=f"🔴 已失效(已使用): {used}")
        self.lbl_invalid.config(text=f"⚠️ 异常/需Cookie: {invalid}")

    def on_double_click_row(self, event):
        selected = self.tree.selection()
        if not selected:
            return
        item = self.tree.item(selected[0])
        url = item['values'][8]
        if url and url.startswith("http"):
            webbrowser.open(url)

    def copy_active_links(self):
        actives = [f"第 {r.get('index', 1)} 条 ({r.get('remaining_time', '有效')} | 截止: {r.get('expire_deadline', '')}): " + (r.get("url") or r.get("raw_input")) for r in self.results if r.get("status") == STATUS_ACTIVE]
        if not actives:
            messagebox.showinfo("提示", "当前无有效激活链接！")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(actives))
        messagebox.showinfo("复制成功", f"已成功复制 {len(actives)} 条有效链接到剪贴板（已带时效与输入行号）！")

    def export_active_txt(self):
        actives = [f"[第 {r.get('index', 1)} 条] [{r.get('remaining_time', '有效')} | 截止: {r.get('expire_deadline', '')}] " + (r.get("url") or r.get("raw_input")) for r in self.results if r.get("status") == STATUS_ACTIVE]
        if not actives:
            messagebox.showinfo("提示", "当前无有效激活链接可导出！")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(actives))
        messagebox.showinfo("导出成功", f"已成功导出 {len(actives)} 条有效链接至 {os.path.basename(file_path)}！")

    def export_excel(self):
        if not self.results:
            messagebox.showinfo("提示", "暂无检测结果！")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
        if not file_path:
            return

        import xlsxwriter
        workbook = xlsxwriter.Workbook(file_path)
        worksheet = workbook.add_worksheet("检测结果")

        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#1a73e8', 'font_color': 'white', 'align': 'center'})
        active_fmt = workbook.add_format({'bg_color': '#e6f4ea', 'font_color': '#137333', 'bold': True})
        used_fmt = workbook.add_format({'bg_color': '#fce8e6', 'font_color': '#c5221f', 'bold': True})

        headers = ["输入行号", "状态判定", "剩余时效倒计时", "截止日期", "Token特征码", "权益方案", "详细说明", "完整链接", "耗时(ms)", "检测时间"]
        for c, h in enumerate(headers):
            worksheet.write(0, c, h, header_fmt)

        sorted_results = sorted(self.results, key=lambda x: x.get("index", 0))

        for r_idx, r in enumerate(sorted_results, start=1):
            st = r.get("status")
            fmt = active_fmt if st == STATUS_ACTIVE else (used_fmt if st == STATUS_USED else None)
            worksheet.write(r_idx, 0, f"第 {r.get('index', r_idx)} 条")
            worksheet.write(r_idx, 1, r.get("status_badge", r.get("status_label", st)), fmt)
            worksheet.write(r_idx, 2, r.get("remaining_time", "-"), fmt)
            worksheet.write(r_idx, 3, r.get("expire_deadline", "-"))
            worksheet.write(r_idx, 4, r.get("token_snippet", "-"))
            worksheet.write(r_idx, 5, r.get("plan_info", "-"))
            worksheet.write(r_idx, 6, r.get("details", ""))
            worksheet.write(r_idx, 7, r.get("url") or r.get("raw_input"))
            worksheet.write(r_idx, 8, r.get("duration_ms", 0))
            worksheet.write(r_idx, 9, r.get("timestamp", ""))

        workbook.close()
        messagebox.showinfo("导出成功", f"已成功生成 Excel 报告至 {os.path.basename(file_path)}！")

    def open_settings_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("检测配置与授权")
        dlg.geometry("550x420")
        dlg.transient(self.root)
        dlg.grab_set()

        cfg = load_config()

        ttk.Label(dlg, text="网络代理 (HTTP/SOCKS5):", font=("Microsoft YaHei", 9, "bold")).pack(anchor=tk.W, padx=15, pady=(15, 2))
        ent_proxy = ttk.Entry(dlg, width=50)
        ent_proxy.insert(0, cfg.get("proxy", "http://127.0.0.1:7890"))
        ent_proxy.pack(fill=tk.X, padx=15)

        ttk.Label(dlg, text="Google 账号 Cookie (登录态):", font=("Microsoft YaHei", 9, "bold")).pack(anchor=tk.W, padx=15, pady=(10, 2))
        txt_cookie = tk.Text(dlg, height=6, font=("Consolas", 8))
        txt_cookie.insert(tk.END, cfg.get("cookie", ""))
        txt_cookie.pack(fill=tk.BOTH, padx=15, expand=True)

        lbl_test = ttk.Label(dlg, text="", font=("Microsoft YaHei", 8))
        lbl_test.pack(anchor=tk.W, padx=15, pady=2)

        def do_test_cookie():
            cookie = txt_cookie.get("1.0", tk.END).strip()
            proxy = ent_proxy.get().strip()
            lbl_test.config(text="正在测试 Cookie 连通性...", foreground="#2563eb")
            dlg.update()
            ok, msg = check_google_cookie_validity(cookie, proxy=proxy)
            if ok:
                lbl_test.config(text=f"✅ {msg}", foreground="#16a34a")
            else:
                lbl_test.config(text=f"❌ {msg}", foreground="#dc2626")

        btn_test = ttk.Button(dlg, text="🔍 测试 Cookie 连通性", command=do_test_cookie)
        btn_test.pack(anchor=tk.W, padx=15, pady=2)

        def do_save():
            save_config({
                "proxy": ent_proxy.get().strip(),
                "cookie": txt_cookie.get("1.0", tk.END).strip()
            })
            dlg.destroy()
            messagebox.showinfo("成功", "配置已成功保存！")

        btn_save = tk.Button(dlg, text="保存配置", bg="#1a73e8", fg="white", font=("Microsoft YaHei", 9, "bold"), relief="flat", padx=15, pady=4, command=do_save)
        btn_save.pack(side=tk.RIGHT, padx=15, pady=10)

    def open_help_dialog(self):
        msg = (
            "【Cookie 获取教程】\n\n"
            "1. 打开 Chrome 浏览器，登录任一 Google 账号并访问 https://one.google.com\n"
            "2. 按键盘 F12 打开开发者工具，切换到「网络 (Network)」标签页\n"
            "3. 刷新页面，点击左侧列表中第一个「one.google.com」或「app?awwd=...」请求\n"
            "4. 在右侧「标头 (Headers)」中找到「Cookie: ...」，右键复制整段 Cookie\n"
            "5. 回到本工具「⚙️ 代理/Cookie配置」，粘贴并保存即可！"
        )
        messagebox.showinfo("Cookie 获取指南", msg)

def main():
    root = tk.Tk()
    app = AppGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
