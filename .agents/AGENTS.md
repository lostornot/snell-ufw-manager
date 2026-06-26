# Workspace Agent Rules

这些规则配置了在此工作区内工作的 AI 编码助手（如 Antigravity）的行为准则。

## 技术栈与架构 (Technology Stack & Architecture)
- **后端**：Python 3.10+ / FastAPI / Uvicorn / aiosqlite (SQLite)。
- **前端**：Jinja2 模板 + HTMX 2.x（提供无刷新局部更新体验）。
- **CSS 样式**：仅使用原生 CSS (Vanilla CSS)。除非用户明确要求，否则不要引入 TailwindCSS 或任何其他 CSS 框架。
- **防火墙被控端**：通过 SSH 以限制权限的 `snellmgr` 用户远程调用目标 VPS 上的 `/usr/local/sbin/snell-fwctl` Bash 脚本。

## 视觉与 UI/UX 规范 (Design Guidelines)
- **色彩设计**：高端暗色模式基础，配合半透明玻璃拟物卡片（`--bg-glass`）、明亮霓虹色调（`--accent-purple`、`--accent-blue` 等）和发光投影，以及高雅的 Outfit/Inter 字体栈。
- **亮色模式适配**：必须维持亮色模式下的绝对可读性。避免在 HTML 中写死字体颜色（例如在浅色背景上硬编码 `color: #fff`），应统一使用 CSS 变量（如 `--text-primary`、`--bg-secondary` 等）。
- **响应式设计**：确保页面和表格在窄屏、移动设备上能优雅缩放和自适应（例如端口卡片列表在小屏下堆叠展示）。

## 按钮与图标规范 (Button Guidelines) - ⚠️ 重要
1. **禁止在按钮文字前添加装饰性 Emoji/箭头**：保持按钮和链接按钮文字的简洁现代，不要在按钮文本内容中塞入修饰性小图标（例如，使用「刷新规则」代替「🔄 刷新规则」，使用「返回」代替「← 返回」，使用「保存」代替「💾 保存」）。
2. **完美水平居中**：所有按钮及类按钮链接必须保证文字完全水平、垂直居中对齐。使用 `display: inline-flex; align-items: center; justify-content: center;` 进行布局。
3. **HTMX Spinner 优先级防冲突**：在 `style.css` 中，`.spinner` 类必须声明在 `.htmx-indicator` 之前，以确保在非加载状态下，加载动画的 `display: none` 优先级最高，防止其因 `display: inline-block` 占用隐形空间而导致按钮文本向右偏移。

## 数据库与幂等设计 (Database & Idempotency)
- **模式升级**：所有的 SQLite 数据库更新必须集成在 `controller/app/database.py` 的 `init_db()` 中，通过 `ALTER TABLE ... ADD COLUMN ...` 辅以异常处理（`try-except`）来完成，确保现有数据不丢失，平滑向前兼容。
- **远程操作幂等性**：在通过 SSH 在目标主机上添加或删除 UFW 规则前，后端必须先拉取并对比该主机的实时 UFW 规则库。若已存在完全相同的放行规则，应直接跳过远程执行，降低 SSH 开销并记录审计日志。
