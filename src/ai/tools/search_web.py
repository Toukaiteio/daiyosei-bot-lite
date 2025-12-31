from .base import BaseTool, register_tool
from ...utils.browser import fetch_page_content
import urllib.parse
import logging
import random
from ...config import config, ModelProvider
from openai import AsyncOpenAI

logger = logging.getLogger("Tools.SearchWeb")

@register_tool("search_web")
class SearchWebTool(BaseTool):
    description = "在互联网上搜索信息"
    
    async def __call__(self, query: str, **kwargs):
        logger.info(f"[Tool] Searching web: {query}")
        
        candidates = config.search.candidates
        if not candidates:
            # Fallback to simple link construction if no AI search available
            logger.warning("[Search] No search-capable LLM found. Returning Google Link.")
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            return f"Search Capability Unavailable. You can check this link: {url}"

        result = ""

        for candidate in candidates:
            logger.info(f"[Search] Trying {candidate.model} ({candidate.provider})...")
            
            keys = candidate.api_keys
            if not keys: continue
            shuffled_keys = keys.copy()
            random.shuffle(shuffled_keys)
            
            for api_key in shuffled_keys:
                try:
                    # Strategy 1: Gemini Native Search
                    if candidate.provider == "gemini":
                        logger.info("[Search] Using Gemini Native Search...")
                        from google import genai
                        from google.genai import types
                        
                        client = genai.Client(api_key=api_key)
                        
                        # Use Google Search Tool
                        # Note: Syntax varies by SDK version. Trying common one.
                        response = await client.aio.models.generate_content(
                            model=candidate.model,
                            contents=f"Please search the web for information about: {query}. Summarize the key findings detailedly.",
                            config=types.GenerateContentConfig(
                                tools=[types.Tool(google_search=types.GoogleSearch())]
                            )
                        )
                        # Gemini response usually contains the answer directly when search is used
                        result = response.text
                        
                    # Strategy 2: OpenAI Compatible (Perplexity etc.)
                    else:
                        logger.info("[Search] Using OpenAI Compatible Search (e.g. Perplexity)...")
                        client = AsyncOpenAI(
                            base_url=candidate.base_url,
                            api_key=api_key,
                        )
                        response = await client.chat.completions.create(
                            model=candidate.model,
                            messages=[
                                {"role": "system", "content": "You are a helpful search assistant. You have access to the internet. Please search for the user's query and provide a detailed summary."},
                                {"role": "user", "content": query}
                            ]
                        )
                        result = response.choices[0].message.content
                        
                    if result:
                        break # Key worked
                        
                except Exception as e:
                    logger.warning(f"[Search] Failed with key {api_key[:4]}...: {e}")
                    continue
            
            if result:
                break # Candidate worked

        if not result:
            return "[Search Failed] 找不到能联网搜索的模型，或所有尝试都失败了。"

        return f"""
[搜索结果]
{result}
"""