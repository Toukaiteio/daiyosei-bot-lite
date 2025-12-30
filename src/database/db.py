"""
数据库管理模块 - 基于 aiosqlite 的异步 SQLite 操作
"""
import aiosqlite
import os
import json
from datetime import datetime
from typing import Optional, List
from .models import Relationship, UserProfile, ConversationMemory, GlobalUserMemory


class Database:
    """异步数据库管理类"""
    
    def __init__(self, db_path: str = "data/game.db"):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self):
        """连接数据库"""
        # 确保目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._init_tables()
        # 初始化后清理黑名单重复项
        await self._clean_blacklist_duplicates()
    
    async def close(self):
        """关闭数据库连接"""
        if self._connection:
            await self._connection.close()
    
    async def _init_tables(self):
        """初始化数据库表"""
        await self._connection.executescript("""
            -- 用户画像表（新）
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                nickname TEXT,
                personality TEXT,
                interests TEXT,
                speaking_style TEXT,
                emotional_state TEXT,
                preferences TEXT,
                important_facts TEXT,
                interaction_count INTEGER DEFAULT 0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, group_id)
            );
            
            -- 对话记忆表（新）
            CREATE TABLE IF NOT EXISTS conversation_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                context TEXT NOT NULL,
                insight TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 好感度表（保留旧表结构以兼容）
            CREATE TABLE IF NOT EXISTS relationships (
                user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                affection INTEGER DEFAULT 0,
                nickname TEXT,
                notes TEXT,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, group_id)
            );
            
            -- 聊天历史表（短期记忆）
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                sender_role TEXT DEFAULT 'member',
                content TEXT NOT NULL,
                raw_image_hash TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 群聊摘要表（长期记忆）
            CREATE TABLE IF NOT EXISTS group_summaries (
                group_id INTEGER PRIMARY KEY,
                summary TEXT NOT NULL,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 表情包库
            CREATE TABLE IF NOT EXISTS meme_library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rel_path TEXT NOT NULL,
                keywords TEXT NOT NULL,
                description TEXT,
                category TEXT,
                last_used DATETIME
            );
            
            -- 长期记忆
            CREATE TABLE IF NOT EXISTS long_term_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_type TEXT NOT NULL,
                key_entity TEXT NOT NULL,
                content TEXT NOT NULL
            );
            
            -- 图片缓存
            CREATE TABLE IF NOT EXISTS image_cache (
                hash TEXT PRIMARY KEY,
                description TEXT NOT NULL
            );

            -- 黑名单表
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, group_id)
            );

            -- COS 文章表
            CREATE TABLE IF NOT EXISTS cos_articles (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- COS 发送历史
            CREATE TABLE IF NOT EXISTS cos_sent_history (
                group_id INTEGER NOT NULL,
                article_id INTEGER NOT NULL,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (group_id, article_id)
            );
            
            -- COS 图片下载记录
            CREATE TABLE IF NOT EXISTS cos_images (
                url TEXT PRIMARY KEY,
                local_path TEXT,
                downloaded INTEGER DEFAULT 0,
                article_id INTEGER,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 跨群组用户记忆表（全局记忆）
            CREATE TABLE IF NOT EXISTS global_user_memory (
                user_id INTEGER PRIMARY KEY,
                nickname TEXT,
                personality TEXT,
                interests TEXT,
                traits TEXT,
                user_facts TEXT,
                notes TEXT,
                interaction_count INTEGER DEFAULT 0,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 群组启用状态表（默认禁用，需要管理员启用）
            CREATE TABLE IF NOT EXISTS enabled_groups (
                group_id INTEGER PRIMARY KEY,
                enabled_by INTEGER NOT NULL,
                enabled_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- 大模型回复禁用表（默认启用，管理员可禁用）
            CREATE TABLE IF NOT EXISTS llm_disabled_groups (
                group_id INTEGER PRIMARY KEY,
                disabled_by INTEGER NOT NULL,
                disabled_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            -- 主动回复配置表（默认禁用）
            CREATE TABLE IF NOT EXISTS proactive_reply_settings (
                group_id INTEGER PRIMARY KEY,
                whitelist TEXT, -- JSON list of allowed user IDs. NULL means ALL.
                enabled_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Hooker Agent 条件钩子表
            CREATE TABLE IF NOT EXISTS hooks (
                hook_id TEXT PRIMARY KEY,
                group_id INTEGER NOT NULL,
                condition_type TEXT NOT NULL,
                condition_value TEXT NOT NULL,
                reason TEXT,
                content_template TEXT NOT NULL,
                created_at REAL NOT NULL,
                triggered INTEGER DEFAULT 0,
                trigger_time REAL,
                script_path TEXT,
                created_by INTEGER
            );
        """)
        
        # 情感状态表 - 记录AI的情感变化历史
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS emotion_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emotion TEXT NOT NULL,
                reason TEXT,
                intensity REAL DEFAULT 0.5,
                triggered_by INTEGER,
                group_id INTEGER,
                created_at REAL NOT NULL
            );
        """)
        
        # 私聊黑名单表 - 管理员设置或用户自己设置的私聊拒绝列表
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS private_chat_blacklist (
                user_id INTEGER PRIMARY KEY,
                set_by INTEGER,
                reason TEXT,
                self_disabled INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            );
        """)
        await self._connection.commit()

        
        # === 自动迁移：检查并修复旧表结构 ===
        try:
            # 尝试给 chat_history 添加 sender_role 字段
            await self._connection.execute(
                "ALTER TABLE chat_history ADD COLUMN sender_role TEXT DEFAULT 'member'"
            )
            await self._connection.commit()
            print("[Database] 已为 chat_history 表添加 sender_role 字段")
        except Exception:
            pass

        # === 自动迁移：添加情感状态表 ===

    
    async def _clean_blacklist_duplicates(self):
        """清理黑名单中的重复项（保留最新的一条）"""
        try:
            # 查询所有重复项（同一 user_id + group_id 有多条记录）
            cursor = await self._connection.execute("""
                SELECT user_id, group_id, COUNT(*) as count
                FROM blacklist
                GROUP BY user_id, group_id
                HAVING count > 1
            """)
            duplicates = await cursor.fetchall()
            
            if not duplicates:
                return
            
            print(f"[Database] 发现 {len(duplicates)} 组黑名单重复项，正在清理...")
            
            for dup in duplicates:
                user_id = dup['user_id']
                group_id = dup['group_id']
                
                # 查找该组合的所有记录
                cursor = await self._connection.execute("""
                    SELECT rowid, timestamp
                    FROM blacklist
                    WHERE user_id = ? AND group_id = ?
                    ORDER BY timestamp DESC
                """, (user_id, group_id))
                
                records = await cursor.fetchall()
                
                if len(records) > 1:
                    # 保留最新的，删除其他
                    latest_rowid = records[0]['rowid']
                    for record in records[1:]:
                        await self._connection.execute(
                            "DELETE FROM blacklist WHERE rowid = ?",
                            (record['rowid'],)
                        )
                    print(f"[Database] 清理 user_id={user_id}, group_id={group_id} 的 {len(records)-1} 条重复项")
            
            await self._connection.commit()
            print(f"[Database] 黑名单清理完成")
            
        except Exception as e:
            print(f"[Database] 清理黑名单失败: {e}")
    
    # =============== 好感度操作 ===============
    
    async def get_relationship(self, user_id: int, group_id: int) -> Optional[Relationship]:
        """获取用户好感度"""
        cursor = await self._connection.execute(
            "SELECT * FROM relationships WHERE user_id = ? AND group_id = ?",
            (user_id, group_id)
        )
        row = await cursor.fetchone()
        if row:
            return Relationship.from_row(dict(row))
        return None
    
    async def get_or_create_relationship(self, user_id: int, group_id: int) -> Relationship:
        """获取或创建好感度记录"""
        rel = await self.get_relationship(user_id, group_id)
        if not rel:
            await self._connection.execute(
                "INSERT INTO relationships (user_id, group_id) VALUES (?, ?)",
                (user_id, group_id)
            )
            await self._connection.commit()
            rel = Relationship(user_id=user_id, group_id=group_id)
        return rel
    
    async def update_relationship(self, relationship: Relationship):
        """更新好感度"""
        await self._connection.execute(
            """UPDATE relationships SET
               affection = ?, nickname = ?, notes = ?, last_updated = ?
               WHERE user_id = ? AND group_id = ?""",
            (relationship.affection, relationship.nickname, relationship.notes,
             datetime.now(), relationship.user_id, relationship.group_id)
        )
        await self._connection.commit()

    async def get_top_relationships(self, group_id: int, limit: int = 5) -> List[Relationship]:
        """获取群内好感度最高的用户"""
        cursor = await self._connection.execute(
            """SELECT * FROM relationships 
               WHERE group_id = ? 
               ORDER BY affection DESC 
               LIMIT ?""",
            (group_id, limit)
        )
        rows = await cursor.fetchall()
        return [Relationship.from_row(dict(row)) for row in rows]
    
    # =============== 聊天历史操作（短期记忆） ===============
    
    async def add_chat_history(self, group_id: int, sender_id: int, sender_name: str, 
                               content: str, sender_role: str = "member", image_hash: Optional[str] = None):
        """添加聊天记录"""
        await self._connection.execute(
            """INSERT INTO chat_history (group_id, sender_id, sender_name, sender_role, content, raw_image_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (group_id, sender_id, sender_name, sender_role, content, image_hash)
        )
        await self._connection.commit()
    
    async def get_recent_chat_history(self, group_id: int, limit: int = 60) -> List[dict]:
        """获取最近的聊天记录（用于恢复短期记忆）"""
        cursor = await self._connection.execute(
            """SELECT sender_id, sender_name, sender_role, content, 
                      strftime('%s', timestamp) as timestamp
               FROM chat_history 
               WHERE group_id = ? 
               ORDER BY id DESC 
               LIMIT ?""",
            (group_id, limit)
        )
        rows = await cursor.fetchall()
        # 反转顺序，使其从旧到新
        result = [dict(row) for row in reversed(rows)]
        # 转换 timestamp 为 float 并映射 role 字段
        for item in result:
            if item.get('timestamp'):
                item['timestamp'] = float(item['timestamp'])
            # Map sender_role to role for consistency
            if 'sender_role' in item:
                item['role'] = item['sender_role']
            elif 'role' not in item:
                item['role'] = 'unknown'  # Fallback
        return result
    
    async def clean_old_chat_history(self, group_id: int, keep_last: int = 200):
        """清理旧的聊天记录，只保留最近的N条"""
        await self._connection.execute(
            """DELETE FROM chat_history 
               WHERE group_id = ? 
               AND id NOT IN (
                   SELECT id FROM chat_history 
                   WHERE group_id = ? 
                   ORDER BY id DESC 
                   LIMIT ?
               )""",
            (group_id, group_id, keep_last)
        )
        await self._connection.commit()
    
    async def get_user_chat_history(self, group_id: int, user_id: int, limit: int = 50) -> List[dict]:
        """获取指定用户在指定群组的历史发言"""
        cursor = await self._connection.execute(
            """SELECT sender_id, sender_name, sender_role, content, 
                      strftime('%Y-%m-%d %H:%M:%S', timestamp) as timestamp
               FROM chat_history 
               WHERE group_id = ? AND sender_id = ?
               ORDER BY id DESC 
               LIMIT ?""",
            (group_id, user_id, limit)
        )
        rows = await cursor.fetchall()
        # 反转顺序，使其从旧到新
        result = [dict(row) for row in reversed(rows)]
        return result
    
    async def get_user_cross_group_history(self, user_id: int, limit: int = 20) -> List[dict]:
        """获取用户在所有群组的历史发言（跨群上下文）"""
        cursor = await self._connection.execute(
            """SELECT group_id, sender_name, content, 
                      strftime('%Y-%m-%d %H:%M:%S', timestamp) as timestamp
               FROM chat_history 
               WHERE sender_id = ? 
               ORDER BY timestamp DESC 
               LIMIT ?""",
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        # 反转顺序，使其从旧到新
        result = [dict(row) for row in reversed(rows)]
        return result
    
    # =============== 图片缓存操作 ===============
    
    async def get_image_description(self, image_hash: str) -> Optional[str]:
        """获取图片描述缓存"""
        cursor = await self._connection.execute(
            "SELECT description FROM image_cache WHERE hash = ?",
            (image_hash,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None
    
    async def set_image_description(self, image_hash: str, description: str):
        """设置图片描述缓存"""
        await self._connection.execute(
            "INSERT OR REPLACE INTO image_cache (hash, description) VALUES (?, ?)",
            (image_hash, description)
        )
        await self._connection.commit()
    
    # =============== 用户画像操作 ===============
    
    async def get_user_profile(self, user_id: int, group_id: int) -> Optional[UserProfile]:
        """获取用户画像"""
        cursor = await self._connection.execute(
            "SELECT * FROM user_profiles WHERE user_id = ? AND group_id = ?",
            (user_id, group_id)
        )
        row = await cursor.fetchone()
        if row:
            return UserProfile.from_row(dict(row))
        return None
    
    async def get_or_create_user_profile(self, user_id: int, group_id: int) -> UserProfile:
        """获取或创建用户画像"""
        profile = await self.get_user_profile(user_id, group_id)
        if not profile:
            await self._connection.execute(
                "INSERT INTO user_profiles (user_id, group_id) VALUES (?, ?)",
                (user_id, group_id)
            )
            await self._connection.commit()
            profile = UserProfile(user_id=user_id, group_id=group_id)
        return profile
    
    async def update_user_profile(self, profile: UserProfile):
        """更新用户画像"""
        await self._connection.execute(
            """UPDATE user_profiles SET
               nickname = ?, personality = ?, interests = ?, speaking_style = ?,
               emotional_state = ?, preferences = ?, important_facts = ?,
               interaction_count = ?, last_updated = ?
               WHERE user_id = ? AND group_id = ?""",
            (profile.nickname, profile.personality, profile.interests, profile.speaking_style,
             profile.emotional_state, profile.preferences, profile.important_facts,
             profile.interaction_count, datetime.now(), profile.user_id, profile.group_id)
        )
        await self._connection.commit()
    
    # =============== 对话记忆操作 ===============
    
    async def add_conversation_memory(self, group_id: int, user_id: int, 
                                     context: str, insight: str, memory_type: str):
        """添加对话记忆"""
        await self._connection.execute(
            """INSERT INTO conversation_memories (group_id, user_id, context, insight, memory_type)
               VALUES (?, ?, ?, ?, ?)""",
            (group_id, user_id, context, insight, memory_type)
        )
        await self._connection.commit()
    
    async def get_user_memories(self, user_id: int, group_id: int, limit: int = 10) -> List[ConversationMemory]:
        """获取用户的对话记忆"""
        cursor = await self._connection.execute(
            """SELECT * FROM conversation_memories 
               WHERE user_id = ? AND group_id = ?
               ORDER BY timestamp DESC 
               LIMIT ?""",
            (user_id, group_id, limit)
        )
        rows = await cursor.fetchall()
        return [ConversationMemory.from_row(dict(row)) for row in rows]
    
    # =============== 群聊摘要操作（长期记忆） ===============
    
    async def save_group_summary(self, group_id: int, summary: str):
        """保存群聊摘要"""
        await self._connection.execute(
            """INSERT OR REPLACE INTO group_summaries (group_id, summary, last_updated)
               VALUES (?, ?, ?)""",
            (group_id, summary, datetime.now())
        )
        await self._connection.commit()
    
    async def get_group_summary(self, group_id: int) -> Optional[str]:
        """获取群聊摘要"""
        cursor = await self._connection.execute(
            "SELECT summary FROM group_summaries WHERE group_id = ?",
            (group_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None
    
    async def get_all_group_summaries(self) -> dict:
        """获取所有群聊摘要（用于恢复长期记忆）"""
        cursor = await self._connection.execute(
            "SELECT group_id, summary FROM group_summaries"
        )
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

    # =============== 黑名单操作 ===============
    
    async def add_to_blacklist(self, user_id: int, group_id: int, reason: str = ""):
        """加入黑名单"""
        await self._connection.execute(
            "INSERT OR REPLACE INTO blacklist (user_id, group_id, reason, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, group_id, reason, datetime.now())
        )
        await self._connection.commit()

    async def is_blacklisted(self, user_id: int, group_id: int) -> bool:
        """检查是否在黑名单中 (支持全局黑名单 group_id=0)"""
        try:
            if user_id is None:
                return False
            user_id = int(user_id)
            # 如果 group_id 是 None，只检查全局黑名单
            if group_id is None:
                group_id = 0
            else:
                group_id = int(group_id)
        except (ValueError, TypeError):
            return False
            
        cursor = await self._connection.execute(
            "SELECT 1 FROM blacklist WHERE user_id = ? AND (group_id = ? OR group_id = 0)",
            (user_id, group_id)
        )
        row = await cursor.fetchone()
        return row is not None
    async def remove_from_blacklist(self, user_id: int, group_id: int):
        """取消拉黑"""
        await self._connection.execute(
            "DELETE FROM blacklist WHERE user_id = ? AND group_id = ?",
            (user_id, group_id)
        )
        await self._connection.commit()


    async def update_black_list(self, user_id: int, is_black: bool, reason: str = ""):
        """更新黑名单状态 (兼容旧 API)"""
        # 对所有群生效 (group_id=0) 或者需要传递 group_id?
        # 既然是 "blacklisted"，通常是全局或当前群。
        # 这里的 handler 传入了 reason，看起来是封禁。
        # 假设 group_id=0 表示全局
        if is_black:
            await self.add_to_blacklist(user_id, 0, reason)
        else:
            await self.remove_from_blacklist(user_id, 0)

    # =============== COS 命令相关 ===============

    async def add_cos_article(self, article_id: int, title: str, link: str):
        """添加 COS 文章记录"""
        await self._connection.execute(
            "INSERT OR IGNORE INTO cos_articles (id, title, link) VALUES (?, ?, ?)",
            (article_id, title, link)
        )
        await self._connection.commit()

    async def is_cos_article_saved(self, article_id: int) -> bool:
        """检查 COS 文章是否已存在"""
        cursor = await self._connection.execute(
            "SELECT 1 FROM cos_articles WHERE id = ?",
            (article_id,)
        )
        row = await cursor.fetchone()
        return row is not None

    async def get_unsent_cos_article(self, group_id: int) -> Optional[dict]:
        """获取当前群聊未发送过的 COS 文章"""
        cursor = await self._connection.execute(
            """SELECT a.id, a.title, a.link 
               FROM cos_articles a
               LEFT JOIN cos_sent_history h ON a.id = h.article_id AND h.group_id = ?
               WHERE h.article_id IS NULL
               ORDER BY a.id ASC
               LIMIT 1""",
            (group_id,)
        )
        row = await cursor.fetchone()
        if row:
            print(f"[Database] Found unsent article for group {group_id}: {row['id']}")
        else:
            print(f"[Database] No unsent articles for group {group_id}")
        return dict(row) if row else None

    async def mark_cos_article_sent(self, group_id: int, article_id: int):
        """标记 COS 文章在指定群聊已发送"""
        await self._connection.execute(
            "INSERT OR IGNORE INTO cos_sent_history (group_id, article_id) VALUES (?, ?)",
            (group_id, article_id)
        )
        await self._connection.commit()

    async def get_cos_image(self, url: str) -> Optional[dict]:
        """获取 COS 图片下载记录"""
        cursor = await self._connection.execute(
            "SELECT * FROM cos_images WHERE url = ?",
            (url,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_image_description(self, image_hash: str) -> Optional[str]:
        """获取图片描述缓存"""
        cursor = await self._connection.execute(
            "SELECT description FROM image_cache WHERE hash = ?",
            (image_hash,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def add_cos_image(self, url: str, article_id: int, local_path: str = None, downloaded: int = 0):
        """添加 COS 图片记录"""
        await self._connection.execute(
            "INSERT OR REPLACE INTO cos_images (url, article_id, local_path, downloaded) VALUES (?, ?, ?, ?)",
            (url, article_id, local_path, downloaded)
        )
        await self._connection.commit()

    # =============== 概念学习 (Long Term Memory) ===============
    
    async def learn_concept(self, concept: str, definition: str):
        """学习或更新一个概念"""
        # 检查是否存在，存在则更新
        cursor = await self._connection.execute(
            "SELECT id FROM long_term_memory WHERE memory_type='concept' AND key_entity=?", (concept,)
        )
        row = await cursor.fetchone()
        if row:
             await self._connection.execute(
                "UPDATE long_term_memory SET content=? WHERE id=?", (definition, row[0])
            )
        else:
            await self._connection.execute(
                "INSERT INTO long_term_memory (memory_type, key_entity, content) VALUES ('concept', ?, ?)",
                (concept, definition)
            )
        await self._connection.commit()

    async def get_concept(self, concept: str) -> Optional[str]:
        """获取概念定义"""
        cursor = await self._connection.execute(
            "SELECT content FROM long_term_memory WHERE memory_type='concept' AND key_entity=?", (concept,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None
        
    async def search_concepts_fuzzy(self, query: str) -> List[tuple]:
        """模糊搜索概念"""
        cursor = await self._connection.execute(
            "SELECT key_entity, content FROM long_term_memory WHERE memory_type='concept' AND (key_entity LIKE ? OR content LIKE ?) LIMIT 5", 
            (f"%{query}%", f"%{query}%")
        )
        rows = await cursor.fetchall()
        return [(row[0], row[1]) for row in rows]

    async def delete_concept(self, concept: str):
        """遗忘概念"""
        await self._connection.execute(
            "DELETE FROM long_term_memory WHERE memory_type='concept' AND key_entity=?", (concept,)
        )
        await self._connection.commit()
    
    async def list_concepts(self, limit: int = 50) -> List[str]:
        """列出所有已学习的概念"""
        cursor = await self._connection.execute(
             "SELECT key_entity FROM long_term_memory WHERE memory_type='concept' ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    # =============== 跨群组用户记忆操作 ===============
    
    async def get_global_user_memory(self, user_id: int) -> Optional[GlobalUserMemory]:
        """获取用户的跨群组记忆"""
        cursor = await self._connection.execute(
            "SELECT * FROM global_user_memory WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return GlobalUserMemory.from_row(dict(row))
        return None
    
    async def get_or_create_global_user_memory(self, user_id: int) -> GlobalUserMemory:
        """获取或创建用户的跨群组记忆"""
        memory = await self.get_global_user_memory(user_id)
        if not memory:
            await self._connection.execute(
                "INSERT INTO global_user_memory (user_id, first_seen, last_seen) VALUES (?, ?, ?)",
                (user_id, datetime.now(), datetime.now())
            )
            await self._connection.commit()
            memory = GlobalUserMemory(user_id=user_id)
        return memory
    
    async def update_global_user_memory(self, memory: GlobalUserMemory):
        """更新用户的跨群组记忆"""
        await self._connection.execute(
            """UPDATE global_user_memory SET
               nickname = ?, personality = ?, interests = ?, traits = ?,
               user_facts = ?, notes = ?, interaction_count = ?, last_seen = ?
               WHERE user_id = ?""",
            (memory.nickname, memory.personality, memory.interests, memory.traits,
             memory.user_facts, memory.notes, memory.interaction_count, 
             datetime.now(), memory.user_id)
        )
        await self._connection.commit()
    
    async def increment_global_user_interaction(self, user_id: int):
        """增加用户的全局互动计数"""
        memory = await self.get_or_create_global_user_memory(user_id)
        memory.interaction_count += 1
        await self.update_global_user_memory(memory)
    
    async def add_user_fact(self, user_id: int, fact: str) -> tuple[bool, str]:
        """
        添加用户请求记住的内容（最多3个）
        返回：(是否成功, 消息)
        """
        memory = await self.get_or_create_global_user_memory(user_id)
        facts = memory.get_user_facts_list()
        
        # 检查是否已存在相同内容
        if fact in facts:
            return False, "我已经记住这个了哦~"
        
        # 如果已经有3个，移除最旧的
        if len(facts) >= 3:
            removed = facts.pop(0)
            facts.append(fact)
            memory.set_user_facts_list(facts)
            await self.update_global_user_memory(memory)
            return True, f"记住啦！（之前的「{removed[:20]}...」被挤掉了，最多只能记3个哦）"
        
        facts.append(fact)
        memory.set_user_facts_list(facts)
        await self.update_global_user_memory(memory)
        return True, f"记住啦！（已记 {len(facts)}/3）"
    
    async def remove_user_fact(self, user_id: int, fact_index: int) -> tuple[bool, str]:
        """移除用户请求记住的内容"""
        memory = await self.get_global_user_memory(user_id)
        if not memory:
            return False, "没有找到你的记忆~"
        
        facts = memory.get_user_facts_list()
        if fact_index < 0 or fact_index >= len(facts):
            return False, f"索引无效，当前有 {len(facts)} 条记忆"
        
        removed = facts.pop(fact_index)
        memory.set_user_facts_list(facts)
        await self.update_global_user_memory(memory)
        return True, f"忘掉了：「{removed[:30]}...」"
    
    async def update_user_trait(self, user_id: int, field: str, value: str) -> str:
        """更新用户特征（性格、兴趣、特点等）"""
        memory = await self.get_or_create_global_user_memory(user_id)
        
        if field == "nickname":
            memory.nickname = value
        elif field == "personality":
            memory.personality = value
        elif field == "interests":
            memory.interests = value
        elif field == "traits":
            memory.traits = value
        elif field == "notes":
            memory.notes = value
        else:
            return f"未知字段: {field}"
        
        await self.update_global_user_memory(memory)
        return f"已更新 {field}"
    
    async def format_user_memory_for_prompt(self, user_id: int) -> Optional[str]:
        """格式化用户记忆供AI提示词使用 - 优化为更自然的格式"""
        memory = await self.get_global_user_memory(user_id)
        if not memory:
            return None
        
        traits = []
        
        # 性格和特点
        if memory.personality:
            traits.append(memory.personality)
        if memory.traits:
            traits.append(memory.traits)
        
        # 兴趣爱好
        if memory.interests:
            traits.append(f"喜欢{memory.interests}")
        
        # 用户请求记住的内容（重要！）
        facts = memory.get_user_facts_list()
        if facts:
            for f in facts:
                traits.append(f'让你记住「{f}」')
        
        # 备注
        if memory.notes:
            traits.append(memory.notes)
        
        if not traits:
            return None
        
        return ", ".join(traits)
    
    async def get_all_speakers_memory(self, user_ids: List[int]) -> dict:
        """批量获取多个用户的记忆（用于群聊上下文）- 包含昵称信息"""
        result = {}
        for uid in user_ids:
            memory = await self.get_global_user_memory(uid)
            if memory:
                mem_str = await self.format_user_memory_for_prompt(uid)
                if mem_str:
                    # 使用昵称开头，更自然
                    name = memory.nickname if memory.nickname else f"用户"
                    result[uid] = f"{name}: {mem_str}"
                elif memory.nickname:
                    # 即使没有其他信息，也记录昵称
                    result[uid] = f"昵称: {memory.nickname}"
        return result

    # =============== 群组启用状态管理 ===============
    
    # =============== 群组启用状态管理 ===============
    
    async def is_group_enabled(self, group_id: int) -> bool:
        """检查群组是否已启用（默认未启用）"""
        cursor = await self._connection.execute(
            "SELECT 1 FROM enabled_groups WHERE group_id = ?",
            (group_id,)
        )
        row = await cursor.fetchone()
        return row is not None
    
    async def enable_group(self, group_id: int, enabled_by: int):
        """启用群组"""
        await self._connection.execute(
            "INSERT OR REPLACE INTO enabled_groups (group_id, enabled_by, enabled_at) VALUES (?, ?, ?)",
            (group_id, enabled_by, datetime.now())
        )
        await self._connection.commit()
    
    async def disable_group(self, group_id: int):
        """禁用群组"""
        await self._connection.execute(
            "DELETE FROM enabled_groups WHERE group_id = ?",
            (group_id,)
        )
        await self._connection.commit()
    
    async def get_all_enabled_groups(self) -> List[int]:
        """获取所有已启用的群组ID列表"""
        cursor = await self._connection.execute(
            "SELECT group_id FROM enabled_groups"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    # =============== 主动回复设置 (Proactive Reply) ===============

    async def get_proactive_config(self, group_id: int) -> tuple[bool, Optional[List[int]]]:
        """
        获取群组主动回复配置
        返回: (is_enabled, whitelist)
        - is_enabled: 是否开启
        - whitelist: None表示对所有人开启，List[int]表示只对特定名单开启
        """
        cursor = await self._connection.execute(
            "SELECT whitelist FROM proactive_reply_settings WHERE group_id = ?",
            (group_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return False, None
        
        whitelist_json = row[0]
        if whitelist_json is None:
            return True, None
        
        try:
            return True, json.loads(whitelist_json)
        except:
            return True, None

    async def enable_proactive_global(self, group_id: int):
        """开启群组全局主动回复"""
        await self._connection.execute(
            "INSERT OR REPLACE INTO proactive_reply_settings (group_id, whitelist) VALUES (?, NULL)",
            (group_id,)
        )
        await self._connection.commit()

    async def disable_proactive_global(self, group_id: int):
        """关闭群组主动回复"""
        await self._connection.execute(
            "DELETE FROM proactive_reply_settings WHERE group_id = ?",
            (group_id,)
        )
        await self._connection.commit()

    async def add_proactive_user(self, group_id: int, user_id: int):
        """添加用户到主动回复白名单 (开启特定用户)"""
        enabled, whitelist = await self.get_proactive_config(group_id)
        
        if not enabled:
            # 如果未开启，开启并初始化为该用户
            new_list = [user_id]
            await self._connection.execute(
                "INSERT INTO proactive_reply_settings (group_id, whitelist) VALUES (?, ?)",
                (group_id, json.dumps(new_list))
            )
        else:
            # 如果已开启
            if whitelist is None:
                # 已经是全局开启，不需要操作 (或者视需求决定是否转为特定列表，这里保持全局)
                pass 
            else:
                # 添加到列表
                if user_id not in whitelist:
                    whitelist.append(user_id)
                    await self._connection.execute(
                        "UPDATE proactive_reply_settings SET whitelist = ? WHERE group_id = ?",
                        (json.dumps(whitelist), group_id)
                    )
        await self._connection.commit()

    async def remove_proactive_user(self, group_id: int, user_id: int):
        """从白名单移除用户"""
        enabled, whitelist = await self.get_proactive_config(group_id)
        if not enabled or whitelist is None:
            # 如果未开启，或全局开启，无法移除特定用户(全局开启时移除特定用户逻辑暂不支持/未定义，暂且忽略)
            return

        if user_id in whitelist:
            whitelist.remove(user_id)
            if not whitelist:
                # 列表空了，是否禁用？或者保留空列表(没人触发)? 
                # 这里选择删除行(禁用)
                await self.disable_proactive_global(group_id)
            else:
                await self._connection.execute(
                    "UPDATE proactive_reply_settings SET whitelist = ? WHERE group_id = ?",
                    (json.dumps(whitelist), group_id)
                )
            await self._connection.commit()

    # =============== 大模型回复开关管理 ===============
    
    async def is_llm_enabled(self, group_id: int) -> bool:
        """检查群组的大模型回复是否启用（默认启用）"""
        cursor = await self._connection.execute(
            "SELECT 1 FROM llm_disabled_groups WHERE group_id = ?",
            (group_id,)
        )
        row = await cursor.fetchone()
        # 如果在禁用表中找到了，说明被禁用了，返回 False
        return row is None
    
    async def disable_llm(self, group_id: int, disabled_by: int):
        """禁用群组的大模型回复"""
        await self._connection.execute(
            "INSERT OR REPLACE INTO llm_disabled_groups (group_id, disabled_by, disabled_at) VALUES (?, ?, ?)",
            (group_id, disabled_by, datetime.now())
        )
        await self._connection.commit()
    
    async def enable_llm(self, group_id: int):
        """启用群组的大模型回复"""
        await self._connection.execute(
            "DELETE FROM llm_disabled_groups WHERE group_id = ?",
            (group_id,)
        )
        await self._connection.commit()

    # ============ 情感状态管理 ============
    
    async def save_emotion_state(
        self, 
        emotion: str, 
        reason: str = "", 
        intensity: float = 0.5,
        triggered_by: int = None,
        group_id: int = None
    ):
        """保存情感状态到数据库"""
        import time
        await self._connection.execute(
            """INSERT INTO emotion_states (emotion, reason, intensity, triggered_by, group_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (emotion, reason, intensity, triggered_by, group_id, time.time())
        )
        await self._connection.commit()
        
        # 只保留最近100条记录
        await self._connection.execute(
            """DELETE FROM emotion_states WHERE id NOT IN 
               (SELECT id FROM emotion_states ORDER BY created_at DESC LIMIT 100)"""
        )
        await self._connection.commit()
    
    async def get_latest_emotion_state(self) -> Optional[dict]:
        """获取最新的情感状态"""
        cursor = await self._connection.execute(
            """SELECT emotion, reason, intensity, triggered_by, group_id, created_at 
               FROM emotion_states ORDER BY created_at DESC LIMIT 1"""
        )
        row = await cursor.fetchone()
        
        if row:
            from datetime import datetime
            return {
                "emotion": row[0],
                "reason": row[1],
                "intensity": row[2],
                "triggered_by": row[3],
                "group_id": row[4],
                "updated_at": datetime.fromtimestamp(row[5]).isoformat() if row[5] else None
            }
        return None
    
    async def get_emotion_history(self, limit: int = 20) -> list:
        """获取情感历史记录"""
        cursor = await self._connection.execute(
            """SELECT emotion, reason, intensity, triggered_by, group_id, created_at 
               FROM emotion_states ORDER BY created_at DESC LIMIT ?""",
            (limit,)
        )
        rows = await cursor.fetchall()
        
        from datetime import datetime
        return [
            {
                "emotion": row[0],
                "reason": row[1],
                "intensity": row[2],
                "triggered_by": row[3],
                "group_id": row[4],
                "updated_at": datetime.fromtimestamp(row[5]).isoformat() if row[5] else None
            }
            for row in rows
        ]
    
    # ============ 私聊黑名单管理 ============
    
    async def add_to_private_blacklist(
        self, 
        user_id: int, 
        set_by: int = 0, 
        reason: str = "",
        self_disabled: bool = False
    ):
        """添加到私聊黑名单"""
        import time
        await self._connection.execute(
            """INSERT OR REPLACE INTO private_chat_blacklist 
               (user_id, set_by, reason, self_disabled, created_at) VALUES (?, ?, ?, ?, ?)""",
            (user_id, set_by, reason, 1 if self_disabled else 0, time.time())
        )
        await self._connection.commit()
    
    async def remove_from_private_blacklist(self, user_id: int):
        """从私聊黑名单移除"""
        await self._connection.execute(
            "DELETE FROM private_chat_blacklist WHERE user_id = ?",
            (user_id,)
        )
        await self._connection.commit()
    
    async def is_private_blacklisted(self, user_id: int) -> bool:
        """检查用户是否在私聊黑名单中"""
        cursor = await self._connection.execute(
            "SELECT 1 FROM private_chat_blacklist WHERE user_id = ?",
            (user_id,)
        )
        return await cursor.fetchone() is not None
    
    async def get_private_blacklist_info(self, user_id: int) -> Optional[dict]:
        """获取私聊黑名单详情"""
        cursor = await self._connection.execute(
            """SELECT user_id, set_by, reason, self_disabled, created_at 
               FROM private_chat_blacklist WHERE user_id = ?""",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {
                "user_id": row[0],
                "set_by": row[1],
                "reason": row[2],
                "self_disabled": bool(row[3]),
                "created_at": row[4]
            }
        return None
    
    async def toggle_private_chat_mode(self, user_id: int, enabled: bool) -> bool:
        """
        切换用户的私聊模式
        
        Args:
            user_id: 用户QQ号
            enabled: True=允许AI主动私聊, False=禁止
        
        Returns:
            操作是否成功
        """
        if enabled:
            # 移除黑名单（如果是自己关闭的）
            info = await self.get_private_blacklist_info(user_id)
            if info and info.get("self_disabled"):
                await self.remove_from_private_blacklist(user_id)
            return True
        else:
            # 添加到黑名单（标记为自己关闭）
            await self.add_to_private_blacklist(
                user_id, 
                set_by=user_id, 
                reason="用户自己关闭私聊模式",
                self_disabled=True
            )
            return True
