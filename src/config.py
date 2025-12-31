"""
配置文件 - 包含所有系统配置项
"""
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
import os
import json
import logging
from dotenv import load_dotenv

# 尝试加载 .env 文件
load_dotenv()

logger = logging.getLogger("Config")

@dataclass
class ModelProvider:
    """大模型提供商配置"""
    provider: str  # "openai", "gemini"
    base_url: str
    api_keys: List[str]
    model: str
    is_vision: bool = False
    is_search: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelProvider":
        keys = data.get("api_keys", [])
        # 兼容旧格式或字符串格式
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split(",") if k.strip()]
        
        return cls(
            provider=data.get("provider", "openai"),
            base_url=data.get("base_url", ""),
            api_keys=keys,
            model=data.get("model", ""),
            is_vision=data.get("is_vision_capable", False),
            is_search=data.get("is_web_search_capable", False)
        )

def _load_providers() -> List[ModelProvider]:
    """从环境变量加载并解析 LLM_PROVIDERS"""
    raw_config = os.getenv("LLM_PROVIDERS", "[]")
    providers = []
    try:
        data = json.loads(raw_config)
        for item in data:
            try:
                providers.append(ModelProvider.from_dict(item))
            except Exception as e:
                logger.error(f"Failed to parse provider config item: {item}, error: {e}")
    except json.JSONDecodeError:
        logger.error(f"Failed to parse LLM_PROVIDERS JSON: {raw_config}")
    
    return providers

# 加载一次
ALL_PROVIDERS = _load_providers()

@dataclass
class LLMConfig:
    """LLM 大模型配置"""
    # 文本生成候选列表 (默认所有配置的模型都作为文本生成候选)
    text_candidates: List[ModelProvider] = field(default_factory=lambda: ALL_PROVIDERS)
    
    max_tokens: int = 2048
    temperature: float = 0.8
    
    # Backward compatibility properties (optional, mainly for type checkers or legacy access)
    @property
    def base_url(self) -> str:
        return self.text_candidates[0].base_url if self.text_candidates else ""
    @property
    def api_key(self) -> str:
        return self.text_candidates[0].api_keys[0] if self.text_candidates and self.text_candidates[0].api_keys else ""
    @property
    def model(self) -> str:
        return self.text_candidates[0].model if self.text_candidates else ""


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
    # 自动筛选具有视觉能力的模型
    candidates: List[ModelProvider] = field(default_factory=lambda: [p for p in ALL_PROVIDERS if p.is_vision])

@dataclass
class SearchConfig:
    """搜索模型配置"""
    # 自动筛选具有搜索能力的模型
    candidates: List[ModelProvider] = field(default_factory=lambda: [p for p in ALL_PROVIDERS if p.is_search])


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
