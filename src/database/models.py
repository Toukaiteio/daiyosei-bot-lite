"""
数据模型定义 - 聊天系统数据结构
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class ChatHistory:
    """短期记忆流"""
    id: int
    group_id: str
    sender_id: str
    sender_name: str
    content: str
    raw_image_hash: Optional[str] = None
    timestamp: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> "ChatHistory":
        ts = row.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace(" ", "T"))
            except:
                pass
        return cls(
            id=row["id"],
            group_id=row["group_id"],
            sender_id=row["sender_id"],
            sender_name=row["sender_name"],
            content=row["content"],
            raw_image_hash=row.get("raw_image_hash"),
            timestamp=ts
        )


@dataclass
class MemeLibrary:
    """本地 RAG 梗库"""
    id: int
    rel_path: str
    keywords: str
    description: str
    category: str
    last_used: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> "MemeLibrary":
        return cls(
            id=row["id"],
            rel_path=row["rel_path"],
            keywords=row["keywords"],
            description=row["description"],
            category=row["category"],
            last_used=row.get("last_used")
        )


@dataclass
class LongTermMemory:
    """长期记忆"""
    id: int
    memory_type: str  # USER_FACT, EVENT, SELF_STATE
    key_entity: str
    content: str

    @classmethod
    def from_row(cls, row: dict) -> "LongTermMemory":
        return cls(
            id=row["id"],
            memory_type=row["memory_type"],
            key_entity=row["key_entity"],
            content=row["content"]
        )


@dataclass
class ImageCache:
    """视觉描述缓存"""
    hash: str
    description: str

    @classmethod
    def from_row(cls, row: dict) -> "ImageCache":
        return cls(
            hash=row["hash"],
            description=row["description"]
        )


@dataclass
class UserProfile:
    """用户画像模型 - 自学习系统核心"""
    user_id: int                           # 用户QQ
    group_id: int                          # 群号
    nickname: Optional[str] = None         # AI给这个人起的昵称
    personality: Optional[str] = None      # 性格特征（例如："开朗活泼"、"内向安静"）
    interests: Optional[str] = None        # 兴趣爱好（JSON字符串存储列表）
    speaking_style: Optional[str] = None   # 说话风格（例如："喜欢用表情"、"话少"）
    emotional_state: Optional[str] = None  # 当前情感状态
    preferences: Optional[str] = None      # 偏好设定（JSON字符串）
    important_facts: Optional[str] = None  # 重要事实记录（JSON字符串）
    interaction_count: int = 0              # 互动次数
    last_updated: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "group_id": self.group_id,
            "nickname": self.nickname,
            "personality": self.personality,
            "interests": self.interests,
            "speaking_style": self.speaking_style,
            "emotional_state": self.emotional_state,
            "preferences": self.preferences,
            "important_facts": self.important_facts,
            "interaction_count": self.interaction_count,
        }
    
    @classmethod
    def from_row(cls, row: dict) -> "UserProfile":
        last_updated = row.get("last_updated")
        if isinstance(last_updated, str):
            try:
                last_updated = datetime.fromisoformat(last_updated.replace(" ", "T"))
            except:
                pass
        return cls(
            user_id=row["user_id"],
            group_id=row["group_id"],
            nickname=row.get("nickname"),
            personality=row.get("personality"),
            interests=row.get("interests"),
            speaking_style=row.get("speaking_style"),
            emotional_state=row.get("emotional_state"),
            preferences=row.get("preferences"),
            important_facts=row.get("important_facts"),
            interaction_count=row.get("interaction_count", 0),
            last_updated=last_updated
        )


@dataclass
class ConversationMemory:
    """对话记忆 - 记录重要对话片段用于自学习"""
    id: int
    group_id: int
    user_id: int
    context: str                           # 对话上下文
    insight: str                           # AI提取的洞察
    memory_type: str                       # 记忆类型：personality, interest, preference, fact
    timestamp: Optional[datetime] = None
    
    @classmethod
    def from_row(cls, row: dict) -> "ConversationMemory":
        return cls(
            id=row["id"],
            group_id=row["group_id"],
            user_id=row["user_id"],
            context=row["context"],
            insight=row["insight"],
            memory_type=row["memory_type"],
            timestamp=row.get("timestamp")
        )


@dataclass
class GlobalUserMemory:
    """跨群组用户记忆 - 记住用户在所有群的特点"""
    user_id: int                           # 用户QQ (主键)
    nickname: Optional[str] = None         # AI给这个人起的昵称
    personality: Optional[str] = None      # 性格特征
    interests: Optional[str] = None        # 兴趣爱好
    traits: Optional[str] = None           # 用户特点/标签
    user_facts: Optional[str] = None       # 用户请求记住的内容 (JSON数组，最多3个)
    notes: Optional[str] = None            # 其他备注
    interaction_count: int = 0             # 总互动次数
    first_seen: Optional[datetime] = None  # 首次见面时间
    last_seen: Optional[datetime] = None   # 最后互动时间
    
    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "nickname": self.nickname,
            "personality": self.personality,
            "interests": self.interests,
            "traits": self.traits,
            "user_facts": self.user_facts,
            "notes": self.notes,
            "interaction_count": self.interaction_count,
        }
    
    def get_user_facts_list(self) -> list:
        """获取用户请求记住的内容列表"""
        if not self.user_facts:
            return []
        try:
            import json
            return json.loads(self.user_facts)
        except:
            return []
    
    def set_user_facts_list(self, facts: list):
        """设置用户请求记住的内容（最多保留3个）"""
        import json
        self.user_facts = json.dumps(facts[-3:], ensure_ascii=False)
    
    @classmethod
    def from_row(cls, row: dict) -> "GlobalUserMemory":
        first_seen = row.get("first_seen")
        if isinstance(first_seen, str):
            try:
                # 尝试解析带空格或 T 的格式
                first_seen = datetime.fromisoformat(first_seen.replace(" ", "T"))
            except:
                pass
                
        last_seen = row.get("last_seen")
        if isinstance(last_seen, str):
            try:
                last_seen = datetime.fromisoformat(last_seen.replace(" ", "T"))
            except:
                pass
                
        return cls(
            user_id=row["user_id"],
            nickname=row.get("nickname"),
            personality=row.get("personality"),
            interests=row.get("interests"),
            traits=row.get("traits"),
            user_facts=row.get("user_facts"),
            notes=row.get("notes"),
            interaction_count=row.get("interaction_count", 0),
            first_seen=first_seen,
            last_seen=last_seen
        )


# 保留旧的Relationship类以保持向后兼容
@dataclass
class Relationship:
    """好感度模型 - 已弃用，保留仅为兼容性"""
    user_id: int
    group_id: int
    affection: int = 0
    nickname: Optional[str] = None
    notes: Optional[str] = None
    last_updated: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "group_id": self.group_id,
            "affection": self.affection,
            "nickname": self.nickname,
            "notes": self.notes,
        }
    
    @classmethod
    def from_row(cls, row: dict) -> "Relationship":
        return cls(
            user_id=row["user_id"],
            group_id=row["group_id"],
            affection=row.get("affection", 0),
            nickname=row.get("nickname"),
            notes=row.get("notes"),
            last_updated=row.get("last_updated")
        )
