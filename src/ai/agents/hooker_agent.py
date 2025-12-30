"""
Hooker Agent - 简化版条件触发消息代理

支持两种触发方式：
1. 时间触发 - 在特定时间点触发
2. 关键词触发 - 检测到特定关键词时触发

特性：
- 每个群组最多 5 个未触发的 Hook
- 使用 LLM 生成触发时的消息内容
"""

import asyncio
import os
import json
import uuid
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger("HookerAgent")


class TriggerType(Enum):
    """触发类型"""
    TIME = "time"        # 时间触发
    KEYWORD = "keyword"  # 关键词触发


@dataclass
class Hook:
    """Hook 数据结构（简化版）"""
    hook_id: str
    group_id: int
    trigger_type: str           # "time" 或 "keyword"
    trigger_value: str          # 时间触发：ISO格式时间字符串，关键词触发：关键词
    content_hint: str           # 内容提示/要发送的消息主题
    reason: str                 # 创建原因/说明
    created_at: float           # 创建时间戳
    triggered: bool = False     # 是否已触发
    trigger_time: Optional[float] = None  # 实际触发时间戳
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @staticmethod
    def from_dict(data: dict) -> 'Hook':
        return Hook(**data)
    
    def is_expired(self) -> bool:
        """检查是否过期（超过7天未触发）"""
        return (datetime.now().timestamp() - self.created_at) > 604800  # 7天


class HookerAgent:
    """
    Hooker Agent - 管理和执行定时/条件钩子（简化版）
    
    只支持：
    1. 时间触发 - 到达指定时间点时触发
    2. 关键词触发 - 检测到关键词时触发
    """
    
    MAX_HOOKS_PER_GROUP = 5
    HOOKS_DIR = "data/hooks"
    
    def __init__(self):
        self.hooks: Dict[str, Hook] = {}  # {hook_id: Hook}
        self.group_hooks: Dict[int, List[str]] = {}  # {group_id: [hook_ids]}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._message_callback: Optional[Callable] = None
        self._db = None
        self._llm_service = None  # LLM 服务引用（优先使用）
        
        # 确保目录存在
        os.makedirs(self.HOOKS_DIR, exist_ok=True)
        
        # 加载持久化的 hooks
        self._load_hooks()
    
    def set_db(self, db):
        """设置数据库引用"""
        self._db = db
    
    def set_llm_service(self, llm_service):
        """设置 LLM 服务引用（优先使用，保持人设和上下文）"""
        self._llm_service = llm_service
        logger.info("[HookerAgent] LLM service configured")
    
    def set_message_callback(self, callback: Callable):
        """设置消息发送回调"""
        self._message_callback = callback
    
    def _load_hooks(self):
        """从本地加载持久化的 hooks"""
        hooks_file = os.path.join(self.HOOKS_DIR, "hooks.json")
        if os.path.exists(hooks_file):
            try:
                with open(hooks_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for hook_data in data.get("hooks", []):
                        hook = Hook.from_dict(hook_data)
                        if not hook.triggered and not hook.is_expired():
                            self.hooks[hook.hook_id] = hook
                            if hook.group_id not in self.group_hooks:
                                self.group_hooks[hook.group_id] = []
                            self.group_hooks[hook.group_id].append(hook.hook_id)
                logger.info(f"[HookerAgent] Loaded {len(self.hooks)} pending hooks")
            except Exception as e:
                logger.error(f"[HookerAgent] Failed to load hooks: {e}")
    
    def _save_hooks(self):
        """持久化 hooks 到本地"""
        hooks_file = os.path.join(self.HOOKS_DIR, "hooks.json")
        try:
            data = {
                "hooks": [hook.to_dict() for hook in self.hooks.values()],
                "last_updated": datetime.now().isoformat()
            }
            with open(hooks_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[HookerAgent] Failed to save hooks: {e}")
    
    def get_group_pending_hooks(self, group_id: int) -> List[Hook]:
        """获取群组的未触发 hooks"""
        hook_ids = self.group_hooks.get(group_id, [])
        return [self.hooks[hid] for hid in hook_ids if hid in self.hooks and not self.hooks[hid].triggered]
    
    def get_hooks_list_for_ai(self, group_id: int) -> str:
        """生成给 AI 看的 hooks 列表 (增强版)"""
        hooks = self.get_group_pending_hooks(group_id)
        if not hooks:
            return "当前群组没有待触发的 Hook。"
        
        lines = [f"当前群组有 {len(hooks)}/{self.MAX_HOOKS_PER_GROUP} 个待触发的 Hook:", ""]
        lines.append("| ID (前8位) | 触发类型 | 触发条件 | 内容主题 |")
        lines.append("| --- | --- | --- | --- |")
        
        for h in hooks:
            type_str = "时间" if h.trigger_type == TriggerType.TIME.value else "关键词"
            value_display = h.trigger_value
            # 只取 ID 前 8 位方便引用
            lines.append(f"| {h.hook_id[:8]} | {type_str} | {value_display} | {h.content_hint} |")
        
        lines.append("\n💡 提示：你可以使用 edit_hook 工具来修改已有的 Hook，避免重复创建。")
        return "\n".join(lines)
    
    def edit_hook(
        self, 
        group_id: int,
        hook_id_prefix: str, 
        new_trigger_value: Optional[str] = None,
        new_content_hint: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        编辑 Hook
        
        Args:
            group_id: 群组 ID
            hook_id_prefix: Hook ID 的前缀（至少4位）
            new_trigger_value: 新的触发值（可选）
            new_content_hint: 新的内容描述（可选）
            
        Returns:
            (success, message)
        """
        # 查找匹配的 Hook
        target_hook = None
        for hid in self.group_hooks.get(group_id, []):
            if hid in self.hooks and hid.startswith(hook_id_prefix) and not self.hooks[hid].triggered:
                target_hook = self.hooks[hid]
                break
        
        if not target_hook:
            return False, f"未找到 ID 匹配 '{hook_id_prefix}' 的有效 Hook"
        
        # 更新字段
        changes = []
        if new_trigger_value:
            # 如果是时间触发，需要验证格式
            if target_hook.trigger_type == TriggerType.TIME.value:
                target_dt = self._parse_time_str(new_trigger_value)
                if not target_dt:
                     return False, f"无效的时间格式: {new_trigger_value}"
                
                # 更新时间
                target_hook.trigger_value = new_trigger_value
                target_hook.trigger_time = target_dt.timestamp()
                changes.append(f"触发时间改为 {target_dt}")
            else:
                target_hook.trigger_value = new_trigger_value
                changes.append(f"触发关键词改为 '{new_trigger_value}'")
        
        if new_content_hint:
            target_hook.content_hint = new_content_hint
            changes.append(f"内容主题更新")
        
        if not changes:
            return False, "没有提供要修改的内容"
        
        # 持久化
        self._save_hooks()
        return True, f"Hook 已更新: {', '.join(changes)}"
    
    def _parse_time_str(self, time_str: str) -> Optional[datetime]:
        """解析时间字符串，支持绝对时间和相对时间"""
        time_str = time_str.strip()
        now = datetime.now()
        
        # 1. 相对时间格式: +10s, +5m, +2h, +1d
        if time_str.startswith("+"):
            unit = time_str[-1].lower()
            try:
                val = int(time_str[1:-1])
                if unit == 's': return now + timedelta(seconds=val)
                elif unit == 'm': return now + timedelta(minutes=val)
                elif unit == 'h': return now + timedelta(hours=val)
                elif unit == 'd': return now + timedelta(days=val)
            except:
                pass
                
        # 2. 中文相对时间: 10秒后, 5分钟后, 2小时后
        import re
        match = re.match(r'(\d+)(秒|分钟|小时|天)后', time_str)
        if match:
            val = int(match.group(1))
            unit = match.group(2)
            if unit == '秒': return now + timedelta(seconds=val)
            elif unit == '分钟': return now + timedelta(minutes=val)
            elif unit == '小时': return now + timedelta(hours=val)
            elif unit == '天': return now + timedelta(days=val)
            
        # 3. 绝对时间格式
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%H:%M:%S", "%H:%M"]:
            try:
                # 对纯时间格式，假设是今天
                dt = datetime.strptime(time_str, fmt)
                if fmt in ["%H:%M:%S", "%H:%M"]:
                    dt = datetime.combine(now.date(), dt.time())
                    if dt <= now: # 如果时间已过，假设是明天
                         dt += timedelta(days=1)
                return dt
            except ValueError:
                continue
        
        # 4. 尝试 ISO 格式
        try:
            return datetime.fromisoformat(time_str)
        except:
            pass
            
        return None

    async def create_time_hook(
        self,
        group_id: int,
        target_time_str: str,  # ISO格式或自然语言（如"2024-12-25 00:00:00"）
        content_hint: str,
        reason: str = ""
    ) -> tuple[bool, str, Optional[str]]:
        """
        创建时间触发的 Hook
        
        Args:
            group_id: 群组 ID
            target_time_str: 目标时间（ISO格式字符串，如 "2024-12-25 00:00:00"）
            content_hint: 内容提示/主题（LLM 基于此生成消息）
            reason: 创建原因
        
        Returns:
            (success, message, hook_id)
        """
        # 检查群组 hook 数量限制
        pending = self.get_group_pending_hooks(group_id)
        if len(pending) >= self.MAX_HOOKS_PER_GROUP:
            return False, f"❌ 该群组已达到最大 Hook 数量限制 ({self.MAX_HOOKS_PER_GROUP})，请先取消一些旧的 Hook。", None
        
        # 解析时间
        target_time = self._parse_time_str(target_time_str)
        
        if not target_time:
             return False, f"❌ 无法解析时间格式: {target_time_str}。请使用如 '+10m'、'10分钟后' 或 'YYYY-MM-DD HH:MM:SS'。", None

        # 检查时间是否已过 (容忍1秒误差)
        if target_time <= datetime.now() - timedelta(seconds=1):
            return False, f"❌ 目标时间已过期: {target_time} (当前: {datetime.now().strftime('%H:%M:%S')})", None
        
        # 生成 Hook ID
        hook_id = uuid.uuid4().hex[:16]
        
        # 创建 Hook 对象
        hook = Hook(
            hook_id=hook_id,
            group_id=group_id,
            trigger_type=TriggerType.TIME.value,
            trigger_value=target_time.isoformat(),
            content_hint=content_hint,
            reason=reason,
            created_at=datetime.now().timestamp()
        )
        
        # 存储
        self.hooks[hook_id] = hook
        if group_id not in self.group_hooks:
            self.group_hooks[group_id] = []
        self.group_hooks[group_id].append(hook_id)
        
        # 持久化
        self._save_hooks()
        
        logger.info(f"[HookerAgent] Created time hook {hook_id} for {target_time_str}")
        
        return True, f"""✅ 时间触发 Hook 创建成功！
ID: {hook_id[:8]}
触发时间: {target_time_str}
内容主题: {content_hint}
原因: {reason}""", hook_id
    
    async def create_keyword_hook(
        self,
        group_id: int,
        keyword: str,
        content_hint: str,
        reason: str = ""
    ) -> tuple[bool, str, Optional[str]]:
        """
        创建关键词触发的 Hook
        
        Args:
            group_id: 群组 ID
            keyword: 关键词
            content_hint: 内容提示/主题（LLM 基于此生成消息）
            reason: 创建原因
        
        Returns:
            (success, message, hook_id)
        """
        # 检查群组 hook 数量限制
        pending = self.get_group_pending_hooks(group_id)
        if len(pending) >= self.MAX_HOOKS_PER_GROUP:
            return False, f"❌ 该群组已达到最大 Hook 数量限制 ({self.MAX_HOOKS_PER_GROUP})，请先取消一些旧的 Hook。", None
        
        # 生成 Hook ID
        hook_id = uuid.uuid4().hex[:16]
        
        # 创建 Hook 对象
        hook = Hook(
            hook_id=hook_id,
            group_id=group_id,
            trigger_type=TriggerType.KEYWORD.value,
            trigger_value=keyword.strip(),
            content_hint=content_hint,
            reason=reason,
            created_at=datetime.now().timestamp()
        )
        
        # 存储
        self.hooks[hook_id] = hook
        if group_id not in self.group_hooks:
            self.group_hooks[group_id] = []
        self.group_hooks[group_id].append(hook_id)
        
        # 持久化
        self._save_hooks()
        
        logger.info(f"[HookerAgent] Created keyword hook {hook_id} for '{keyword}'")
        
        return True, f"""✅ 关键词触发 Hook 创建成功！
ID: {hook_id[:8]}
关键词: {keyword}
内容主题: {content_hint}
原因: {reason}""", hook_id
    
    def cancel_hook(self, hook_id: str, group_id: Optional[int] = None) -> tuple[bool, str]:
        """取消一个 Hook"""
        # 支持前缀匹配
        matching_ids = [hid for hid in self.hooks.keys() if hid.startswith(hook_id)]
        
        if not matching_ids:
            return False, f"未找到 Hook: {hook_id}"
        
        if len(matching_ids) > 1:
            return False, f"多个 Hook 匹配 '{hook_id}'，请提供更精确的 ID: {', '.join([x[:8] for x in matching_ids])}"
        
        full_id = matching_ids[0]
        hook = self.hooks.get(full_id)
        
        if not hook:
            return False, f"未找到 Hook: {hook_id}"
        
        if group_id is not None and hook.group_id != group_id:
            return False, f"该 Hook 不属于当前群组"
        
        # 从存储中移除
        del self.hooks[full_id]
        if hook.group_id in self.group_hooks:
            self.group_hooks[hook.group_id] = [
                hid for hid in self.group_hooks[hook.group_id] if hid != full_id
            ]
        
        # 持久化
        self._save_hooks()
        
        logger.info(f"[HookerAgent] Cancelled hook {full_id}")
        return True, f"✅ 已取消 Hook: {full_id[:8]}"
    
    async def check_message_for_keyword_hooks(self, group_id: int, message_text: str):
        """
        检查消息是否触发关键词 Hook
        
        应该在消息处理流程中调用此方法
        """
        triggered_hooks = []
        
        for hook_id, hook in list(self.hooks.items()):
            if hook.triggered or hook.group_id != group_id:
                continue
            
            if hook.trigger_type == TriggerType.KEYWORD.value:
                # 检查关键词是否在消息中
                if hook.trigger_value in message_text:
                    triggered_hooks.append(hook)
                    hook.triggered = True
                    hook.trigger_time = datetime.now().timestamp()
                    logger.info(f"[HookerAgent] Keyword hook {hook_id} triggered by message: {message_text[:50]}")
        
        # 触发消息发送
        for hook in triggered_hooks:
            await self._trigger_hook_with_llm(hook)
        
        # 保存状态
        if triggered_hooks:
            self._save_hooks()
    
    async def check_and_trigger_time_hooks(self):
        """检查并触发满足时间条件的 hooks"""
        current_time = datetime.now()
        triggered_hooks = []
        
        for hook_id, hook in list(self.hooks.items()):
            if hook.triggered:
                continue
            
            # 检查是否过期
            if hook.is_expired():
                logger.info(f"[HookerAgent] Hook {hook_id} expired, removing")
                hook.triggered = True
                continue
            
            # 检查时间触发类型
            if hook.trigger_type == TriggerType.TIME.value:
                try:
                    target_time = datetime.fromisoformat(hook.trigger_value)
                    
                    # 检查是否到达目标时间
                    if current_time >= target_time:
                        triggered_hooks.append(hook)
                        
                        # 立即标记为已触发并保存状态
                        # 防止消息发送过程中的崩溃导致重复触发或状态不一致
                        hook.triggered = True
                        hook.trigger_time = datetime.now().timestamp()
                        logger.info(f"[HookerAgent] Time hook {hook_id} triggered at {current_time}")
                        self._save_hooks()
                except Exception as e:
                    logger.error(f"[HookerAgent] Failed to parse time for hook {hook_id}: {e}")
        
        # 触发消息发送 (串行处理，互不影响)
        for hook in triggered_hooks:
            try:
                await self._trigger_hook_with_llm(hook)
            except Exception as e:
                logger.error(f"[HookerAgent] Failed to trigger hook {hook.hook_id}: {e}")
    
    async def _trigger_hook_with_llm(self, hook: Hook):
        """使用 LLM 服务生成消息并发送（保持人设和上下文）"""
        if not self._message_callback:
            logger.warning("[HookerAgent] No message callback set")
            return
        
        # 直接使用 content_hint 作为消息内容（AI 创建 Hook 时已经提供了完整的话）
        content = hook.content_hint
        logger.info(f"[HookerAgent] Triggering hook {hook.hook_id} with message: {content[:50]}...")
        
        # 发送消息
        try:
            await self._message_callback(hook.group_id, content)
            logger.info(f"[HookerAgent] Sent message to group {hook.group_id}: {content[:50]}...")
        except Exception as e:
            logger.error(f"[HookerAgent] Failed to send message: {e}")
    
    async def start_monitoring(self):
        """启动后台监控循环（只监控时间触发）"""
        if self._running:
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("[HookerAgent] Monitoring started")
    
    async def stop_monitoring(self):
        """停止后台监控"""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("[HookerAgent] Monitoring stopped")
    
    async def _monitoring_loop(self):
        """监控循环（只检查时间触发）"""
        ticks = 0
        logger.info("[HookerAgent] Worker loop started")
        
        while self._running:
            try:
                # 心跳日志 (每 60 秒)
                if ticks % 12 == 0:
                    logger.info("[HookerAgent] Worker heartbeat - scanning hooks...")
                
                await self.check_and_trigger_time_hooks()
                
            except asyncio.CancelledError:
                logger.info("[HookerAgent] Worker task cancelled")
                break
            except BaseException as e:
                # 捕获所有异常（包括系统退出以外的严重错误），防止循环崩溃
                logger.error(f"[HookerAgent] CRITICAL monitoring error: {e}")
                import traceback
                traceback.print_exc()
            
            ticks += 1
            # 每 5 秒检查一次
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break


# 全局单例
hooker_agent = HookerAgent()
