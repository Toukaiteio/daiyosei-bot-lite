import logging
import asyncio
import requests
import re
import hashlib
import base64
import random
from PIL import Image
from io import BytesIO
from .base import BaseTool, register_tool
from ...config import config, ModelProvider
from openai import AsyncOpenAI

logger = logging.getLogger("Tools.LookAtImage")

@register_tool("look_at_image")
class LookAtImageTool(BaseTool):
    description = "视觉工具：查看图片内容 (带缓存)"

    async def _calculate_image_hash(self, image_bytes: bytes) -> str:
        return hashlib.md5(image_bytes).hexdigest()

    async def __call__(self, image_url: str = "", **kwargs):
        service = kwargs.get("service")
        if not service:
            return "Error: LLMService instance not provided."

        # 如果没有提供URL，委托 SkillAgent 查找
        if not image_url and hasattr(service, 'skill_agent') and service.skill_agent:
            from ..llm_service import active_group_id, current_chat_context
            logger.info("[Vision] No Image URL provided, delegating to SkillAgent...")
            group_id = active_group_id.get()
            context = current_chat_context.get()
            # 取最近 20 条消息作为上下文
            recent_msgs = context[-20:] if context else []
            
            task_desc = "用户想要看图，但没有提供 specific URL。请分析 Context 找到最近一张用户发送的图片(Image Message)，并提取其 URL (通常在[图片:...]或[IMG:...]标签中)。找到后，请调用 look_at_image 工具并传入正确的 URL。如果找不到图片，请直接告知用户'没看到图片诶'。"
            
            result = await service.skill_agent.execute_task(
                task_desc, 
                context_info={
                    "group_id": group_id, 
                    "chat_history_snippet": [
                        {"role": m.get("role"), "content": m.get("content")} 
                        for m in recent_msgs
                    ]
                }
            )
            return f"[Delegated to SkillAgent]: {result}"

        if not image_url:
            return "Error: No image URL provided and SkillAgent is not available."

        try:
            # Download image
            logger.info(f"[Vision] Request to look at image: {image_url}")
            
            # 强化 URL 清洗
            url_match = re.search(r'https?://[^\s\]]+', image_url)
            if url_match:
                image_url = url_match.group(0)
                logger.info(f"[Vision] Regex matched URL: {image_url}")
            else:
                image_url = image_url.strip().strip('[]').replace('图片:', '').strip()
                logger.warning(f"[Vision] Regex failed, manual clean result: {image_url}")

            logger.info(f"[Vision] Final downloading URL: {image_url}...")
            
            def download():
                # 添加请求头模拟浏览器，避免被 QQ 图片服务器拒绝
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://qun.qq.com/',
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Connection': 'keep-alive'
                }
                resp = requests.get(image_url, headers=headers, timeout=60, allow_redirects=True)
                resp.raise_for_status()
                return resp.content
            
            loop = asyncio.get_running_loop()
            img_bytes = await loop.run_in_executor(None, download)
            
            # Check Cache
            img_hash = ""
            if hasattr(service, 'db') and service.db:
                img_hash = await self._calculate_image_hash(img_bytes)
                cached = await service.db.get_image_description(img_hash)
                if cached:
                    logger.info(f"[Vision] Cache hit for {img_hash}")
                    return f"[图片内容(已缓存)]: {cached}"
            
            description = ""
            candidates = config.vision.candidates
            
            if not candidates:
                return "[Vision Failed] 配置中没有启用任何视觉模型 (is_vision_capable=true)"

            # Detect MIME type and Prepare Base64
            try:
                pil_img = Image.open(BytesIO(img_bytes))
                fmt = pil_img.format.lower() if pil_img.format else "jpeg"
                mime_type = f"image/{fmt}"
            except Exception:
                mime_type = "image/jpeg" # Fallback

            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
            img_data_url = f"data:{mime_type};base64,{img_b64}"

            # Iterate candidates
            for candidate in candidates:
                logger.info(f"[Vision] Trying {candidate.model} ({candidate.provider})...")
                
                # Iterate keys (Load balancing / Retry)
                keys = candidate.api_keys
                if not keys: continue
                
                # Shuffle keys for this attempt
                shuffled_keys = keys.copy()
                random.shuffle(shuffled_keys)
                
                for api_key in shuffled_keys:
                    try:
                        # Special handling for Native Gemini (if no base_url provided or explicit google provider request without openai url)
                        if candidate.provider == "gemini" and "openai" not in candidate.base_url and not candidate.base_url:
                            logger.info("[Vision] Using Native Gemini Client...")
                            from google import genai
                            client = genai.Client(api_key=api_key)
                            # Convert bytes to PIL Image
                            image = Image.open(BytesIO(img_bytes))
                            response = await client.aio.models.generate_content(
                                model=candidate.model,
                                contents=[image, "Describe this image in detail but briefly. Focus on anime style features if present."]
                            )
                            description = response.text
                        else:
                            # Use OpenAI Compatible Client (for OpenAI, ModelScope, and Gemini-OpenAI)
                            logger.info("[Vision] Using OpenAI Compatible Client...")
                            client = AsyncOpenAI(
                                base_url=candidate.base_url,
                                api_key=api_key,
                            )
                            response = await client.chat.completions.create(
                                model=candidate.model,
                                messages=[
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": "Describe this image in detail but briefly. Focus on anime style features if present."},
                                            {
                                                "type": "image_url",
                                                "image_url": {"url": img_data_url},
                                            },
                                        ],
                                    }
                                ],
                                max_tokens=512,
                            )
                            description = response.choices[0].message.content

                        if description:
                            break # Key worked
                            
                    except Exception as e:
                        logger.warning(f"[Vision] Failed with key {api_key[:4]}...: {e}")
                        continue # Try next key
                
                if description:
                    break # Candidate worked

            if not description:
                logger.error("[Vision] All models/keys exhausted")
                return "[Vision Failed] 找不到任何能看图的模型..."
                
            # Save to Cache
            if hasattr(service, 'db') and service.db and img_hash:
                await service.db.set_image_description(img_hash, description)
            
            # 强制指令：包裹结果，强迫模型重写
            return f"""
[视觉工具结果 (⚠️ 这是你看到的画面，请用琪露诺的口吻评价这张图，禁止直接复读描述！)]
{description}
"""
            
        except Exception as e:
            logger.error(f"[Vision] Error: {e}")
            return f"[加载图片失败: {e}]"
