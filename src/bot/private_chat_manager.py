"""
私聊管理器 - Private Chat Manager

核心功能：
1. 管理私聊会话状态
2. 实现主动发起对话
3. 跟踪用户关系深度
4. 私聊内容反馈到用户记忆

设计理念：
- 私聊中的AI更加主动和亲密
- 根据互动历史调整沟通风格
- 形成持续的对话感
"""

import asyncio
import logging
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("PrivateChatManager")


class RelationshipLevel(Enum):
    """关系深度等级"""
    STRANGER = 1      # 陌生人（少于5次互动）
    ACQUAINTANCE = 2  # 认识（5-20次互动）
    FRIEND = 3        # 朋友（20-50次互动）
    CLOSE_FRIEND = 4  # 亲密朋友（50+次互动）


@dataclass
class PrivateChatSession:
    """私聊会话"""
    user_id: int
    nickname: str = "用户"
    
    # 会话状态
    is_active: bool = True
    last_message_time: float = 0
    last_bot_message_time: float = 0
    message_count: int = 0
    
    # 关系状态
    relationship_level: RelationshipLevel = RelationshipLevel.STRANGER
    total_interactions: int = 0
    first_interaction: Optional[datetime] = None
    
    # 对话上下文
    context: List[dict] = field(default_factory=list)
    max_context_size: int = 30
    
    # 主动对话状态
    proactive_cooldown: float = 0  # 主动消息冷却时间
    last_proactive_time: float = 0
    
    def add_message(self, role: str, content: str, user_id: int = None, nickname: str = None):
        """添加消息到上下文"""
        self.context.append({
            "role": role,
            "content": content,
            "sender_id": user_id or self.user_id,
            "sender_name": nickname or self.nickname,
            "timestamp": time.time()
        })
        
        # 限制上下文大小
        if len(self.context) > self.max_context_size:
            self.context = self.context[-self.max_context_size:]
        
        # 更新时间
        if role == "user":
            self.last_message_time = time.time()
            self.message_count += 1
        else:
            self.last_bot_message_time = time.time()
    
    def update_relationship(self):
        """更新关系等级"""
        if self.total_interactions >= 50:
            self.relationship_level = RelationshipLevel.CLOSE_FRIEND
        elif self.total_interactions >= 20:
            self.relationship_level = RelationshipLevel.FRIEND
        elif self.total_interactions >= 5:
            self.relationship_level = RelationshipLevel.ACQUAINTANCE
        else:
            self.relationship_level = RelationshipLevel.STRANGER
    
    @property
    def is_conversation_active(self) -> bool:
        """对话是否活跃（5分钟内有互动）"""
        return time.time() - self.last_message_time < 300
    
    @property
    def should_initiate_proactive(self) -> bool:
        """是否应该主动发起对话"""
        now = time.time()
        
        # 冷却时间内不主动
        if now < self.proactive_cooldown:
            return False
        
        # 最近已经发过主动消息
        if now - self.last_proactive_time < 3600:  # 1小时内
            return False
        
        # 对话正在进行中不主动打断
        if self.is_conversation_active:
            return False
        
        # 根据关系等级决定主动频率
        if self.relationship_level == RelationshipLevel.CLOSE_FRIEND:
            # 亲密朋友：8小时后可能主动联系
            return now - self.last_message_time > 28800
        elif self.relationship_level == RelationshipLevel.FRIEND:
            # 朋友：24小时后可能主动联系
            return now - self.last_message_time > 86400
        else:
            # 普通认识：不主动联系
            return False


class PrivateChatManager:
    """
    私聊管理器
    
    负责：
    1. 管理所有私聊会话
    2. 决定是否主动发起对话
    3. 生成主动消息内容
    4. 与记忆库联动
    """
    
    def __init__(self):
        self.sessions: Dict[int, PrivateChatSession] = {}
        self._memory_store = None
        self._llm_service = None
        self._send_callback: Optional[Callable] = None
        
        # 主动对话检查任务
        self._proactive_check_task: Optional[asyncio.Task] = None
        self._running = False
    
    def set_memory_store(self, memory_store):
        """设置记忆库引用"""
        self._memory_store = memory_store
    
    def set_llm_service(self, llm_service):
        """设置LLM服务引用"""
        self._llm_service = llm_service
    
    def set_send_callback(self, callback: Callable):
        """设置发送消息回调"""
        self._send_callback = callback
    
    def get_or_create_session(self, user_id: int, nickname: str = "用户") -> PrivateChatSession:
        """获取或创建私聊会话"""
        if user_id not in self.sessions:
            session = PrivateChatSession(user_id=user_id, nickname=nickname)
            session.first_interaction = datetime.now()
            self.sessions[user_id] = session
            logger.info(f"[PrivateChat] Created new session for user {user_id}")
        else:
            # 更新昵称
            self.sessions[user_id].nickname = nickname
        
        return self.sessions[user_id]
    
    async def handle_message(
        self,
        user_id: int,
        nickname: str,
        content: str,
        message_id: int = 0
    ) -> Optional[str]:
        """
        处理私聊消息
        
        返回AI的回复文本
        """
        from ..config import config
        
        # 0. 检查私聊黑名单
        if self._memory_store and self._memory_store.db:
            # 检查数据库黑名单 (包括管理员设置的和用户自己关闭的)
            if await self._memory_store.db.is_private_blacklisted(user_id):
                info = await self._memory_store.db.get_private_blacklist_info(user_id)
                # 如果是用户自己关闭的，且发送了消息，则不处理（让他用指令开启）
                if info and info.get("self_disabled"):
                    return "你已关闭私聊模式。发送 $$开启私聊模式 即可重新和我聊天哦~"
                # 如果是管理员拉黑的
                return None
        
        # 检查初始黑名单配置
        if user_id in getattr(config.bot_info, 'private_chat_blacklist', ()):
            return None
        
        session = self.get_or_create_session(user_id, nickname)
        
        # 增加互动计数
        session.total_interactions += 1
        session.update_relationship()
        
        # 添加消息到上下文
        session.add_message("user", content, user_id, nickname)
        
        # 更新用户记忆
        await self._update_user_memory(user_id, content, session)
        
        logger.info(f"[PrivateChat] User {user_id} ({nickname}): {content[:50]}...")
        logger.info(f"[PrivateChat] Relationship: {session.relationship_level.name}, Interactions: {session.total_interactions}")
        
        # 获取用户在群聊中的近期发言（作为上下文）
        cross_group_history = []
        if self._memory_store and self._memory_store.db:
            try:
                # 获取该用户在所有群的最近发言
                history = await self._memory_store.db.get_user_cross_group_history(user_id, limit=5)
                if history:
                    for msg in history:
                        timestamp = msg.get('timestamp', '')
                        content = msg.get('content', '')
                        # group_id = msg.get('group_id', 0)
                        cross_group_history.append(f"[{timestamp}] (在某群) {content}")
            except Exception as e:
                logger.warning(f"[PrivateChat] Failed to fetch cross-group history: {e}")
            
        # 生成回复
        reply = await self._generate_reply(session, cross_group_history)
        
        if reply:
            # 添加AI回复到上下文
            session.add_message("assistant", reply)
        
        return reply
    
    async def _generate_reply(self, session: PrivateChatSession, extra_context: List[str] = None) -> Optional[str]:
        """生成私聊回复"""
        if not self._llm_service:
            logger.warning("[PrivateChat] LLM service not configured")
            return None
        
        # 构建增强的系统提示（私聊版本）
        relationship_hints = {
            RelationshipLevel.STRANGER: "这是你和TA的初次或早期接触，表现得友好但保持适当距离。",
            RelationshipLevel.ACQUAINTANCE: "你们已经有一些互动了，可以更自然地交流。",
            RelationshipLevel.FRIEND: "你们是朋友了！可以更亲密、更轻松地聊天，会开玩笑。",
            RelationshipLevel.CLOSE_FRIEND: "你们是亲密的朋友！可以分享更多私人话题，表达关心。"
        }
        
        # 构建跨群上下文提示
        context_str = ""
        if extra_context:
            context_str = "\n[该用户近期在群聊中的发言 (仅供参考，不要直接回复这些内容)]:\n" + "\n".join(extra_context) + "\n"
        
        private_prompt = f"""
{context_str}
[私聊模式 - 更亲密的对话]
[私聊模式 - 更亲密的对话]
你正在和 {session.nickname} 一对一私聊。
关系等级: {session.relationship_level.name}
{relationship_hints.get(session.relationship_level, "")}

在私聊中你可以：
- 更主动地提问和关心对方
- 记住并回忆之前聊过的话题
- 表达更多个人情感
"""
        
        # 获取用户记忆
        user_memory_str = ""
        if self._memory_store:
            user_data = await self._memory_store.recall_about_user(session.user_id)
            if user_data:
                facts = user_data.get("facts", [])
                interests = user_data.get("interests", "")
                personality = user_data.get("personality", "")
                
                memory_parts = []
                if personality:
                    memory_parts.append(f"性格: {personality}")
                if interests:
                    memory_parts.append(f"喜欢: {interests}")
                for f in facts[:3]:
                    memory_parts.append(f'你记住的: "{f}"')
                
                if memory_parts:
                    user_memory_str = f"\n[🧠 关于 {session.nickname} 的记忆]\n" + "\n".join(f"- {p}" for p in memory_parts)
        
        # 构建消息
        messages = [
            {"role": "system", "content": private_prompt + user_memory_str}
        ]
        
        # 添加对话历史
        for msg in session.context:
            role = msg.get("role", "user")
            if role in ["user", "assistant"]:
                messages.append({
                    "role": role,
                    "content": msg.get("content", "")
                })
        
        try:
            # 调用LLM
            reply_texts = await self._llm_service.generate_chat_response(
                session.context,
                group_context=messages,
                summary=None,
                bot_id=0,
                group_id=session.user_id,  # 私聊用user_id作为group_id
                status_callback=None
            )
            
            if reply_texts:
                return "\n".join(reply_texts)
            
        except Exception as e:
            logger.error(f"[PrivateChat] LLM error: {e}")
        
        return None
    
    async def _update_user_memory(self, user_id: int, content: str, session: PrivateChatSession):
        """更新用户记忆"""
        if not self._memory_store:
            return
        
        # 检测用户是否告诉AI要记住什么
        remember_patterns = ["记住", "请记住", "帮我记住", "你要记住", "别忘了"]
        for pattern in remember_patterns:
            if pattern in content:
                # 提取要记住的内容
                idx = content.find(pattern) + len(pattern)
                fact = content[idx:].strip()
                if fact and len(fact) > 2:
                    await self._memory_store.remember_about_user(
                        user_id, 
                        fact[:100],  # 限制长度
                        category="general",
                        importance=0.8
                    )
                    logger.info(f"[PrivateChat] Remembered about {user_id}: {fact[:50]}...")
                    break
    
    async def start_proactive_check(self):
        """启动主动对话检查任务"""
        self._running = True
        self._proactive_check_task = asyncio.create_task(self._proactive_check_loop())
        logger.info("[PrivateChat] Proactive check started")
    
    async def stop_proactive_check(self):
        """停止主动对话检查"""
        self._running = False
        if self._proactive_check_task:
            self._proactive_check_task.cancel()
    
    async def _proactive_check_loop(self):
        """主动对话检查循环"""
        from ..config import config
        
        while self._running:
            try:
                await asyncio.sleep(3600)  # 每小时检查一次
                
                # 检查全局配置开关
                if not getattr(config.bot_info, 'private_chat_proactive', True):
                    continue
                
                for user_id, session in self.sessions.items():
                    # 检查是否应该主动
                    if not session.should_initiate_proactive:
                        continue
                    
                    # 检查黑名单
                    is_blocked = False
                    if self._memory_store and self._memory_store.db:
                        if await self._memory_store.db.is_private_blacklisted(user_id):
                            is_blocked = True
                    
                    if user_id in getattr(config.bot_info, 'private_chat_blacklist', ()):
                        is_blocked = True
                        
                    if is_blocked:
                        continue

                    await self._send_proactive_message(user_id, session)
                    session.last_proactive_time = time.time()
                    session.proactive_cooldown = time.time() + 86400  # 24小时冷却
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PrivateChat] Proactive check error: {e}")

    
    async def _send_proactive_message(self, user_id: int, session: PrivateChatSession):
        """发送主动消息"""
        if not self._send_callback:
            return
        
        # 生成主动问候
        greetings = [
            f"嘿 {session.nickname}~ 好久没聊了，你最近怎么样呀？",
            f"{session.nickname}！我刚才想到你了，你在干嘛呢~",
            f"诶嘿 {session.nickname}~ 今天过得怎么样？",
        ]
        
        message = random.choice(greetings)
        
        try:
            await self._send_callback(user_id, message, is_group=False)
            session.add_message("assistant", message)
            logger.info(f"[PrivateChat] Sent proactive message to {user_id}")
        except Exception as e:
            logger.error(f"[PrivateChat] Failed to send proactive message: {e}")


# 全局单例
private_chat_manager = PrivateChatManager()
