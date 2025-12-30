"""
流控模块 - 多级漏桶策略实现
实现全局限流、群组限流、用户冷却
"""
import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple
from ..config import config


class ThrottleResult(Enum):
    """流控结果"""
    ALLOWED = "ALLOWED"                    # 允许通过
    GLOBAL_LIMIT = "GLOBAL_LIMIT"          # 全局限流
    GROUP_LIMIT = "GROUP_LIMIT"            # 群组限流
    USER_COOLDOWN = "USER_COOLDOWN"        # 用户冷却中
    STATIC_COMMAND = "STATIC_COMMAND"      # 静态指令（不消耗AI）


@dataclass
class ThrottleInfo:
    """限流信息"""
    result: ThrottleResult
    wait_time: float = 0.0  # 需要等待的时间（秒）
    message: str = ""


class TokenBucket:
    """令牌桶实现"""
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Args:
            capacity: 桶容量
            refill_rate: 每秒填充速率
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> Tuple[bool, float]:
        """
        尝试获取令牌
        Returns: (是否成功, 需等待时间)
        """
        async with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, 0.0
            
            # 计算需要等待的时间
            needed = tokens - self.tokens
            wait_time = needed / self.refill_rate
            return False, wait_time
    
    def _refill(self):
        """填充令牌"""
        now = time.time()
        elapsed = now - self.last_refill
        refill_amount = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + refill_amount)
        self.last_refill = now


class RateLimiter:
    """
    多级流控器
    
    - 全局限流：保护 LLM API Key
    - 群组限流：防止单群耗尽资源
    - 用户冷却：防止单人刷屏
    """
    
    # 静态指令列表（不消耗AI配额）
    STATIC_COMMANDS = {
        "查看背包", "背包", "物品",
        "查看属性", "属性", "状态",
        "签到", "领取", "礼包",
        "商店", "购买", "出售",
        "帮助", "help", "菜单",
    }
    
    def __init__(self):
        self.config = config.rate_limit
        
        # 全局令牌桶 (每分钟 global_rpm 次)
        self._global_bucket = TokenBucket(
            capacity=self.config.global_rpm,
            refill_rate=self.config.global_rpm / 60.0
        )
        
        # 群组限流 {group_id: TokenBucket}
        self._group_buckets: Dict[int, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                capacity=self.config.group_rpm,
                refill_rate=self.config.group_rpm / 60.0
            )
        )
        
        # 用户上次操作时间 {(user_id, group_id): timestamp}
        self._user_last_action: Dict[Tuple[int, int], float] = {}
        
        self._lock = asyncio.Lock()
    
    def is_static_command(self, command: str) -> bool:
        """判断是否为静态指令"""
        command_lower = command.lower().strip()
        for static_cmd in self.STATIC_COMMANDS:
            if command_lower.startswith(static_cmd):
                return True
        return False
    
    async def check(self, user_id: int, group_id: int, command: str) -> ThrottleInfo:
        """
        检查是否允许执行指令
        
        Args:
            user_id: 用户ID
            group_id: 群组ID
            command: 指令内容
            
        Returns:
            ThrottleInfo: 限流信息
        """
        # 1. 检查是否为静态指令
        if self.is_static_command(command):
            return ThrottleInfo(
                result=ThrottleResult.STATIC_COMMAND,
                message="静态指令，无需AI处理"
            )
        
        async with self._lock:
            now = time.time()
            user_key = (user_id, group_id)
            
            # 2. 用户冷却检查
            last_action = self._user_last_action.get(user_key, 0)
            elapsed = now - last_action
            if elapsed < self.config.user_cooldown:
                wait = self.config.user_cooldown - elapsed
                return ThrottleInfo(
                    result=ThrottleResult.USER_COOLDOWN,
                    wait_time=wait,
                    message=f"请稍等 {wait:.1f} 秒后再试"
                )
            
            # 3. 群组限流检查
            group_bucket = self._group_buckets[group_id]
            success, wait_time = await group_bucket.acquire()
            if not success:
                return ThrottleInfo(
                    result=ThrottleResult.GROUP_LIMIT,
                    wait_time=wait_time,
                    message=f"本群请求过于频繁，请等待 {wait_time:.1f} 秒"
                )
            
            # 4. 全局限流检查
            success, wait_time = await self._global_bucket.acquire()
            if not success:
                return ThrottleInfo(
                    result=ThrottleResult.GLOBAL_LIMIT,
                    wait_time=wait_time,
                    message=f"系统繁忙，请稍后再试"
                )
            
            # 更新用户最后操作时间
            self._user_last_action[user_key] = now
            
            return ThrottleInfo(
                result=ThrottleResult.ALLOWED,
                message="通过"
            )
    
    def get_stats(self) -> dict:
        """获取流控统计信息"""
        return {
            "global_tokens": self._global_bucket.tokens,
            "global_capacity": self._global_bucket.capacity,
            "active_groups": len(self._group_buckets),
            "active_users": len(self._user_last_action),
        }


# 全局流控器实例
rate_limiter = RateLimiter()
