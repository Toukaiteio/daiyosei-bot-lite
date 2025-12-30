"""
DaiyoseiBot - 基于 OneBot V11 反向 WebSocket 的拟人化群聊机器人
"""
import os
import asyncio
import base64
import json
import random
import traceback
from typing import Optional
from datetime import datetime

from aiocqhttp import CQHttp, Event, MessageSegment

from ..config import config
from ..database.db import Database
from .handler import GameHandler, GameResponse


def log(level: str, msg: str):
    """简单日志函数"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


class DaiyoseiBot:
    """
    琪露诺机器人
    
    基于 aiocqhttp 实现的反向 WebSocket 服务器，
    接收来自 NapCat/OneBot 的消息并处理聊天逻辑。
    """
    
    def __init__(self):
        self._bot = CQHttp()
        self._db: Optional[Database] = None
        self._handler: Optional[GameHandler] = None
        self._running = False
        
        # 注册消息处理器
        self._register_handlers()
    
    async def _on_handler_proactive_message(self, target_id: int, response: GameResponse, is_group: bool = True):
        """处理来自 Handler 的即时主动消息"""
        try:
            # 统一分发逻辑
            await self._dispatch_response(target_id, response, is_group)
        except Exception as e:
            log("ERROR", f"发送即时主动消息出错: {e}")
            
    async def _dispatch_response(self, target_id: int, response: GameResponse, is_group: bool):
        """
        统一的消息发送分发核心 (Implementation of send_message)
        
        Args:
           target_id: group_id or user_id
           response: GameResponse Object
           is_group: True for group message, False for private message
        """
        if not hasattr(response, 'multi_segments') or not response.multi_segments:
            return

        for i, segment in enumerate(response.multi_segments):
            text = segment.get("text", "")
            image_path = segment.get("image_path")
            custom_action = segment.get("custom_action")
            
            # 1. 特殊消息处理: 自定义动作 (Node, File, API calls)
            if custom_action:
                try:
                    action = custom_action.get("action")
                    params = custom_action.get("params", {})
                    if action:
                        # 自动补全 ID
                        if is_group and "group_id" not in params:
                            params["group_id"] = target_id
                        elif not is_group and "user_id" not in params:
                            params["user_id"] = target_id
                        
                        log("DEBUG", f"执行自定义动作: {action}, target: {target_id}")
                        await self._bot.call_action(action, **params)
                except Exception as e:
                    log("ERROR", f"执行自定义动作失败: {e}")
                continue

            # 2. 普通消息转换与构建
            msg_chain = []
            
            # 这里的 reply_to 主要是针对这轮对话的首次回复
            # 如果是多条气泡，通常只在第一条引用 (或者根据业务需求)
            if i == 0 and response.reply_to:
                msg_chain.append(MessageSegment.reply(response.reply_to))
                
            # 添加图片
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as f:
                        image_data = base64.b64encode(f.read()).decode()
                    msg_chain.append(MessageSegment.image(f"base64://{image_data}"))
                except Exception as e:
                    log("ERROR", f"读取图片失败: {e}")
            
            # 添加文本 (OneBot v11 JSON 数组格式转换)
            if text:
                parsed_text_segments = self._build_message_segments(text)
                msg_chain.extend(parsed_text_segments)
            
            # 检查实质内容
            has_substance = bool(image_path and os.path.exists(image_path)) or bool(text and text.strip())
            if not has_substance:
                continue
                
            # 3. 底层发送 (_dispatch_send equivalent)
            try:
                if is_group:
                    log("INFO", f"Sending group msg to {target_id} (segment {i+1})...")
                    await self._bot.send_group_msg(group_id=target_id, message=msg_chain)
                else:
                    log("INFO", f"Sending private msg to {target_id} (segment {i+1})...")
                    await self._bot.send_private_msg(user_id=target_id, message=msg_chain)
            except Exception as e:
                log("ERROR", f"发送消息气泡失败: {e}")
                # 私聊发送失败时重新抛出，以便调用者知道失败（如好友检测）
                if not is_group:
                    raise
            
            # 气泡延迟
            if i < len(response.multi_segments) - 1:
                await asyncio.sleep(1.5)

            
    def _register_handlers(self):
        """注册消息处理器"""
        
        # 添加一个通用的事件处理器来捕获所有事件
        @self._bot.on('message')
        async def handle_all_messages(event: Event):
            """处理所有消息事件"""
            log("DEBUG", f">>> 收到消息事件: {event.post_type}")
            log("DEBUG", f"    消息类型: {getattr(event, 'message_type', 'unknown')}")
            log("DEBUG", f"    用户ID: {getattr(event, 'user_id', 'unknown')}")
            log("DEBUG", f"    群ID: {getattr(event, 'group_id', 'unknown')}")
            log("DEBUG", f"    原始消息: {getattr(event, 'message', 'unknown')}")
            log("DEBUG", f"    Raw message type: {type(event.message)}")
            
            # 打印完整事件数据用于调试
            try:
                event_dict = {k: v for k, v in event.__dict__.items() if not k.startswith('_')}
                log("DEBUG", f"    完整事件: {json.dumps(event_dict, ensure_ascii=False, default=str)[:500]}")
            except Exception as e:
                log("DEBUG", f"    无法序列化事件: {e}")
            
            # Blacklist interception layer
            user_id = getattr(event, 'user_id', None)
            group_id = getattr(event, 'group_id', 0)
            if user_id and self._db:
                if await self._db.is_blacklisted(user_id, group_id):
                    log("INFO", f"🚫 [Blacklist] 拦截黑名单用户消息: User={user_id}, Group={group_id}")
                    return
            
            # 根据消息类型分发处理
            msg_type = getattr(event, 'message_type', None)
            if msg_type == 'group':
                await self._process_group_message(event)
            elif msg_type == 'private':
                await self._process_private_message(event)
            else:
                log("WARN", f"未知消息类型: {msg_type}")
        
        @self._bot.on_meta_event
        async def handle_meta(event: Event):
            """处理元事件（心跳等）"""
            if event.meta_event_type == "lifecycle":
                log("INFO", f"生命周期事件: {event.sub_type}")
                if event.sub_type == "connect":
                    # 尝试获取机器人 QQ 号
                    self_id = getattr(event, 'self_id', None)
                    if self_id:
                        self._bot.self_id = self_id
                        if self._handler:
                            self._handler.self_id = int(self_id)
                        log("INFO", f"机器人 QQ: {self_id}")
                    print(f"✅ OneBot 客户端已连接")
                    
                    # 关键修复：在正确的事件循环中启动后台任务
                    if self._handler:
                        self._handler.start_background_tasks()
                    
                    # 启动任务队列
                    from ..utils.task_queue import task_queue
                    await task_queue.start()
            # 心跳事件也会带有 self_id
            elif event.meta_event_type == "heartbeat":
                self_id = getattr(event, 'self_id', None)
                if self_id and not hasattr(self._bot, 'self_id'):
                    self._bot.self_id = self_id
                    log("INFO", f"从心跳获取机器人 QQ: {self_id}")
                
                # 检查是否有待发送的主动消息
                if self._handler:
                    await self._check_proactive_messages()
        
        @self._bot.on_notice
        async def handle_notice(event: Event):
            """处理通知事件"""
            log("DEBUG", f"通知事件: {getattr(event, 'notice_type', 'unknown')}")
        
        @self._bot.on_request
        async def handle_request(event: Event):
            """处理请求事件（好友请求、群邀请等）"""
            request_type = getattr(event, 'request_type', None)
            
            if request_type == 'friend':
                # 好友添加请求
                await self._handle_friend_request(event)
            elif request_type == 'group':
                # 群邀请或加群请求
                log("INFO", f"收到群请求: {getattr(event, 'sub_type', 'unknown')}")
    
    def _extract_text_from_message(self, message) -> tuple[str, bool, int]:
        """
        从 OneBot 消息中提取纯文本内容
        
        Args:
            message: event.message (可能是 list 或 str)
            
        Returns:
            (纯文本内容, 是否@了机器人, 机器人QQ号)
        """
        text_parts = []
        at_self = False
        self_id = getattr(self._bot, 'self_id', None)
        
        # 如果是 list (array 格式)
        if isinstance(message, list):
            for seg in message:
                if isinstance(seg, dict):
                    seg_type = seg.get('type', '')
                    seg_data = seg.get('data', {})
                    
                    if seg_type == 'text':
                        text_parts.append(seg_data.get('text', ''))
                    elif seg_type == 'at':
                        at_qq = seg_data.get('qq', '')
                        # 检查是否 @ 了机器人，是则标记 at_self
                        if self_id and str(at_qq) == str(self_id):
                            at_self = True
                            # 即使是 @机器人，也保留标准格式 [AT: QQ] 吗？
                            # 为了让 LLM 清楚知道是艾特自己，可以使用 [@bot] 或 [AT: self_id]
                            # 这里我们保留两者语义：[@bot] 用于强调，[AT: QQ] 用于统一
                            # 简化起见，对 @机器人 使用 [@bot]，对其他人使用 [AT: QQ]
                            text_parts.append('[@bot] ')
                        elif at_qq == 'all':
                            at_self = True  # @全体成员也响应
                            text_parts.append('[@all] ')
                        else:
                            # 保留艾特其他人的信息！这是之前漏掉的
                            text_parts.append(f'[AT: {at_qq}] ')
                            
                    elif seg_type == 'image':
                        # 提取图片哈希和URL，格式化为 [IMG:hash|url]
                        # file 通常是 {hash}.image 格式
                        file_name = seg_data.get('file', '')
                        url = seg_data.get('url', '')
                        img_hash = file_name.split('.')[0] if file_name else 'unknown'
                        text_parts.append(f'[IMG:{img_hash}|{url}]')
                else:
                    # aiocqhttp 的 MessageSegment 对象
                    if hasattr(seg, 'type') and hasattr(seg, 'data'):
                        if seg.type == 'text':
                            text_parts.append(seg.data.get('text', ''))
                        elif seg.type == 'at':
                            at_qq = seg.data.get('qq', '')
                            if self_id and str(at_qq) == str(self_id):
                                at_self = True
                                text_parts.append('[@bot] ')
                            else:
                                text_parts.append(f'[AT: {at_qq}] ')
                        elif seg.type == 'image':
                            file_name = seg.data.get('file', '')
                            url = seg.data.get('url', '')
                            img_hash = file_name.split('.')[0] if file_name else 'unknown'
                            text_parts.append(f'[IMG:{img_hash}|{url}]')
        else:
            # 字符串格式 (CQ码)
            text_parts.append(str(message))
            # 简单检测 CQ:at
            if self_id and f'[CQ:at,qq={self_id}]' in str(message):
                at_self = True
                # 在字符串开头添加 [@bot] 标记可能不准确，但也只能这样
                # 更理想的是正则替换，但这里先简单处理
                if '[@bot]' not in str(message): 
                     text_parts.insert(0, '[@bot] ')
        
        return ''.join(text_parts).strip(), at_self, self_id
    
    async def _process_group_message(self, event: Event):
        """处理群消息"""
        user_id = event.user_id
        group_id = event.group_id
        
        # 正确解析消息内容
        text_content, at_self, self_id = self._extract_text_from_message(event.message)
        
        log("INFO", f"=== 处理群消息 ===")
        log("INFO", f"用户: {user_id}, 群: {group_id}")
        log("INFO", f"提取的文本: '{text_content}'")
        
        # 0. 如果是机器人自己的消息，只添加到上下文，不触发处理
        if self_id and str(user_id) == str(self_id):
            log("DEBUG", "检测到自身发送的消息，检查是否需要添加到上下文")
            if self._handler:
                # 检查最后一条消息是否相同，避免重复（因为 process_message 可能已经加过了）
                last_msgs = self._handler._get_context(group_id, limit=1)
                should_add = True
                if last_msgs:
                    last_msg = last_msgs[-1]
                    # 检查发送者是否是自己，且内容是否极其相似（去空格后）
                    if (str(last_msg.get('sender_id')) == str(self_id) and 
                        last_msg.get('content', '').strip() == text_content.strip()):
                        should_add = False
                        log("DEBUG", "检测到重复的自身消息（已在上下文中），跳过添加")
                
                if should_add:
                    self._handler._add_to_context(
                        group_id, 
                        config.bot_info.name, 
                        user_id, 
                        text_content, 
                        role="assistant",
                        message_id=event.message_id  # 添加消息ID
                    )
            return
        
        # 检查是否是回复消息 (检查消息段中的 reply 类型)
        reply_id = None
        if isinstance(event.message, list):
            for seg in event.message:
                if isinstance(seg, dict) and seg.get('type') == 'reply':
                    reply_id = seg.get('data', {}).get('id')
                    break
                elif hasattr(seg, 'type') and seg.type == 'reply':
                    reply_id = seg.data.get('id')
                    break
        
        # 也可以检查 event.reply (NapCat/Go-CQHTTP 扩展字段)
        if not reply_id and getattr(event, 'reply', None):
            reply_id = event.reply.get('message_id')

        is_reply_to_me = False
        reply_content_text = ""
        reply_sender_nickname = ""
        
        if reply_id:
            try:
                log("DEBUG", f"检测到回复消息 struct, ID: {reply_id}, 正在拉取原始内容...")
                # 调用 get_msg 获取被回复的消息详情
                reply_msg_data = await self._bot.get_msg(message_id=int(reply_id))
                
                if reply_msg_data:
                    # 提取发送者信息
                    r_sender = reply_msg_data.get('sender', {})
                    reply_sender_id = r_sender.get('user_id')
                    reply_sender_nickname = r_sender.get('nickname', '未知')
                    
                    # 检查是否回复的机器人
                    if self_id and str(reply_sender_id) == str(self_id):
                        is_reply_to_me = True
                        log("DEBUG", "检测到回复机器人的消息")
                    
                    # 提取被回复的消息内容
                    r_message = reply_msg_data.get('message')
                    r_text, _, _ = self._extract_text_from_message(r_message)
                    reply_content_text = r_text
                    
                    # 引用消息中的图片：显示完整URL，因为用户可能在询问引用的图片
                    if isinstance(r_message, list):
                        for seg in r_message:
                             if isinstance(seg, dict) and seg.get('type') == 'image':
                                url = seg.get('data', {}).get('url', '')
                                if url: reply_content_text += f"[图片:{url}]"
                    
                    log("DEBUG", f"获取到引用内容: {reply_sender_nickname}: {reply_content_text[:30]}...")
                    
            except Exception as e:
                log("WARN", f"拉取回复消息失败: {e}")
                # Fallback: 尝试使用 event.reply 如果存在
                if getattr(event, 'reply', None):
                    r_sender_id = event.reply.get('sender', {}).get('user_id')
                    if self_id and str(r_sender_id) == str(self_id):
                        is_reply_to_me = True
                    # 尝试提取文本（可能不完整）
                    reply_content_text = str(event.reply.get('message', ''))

        # 将引用内容附加到文本中,供 AI 理解上下文
        # 格式包含QQ号，便于AI进行AT操作和记忆关联
        if reply_content_text:
            if reply_sender_id:
                text_content += f"\n[引用 {reply_sender_nickname}(QQ:{reply_sender_id}): {reply_content_text}]"
            else:
                text_content += f"\n[引用 {reply_sender_nickname}: {reply_content_text}]"
            log("DEBUG", f"附加引用内容后的完整消息: {text_content}")

        # 合并触发条件 (at_self OR is_reply_to_me) 
        # 我们统一传给 handler 的 at_self 参数,或者改名为 triggered_directly
        should_trigger = at_self or is_reply_to_me
        
        log("DEBUG", f"是否触发: {should_trigger} (At: {at_self}, Reply: {is_reply_to_me})")
        
        # 只有被 @ 时才响应 -> 交给 handler 判断
        # if not at_self:
        #     log("DEBUG", "未被@，忽略消息")
        #     return
        
        # 获取发送者信息
        sender = event.sender or {}
        nickname = sender.get("nickname") or sender.get("card") or "群友"
        role = sender.get("role", "member") # 获取角色：owner, admin, member
        
        log("DEBUG", f"昵称: {nickname}, 角色: {role}")
        
        # 检查 handler 是否初始化
        if not self._handler:
            log("ERROR", "Handler 未初始化!")
            return
        
        if self_id and self._handler:
            self._handler.self_id = int(self_id)
            
        try:
            log("DEBUG", "调用 handler.process_message...")
            response = await self._handler.process_message(
                user_id=user_id,
                group_id=group_id,
                nickname=nickname,
                message=text_content,
                message_id=event.message_id,
                sender_role=role,
                at_self=should_trigger
            )
            
            if response:
                first_text = response.multi_segments[0].get("text", "") if response.multi_segments else "None"
                log("INFO", f"发送响应: text={first_text[:50]}...")
                await self._send_response(event, response, is_group=True)
                
        except Exception as e:
            log("ERROR", f"处理消息时出错: {e}")
            import traceback
            traceback.print_exc()
    
    async def _process_private_message(self, event: Event):
        """处理私聊消息"""
        user_id = event.user_id
        
        # 正确解析消息内容（私聊不需要检查@）
        text_content, _, _ = self._extract_text_from_message(event.message)
        
        log("INFO", f"=== 处理私聊消息 ===")
        log("INFO", f"用户: {user_id}")
        log("INFO", f"提取的文本: '{text_content}'")
        
        # 2. 对话处理
        return await self._handler.handle_private_message(user_id, text_content)

        
        # 私聊使用 user_id 作为 session_id
        session_id = user_id
        
        sender = event.sender or {}
        nickname = sender.get("nickname") or "用户"
        role = sender.get("role", "private") # 私聊角色默认为 private
        
        # 检查 handler 是否初始化
        if not self._handler:
            log("ERROR", "Handler 未初始化!")
            return
        
        try:
            response = await self._handler.process_message(
                user_id=user_id,
                group_id=session_id,
                nickname=nickname,
                message=text_content,
                message_id=event.message_id,
                sender_role=role,
                at_self=True, # 私聊默认视为直接触发
                is_group=False  # 标记为私聊
            )
            
            if response:
                first_text = response.multi_segments[0].get("text", "") if response.multi_segments else "None"
                log("INFO", f"发送响应: {first_text[:50]}...")
                await self._send_response(event, response, is_group=False)
                
        except Exception as e:
            log("ERROR", f"处理私聊消息时出错: {e}")
            traceback.print_exc()
    
    async def _handle_friend_request(self, event: Event):
        """
        处理好友添加请求
        
        基于用户记忆决定是否同意：
        1. 如果用户有互动记录（记忆库中存在），自动同意
        2. 如果是陌生人，根据验证消息和配置决定
        """
        user_id = getattr(event, 'user_id', 0)
        flag = getattr(event, 'flag', '')
        comment = getattr(event, 'comment', '')  # 验证消息
        
        log("INFO", f"=== 收到好友请求 ===")
        log("INFO", f"用户ID: {user_id}")
        log("INFO", f"验证消息: {comment}")
        
        should_approve = False
        reason = ""
        
        try:
            # 1. 检查用户记忆
            if self._handler and hasattr(self._handler, '_memory_store') and self._handler._memory_store:
                memory_store = self._handler._memory_store
                user_memory = await memory_store.recall_about_user(user_id)
                
                if user_memory:
                    # 有互动记录，自动同意
                    interaction_count = user_memory.get('interaction_count', 0)
                    nickname = user_memory.get('nickname', '用户')
                    should_approve = True
                    reason = f"老朋友 {nickname} (互动{interaction_count}次)"
                    log("INFO", f"用户有记忆记录: {reason}")
            
            # 2. 如果没有记忆，检查验证消息
            if not should_approve and comment:
                # 检查是否包含关键词（简单规则）
                approve_keywords = ["琪露诺", "⑨", "bot", "机器人", "你好", "想加你"]
                if any(k.lower() in comment.lower() for k in approve_keywords):
                    should_approve = True
                    reason = f"验证消息包含关键词: {comment[:20]}"
            
            # 3. 默认策略：同意所有请求（可通过配置修改）
            if not should_approve:
                # 默认同意，让AI有机会认识新朋友
                should_approve = True
                reason = "新朋友，欢迎认识~"
            
            # 执行操作
            if should_approve:
                log("INFO", f"同意好友请求: {reason}")
                await self._bot.call_action(
                    'set_friend_add_request',
                    flag=flag,
                    approve=True,
                    remark=""  # 可以设置备注
                )
                
                # 发送欢迎消息（延迟2秒后）
                async def send_welcome():
                    await asyncio.sleep(2)
                    try:
                        welcome_msgs = [
                            "嘿嘿，你好呀~ 我是琪露诺，最强的冰精灵！有什么想聊的吗？",
                            "哇！是新朋友！你好你好~ 我是⑨哦~",
                            "欢迎欢迎！以后有什么事可以找我聊天哦~"
                        ]
                        import random
                        await self._bot.send_private_msg(user_id=user_id, message=random.choice(welcome_msgs))
                    except Exception as e:
                        log("WARNING", f"发送欢迎消息失败: {e}")
                
                asyncio.create_task(send_welcome())
            else:
                log("INFO", f"拒绝好友请求: {reason}")
                await self._bot.call_action(
                    'set_friend_add_request',
                    flag=flag,
                    approve=False
                )
                
        except Exception as e:
            log("ERROR", f"处理好友请求失败: {e}")
            import traceback
            traceback.print_exc()
    
    async def _check_proactive_messages(self):
        """检查并发送待发送的主动消息"""
        if not self._handler:
            return
        
        # 获取所有有待发送消息的群
        if not hasattr(self._handler, '_pending_proactive_messages'):
            return
        
        # 复制一份待处理列表
        pending_groups = list(self._handler._pending_proactive_messages.keys())
        
        for group_id in pending_groups:
            data = self._handler.get_proactive_message(group_id)
            if not data:
                continue
            
            text = data.get("text", "")
            meme_path = data.get("meme_path")
            
            try:
                log("INFO", f"[ProactiveChat] 向群 {group_id} 发送主动消息: {text[:30]}...")
                
                # 构造消息段
                msg_segments = []
                if meme_path and os.path.exists(meme_path):
                    with open(meme_path, "rb") as f:
                        image_data = base64.b64encode(f.read()).decode()
                    msg_segments.append(MessageSegment.image(f"base64://{image_data}"))
                    if text:
                        msg_segments.append(MessageSegment.text(f"\n{text}"))
                elif text:
                    msg_segments.append(MessageSegment.text(text))
                
                if msg_segments:
                    await self._bot.send_group_msg(
                        group_id=group_id,
                        message=msg_segments
                    )
            except Exception as e:
                log("ERROR", f"发送主动消息失败: {e}")
    
    async def _send_response(self, event: Event, response: GameResponse, is_group: bool):
        """发送响应 - 真正的分条发送"""
        if not hasattr(response, 'multi_segments') or not response.multi_segments:
            return

        for i, segment in enumerate(response.multi_segments):
            text = segment.get("text", "")
            image_path = segment.get("image_path")
            custom_action = segment.get("custom_action")
            
            # 如果存在自定义动作（例如合并转发）
            if custom_action:
                try:
                    action = custom_action.get("action")
                    params = custom_action.get("params", {})
                    if action:
                        # 补充 group_id 或 user_id 如果缺失
                        if is_group and "group_id" not in params:
                            params["group_id"] = event.group_id
                        elif not is_group and "user_id" not in params:
                            params["user_id"] = event.user_id
                        
                        await self._bot.call_action(action, **params)
                except Exception as e:
                    log("ERROR", f"执行自定义动作失败: {e}")
                continue

            # 构造消息段列表
            msg_chain = []
            
            # 如果是第一条消息且有回复目标
            if i == 0 and response.reply_to:
                msg_chain.append(MessageSegment.reply(response.reply_to))
                
            # 添加图片（如果存在）
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as f:
                        image_data = base64.b64encode(f.read()).decode()
                    msg_chain.append(MessageSegment.image(f"base64://{image_data}"))
                except Exception as e:
                    log("ERROR", f"读取图片失败: {e}")
            
            # 添加文本并解析 [AT: QQ]
            if text:
                parsed_text_segments = self._build_message_segments(text)
                msg_chain.extend(parsed_text_segments)
            
            # 检查是否有实质性内容（文字或图片）
            has_substance = bool(image_path and os.path.exists(image_path)) or bool(text and text.strip())
            
            # 如果没有任何实质内容，跳过该气泡（即使它有 reply_to）
            if not has_substance:
                continue
                
            # 发送当前气泡
            try:
                if is_group:
                    await self._bot.send_group_msg(group_id=event.group_id, message=msg_chain)
                else:
                    await self._bot.send_private_msg(user_id=event.user_id, message=msg_chain)
            except Exception as e:
                log("ERROR", f"发送消息气泡失败: {e}")
            
            # 气泡之间的硬性延迟 1.5 秒
            if i < len(response.multi_segments) - 1:
                await asyncio.sleep(1.5)

    def _build_message_segments(self, text: str) -> list:
        """解析文本中的 [AT: QQ] 标签并构造消息段列表
        
        增强版：
        1. 支持容错匹配常见格式错误（[AT:123]、[AT 123]等）
        2. 过滤掉看起来像用户消息元数据的错误AT（如 花山由(QQ:123)[owner]: ）
        """
        import re
        
        # 第一步：预处理文本，修正一些常见格式错误
        # 1. [AT:123] -> [AT: 123]（缺少空格）
        text = re.sub(r'\[AT:(\d+)\]', r'[AT: \1]', text)
        # 2. [AT 123] -> [AT: 123]（缺少冒号）
        text = re.sub(r'\[AT\s+(\d+)\]', r'[AT: \1]', text)
        # 3. [at: 123] -> [AT: 123]（大小写）
        text = re.sub(r'\[at:\s*(\d+)\]', r'[AT: \1]', text, flags=re.IGNORECASE)
        
        # 第二步：过滤掉看起来像用户消息元数据的内容
        # 例如 "花山由(QQ:2827087188)[owner]: 你好" 不应该被当作AT指令
        # 先检测并移除这种格式的 AT 误匹配
        # 匹配 "姓名(QQ:ID)[角色]: " 这种格式（用户消息元数据）
        metadata_pattern = r'([^\[\]]+)\(QQ:(\d+)\)\[(owner|admin|member)\]:\s*'
        # 不要将这种格式中的 QQ 号当作 AT
        
        segments = []
        pattern = r'\[AT:\s*(\d+)\]'
        last_pos = 0
        
        for match in re.finditer(pattern, text):
            qq_number = match.group(1)
            
            # 检查这个 AT 标签是否在用户元数据格式中（误识别）
            # 查看匹配位置之前的文本，看是否包含 "(QQ:" 模式
            before_text = text[max(0, match.start()-50):match.start()]
            
            # 如果在元数据格式中，跳过这个匹配
            # 元数据格式应该是 "姓名(QQ:ID)[角色]: " 形式
            # AT格式应该是独立的 "[AT: ID]"
            # 简单检测：如果前面有 (QQ: 且后面紧跟 )[...]，说明是元数据
            if re.search(r'\(QQ:' + re.escape(qq_number) + r'\)\[', text[:match.end()+10]):
                # 这可能是元数据，不是AT，跳过
                continue
            
            # 添加匹配前的文本
            if match.start() > last_pos:
                segments.append(MessageSegment.text(text[last_pos:match.start()]))
            # 添加 AT 段
            segments.append(MessageSegment.at(qq_number))
            last_pos = match.end()
            
        # 添加剩余文本
        if last_pos < len(text):
            segments.append(MessageSegment.text(text[last_pos:]))
            
        return segments if segments else [MessageSegment.text(text)]
    
    async def start(self):
        """启动机器人"""
        print("=" * 50)
        print("❄️  DaiyoseiBot - 拟人化群聊机器人 (琪露诺)")
        print("=" * 50)
        
        # 初始化数据库
        print("📦 正在初始化数据库...")
        self._db = Database(config.database.db_path)
        await self._db.connect()
        print("✅ 数据库初始化完成")
        
        # 初始化聊天处理器
        print("💭 正在初始化聊天引擎...")
        self._handler = GameHandler(self._db)
        # 设置即时发送回调
        self._handler.set_sender_callback(self._on_handler_proactive_message)
        await self._handler.init()
        print("✅ 聊天引擎初始化完成")
        
        # 启动 WebSocket 服务器
        print(f"\n🌐 正在启动 WebSocket 服务器...")
        print(f"   地址: ws://{config.websocket.host}:{config.websocket.port}/")
        print(f"\n💡 请在 NapCat 配置中添加反向 WebSocket 地址:")
        print(f"   ws://{config.websocket.host}:{config.websocket.port}/")
        print("\n⏳ 等待 NapCat 连接...")
        
        self._running = True
        
        # 运行 bot
        self._bot.run(
            host=config.websocket.host,
            port=config.websocket.port
        )
    
    async def stop(self):
        """停止机器人"""
        self._running = False
        
        # 关闭数据库
        if self._db:
            print("📦 正在关闭数据库连接...")
            await self._db.close()
            
        print("👋 机器人已停止")


def run_bot():
    """启动机器人（同步入口）"""
    bot = DaiyoseiBot()
    
    try:
        # aiocqhttp.CQHttp.run() 内部会处理事件循环
        # 我们需要先初始化数据库
        async def init_and_run():
            print("=" * 50)
            print("❄️  DaiyoseiBot - 拟人化群聊机器人 (琪露诺)")
            print("=" * 50)
            
            # 初始化数据库
            print("📦 正在初始化数据库...")
            bot._db = Database(config.database.db_path)
            await bot._db.connect()
            print("✅ 数据库初始化完成")
            
            # 初始化聊天处理器
            print("💭 正在初始化聊天引擎...")
            bot._handler = GameHandler(bot._db)
            await bot._handler.init()
            print("✅ 聊天引擎初始化完成")
        
        # 运行初始化
        loop = asyncio.get_event_loop()
        # 这里我们在 run 之前确保 init 里的任务都进入了 loop
        loop.run_until_complete(init_and_run())
        
        # 再次确保 handler 的回调已经设置（虽然 init_and_run 里已经做了）
        if bot._handler:
            bot._handler.set_sender_callback(bot._on_handler_proactive_message)
        
        # 启动 WebSocket 服务器
        print(f"\n🌐 正在启动 WebSocket 服务器...")
        print(f"   地址: ws://{config.websocket.host}:{config.websocket.port}/")
        print(f"\n💡 请在 NapCat 配置中添加反向 WebSocket 地址:")
        print(f"   ws://{config.websocket.host}:{config.websocket.port}/")
        print("\n⏳ 等待 NapCat 连接...\n")
        
        bot._bot.run(
            host=config.websocket.host,
            port=config.websocket.port
        )
        
    except KeyboardInterrupt:
        print("\n👋 收到停止信号，正在停止机器人...")
        # 运行清理逻辑
        loop = asyncio.get_event_loop()
        loop.run_until_complete(bot.stop())
        
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
