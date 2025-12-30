from playwright.async_api import async_playwright
import asyncio

async def fetch_page_content(url: str, timeout: int = 30000) -> str:
    """
    使用 Playwright 获取网页内容（支持动态渲染）
    返回网页的 innerText，若失败返回错误信息
    """
    try:
        async with async_playwright() as p:
            # 启动浏览器，headless=True 表示无头模式
            browser = await p.chromium.launch(headless=True)
            # 创建新页面
            # 设置 user_agent 防止被部分网站拦截
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = await context.new_page()
            
            try:
                # 访问 URL
                await page.goto(url, wait_until="networkidle", timeout=timeout)
                
                # 获取标题和正文
                title = await page.title()
                # 使用 evaluate 获取主要文本内容，避免获取过多隐藏元素的文字
                # 这里简单获取 body.innerText作为参考，也可以做更多清洗
                content = await page.evaluate("() => document.body.innerText")
                
                # 简单的长度限制
                if len(content) > 10000:
                    content = content[:10000] + "\n[内容过长已截断...]"
                    
                result = f"Title: {title}\nURL: {url}\n\nContent:\n{content}"
                return result
                
            except Exception as e:
                return f"Error loading page {url}: {str(e)}"
            finally:
                await browser.close()
    except Exception as e:
        return f"Browser init failed: {str(e)}"
