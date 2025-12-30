"""
配置文件 - 包含所有系统配置项
"""
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import os
from dotenv import load_dotenv

# 尝试加载 .env 文件
load_dotenv()

@dataclass
class LLMConfig:
    """LLM 大模型配置"""
    base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key: str = os.getenv("LLM_API_KEY", "")
    model: str = os.getenv("LLM_MODEL", "gpt-4o")
    
    max_tokens: int = 2048
    temperature: float = 0.8

    # Fallback 1
    fallback_base_url: str = os.getenv("LLM_FALLBACK_BASE_URL", "")
    fallback_api_key: str = os.getenv("LLM_FALLBACK_API_KEY", "")
    fallback_model: str = os.getenv("LLM_FALLBACK_MODEL", "")
    
    # Fallback 2
    fallback2_base_url: str = os.getenv("LLM_FALLBACK2_BASE_URL", "")
    fallback2_api_key: str = os.getenv("LLM_FALLBACK2_API_KEY", "")
    fallback2_model: str = os.getenv("LLM_FALLBACK2_MODEL", "")


@dataclass
class RateLimitConfig:
    """流控配置"""
    global_rpm: int = 60
    group_rpm: int = 60
    user_cooldown: float = 1.5


@dataclass
class WebSocketConfig:
    """WebSocket 服务器配置"""
    host: str = os.getenv("WS_HOST", "127.0.0.1")
    port: int = int(os.getenv("WS_PORT", "6199"))
    access_token: Optional[str] = os.getenv("WS_TOKEN")


@dataclass
class DatabaseConfig:
    """数据库配置"""
    db_path: str = os.getenv("DB_PATH", "data/game.db")


@dataclass
class RenderConfig:
    """渲染配置"""
    templates_dir: str = "templates"
    output_dir: str = "data/renders"
    screenshot_width: int = 800
    screenshot_height: int = 600


@dataclass
class BotConfig:
    """机器人信息配置"""
    name: str = os.getenv("BOT_NAME", "琪露诺")
    keywords: Tuple[str, ...] = (
        "琪露诺", "棋露诺", "琦露诺", "Cirno","Ciruno","Chiruno", "⑨", 
        "大妖精", "笨蛋", "baka", "最强", "冰精","qilunuo","宝宝","小九","小9" 
    )
    admin_qq: int = int(os.getenv("ADMIN_QQ", "0"))
    
    use_message_aggregator: bool = True
    aggregator_normal_window: float = 2.0
    aggregator_high_priority_window: float = 1.0
    aggregator_max_window: float = 5.0
    
    private_chat_proactive: bool = True
    friend_request_auto_approve: bool = True
    private_chat_blacklist: Tuple[int, ...] = field(default_factory=tuple)

@dataclass
class VisionConfig:
    """视觉模型配置"""
    ms_base_url: str = os.getenv("MS_BASE_URL", "https://api-inference.modelscope.cn/v1")
    ms_api_key: str = os.getenv("MS_API_KEY", "")
    ms_model: str = os.getenv("MS_MODEL", "Qwen/Qwen2-VL-72B-Instruct")
    
    gemini_keys: List[str] = field(default_factory=lambda: [
        k.strip() for k in os.getenv("GEMINI_KEYS", "").split(",") if k.strip()
    ])

@dataclass
class SearchConfig:
    """搜索模型配置"""
    gemini_keys: List[str] = field(default_factory=lambda: [
        k.strip() for k in os.getenv("GEMINI_KEYS", "").split(",") if k.strip()
    ])


class Config:
    """全局配置类"""
    
    def __init__(self):
        self.llm = LLMConfig()
        self.rate_limit = RateLimitConfig()
        self.websocket = WebSocketConfig()
        self.database = DatabaseConfig()
        self.render = RenderConfig()
        self.bot_info = BotConfig()
        self.vision = VisionConfig()
        self.search = SearchConfig()


# 全局配置实例
config = Config()