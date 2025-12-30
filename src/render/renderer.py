"""
图片渲染模块 - 使用 Jinja2 + Playwright 生成游戏图片
"""
import os
import asyncio
from enum import Enum
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
from ..config import config




class RenderType(Enum):
    """渲染类型"""
    NARRATIVE = "narrative"      # Type A: 探索与剧情
    COMBAT = "combat"            # Type B: 战斗结算  
    DASHBOARD = "dashboard"      # Type C: 数据面板
    HIGHLIGHT = "highlight"      # Type D: 奖励高光
    DIALOGUE = "dialogue"        # Type E: NPC对话
    HELP = "help"                # Type F: 帮助


# 现代工业风 SVG 图标库
ICONS = {
    "help": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H8c0-2.21 1.79-4 4-4s4 1.79 4 4c0 .88-.36 1.68-.93 2.25z"/></svg>',
    "hp": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>',
    "mp": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 2L2 22h20L12 2zm0 3.8l6.5 13.2H5.5L12 5.8z"/></svg>',
    "gold": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 16.09V20h-2.67v-1.93c-1.71-.36-3.16-1.46-3.27-3.4h1.96c.1 1.05 1.18 1.91 2.53 1.91 1.29 0 2.13-.81 2.13-1.88 0-1.09-.86-1.63-2.42-2l-1.06-.25c-2.15-.52-3.32-1.78-3.32-3.42 0-1.77 1.39-3.11 3.25-3.43V4h2.67v1.9c1.65.34 2.87 1.42 3.01 3.22h-2.02c-.14-1.01-.98-1.76-2.25-1.76-1.14 0-1.92.73-1.92 1.76 0 1.16.89 1.63 2.5 2l1.01.24c2.19.53 3.43 1.73 3.43 3.48 0 1.88-1.42 3.25-3.3 3.49z"/></svg>',
    "attack": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M2.06 16.3l4.67 4.67 3.77-3.77L2.06 16.3zm3.77-8.4L18.4 21.36l1.3-1.3-3.05-3.05L7.13 6.6l-1.3 1.3zM20.6 5.8l-1.62-1.62L17.3 5.85l1.62 1.62L20.6 5.8zm-3.06 3.06l-1.62-1.62L5.85 17.3l1.62 1.62 10.07-10.06z"/></svg>',
    "defense": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>',
    "exp": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>',
    "bag": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M20 6h-4V4c0-1.11-.89-2-2-2h-4c-1.11 0-2 .89-2 2v2H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-6 0h-4V4h4v2z"/></svg>',
    "location": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>',
    "player": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>',
    "monster": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M11 7c0 .55.45 1 1 1s1-.45 1-1-.45-1-1-1-1 .45-1 1zm0 4h2v2h-2v-2zm-1-8C4.48 3 0 7.48 0 13c0 2.98 1.29 5.66 3.39 7.47.52.45 1.32.32 1.63-.3.26-.52.09-1.15-.4-1.48C2.96 17.58 2 15.42 2 13 2 8.59 5.59 5 10 5c4.41 0 8 3.59 8 8 0 2.42-.96 4.58-2.62 5.69-.49.34-.66.96-.39 1.49.27.52 1.05.69 1.57.34C19.78 18.23 21.43 15.34 22 12.11V12h-2v2h2v-2h-3v-2h5v4.2c0 .41-.31.78-.71.86-1.92.38-3.08 1.1-4.29 2.05V13h-2v8h2v-1.79c1.67-.84 3.3-1.39 4.39-1.81.9-.35 1.61-1.22 1.61-2.2V12c0-5.52-4.48-10-10-10z"/></svg>'
}

class ImageRenderer:

    
    def __init__(self, templates_dir: str = None):
        self.templates_dir = templates_dir or config.render.templates_dir
        self.output_dir = config.render.output_dir
        
        # 优化：不设置固定的截图宽高，而是自适应
        self.width = config.render.screenshot_width
        self.height = config.render.screenshot_height
        
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.templates_dir, exist_ok=True)
        self._env: Optional[Environment] = None
        self._executor = ThreadPoolExecutor(max_workers=2)

    async def init(self):
        """初始化渲染器"""
        # 初始化 Jinja2
        if os.path.exists(self.templates_dir):
            self._env = Environment(
                loader=FileSystemLoader(self.templates_dir),
                autoescape=True
            )
        print("[Renderer] 渲染器初始化完成 (使用线程池模式)")
    
    async def close(self):
        """关闭渲染器"""
        print("[Renderer] 正在关闭线程池...")
        self._executor.shutdown(wait=False)
        print("[Renderer] 线程池已关闭")
    
    async def render(
        self,
        render_type: RenderType,
        data: Dict[str, Any],
        filename: Optional[str] = None
    ) -> str:
        """
        渲染图片
        
        Args:
            render_type: 渲染类型
            data: 模板数据
            filename: 输出文件名（不含路径）
            
        Returns:
            生成的图片路径
        """
        print(f"[Renderer] 开始渲染 {render_type.value}...")
        
        try:
            # 选择模板
            template_name = f"{render_type.value}.html"
            
            # 如果模板不存在，使用内置HTML
            if self._env and template_name in self._env.list_templates():
                template = self._env.get_template(template_name)
                html_content = template.render(**data)
            else:
                # 使用内置模板
                html_content = self._get_builtin_template(render_type, data)
            
            print(f"[Renderer] HTML 内容生成完成，长度: {len(html_content)}")
            
            # 生成文件名
            if not filename:
                import time
                filename = f"{render_type.value}_{int(time.time() * 1000)}.png"
            
            output_path = os.path.join(self.output_dir, filename)
            print(f"[Renderer] 输出路径: {output_path}")
            
            # 在线程池中运行同步 Playwright
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._render_sync,
                html_content,
                output_path,
                self.width,
                self.height
            )
            
            if result:
                print(f"[Renderer] 截图完成: {output_path}")
                return output_path
            else:
                print(f"[Renderer] 截图失败")
                return None
            
        except Exception as e:
            print(f"[Renderer] 渲染出错: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def _render_sync(html_content: str, output_path: str, width: int, height: int) -> bool:
        """同步渲染方法，在线程池中运行"""
        try:
            print(f"[Renderer-Thread] 启动 Playwright...")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_viewport_size({"width": width, "height": height})
                
                # 加载 HTML
                page.set_content(html_content, timeout=5000)
                page.wait_for_timeout(200)
                
                # 关键修改：获取 .card 元素并截图，而不是截整个页面
                # 这能完美解决留白问题
                card = page.locator(".card")
                if card.count() > 0:
                    print(f"[Renderer-Thread] 截图 .card 元素...")
                    card.first.screenshot(path=output_path)
                else:
                    print(f"[Renderer-Thread] 未找到 .card，回退到页面截图...")
                    page.screenshot(path=output_path, full_page=True)
                
                page.close()
                browser.close()
            
            print(f"[Renderer-Thread] 完成!")
            return True
            
        except Exception as e:
            print(f"[Renderer-Thread] 出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _get_builtin_template(self, render_type: RenderType, data: Dict[str, Any]) -> str:
        """获取内置模板（全新设计：赛博工业风）"""
        
        # 背景图路径 (假设已下载到 assets)
        bg_path = os.path.abspath("assets/backgrounds/tech_grid_dark_background_1766038179989.png").replace("\\", "/")
        
        base_styles = f"""
        <style>
            :root {{
                --c-bg-dark: #0a0a0f;
                --c-bg-card: rgba(18, 18, 24, 0.85);
                --c-border: #4a4a5e;
                --c-accent: #e5c07b;
                --c-text-primary: #e0e0e0;
                --c-text-secondary: #9a9a9a;
                --c-hp: #ff5c5c;
                --c-mp: #5c9cff;
                --c-gold: #ffd700;
                
                --font-primary: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", "Microsoft YaHei", sans-serif;
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: var(--font-primary);
                background: url('file:///{bg_path}') center/cover no-repeat;
                color: var(--c-text-primary);
                padding: 40px;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                align-items: center; # 居中对齐
            }}
            
            /* 
               核心设计：工业风卡片
               切角实现：clip-path: polygon(...)
               无圆角，硬朗线条
            */
            .card {{
                position: relative;
                width: 100%;
                max-width: 600px;
                background: var(--c-bg-card);
                backdrop-filter: blur(20px);
                -webkit-backdrop-filter: blur(20px);
                /* 45度切角 */
                clip-path: polygon(
                    20px 0, 100% 0, 
                    100% calc(100% - 20px), calc(100% - 20px) 100%, 
                    0 100%, 0 20px
                );
                padding: 0; /* 使用内部容器控制 padding */
                box-shadow: 0 20px 40px rgba(0,0,0,0.6);
            }}
            
            /* 装饰性边框 (模拟 clip-path 的边框) */
            .card::before {{
                content: "";
                position: absolute;
                inset: 0;
                background: linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.02));
                z-index: -1;
            }}
            
            /* 顶部状态栏装饰 */
            .card-header {{
                background: rgba(255, 255, 255, 0.05);
                padding: 16px 24px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                display: flex;
                align-items: center;
                justify-content: space-between;
            }}
            
            .header-deco {{
                font-family: monospace;
                font-size: 10px;
                color: var(--c-text-secondary);
                letter-spacing: 2px;
                opacity: 0.5;
            }}
            
            .title {{
                font-size: 18px;
                font-weight: 600;
                color: var(--c-text-primary);
                letter-spacing: 0.5px;
                display: flex;
                align-items: center;
                gap: 8px;
            }}
            
            .card-body {{
                padding: 24px;
            }}
            
            .content-text {{
                font-size: 15px;
                line-height: 1.6;
                color: #ccc;
                text-align: justify;
                margin-bottom: 20px;
            }}
            
            /* 数据状态行 */
            .status-row {{
                display: flex;
                gap: 16px;
                margin-top: 16px;
                padding-top: 16px;
                border-top: 1px solid rgba(255, 255, 255, 0.05);
            }}
            
            .stat-item {{
                display: flex;
                align-items: center;
                gap: 6px;
                font-size: 13px;
                color: var(--c-text-secondary);
                font-family: monospace;
            }}
            
            .icon {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }}
            
            .icon svg {{
                fill: currentColor;
            }}
            
            /* 进度条 - 极简风格 */
            .bar-container {{
                width: 100px;
                height: 4px;
                background: rgba(255,255,255,0.1);
                position: relative;
            }}
            
            .bar-fill {{
                height: 100%;
                background: #ccc;
            }}
            
            .hp-fill {{ background: var(--c-hp); }}
            .mp-fill {{ background: var(--c-mp); }}
            
            /* 按钮/建议胶囊 */
            .suggestions {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 20px;
            }}
            
            .suggestion-btn {{
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: var(--c-text-secondary);
                padding: 6px 12px;
                font-size: 12px;
                cursor: pointer;
                transition: all 0.2s;
            }}
            
            /* 物品网格 */
            .item-grid {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 12px;
                margin-top: 16px;
            }}
            
            .item-slot {{
                background: rgba(0,0,0,0.2);
                border: 1px solid rgba(255,255,255,0.05);
                padding: 12px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                aspect-ratio: 1;
                position: relative;
            }}
            
            .item-count {{
                position: absolute;
                bottom: 4px;
                right: 4px;
                font-size: 10px;
                color: var(--c-text-secondary);
                font-family: monospace;
            }}
            
            /* VS 布局 */
            .vs-layout {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin: 20px 0;
            }}
            
            .vs-divider {{
                width: 1px;
                height: 40px;
                background: rba(255,255,255,0.1);
            }}
            
            /* 日志 */
            .log-container {{
                font-family: monospace;
                font-size: 12px;
                color: var(--c-text-secondary);
                background: rgba(0,0,0,0.3);
                padding: 12px;
                margin-top: 16px;
                border-left: 2px solid var(--c-accent);
            }}
            
            .log-entry {{ margin-bottom: 4px; }}
            .log-entry:last-child {{ margin-bottom: 0; color: var(--c-text-primary); }}
        </style>
        """

        if render_type == RenderType.NARRATIVE:
            return self._narrative_template(data, base_styles)
        elif render_type == RenderType.COMBAT:
            return self._combat_template(data, base_styles)
        elif render_type == RenderType.DASHBOARD:
            return self._dashboard_template(data, base_styles)
        elif render_type == RenderType.HIGHLIGHT:
            return self._highlight_template(data, base_styles)
        elif render_type == RenderType.DIALOGUE:
            return self._dialogue_template(data, base_styles)
        elif render_type == RenderType.HELP:
            return self._help_template(data, base_styles)
        else:
            return f"<html><body><p>Unknown Render Type</p></body></html>"

    def _help_template(self, data: Dict[str, Any], styles: str) -> str:
        categories_html = ""
        for cat in data.get("categories", []):
            cmds_html = "".join([f'<div class="cmd-item">{cmd}</div>' for cmd in cat["commands"]])
            categories_html += f"""
            <div class="help-category">
                <div class="category-title">{cat['title']}</div>
                <div class="category-body">{cmds_html}</div>
            </div>
            """
            
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            {styles}
            <style>
                .help-grid {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 16px;
                    margin-top: 16px;
                }}
                .help-category {{
                    background: rgba(0,0,0,0.2);
                    border: 1px solid rgba(255,255,255,0.05);
                    padding: 16px;
                    /* 切角 */
                    clip-path: polygon(
                        10px 0, 100% 0, 
                        100% calc(100% - 10px), calc(100% - 10px) 100%, 
                        0 100%, 0 10px
                    );
                }}
                .category-title {{
                    color: var(--c-accent);
                    font-size: 12px;
                    margin-bottom: 12px;
                    letter-spacing: 1px;
                    border-bottom: 1px solid rgba(255,255,255,0.1);
                    padding-bottom: 8px;
                    font-weight: bold;
                }}
                .cmd-item {{
                    font-family: monospace;
                    font-size: 13px;
                    color: var(--c-text-primary);
                    margin-bottom: 8px;
                    display: flex;
                    align-items: center;
                }}
                .cmd-item::before {{
                    content: ">";
                    color: var(--c-text-secondary);
                    margin-right: 8px;
                    font-size: 10px;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="card-header">
                    <div class="title">
                        <span class="icon">{ICONS['help']}</span>
                        SYSTEM MANUAL
                    </div>
                    <div class="header-deco">protocol_v1.0</div>
                </div>
                <div class="card-body">
                    <div class="content-text" style="text-align: center; margin-bottom: 8px; font-size: 14px; color: var(--c-text-secondary);">
                        DaiyoseiBot Operation Guide
                    </div>
                    <div class="help-grid">
                        {categories_html}
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

    def _narrative_template(self, data: Dict[str, Any], styles: str) -> str:
        location = data.get("location", {})
        narration = data.get("narration", {})
        player = data.get("player", {})
        
        suggestions_html = ""
        for s in narration.get("suggestions", []):
            suggestions_html += f'<div class="suggestion-btn">{s}</div>'
        
        hp_percent = (player.get('hp', 0) / player.get('max_hp', 100)) * 100
        mp_percent = (player.get('mp', 0) / player.get('max_mp', 50)) * 100

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8">{styles}</head>
        <body>
            <div class="card">
                <div class="card-header">
                    <div class="title">
                        <span class="icon">{ICONS['location']}</span>
                        {location.get('name', '未知领域')}
                    </div>
                    <div class="header-deco">SECTOR-09 // EXPLORATION</div>
                </div>
                
                <div class="card-body">
                    <div class="content-text">
                        {narration.get('text_content', 'Signal lost...')}
                    </div>
                    
                    {f'<div class="suggestions">{suggestions_html}</div>' if suggestions_html else ''}
                    
                    <div class="status-row">
                        <div class="stat-item">
                            <span class="icon" style="color: var(--c-hp)">{ICONS['hp']}</span>
                            <div class="bar-container"><div class="bar-fill hp-fill" style="width: {hp_percent}%"></div></div>
                            <span>{player.get('hp')}/{player.get('max_hp')}</span>
                        </div>
                        <div class="stat-item">
                            <span class="icon" style="color: var(--c-mp)">{ICONS['mp']}</span>
                            <div class="bar-container"><div class="bar-fill mp-fill" style="width: {mp_percent}%"></div></div>
                            <span>{player.get('mp')}/{player.get('max_mp')}</span>
                        </div>
                        <div class="stat-item" style="margin-left: auto;">
                            <span class="icon" style="color: var(--c-gold)">{ICONS['gold']}</span>
                            <span>{player.get('gold')} G</span>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _combat_template(self, data: Dict[str, Any], styles: str) -> str:
        player = data.get("player", {})
        monster = data.get("monster", {})
        combat_result = data.get("combat_result", {})
        narration = data.get("narration", {})
        combat_log = data.get("combat_log", [])
        
        player_hp_percent = (player.get('hp', 0) / player.get('max_hp', 100)) * 100
        monster_hp_percent = (monster.get('hp', 0) / monster.get('max_hp', 50)) * 100
        
        log_html = ""
        for log in combat_log[-5:]:
            log_html += f'<div class="log-entry">> {log}</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8">{styles}</head>
        <body>
            <div class="card">
                <div class="card-header">
                    <div class="title" style="color: var(--c-hp)">
                        <span class="icon">{ICONS['attack']}</span>
                        COMBAT MODE
                    </div>
                    <div class="header-deco">ENGAGEMENT // HOSTILE</div>
                </div>
                
                <div class="card-body">
                    <div class="vs-layout">
                        <div style="width: 45%;">
                            <div style="font-size: 16px; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                                <span class="icon">{ICONS['player']}</span> {player.get('nickname', 'UNIT-01')}
                            </div>
                            <div class="bar-container" style="width: 100%; height: 6px;">
                                <div class="bar-fill hp-fill" style="width: {player_hp_percent}%"></div>
                            </div>
                            <div style="font-size: 12px; color: var(--c-text-secondary); margin-top: 4px; font-family: monospace;">
                                HP: {player.get('hp')}/{player.get('max_hp')}
                            </div>
                        </div>
                        
                        <div style="font-size: 20px; font-weight: 900; color: #444; font-style: italic;">VS</div>
                        
                        <div style="width: 45%; text-align: right;">
                            <div style="font-size: 16px; margin-bottom: 8px; display: flex; align-items: center; justify-content: flex-end; gap: 6px; color: var(--c-hp);">
                                {monster.get('name', 'UNKNOWN')} <span class="icon">{ICONS['monster']}</span>
                            </div>
                            <div class="bar-container" style="width: 100%; height: 6px; margin-left: auto;">
                                <div class="bar-fill hp-fill" style="width: {monster_hp_percent}%"></div>
                            </div>
                            <div style="font-size: 12px; color: var(--c-text-secondary); margin-top: 4px; font-family: monospace;">
                                HP: {monster.get('hp')}/{monster.get('max_hp')}
                            </div>
                        </div>
                    </div>
                    
                    <div class="content-text" style="text-align: center; margin: 24px 0; font-style: italic; color: #fff;">
                        {narration.get('text_content', '')}
                    </div>
                    
                    {f'<div style="text-align: center; color: var(--c-hp); font-size: 24px; font-weight: bold; margin-bottom: 16px;">CRITICAL DAMAGE: -{combat_result.get("damage")}</div>' if combat_result.get("damage") else ''}
                    
                    <div class="log-container">
                        {log_html if log_html else '<div class="log-entry">> Initializing combat sequence...</div>'}
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _dashboard_template(self, data: Dict[str, Any], styles: str) -> str:
        player = data.get("player", {})
        inventory = data.get("inventory", [])
        
        hp_percent = (player.get('hp', 0) / player.get('max_hp', 100)) * 100
        mp_percent = (player.get('mp', 0) / player.get('max_mp', 50)) * 100
        
        items_html = ""
        for item in inventory[:12]:
            items_html += f"""
            <div class="item-slot">
                <span class="icon" style="color: var(--c-accent)">{ICONS['bag']}</span>
                <div class="item-name" style="font-size: 11px; margin-top: 4px; color: var(--c-text-secondary);">{item.get('name', 'N/A')}</div>
                <div class="item-count">x{item.get('count', 1)}</div>
            </div>
            """
        
        if not items_html:
            items_html = '<div style="grid-column: span 4; text-align: center; color: var(--c-text-secondary); padding: 20px; font-style: italic;">No items detected</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8">{styles}</head>
        <body>
            <div class="card">
                <div class="card-header">
                    <div class="title">
                        <span class="icon">{ICONS['player']}</span>
                        STATUS : {player.get('nickname', 'UNKNOWN')}
                    </div>
                    <div class="header-deco">DATA-LINK // ACTIVE</div>
                </div>
                
                <div class="card-body">
                    <div style="display: flex; gap: 24px; margin-bottom: 24px;">
                        <div style="flex: 1;">
                            <div style="margin-bottom: 8px; color: var(--c-text-secondary); font-size: 12px;">LEVEL & EXPERTISE</div>
                            <div style="font-size: 24px; font-weight: bold; color: var(--c-accent);">Lv.{player.get('level', 1)}</div>
                            <div style="font-size: 13px; margin-top: 4px;">EXP: {player.get('exp', 0)}</div>
                        </div>
                        <div style="flex: 1; border-left: 1px solid rgba(255,255,255,0.1); padding-left: 24px;">
                            <div style="margin-bottom: 8px; color: var(--c-text-secondary); font-size: 12px;">COMBAT STATS</div>
                            <div style="font-size: 14px; margin-bottom: 4px;">
                                <span class="icon">{ICONS['attack']}</span> ATK: {player.get('attack', 10)}
                            </div>
                            <div style="font-size: 14px;">
                                <span class="icon">{ICONS['defense']}</span> DEF: {player.get('defense', 5)}
                            </div>
                        </div>
                    </div>
                    
                    <div style="margin-bottom: 24px;">
                        <div class="status-row" style="margin-top: 0; padding-top: 0; border: none;">
                            <div style="flex: 1;">
                                <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
                                    <span>HP</span> <span>{player.get('hp')}/{player.get('max_hp')}</span>
                                </div>
                                <div class="bar-container" style="width: 100%;"><div class="bar-fill hp-fill" style="width: {hp_percent}%"></div></div>
                            </div>
                            <div style="flex: 1;">
                                <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
                                    <span>MP</span> <span>{player.get('mp')}/{player.get('max_mp')}</span>
                                </div>
                                <div class="bar-container" style="width: 100%;"><div class="bar-fill mp-fill" style="width: {mp_percent}%"></div></div>
                            </div>
                        </div>
                    </div>
                    
                    <div>
                        <div style="font-size: 12px; color: var(--c-text-secondary); margin-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 8px;">
                            INVENTORY MODULE
                        </div>
                        <div class="item-grid">
                            {items_html}
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _highlight_template(self, data: Dict[str, Any], styles: str) -> str:
        title = data.get("title", "SYSTEM ALERT")
        content = data.get("content", "")
        rewards = data.get("rewards", {})
        
        rewards_html = ""
        if rewards.get("gold"):
            rewards_html += f"""
            <div style="display: flex; align-items: center; justify-content: center; gap: 8px; margin: 12px 0; color: var(--c-gold); font-size: 20px;">
                <span class="icon">{ICONS['gold']}</span> +{rewards["gold"]} CREDITS
            </div>
            """
        for item in rewards.get("items", []):
            rewards_html += f"""
            <div style="display: flex; align-items: center; justify-content: center; gap: 8px; margin: 8px 0; color: var(--c-text-primary);">
                <span class="icon">{ICONS['bag']}</span> ACQUIRED: {item.get("name", "Unknown")} x{item.get("count", 1)}
            </div>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8">{styles}</head>
        <body>
            <div class="card">
                 <div class="card-header" style="justify-content: center; background: rgba(229, 192, 123, 0.1);">
                    <div class="title" style="color: var(--c-accent); font-size: 24px;">
                        {title}
                    </div>
                </div>
                
                <div class="card-body" style="text-align: center;">
                    <div class="content-text" style="font-size: 18px; color: #fff; margin: 24px 0;">
                        {content}
                    </div>
                    
                    <div style="margin-top: 32px; padding: 24px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.05);">
                        <div style="font-size: 12px; color: var(--c-text-secondary); margin-bottom: 16px; letter-spacing: 2px;">REWARD SEQUENCE</div>
                        {rewards_html}
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

    def _dialogue_template(self, data: Dict[str, Any], styles: str) -> str:
        npc = data.get("npc", {})
        narration = data.get("narration", {})
        
        suggestions_html = ""
        for s in narration.get("suggestions", []):
            suggestions_html += f'<div class="suggestion-btn">{s}</div>'
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8">{styles}</head>
        <body>
            <div class="card">
                 <div class="card-header">
                    <div class="title" style="color: var(--c-mp);">
                        <span class="icon">{ICONS['player']}</span>
                        COMMUNICATION LINK
                    </div>
                    <div class="header-deco">TARGET: {npc.get('name', 'UNKNOWN')}</div>
                </div>
                
                <div class="card-body">
                    <div style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px;">
                        <div style="font-size: 14px; color: var(--c-text-secondary);">INCOMING MESSAGE FROM</div>
                        <div style="font-size: 20px; font-weight: bold; color: var(--c-mp); display: flex; align-items: center; gap: 8px;">
                             <span>{npc.get('name', '神秘人')}</span>
                        </div>
                        
                        <div class="content-text" style="margin-top: 12px; padding: 20px; background: rgba(92, 156, 255, 0.05); border-left: 3px solid var(--c-mp);">
                            {narration.get('text_content', '...')}
                        </div>
                    </div>
                    
                    {f'<div class="suggestions">{suggestions_html}</div>' if suggestions_html else ''}
                </div>
            </div>
        </body>
        </html>
        """


# 全局渲染器实例
renderer: Optional[ImageRenderer] = None


async def get_renderer() -> ImageRenderer:
    """获取渲染器实例"""
    global renderer
    if renderer is None:
        renderer = ImageRenderer()
        await renderer.init()
    return renderer
