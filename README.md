# Google One / Jio 18个月 AI Pro 激活链接活性批量检测工具

专门针对 **Jio 提供的 Google One 18个月免费 Google AI Pro (5TB + Gemini Pro / Nano Banana Pro)** 激活链接设计的活性批量检测工具。

---

## 🌟 核心判定逻辑（精准匹配官方页面特征）

1. **🟢 有效未激活（有效活性）**
   - 页面特征：显示 `激活Jio提供的Google AI Pro方案（原价为 ₹35,100）*，免费畅享 18 个月`、`安全存储 5 TB`、`Nano Banana Pro`、`切换方案 / 立即激活`。
2. **🔴 已失效（已被使用 / 失去活性）**
   - 页面特征：显示 Google One 图标与 `订阅已在使用中`、`此订阅链接已被使用。探索 Google One 提供的福利和其他优惠。`。
3. **⚠️ 链接异常 / 已过期**
   - 页面特征：404 页面、链接不存在或超出兑换期限。
4. **🟡 需配置 Cookie**
   - 页面特征：提示未登录，被重定向至 Google 登录页面。

---

## 🚀 快速启动方式

### 方式一：Web 可视化界面（推荐，功能最全）
直接双击运行：
👉 **`双击启动Web版.bat`**
- 会自动在浏览器中打开 `http://127.0.0.1:5000`
- 支持批量粘贴、拖拽上传 `.txt` / `.csv` / `.xlsx` 文件
- 实时展示检测进度条、统计卡片、分类筛选
- 支持 **一键复制所有有效链接**、**导出有效链接 TXT**、**导出完整检测报告 Excel**

### 方式二：桌面版客户端（原生窗口）
直接双击运行：
👉 **`双击启动桌面版.bat`**
- 纯本地绿色 GUI 客户端，免开浏览器

### 方式三：命令行模式（CLI 批处理）
```bash
# 检测单个链接
python cli_check.py "https://serviceactivation.google.com/subscription/new/AQCpiI..."

# 批量检测文件中的链接并输出有效链接
python cli_check.py -i links.txt -o valid_links.txt -t 10
```

---

## ⚙️ 核心配置说明 (代理与 Cookie)

### 1. 为什么需要配置代理？
由于 Google 服务在中国大陆网络环境下无法直接访问，工具默认集成了本地代理设置：
- 默认代理：`http://127.0.0.1:7890`（适用于 Clash / Sing-box / V2Ray 等常见代理工具）。
- 可在工具界面右上角「⚙️ 配置中心」随时修改为您使用的代理端口。

### 2. 为什么需要 Google Cookie？
Google 激活链接在未登录状态下会强制跳转至 Google 登录页。配置 Cookie 后，工具即可模拟已登录状态快速获取链接对应的真实套餐详情与活性状态。

#### 💡 如何获取 Cookie（极简 4 步）：
1. 在 Chrome 浏览器中登录您的任一 Google 账号并打开 [https://one.google.com](https://one.google.com)；
2. 按键盘 **F12**（或右键 -> 检查）打开开发者工具，切换到 **「网络 (Network)」** 标签页；
3. 刷新页面（F5），点击左侧列表中第一个 **`one.google.com`** 请求；
4. 在右侧 **「标头 (Headers)」->「请求标头 (Request Headers)」** 中找到 **`Cookie:`**，右键复制其完整内容；
5. 回到本工具右上角 **「配置中心」**，粘贴到 Cookie 输入框中，点击 **「测试 Cookie 连通性」** 成功后保存即可！

---

## 📁 目录文件结构

- `app.py`: Web 端服务后端与 API
- `templates/index.html`: 现代化 Web 界面前端
- `gui.py`: Tkinter 桌面版客户端
- `cli_check.py`: 命令行检测工具
- `checker.py`: 核心检测引擎（多线程、状态智能识别算法）
- `config.py` / `config.json`: 本地配置与凭证存储
- `双击启动Web版.bat`: Web 版一键启动脚本
- `双击启动桌面版.bat`: 桌面版一键启动脚本
