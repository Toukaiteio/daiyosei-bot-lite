from .base import BaseTool, register_tool
from ...utils.browser import fetch_page_content
import logging

logger = logging.getLogger("Tools.FetchPage")

@register_tool("fetch_page")
class FetchPageTool(BaseTool):
    description = "抓取并读取网页内容"
    
    async def __call__(self, url: str, **kwargs):
        logger.info(f"[Tool] Fetching page: {url}")
        return await fetch_page_content(url)
