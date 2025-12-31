from typing import Callable, Any, Dict
import inspect
import logging

logger = logging.getLogger("Tools")

class BaseTool:
    """所有工具的基类"""
    name: str = "base_tool"
    description: str = "Base tool description"
    
    async def __call__(self, *args, **kwargs) -> Any:
        raise NotImplementedError

# 工具注册表
TOOL_REGISTRY: Dict[str, BaseTool] = {}

def register_tool(name: str):
    """工具注册装饰器"""
    def decorator(cls):
        if not issubclass(cls, BaseTool):
            raise TypeError(f"Tool {cls.__name__} must inherit from BaseTool")
        
        instance = cls()
        instance.name = name
        TOOL_REGISTRY[name] = instance
        logger.info(f"[ToolRegistry] Registered tool: {name}")
        return cls
    return decorator
