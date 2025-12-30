"""
表情包偷取工具
Project Turing: 拟人化群聊智能体 (琪露诺)
"""
import os
import hashlib
import httpx
from datetime import datetime
from typing import Optional, Literal

MemeCategory = Literal["happy", "negative", "positive", "sad"]

class MemeStealer:
    """表情包偷取工具"""
    
    def __init__(self, base_dir: str = "assets/memes"):
        self.base_dir = base_dir
        # 确保所有分类目录存在
        for category in ["happy", "negative", "positive", "sad"]:
            category_dir = os.path.join(base_dir, category)
            os.makedirs(category_dir, exist_ok=True)
    
    async def steal_meme(
        self, 
        image_url: str, 
        category: MemeCategory,
        description: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        偷取（保存）表情包到指定分类
        
        Args:
            image_url: 图片URL
            category: 表情包分类 (happy/negative/positive/sad)
            description: 可选的描述说明（会保存到同名.txt文件）
        
        Returns:
            (成功与否, 消息)
        """
        try:
            print(f"[MemeStealer] 开始偷取表情包: {image_url[:50]}... -> {category}")
            
            # 1. 下载图片
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(image_url)
                response.raise_for_status()
                image_data = response.content
            
            # 2. 生成文件名（使用URL的hash + 时间戳）
            url_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 检测图片格式
            content_type = response.headers.get('content-type', '').lower()
            if 'gif' in content_type:
                ext = '.gif'
            elif 'png' in content_type:
                ext = '.png'
            elif 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'webp' in content_type:
                ext = '.webp'
            else:
                # 默认使用 .jpg
                ext = '.jpg'
            
            filename = f"meme_{timestamp}_{url_hash}{ext}"
            
            # 3. 保存到对应分类目录
            category_dir = os.path.join(self.base_dir, category)
            image_path = os.path.join(category_dir, filename)
            
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            print(f"[MemeStealer] 表情包已保存: {image_path}")
            
            # 4. 如果有描述，保存描述文件
            if description:
                desc_path = os.path.join(category_dir, f"{filename}.txt")
                with open(desc_path, 'w', encoding='utf-8') as f:
                    f.write(f"URL: {image_url}\n")
                    f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"分类: {category}\n")
                    f.write(f"描述: {description}\n")
                print(f"[MemeStealer] 描述已保存: {desc_path}")
            
            return True, f"表情包已成功偷取到 {category} 分类！"
            
        except httpx.HTTPError as e:
            error_msg = f"下载图片失败: {str(e)}"
            print(f"[MemeStealer] {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"偷取失败: {str(e)}"
            print(f"[MemeStealer] {error_msg}")
            import traceback
            traceback.print_exc()
            return False, error_msg
    
    def get_stats(self) -> dict:
        """获取各分类的表情包数量统计"""
        stats = {}
        for category in ["happy", "negative", "positive", "sad"]:
            category_dir = os.path.join(self.base_dir, category)
            if os.path.exists(category_dir):
                files = [f for f in os.listdir(category_dir) 
                        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))]
                stats[category] = len(files)
            else:
                stats[category] = 0
        return stats

# 全局实例
meme_stealer = MemeStealer()
