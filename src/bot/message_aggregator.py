"""
消息聚合器 - Message Aggregator (增强版)

核心功能：
1. 收集短时间窗口内的所有消息
2. 智能判断是否需要回复
3. 为多个触发者分别构建上下文
4. 避免高并发时的重复回复

场景示例：
A: @bot 你觉得C怎么样？  → 需要回复A，回复中应该提到C
B: @bot 能不能和我说一声晚安  → 需要回复B，说晚安
C: 好久不见 bot,你还记得我是谁吗？ → 需要回复C，回忆关于C的事
D: @B 今晚记得上号  → 无关消息，只是上下文

设计理念：
- 不急于回复每条消息，而是"看完一段对话再发言"
- 识别所有需要回复的对象，分别生成回复
- 无关消息只作为背景上下文
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("MessageAggregator")


class MessagePriority(Enum):
    """消息优先级"""
    CRITICAL = 1    # 直接@bot + 紧急关键词
    HIGH = 2        # 直接@bot 或 回复bot
    MEDIUM = 3      # 包含bot关键词
    LOW = 4         # 普通消息（只作为上下文）
    NONE = 5        # 无需处理


@dataclass
class PendingMessage:
    """待处理消息"""
    message_id: int
    user_id: int
    nickname: str
    content: str
    at_self: bool
    reply_to_bot: bool
    timestamp: float
    priority: MessagePriority
    sender_role: str = "member"
    is_group: bool = True
    raw_data: dict = field(default_factory=dict)


@dataclass
class ReplyTarget:
    """回复目标 - 每个需要回复的用户"""
    user_id: int
    nickname: str
    messages: List[PendingMessage]  # 该用户发送的所有触发消息
    highest_priority: MessagePriority
    
    def get_combined_content(self) -> str:
        """获取该用户的所有消息合并内容"""
        return " | ".join(m.content for m in self.messages)
    
    def get_latest_message(self) -> PendingMessage:
        """获取该用户的最新消息"""
        return self.messages[-1] if self.messages else None


@dataclass
class AggregatedTask:
    """聚合后的处理任务 - 增强版"""
    group_id: int
    reply_targets: List[ReplyTarget]  # 需要回复的目标列表
    context_messages: List[PendingMessage]  # 上下文消息（包括无关消息）
    all_messages: List[PendingMessage]  # 窗口内所有消息（按时间排序）
    aggregated_at: float
    
    @property
    def should_reply(self) -> bool:
        return len(self.reply_targets) > 0
    
    @property
    def total_triggers(self) -> int:
        """触发消息总数"""
        return sum(len(t.messages) for t in self.reply_targets)
    
    @property
    def primary_target(self) -> Optional[ReplyTarget]:
        """主要回复目标（优先级最高的）"""
        if not self.reply_targets:
            return None
        return self.reply_targets[0]
    
    def build_context_for_llm(self) -> List[dict]:
        """
        构建给LLM的上下文
        
        格式：按时间排序的所有消息 + 明确标注哪些需要回复
        """
        context = []
        needs_reply_ids = set()
        
        for target in self.reply_targets:
            for msg in target.messages:
                needs_reply_ids.add(msg.message_id)
        
        for msg in self.all_messages:
            content = msg.content
            # 标注需要回复的消息
            if msg.message_id in needs_reply_ids:
                content = f"[需要回复此消息] {content}"
            
            context.append({
                "sender_name": msg.nickname,
                "sender_id": msg.user_id,
                "content": content,
                "role": "user",
                "timestamp": msg.timestamp
            })
        
        return context


class MessageAggregator:
    """
    消息聚合器 (增强版)
    
    核心逻辑：
    1. 消息到达时放入待处理队列，启动/重置聚合窗口定时器
    2. 如果是高优先级消息（直接@），缩短等待时间
    3. 窗口结束后，分析所有消息，识别每个需要回复的用户
    4. 为每个用户生成独立的回复上下文
    """
    
    # 聚合窗口配置
    NORMAL_WINDOW = 2.0       # 普通消息窗口：2秒
    HIGH_PRIORITY_WINDOW = 1.0  # 高优先级窗口：1秒
    MAX_WINDOW = 5.0          # 最大等待时间：5秒
    
    def __init__(self, bot_id: int = 0):
        self.bot_id = bot_id
        
        # 每个群组的待处理消息 {group_id: [PendingMessage, ...]}
        self._pending_messages: Dict[int, List[PendingMessage]] = defaultdict(list)
        
        # 每个群组的聚合定时器 {group_id: asyncio.Task}
        self._window_timers: Dict[int, asyncio.Task] = {}
        
        # 每个群组的第一条消息时间（用于计算最大等待时间）
        self._first_message_time: Dict[int, float] = {}
        
        # 处理器回调
        self._task_handler: Optional[Callable[[AggregatedTask], Any]] = None
        
        # 关键词列表（用于优先级判断）
        self._keywords: List[str] = ["琪露诺", "⑨", "笨蛋", "冰精", "bot"]
        
        # 运行标志
        self._running = True
    
    def set_bot_id(self, bot_id: int):
        """设置机器人QQ号"""
        self.bot_id = bot_id
    
    def set_keywords(self, keywords: List[str]):
        """设置触发关键词"""
        self._keywords = keywords
    
    def set_task_handler(self, handler: Callable[[AggregatedTask], Any]):
        """设置任务处理器回调"""
        self._task_handler = handler
    
    def evaluate_priority(self, message: PendingMessage) -> MessagePriority:
        """评估消息优先级"""
        # 直接@bot
        if message.at_self:
            # 检查是否有紧急关键词
            urgent_keywords = ["急", "马上", "快", "立刻", "帮我", "救命"]
            if any(k in message.content for k in urgent_keywords):
                return MessagePriority.CRITICAL
            return MessagePriority.HIGH
        
        # 回复bot的消息
        if message.reply_to_bot:
            return MessagePriority.HIGH
        
        # 包含关键词（不区分大小写）
        content_lower = message.content.lower()
        if any(k.lower() in content_lower for k in self._keywords):
            return MessagePriority.MEDIUM
        
        # 普通消息（只作为上下文，不触发回复）
        return MessagePriority.LOW
    
    async def add_message(
        self,
        group_id: int,
        message_id: int,
        user_id: int,
        nickname: str,
        content: str,
        at_self: bool,
        reply_to_bot: bool = False,
        sender_role: str = "member",
        is_group: bool = True,
        raw_data: dict = None
    ):
        """
        添加消息到聚合队列
        
        这是外部调用的主入口
        """
        # 过滤自己的消息
        if user_id == self.bot_id:
            return
        
        now = time.time()
        
        # 创建消息对象
        msg = PendingMessage(
            message_id=message_id,
            user_id=user_id,
            nickname=nickname,
            content=content,
            at_self=at_self,
            reply_to_bot=reply_to_bot,
            timestamp=now,
            priority=MessagePriority.NONE,
            sender_role=sender_role,
            is_group=is_group,
            raw_data=raw_data or {}
        )
        
        # 评估优先级
        msg.priority = self.evaluate_priority(msg)
        
        # 加入待处理队列
        self._pending_messages[group_id].append(msg)
        
        # 记录第一条消息时间
        if group_id not in self._first_message_time:
            self._first_message_time[group_id] = now
        
        # 计算窗口时间
        window_duration = self._calculate_window_duration(group_id, msg.priority)
        
        # 重置/启动定时器
        await self._reset_window_timer(group_id, window_duration)
        
        priority_emoji = {
            MessagePriority.CRITICAL: "🔴",
            MessagePriority.HIGH: "🟠",
            MessagePriority.MEDIUM: "🟡",
            MessagePriority.LOW: "⚪",
        }.get(msg.priority, "⚫")
        
        logger.info(f"[Aggregator] Group {group_id}: {priority_emoji} {nickname}: '{content[:30]}...' (priority={msg.priority.name})")
    
    def _calculate_window_duration(self, group_id: int, new_priority: MessagePriority) -> float:
        """计算聚合窗口时长"""
        # 已经等待的时间
        first_time = self._first_message_time.get(group_id, time.time())
        elapsed = time.time() - first_time
        
        # 剩余最大等待时间
        remaining_max = max(0, self.MAX_WINDOW - elapsed)
        
        # 根据优先级选择窗口
        if new_priority in [MessagePriority.CRITICAL, MessagePriority.HIGH]:
            base_window = self.HIGH_PRIORITY_WINDOW
        else:
            base_window = self.NORMAL_WINDOW
        
        # 返回较小值
        return min(base_window, remaining_max)
    
    async def _reset_window_timer(self, group_id: int, duration: float):
        """重置聚合窗口定时器"""
        # 取消现有定时器
        if group_id in self._window_timers:
            self._window_timers[group_id].cancel()
            try:
                await self._window_timers[group_id]
            except asyncio.CancelledError:
                pass
        
        # 创建新定时器
        self._window_timers[group_id] = asyncio.create_task(
            self._window_timeout(group_id, duration)
        )
    
    async def _window_timeout(self, group_id: int, duration: float):
        """窗口超时，开始聚合处理"""
        try:
            await asyncio.sleep(duration)
            await self._process_aggregated_messages(group_id)
        except asyncio.CancelledError:
            pass  # 定时器被取消是正常的
    
    async def _process_aggregated_messages(self, group_id: int):
        """处理聚合后的消息 - 增强版"""
        # 取出所有待处理消息
        messages = self._pending_messages.pop(group_id, [])
        self._first_message_time.pop(group_id, None)
        self._window_timers.pop(group_id, None)
        
        if not messages:
            return
        
        logger.info(f"[Aggregator] Group {group_id}: Processing {len(messages)} aggregated messages")
        
        # 按用户分组触发消息
        user_triggers: Dict[int, List[PendingMessage]] = defaultdict(list)
        context_messages: List[PendingMessage] = []
        
        for msg in messages:
            if msg.priority in [MessagePriority.CRITICAL, MessagePriority.HIGH, MessagePriority.MEDIUM]:
                # 需要回复的消息，按用户分组
                user_triggers[msg.user_id].append(msg)
            else:
                # 无关消息，只作为上下文
                context_messages.append(msg)
        
        # 如果没有触发消息，不回复
        if not user_triggers:
            logger.info(f"[Aggregator] Group {group_id}: No trigger messages, skipping reply")
            return
        
        # 构建回复目标列表
        reply_targets: List[ReplyTarget] = []
        
        for user_id, user_msgs in user_triggers.items():
            # 找出该用户的最高优先级
            highest = min(m.priority for m in user_msgs)
            nickname = user_msgs[0].nickname
            
            target = ReplyTarget(
                user_id=user_id,
                nickname=nickname,
                messages=sorted(user_msgs, key=lambda m: m.timestamp),
                highest_priority=highest
            )
            reply_targets.append(target)
        
        # 按优先级排序（CRITICAL > HIGH > MEDIUM）
        reply_targets.sort(key=lambda t: t.highest_priority.value)
        
        # 所有消息按时间排序（用于构建上下文）
        all_messages_sorted = sorted(messages, key=lambda m: m.timestamp)
        
        # 创建任务
        task = AggregatedTask(
            group_id=group_id,
            reply_targets=reply_targets,
            context_messages=context_messages,
            all_messages=all_messages_sorted,
            aggregated_at=time.time()
        )
        
        # 日志
        target_info = ", ".join([f"{t.nickname}({len(t.messages)}条)" for t in reply_targets])
        logger.info(f"[Aggregator] Group {group_id}: Need to reply to {len(reply_targets)} users: {target_info}")
        logger.info(f"[Aggregator] Group {group_id}: Context messages from {len(context_messages)} unrelated messages")
        
        # 调用处理器 (Fire-and-Forget)
        if self._task_handler:
            if asyncio.iscoroutinefunction(self._task_handler):
                asyncio.create_task(self._task_handler(task))
            else:
                self._task_handler(task)
    
    async def force_flush(self, group_id: int):
        """强制刷新（立即处理所有待处理消息）"""
        if group_id in self._window_timers:
            self._window_timers[group_id].cancel()
        await self._process_aggregated_messages(group_id)
    
    async def shutdown(self):
        """关闭聚合器"""
        self._running = False
        
        # 取消所有定时器
        for timer in self._window_timers.values():
            timer.cancel()
        
        # 处理剩余消息
        for group_id in list(self._pending_messages.keys()):
            await self._process_aggregated_messages(group_id)


# 全局单例
message_aggregator = MessageAggregator()
