"""
通用记忆库 Memory Store

设计目标：
1. 提供统一的记忆存取接口
2. 支持多种记忆类型：用户画像、事件、知识、对话片段
3. 支持模糊搜索和语义检索
4. 为未来跨项目调用做准备

记忆类型：
- user: 用户相关记忆（画像、偏好、事实）
- event: 事件记忆（发生的重要事情）
- knowledge: 知识记忆（学习到的概念）
- emotion: 情感状态记忆（AI的心情变化）
- conversation: 对话片段记忆（重要的对话）
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict, field
from enum import Enum

logger = logging.getLogger("MemoryStore")


class MemoryType(Enum):
    """记忆类型枚举"""
    USER = "user"           # 用户画像
    EVENT = "event"         # 事件记忆
    KNOWLEDGE = "knowledge" # 知识记忆
    EMOTION = "emotion"     # 情感状态
    CONVERSATION = "conversation"  # 对话片段


@dataclass
class Memory:
    """单条记忆"""
    memory_id: str                    # 唯一标识
    memory_type: str                  # 记忆类型 (MemoryType.value)
    content: str                      # 记忆内容
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据 (用户ID、群组ID等)
    importance: float = 0.5           # 重要性 (0-1)
    created_at: datetime = None       # 创建时间
    last_accessed: datetime = None    # 最后访问时间
    access_count: int = 0             # 访问次数
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_accessed is None:
            self.last_accessed = datetime.now()
    
    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'Memory':
        if data.get("created_at"):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("last_accessed"):
            data["last_accessed"] = datetime.fromisoformat(data["last_accessed"])
        return Memory(**data)


class MemoryStore:
    """
    通用记忆库
    
    提供统一的记忆存取接口，支持多种记忆类型。
    当前实现基于数据库，未来可扩展为向量数据库支持语义检索。
    """
    
    def __init__(self, db=None):
        self.db = db
        self._cache: Dict[str, Memory] = {}  # 内存缓存 {memory_id: Memory}
    
    def set_db(self, db):
        """设置数据库引用"""
        self.db = db
    
    # ============ 用户记忆 ============
    
    async def remember_about_user(
        self, 
        user_id: int, 
        fact: str, 
        category: str = "general",
        importance: float = 0.6
    ) -> bool:
        """
        记住关于用户的事实
        
        Args:
            user_id: 用户QQ号
            fact: 要记住的内容
            category: 分类 (general, preference, personality, relationship)
            importance: 重要性 (0-1)
        """
        if not self.db:
            logger.warning("[MemoryStore] Database not connected")
            return False
        
        try:
            # 优先使用现有的用户记忆系统
            memory = await self.db.get_or_create_global_user_memory(user_id)
            
            # 根据分类存储到不同字段
            if category == "preference" or category == "interests":
                # 追加到兴趣爱好
                current = memory.interests or ""
                if fact not in current:
                    memory.interests = f"{current}, {fact}" if current else fact
            elif category == "personality":
                # 存储到性格特征
                current = memory.personality or ""
                if fact not in current:
                    memory.personality = f"{current}, {fact}" if current else fact
            else:
                # 存储到用户请求记住的内容 (user_facts)
                facts = memory.get_user_facts_list()
                if fact not in facts:
                    facts.append(fact)
                    memory.set_user_facts_list(facts)
            
            await self.db.update_global_user_memory(memory)
            logger.info(f"[MemoryStore] Remembered about user {user_id}: {fact[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"[MemoryStore] Failed to remember: {e}")
            return False
    
    async def recall_about_user(self, user_id: int) -> Optional[Dict]:
        """
        回忆关于用户的所有信息
        
        Returns:
            {
                "nickname": "张三",
                "personality": "开朗",
                "interests": "猫, 编程",
                "facts": ["喜欢喝咖啡", "是程序员"],
                "notes": "..."
            }
        """
        if not self.db:
            return None
        
        try:
            memory = await self.db.get_global_user_memory(user_id)
            if not memory:
                return None
            
            # 防御性解析：部分 SQLite 字段可能返回字符串而非 datetime 对象
            first_seen = memory.first_seen
            if first_seen and hasattr(first_seen, 'isoformat'):
                first_seen = first_seen.isoformat()
                
            last_seen = memory.last_seen
            if last_seen and hasattr(last_seen, 'isoformat'):
                last_seen = last_seen.isoformat()

            return {
                "user_id": user_id,
                "nickname": memory.nickname,
                "personality": memory.personality,
                "interests": memory.interests,
                "traits": memory.traits,
                "facts": memory.get_user_facts_list(),
                "notes": memory.notes,
                "interaction_count": memory.interaction_count,
                "first_seen": first_seen,
                "last_seen": last_seen
            }
        except Exception as e:
            logger.error(f"[MemoryStore] Failed to recall: {e}")
            return None
    
    async def forget_about_user(self, user_id: int, fact: str) -> bool:
        """忘记关于用户的特定事实"""
        if not self.db:
            return False
        
        try:
            memory = await self.db.get_global_user_memory(user_id)
            if not memory:
                return False
            
            # 从 user_facts 中移除
            facts = memory.get_user_facts_list()
            if fact in facts:
                facts.remove(fact)
                memory.set_user_facts_list(facts)
                await self.db.update_global_user_memory(memory)
                logger.info(f"[MemoryStore] Forgot about user {user_id}: {fact}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"[MemoryStore] Failed to forget: {e}")
            return False
    
    # ============ 知识记忆 ============
    
    async def learn_knowledge(self, concept: str, definition: str, category: str = "general") -> bool:
        """
        学习新知识
        
        Args:
            concept: 概念/标题
            definition: 定义/内容
            category: 分类
        """
        if not self.db:
            return False
        
        try:
            await self.db.save_knowledge(concept, definition, category)
            logger.info(f"[MemoryStore] Learned: {concept}")
            return True
        except Exception as e:
            logger.error(f"[MemoryStore] Failed to learn: {e}")
            return False
    
    async def recall_knowledge(self, query: str, limit: int = 5) -> List[Dict]:
        """
        回忆知识（模糊搜索）
        
        Returns:
            [{"concept": "xxx", "definition": "xxx", "category": "xxx"}]
        """
        if not self.db:
            return []
        
        try:
            results = await self.db.search_knowledge(query, limit)
            return results
        except Exception as e:
            logger.error(f"[MemoryStore] Failed to recall knowledge: {e}")
            return []
    
    # ============ 情感状态 ============
    
    async def update_emotion(
        self, 
        emotion: str, 
        reason: str = "", 
        intensity: float = 0.5,
        triggered_by: int = None,  # 触发者的QQ号
        group_id: int = None       # 群组ID
    ) -> bool:
        """
        更新情感状态（支持持久化）
        
        Args:
            emotion: 情感类型 (happy, sad, curious, annoyed, excited, calm, playful, tired)
            reason: 原因
            intensity: 强度 (0-1)
            triggered_by: 触发者QQ号
            group_id: 群组ID
        
        Returns:
            是否成功更新
        """
        emotion_data = {
            "emotion": emotion,
            "reason": reason,
            "intensity": intensity,
            "triggered_by": triggered_by,
            "group_id": group_id,
            "updated_at": datetime.now().isoformat()
        }
        
        # 更新内存缓存
        self._current_emotion = emotion_data
        
        # 添加到历史记录（内存中保留最近20条）
        if not hasattr(self, '_emotion_history'):
            self._emotion_history = []
        self._emotion_history.append(emotion_data)
        if len(self._emotion_history) > 20:
            self._emotion_history = self._emotion_history[-20:]
        
        # 持久化到数据库
        if self.db:
            try:
                await self.db.save_emotion_state(emotion, reason, intensity, triggered_by, group_id)
            except AttributeError:
                # 如果数据库没有这个方法，静默失败
                pass
            except Exception as e:
                logger.warning(f"[MemoryStore] Failed to persist emotion: {e}")
        
        logger.info(f"[MemoryStore] Emotion updated: {emotion} ({intensity:.1f}) - {reason[:30]}...")
        return True
    
    def get_current_emotion(self) -> Optional[Dict]:
        """获取当前情感状态"""
        return getattr(self, '_current_emotion', None)
    
    def get_emotion_history(self, limit: int = 10) -> List[Dict]:
        """获取情感历史记录"""
        history = getattr(self, '_emotion_history', [])
        return history[-limit:] if history else []
    
    async def load_emotion_from_db(self) -> Optional[Dict]:
        """从数据库加载最近的情感状态"""
        if not self.db:
            return None
        
        try:
            emotion = await self.db.get_latest_emotion_state()
            if emotion:
                self._current_emotion = emotion
                return emotion
        except AttributeError:
            pass
        except Exception as e:
            logger.warning(f"[MemoryStore] Failed to load emotion: {e}")
        
        return None
    
    def get_emotion_prompt(self) -> str:
        """
        获取情感状态提示词（用于注入到AI系统提示）
        
        Returns:
            描述当前心情的提示词片段
        """
        emotion = self.get_current_emotion()
        if not emotion:
            return ""
        
        emotion_type = emotion.get("emotion", "calm")
        intensity = emotion.get("intensity", 0.5)
        reason = emotion.get("reason", "")
        
        # 情感描述映射
        emotion_descriptions = {
            "happy": ["开心", "心情很好", "特别高兴"],
            "sad": ["有点难过", "心情不太好", "感觉有些低落"],
            "curious": ["很好奇", "想知道更多", "觉得很有趣"],
            "annoyed": ["有点烦", "不太想说话", "略微不耐烦"],
            "excited": ["超级兴奋", "特别激动", "太棒了"],
            "calm": ["心情平静", "状态稳定", "一切正常"],
            "playful": ["想玩", "调皮捣蛋中", "嘿嘿"],
            "tired": ["有点累", "想休息", "困了"],
        }
        
        descriptions = emotion_descriptions.get(emotion_type, ["状态正常"])
        
        # 根据强度选择描述
        if intensity >= 0.7:
            desc = descriptions[-1] if len(descriptions) > 2 else descriptions[-1]
        elif intensity >= 0.4:
            desc = descriptions[1] if len(descriptions) > 1 else descriptions[0]
        else:
            desc = descriptions[0]
        
        prompt = f"\n[当前心情: {desc}]"
        if reason:
            prompt += f" ({reason[:20]}...)"
        
        return prompt
    
    # ============ 综合查询 ============
    
    async def search_all(self, query: str, limit: int = 10) -> Dict[str, List]:
        """
        综合搜索所有记忆类型
        
        Returns:
            {
                "users": [...],
                "knowledge": [...],
                "events": [...]
            }
        """
        results = {
            "users": [],
            "knowledge": [],
            "events": []
        }
        
        # 搜索知识库
        knowledge_results = await self.recall_knowledge(query, limit)
        results["knowledge"] = knowledge_results
        
        # 未来可扩展：搜索用户记忆、事件记忆等
        
        return results
    
    # ============ 记忆导出/导入（为跨项目调用准备） ============
    
    async def export_user_memories(self, user_id: int) -> Optional[str]:
        """
        导出用户记忆为 JSON
        便于跨项目迁移
        """
        data = await self.recall_about_user(user_id)
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return None
    
    async def import_user_memories(self, user_id: int, json_data: str) -> bool:
        """
        从 JSON 导入用户记忆
        """
        try:
            data = json.loads(json_data)
            
            if not self.db:
                return False
            
            memory = await self.db.get_or_create_global_user_memory(user_id)
            
            if data.get("nickname"):
                memory.nickname = data["nickname"]
            if data.get("personality"):
                memory.personality = data["personality"]
            if data.get("interests"):
                memory.interests = data["interests"]
            if data.get("traits"):
                memory.traits = data["traits"]
            if data.get("facts"):
                memory.set_user_facts_list(data["facts"])
            if data.get("notes"):
                memory.notes = data["notes"]
            
            await self.db.update_global_user_memory(memory)
            logger.info(f"[MemoryStore] Imported memories for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"[MemoryStore] Failed to import: {e}")
            return False


# 全局单例
memory_store = MemoryStore()
