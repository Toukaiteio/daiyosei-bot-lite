import httpx
import re
import json
import os
import asyncio
from typing import List, Dict, Optional
import random

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0"
SEARCH_URL = "https://search.bilibili.com/article?keyword=cos&page={page}"
ARTICLE_BASE_URL = "https://www.bilibili.com/read/cv{id}?from=search"
REFERER = "https://search.bilibili.com/article?keyword=cos"

class BilibiliCos:
    def __init__(self, db):
        self.db = db
        self.client = httpx.AsyncClient(headers={"User-Agent": UA}, timeout=10.0)
        self.image_dir = "data/cos_images"
        os.makedirs(self.image_dir, exist_ok=True)

    async def close(self):
        await self.client.aclose()

    async def fetch_search_results(self, page: int = 1) -> List[Dict]:
        """抓取并解析搜索结果页"""
        url = SEARCH_URL.format(page=page)
        try:
            resp = await self.client.get(url, follow_redirects=True)
            resp.raise_for_status()
            html = resp.text
            
            # 查找 searchTypeResponse:{
            match_start = html.find('searchTypeResponse:{')
            if match_start == -1:
                match_start = html.find('"searchTypeResponse":{')
            
            if match_start != -1:
                # 提取平衡括号的对象块
                obj_str = self._get_balanced_obj(html, match_start + html[match_start:].find('{'))
                if obj_str:
                    # 尝试解析 JSON (包含修复逻辑)
                    data = self._parse_relaxed_json(obj_str)
                    if data:
                        inner = data.get('searchTypeResponse', data)
                        result = inner.get('result', [])
                        
                        items = []
                        for item in result:
                            iid = item.get('id')
                            title = item.get('title', '')
                            if iid and title:
                                # 移除 HTML 标签
                                title = re.sub(r'<.*?>', '', title)
                                items.append({"id": int(iid), "title": title})
                        return items

            # 保底方案：由于正则解析可能失败，使用更精确的 regex 匹配每个 result 项
            results = []
            id_title_pattern = re.compile(r'id:\s*(\d+).*?title:\s*"(.*?)"', re.DOTALL)
            std_id_title_pattern = re.compile(r'"id":\s*(\d+).*?"title":\s*"(.*?)"', re.DOTALL)
            
            result_block_match = re.search(r'result:\s*\[(.*?)\]\s*\}\s*\}', html, re.DOTALL)
            if result_block_match:
                block_content = result_block_match.group(1)
                for m in id_title_pattern.finditer(block_content):
                    title = m.group(2).encode('utf-8').decode('unicode_escape')
                    title = re.sub(r'<.*?>', '', title)
                    results.append({"id": int(m.group(1)), "title": title})
            
            if not results:
                # 尝试标准 JSON 匹配
                for m in std_id_title_pattern.finditer(html):
                    title = m.group(2).encode('utf-8').decode('unicode_escape')
                    title = re.sub(r'<.*?>', '', title)
                    results.append({"id": int(m.group(1)), "title": title})

            if not results:
                print(f"[BilibiliCos] Warning: No results parsed from page {page}.")
                # 检查页面标题，看是否被风控
                title_match = re.search(r'<title>(.*?)</title>', html)
                page_title = title_match.group(1) if title_match else "No Title"
                print(f"[BilibiliCos] Page Title: {page_title}")
                print(f"[BilibiliCos] HTML snippet (first 500 chars): {html[:500]}...")
                
                if "验证码" in html or "访问频繁" in html or "Security" in html:
                    print("[BilibiliCos] Detected anti-bot page.")

            return results

        except Exception as e:
            print(f"Fetch search results error: {e}")
            return []

    def _get_balanced_obj(self, text, start_idx):
        count = 0
        found_first = False
        for i in range(start_idx, len(text)):
            if text[i] == '{':
                count += 1
                found_first = True
            elif text[i] == '}':
                count -= 1
                if found_first and count == 0:
                    return text[start_idx:i+1]
        return None

    def _parse_relaxed_json(self, s):
        """尝试解析不规范的 JSON (B站页面 JS 对象)"""
        try:
            # 1. 给未加引号的键加引号
            s = re.sub(r'([\{\,])\s*(\w+)\s*:', r'\1"\2":', s)
            # 2. 处理简单的变量 (占位符)
            def fix_vars(m):
                val = m.group(1)
                if val.lower() in ['true', 'false', 'null']:
                    return f':{val}'
                return f':"{val}"'
            s = re.sub(r':\s*([a-zA-Z_]\w*)', fix_vars, s)
            # 3. 移除尾随逗号
            s = re.sub(r',\s*([\}\]])', r'\1', s)
            return json.loads(s)
        except:
            return None

    async def get_article_images(self, article_id: int) -> List[str]:
        """获取文章页面的所有 COS 图片地址"""
        url = ARTICLE_BASE_URL.format(id=article_id)
        headers = {
            "User-Agent": UA,
            "Referer": REFERER
        }
        try:
            # 开启跟随跳转
            resp = await self.client.get(url, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            final_url = str(resp.url)
            html = resp.text
            
            img_urls = []
            
            # 使用多种模式进行匹配
            # 1. Opus 页面结构 (动态/图文)
            if "/opus/" in final_url:
                # 匹配动态插图
                pattern = re.compile(r'class="bili-dyn-pic__img">.*?src="(.*?)"', re.DOTALL)
                matches = pattern.findall(html)
            
            # 2. CV 专栏页面结构
            else:
                pattern = re.compile(r'<div class="bili-dyn-pic__img"><div class="b-img sleepy"><img src="(.*?)"', re.DOTALL)
                matches = pattern.findall(html)
            
            # 3. 如果上述模式没找到，使用通用匹配寻找典型的 B站专栏图片路径
            if not matches:
                # 寻找典型的 B站专栏/动态图片路径 (//iX.hdslb.com/bfs/article/...)
                matches = re.findall(r'//i\d\.hdslb\.com/bfs/article/.*?\.(?:jpg|png|webp)(?:@\d+w)?', html)
            
            for src in matches:
                # 补全协议
                if src.startswith("//"):
                    src = "https:" + src
                # 移除 @ 后缀
                if "@" in src:
                    src = src.split("@")[0]
                
                # 去重并过滤掉一些可能的非图片项
                if src not in img_urls and src.endswith(('.jpg', '.png', '.webp', '.jpeg')):
                    img_urls.append(src)
            
            return img_urls
        except Exception as e:
            print(f"Fetch article images error: {article_id}, {e}")
            return []

    async def download_image(self, url: str, article_id: int) -> Optional[str]:
        """下载图片并记录到数据库"""
        # 检查是否已下载
        record = await self.db.get_cos_image(url)
        if record and record.get('downloaded') and record.get('local_path') and os.path.exists(record.get('local_path')):
            print(f"[BilibiliCos] Image found in cache: {record.get('local_path')}")
            return record.get('local_path')
        
        # 准备路径 (使用 MD5 保证文件名跨会话一致)
        import hashlib
        ext = url.split('.')[-1] if '.' in url else 'jpg'
        if len(ext) > 5: ext = 'jpg'
        
        # 移除 URL 查询参数再计算 hash，避免参数变化导致重复下载
        clean_url = url.split('?')[0]
        url_hash = hashlib.md5(clean_url.encode('utf-8')).hexdigest()
        filename = f"{article_id}_{url_hash}.{ext}"
        local_path = os.path.join(self.image_dir, filename)
        
        # 双重检查：如果文件已存在但数据库没记录（可能数据库重置了）
        if os.path.exists(local_path):
             print(f"[BilibiliCos] File exists but DB missing, registering: {local_path}")
             await self.db.add_cos_image(url, article_id, local_path, 1)
             return local_path

        try:
            # 下载图片时携带 UA 和 Referer
            # UA 已经在 __init__ 的 self.client 默认 headers 中
            headers = {"Referer": REFERER}
            resp = await self.client.get(url, headers=headers, timeout=30.0)
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                f.write(resp.content)
            
            await self.db.add_cos_image(url, article_id, local_path, 1)
            print(f"[BilibiliCos] Downloaded new image: {local_path}")
            return local_path
        except Exception as e:
            print(f"Download image error: {url}, {e}")
            return None


    async def get_new_article_for_group(self, group_id: int, start_page: int = 1) -> Optional[Dict]:
        """为特定群组获取一个全新的 COS 文章"""
        # 策略1：优先查看库存（数据库中有且该群未发送过的）
        # 这样即使爬虫挂了，只要有库存也能正常工作
        article = await self.db.get_unsent_cos_article(group_id)
        if article:
            print(f"[BilibiliCos] Found unsent article from cache for group {group_id}: {article['id']}")
            return article

        print(f"[BilibiliCos] No cached article found for group {group_id}, starting scraper...")

        page = start_page
        max_pages = 10  # 限制最大翻页数，避免无限循环
        
        while page <= max_pages:
            print(f"[BilibiliCos] Fetching page {page} for group {group_id}...")
            results = await self.fetch_search_results(page)
            if not results:
                print(f"[BilibiliCos] No results on page {page}, stopping scrape.")
                # 即使当前页没结果，也不直接返回 None，最好 break 出去看看是不是有其他逻辑
                break
            
            # 将本页所有文章存入数据库（如果不存在）
            new_articles_count = 0
            for item in results:
                article_id = item['id']
                title = item['title']
                link = ARTICLE_BASE_URL.format(id=article_id)
                
                if not await self.db.is_cos_article_saved(article_id):
                    await self.db.add_cos_article(article_id, title, link)
                    new_articles_count += 1
                    print(f"[BilibiliCos] Saved new article: {article_id} - {title[:30]}...")
            
            print(f"[BilibiliCos] Page {page}: {new_articles_count} new articles saved.")
            
            # 存入新数据后，再次检查是否有适合该群的文章
            article = await self.db.get_unsent_cos_article(group_id)
            if article:
                print(f"[BilibiliCos] Found unsent article for group {group_id}: {article['id']}")
                return article
            
            # 如果没找到，继续尝试下一页
            page += 1
            await asyncio.sleep(random.uniform(1.0, 2.0))  # 休息机制
        
        print(f"[BilibiliCos] Reached max pages ({max_pages}) or no more results for group {group_id}.")
        return None
