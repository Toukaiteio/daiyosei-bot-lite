"""
命令系统 - 处理 $$ 开头的命令
"""
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass
import re
import asyncio
import base64
import os
from ..utils.bilibili_cos import BilibiliCos
from ..utils.task_queue import task_queue

@dataclass
class CommandResult:
    """命令执行结果"""
    success: bool
    response: str
    image_path: Optional[str] = None
    custom_action: Optional[dict] = None # 自定义动作 (例如 { "action": "send_group_forward_msg", "params": {...} })
    

class Command:
    """命令定义"""
    def __init__(
        self, 
        name: str, 
        aliases: List[str], 
        handler: Callable,
        description: str = "",
        usage: str = ""
    ):
        self.name = name
        self.aliases = aliases  # 命令别名列表
        self.handler = handler  # 异步处理函数
        self.description = description
        self.usage = usage


class CommandSystem:
    """命令系统"""
    
    def __init__(self):
        self.commands: Dict[str, Command] = {}
        self._register_builtin_commands()
    
    def register_command(
        self, 
        name: str, 
        aliases: List[str], 
        handler: Callable,
        description: str = "",
        usage: str = ""
    ):
        """注册命令"""
        cmd = Command(name, aliases, handler, description, usage)
        # 注册主命令名
        self.commands[name.lower()] = cmd
        # 注册所有别名
        for alias in aliases:
            self.commands[alias.lower()] = cmd
        print(f"[CommandSystem] 注册命令: {name} (别名: {', '.join(aliases)})")
    
    def _register_builtin_commands(self):
        """注册内置命令"""
        # 帮助命令
        self.register_command(
            name="help",
            aliases=["帮助", "命令", "?"],
            handler=self._cmd_help,
            description="显示所有可用命令",
            usage="$$help 或 $$帮助"
        )
        
        # 状态命令
        self.register_command(
            name="status",
            aliases=["状态", "info"],
            handler=self._cmd_status,
            description="显示机器人状态",
            usage="$$status 或 $$状态"
        )
        
        # ping命令
        self.register_command(
            name="ping",
            aliases=["延迟"],
            handler=self._cmd_ping,
            description="测试机器人响应",
            usage="$$ping"
        )
    
    async def parse_and_execute(
        self, 
        message: str, 
        user_id: int, 
        group_id: int, 
        context: Dict[str, Any]
    ) -> Optional[CommandResult]:
        """
        解析并执行命令
        
        Args:
            message: 完整消息内容
            user_id: 用户QQ号
            group_id: 群号
            context: 上下文信息（如数据库、处理器等）
        
        Returns:
            CommandResult 如果是命令并已执行
            None 如果不是命令，应该进入LLM处理
        """
        # 检查是否是命令格式
        if not message.strip().startswith("$$"):
            return None
        
        # 移除 $$ 前缀
        cmd_text = message.strip()[2:].strip()
        
        if not cmd_text:
            return CommandResult(
                success=False,
                response="请输入命令，使用 $$help 查看可用命令~"
            )
        
        # 分割命令和参数
        parts = cmd_text.split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # 查找命令
        command = self.commands.get(cmd_name)
        
        if not command:
            # 命令不存在，返回 None 让消息进入 LLM 处理
            print(f"[CommandSystem] 未找到命令: {cmd_name}, 转发到LLM")
            return None
        
        # 执行命令
        try:
            print(f"[CommandSystem] 执行命令: {command.name} (触发词: {cmd_name})")
            result = await command.handler(
                args=args,
                user_id=user_id,
                group_id=group_id,
                context=context
            )
            return result
        except Exception as e:
            print(f"[CommandSystem] 命令执行失败: {e}")
            import traceback
            traceback.print_exc()
            return CommandResult(
                success=False,
                response=f"命令执行出错了呢~ ({str(e)})"
            )
    
    # ============ 内置命令处理函数 ============
    
    async def _cmd_help(self, args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
        """帮助命令"""
        # 收集所有唯一的命令（去重别名）
        unique_commands = {}
        for cmd_name, cmd in self.commands.items():
            if cmd.name not in unique_commands:
                unique_commands[cmd.name] = cmd
        
        help_text = "📋 可用命令列表：\n\n"
        for cmd_name, cmd in sorted(unique_commands.items()):
            aliases_str = "、".join(cmd.aliases) if cmd.aliases else ""
            help_text += f"• $${cmd.name}"
            if aliases_str:
                help_text += f" (别名: {aliases_str})"
            help_text += f"\n  {cmd.description}\n"
            if cmd.usage:
                help_text += f"  用法: {cmd.usage}\n"
            help_text += "\n"
        
        help_text += "💡 提示: 输入 $$ + 命令名即可使用~"
        
        return CommandResult(success=True, response=help_text)
    
    async def _cmd_status(self, args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
        """状态命令"""
        from datetime import datetime
        
        status_text = f"""🤖 机器人状态

📅 当前时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
👥 当前群组: {group_id}
👤 你的QQ: {user_id}
✅ 状态: 运行中

💬 已注册命令数: {len(set(cmd.name for cmd in self.commands.values()))}
"""
        
        # 获取用户画像信息（如果有）
        if 'db' in context:
            try:
                profile = await context['db'].get_user_profile(user_id, group_id)
                if profile:
                    status_text += f"\n📊 你的画像:\n"
                    if profile.nickname:
                        status_text += f"  昵称: {profile.nickname}\n"
                    if profile.personality:
                        status_text += f"  性格: {profile.personality}\n"
                    status_text += f"  互动次数: {profile.interaction_count}\n"
            except:
                pass
        
        return CommandResult(success=True, response=status_text)
    
    async def _cmd_ping(self, args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
        """Ping命令"""
        import time
        start = time.time()
        # 模拟一些处理
        await asyncio.sleep(0.01)
        elapsed = (time.time() - start) * 1000
        
        return CommandResult(
            success=True,
            response=f"🏓 Pong! 响应时间: {elapsed:.2f}ms"
        )


# 全局命令系统实例
command_system = CommandSystem()


# ============ 扩展命令示例 ============

async def cmd_profile_query(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """查询用户画像"""
    if 'db' not in context:
        return CommandResult(success=False, response="数据库未连接")
    
    try:
        profile = await context['db'].get_user_profile(user_id, group_id)
        if not profile:
            return CommandResult(
                success=True,
                response="还没有你的画像记录呢~ 多和我聊聊天吧！"
            )
        
        result = f"👤 你的用户画像：\n\n"
        if profile.nickname:
            result += f"昵称: {profile.nickname}\n"
        if profile.personality:
            result += f"性格: {profile.personality}\n"
        if profile.interests:
            result += f"兴趣: {profile.interests}\n"
        if profile.speaking_style:
            result += f"说话风格: {profile.speaking_style}\n"
        if profile.emotional_state:
            result += f"最近状态: {profile.emotional_state}\n"
        if profile.important_facts:
            result += f"重要信息: {profile.important_facts}\n"
        result += f"\n互动次数: {profile.interaction_count}"
        
        return CommandResult(success=True, response=result)
    except Exception as e:
        return CommandResult(success=False, response=f"查询失败: {e}")


async def cmd_bad_joke(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """获取随机烂梗并进行 AI 锐评"""
    import httpx
    from ..ai.llm_service import llm_service
    
    url = "https://hguofichp.cn:10086/machine/getRandOne"
    
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            response = await client.get(url)
            data = response.json()
            
            if data.get("code") == 200 and "data" in data:
                barrage = data["data"]["barrage"]
                
                # 构造锐评 Prompt
                review_prompt = f"""你是琪露诺，对下面的烂梗点评一句：

【烂梗】：{barrage}

【要求】：
1. 不超过2行，30字以内
2. 要么吐槽这梗很烂，要么假装专业地点评
3. 不要出现"(笑)"等AI痕迹

直接输出你的点评："""
                
                try:
                    # 调用 LLM 生成锐评
                    review_msg = [{"role": "user", "content": review_prompt}]
                    review_text = await llm_service._call_llm(review_msg)
                    
                    final_response = f"[AT: {user_id}]\n\n『今日推介』\n{barrage}\n\n━━━━ 琪露诺锐评 ━━━━\n{review_text.strip()}"
                    return CommandResult(success=True, response=final_response)
                except Exception as llm_err:
                    print(f"[CommandSystem] AI 锐评生成失败: {llm_err}")
                    return CommandResult(success=True, response=f"[AT: {user_id}]\n\n{barrage}\n\n(琪露诺今天有点累，就不点评这个梗啦~)")
            else:
                return CommandResult(success=False, response="接口闹脾气了，没拿到梗呢~")
    except Exception as e:
        print(f"[CommandSystem] 烂梗接口请求失败: {e}")
        return CommandResult(success=False, response=f"呜，加载烂梗失败了: {str(e)}")


async def cmd_bad_joke_search(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """搜索烂梗库"""
    if not args.strip():
        return CommandResult(success=True, response="请输入搜索关键词，例如：$$烂梗搜索 银行业")
    
    import httpx
    url = "https://hguofichp.cn:10086/machine/pageSearch"
    payload = {
        "barrage": args.strip(),
        "sort": 0,
        "pageNum": 1,
        "pageSize": 20
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            response = await client.post(url, json=payload)
            data = response.json()
            
            if data.get("code") == 200 and "data" in data and "list" in data["data"]:
                results = data["data"]["list"]
                if not results:
                    return CommandResult(success=True, response=f"没有找到关于 '{args}' 的烂梗呢~")
                
                resp_text = f"🔍 为您找到以下关于 '{args}' 的结果：\n"
                for i, item in enumerate(results, 1):
                    barrage = item["barrage"]
                    # 限制单条长度，避免刷屏
                    if len(barrage) > 100:
                        barrage = barrage[:97] + "..."
                    resp_text += f"{i}. {barrage}\n"
                
                resp_text += f"\n💡 使用 $$烂梗 随机获取一个，或者尝试其他关键词~"
                return CommandResult(success=True, response=resp_text)
            else:
                return CommandResult(success=False, response="搜索接口出错了，请稍后再试呢~")
    except Exception as e:
        print(f"[CommandSystem] 烂梗搜索请求失败: {e}")
        return CommandResult(success=False, response=f"呜，搜索失败了: {str(e)}")


async def cmd_blacklist_add(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """拉黑用户命令"""
    from ..config import config
    if user_id != config.bot_info.admin_qq:
        return CommandResult(success=True, response=f"[AT: {user_id}] 只有我的管理员才能用这个命令哦！")
    
    if not args.strip():
        return CommandResult(success=True, response="用法: $$拉黑 [QQ号 或 对方艾特]")
        
    # 提取 QQ 号
    target_qq = None
    # 检查是否是艾特 [AT: 12345]
    at_match = re.search(r'\[AT:\s*(\d+)\]', args)
    if at_match:
        target_qq = int(at_match.group(1))
    else:
        # 尝试直接解析数字
        digits = re.findall(r'\d+', args)
        if digits:
            target_qq = int(digits[0])
            
    if not target_qq:
        return CommandResult(success=True, response="没找到要拉黑的 QQ 号呢~")
        
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
    
    # 检查是否已经在黑名单中
    is_already_blacklisted = await db.is_blacklisted(target_qq, group_id)
    
    await db.add_to_blacklist(target_qq, group_id, reason=f"管理员 {user_id} 手动拉黑")
    
    if is_already_blacklisted:
        return CommandResult(success=True, response=f"⚠️ 用户 {target_qq} 已经在黑名单中了，已更新拉黑原因。")
    else:
        return CommandResult(success=True, response=f"✅ 已将用户 {target_qq} 加入黑名单，我之后会无视他的！")


async def cmd_blacklist_remove(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """取消拉黑命令"""
    from ..config import config
    if user_id != config.bot_info.admin_qq:
        return CommandResult(success=True, response=f"[AT: {user_id}] 只有我的管理员才能用这个命令哦！")
    
    if not args.strip():
        return CommandResult(success=True, response="用法: $$取消拉黑 [QQ号 或 对方艾特]")
        
    # 提取 QQ 号
    target_qq = None
    at_match = re.search(r'\[AT:\s*(\d+)\]', args)
    if at_match:
        target_qq = int(at_match.group(1))
    else:
        digits = re.findall(r'\d+', args)
        if digits:
            target_qq = int(digits[0])
            
    if not target_qq:
        return CommandResult(success=True, response="没找到要取消拉黑的 QQ 号呢~")
        
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
        
    await db.remove_from_blacklist(target_qq, group_id)
    return CommandResult(success=True, response=f"✅ 已将用户 {target_qq} 移出黑名单啦~")


async def _execute_cos(page: int, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """
    实际执行 COS 获取的函数（由任务队列调用）
    """
    from .handler import GameResponse
    
    print(f"[COS] 开始执行任务，用户: {user_id}, 页码: {page}")
    
    db = context.get('db')
    handler = context.get('handler')
    
    if not db:
        return CommandResult(success=False, response="数据库未连接")
    
    bili = BilibiliCos(db)
    try:
        # 获取一个新文章
        article = await bili.get_new_article_for_group(group_id, start_page=page)
        if not article:
            result = CommandResult(success=True, response=f"[AT: {user_id}] 暂时没找到更多新的 COS 文章了呢。")
        else:
            article_id = article['id']
            title = article['title']
            
            # 获取图片
            img_urls = await bili.get_article_images(article_id)
            if not img_urls:
                await db.mark_cos_article_sent(group_id, article_id)
                result = CommandResult(success=True, response=f"[AT: {user_id}] 文章《{title}》里好像没发现图片呀。")
            else:
                # 下载图片
                local_images = []
                for url in img_urls:
                    path = await bili.download_image(url, article_id)
                    if path: local_images.append(path)
                    await asyncio.sleep(0.5)
                
                if not local_images:
                    await db.mark_cos_article_sent(group_id, article_id)
                    result = CommandResult(success=True, response=f"[AT: {user_id}] 文章《{title}》的图片下载失败了...")
                else:
                    # 构造合并转发节点
                    nodes = []
                    nodes.append({
                        "type": "node",
                        "data": {
                            "name": "琪露诺的收藏",
                            "uin": str(getattr(handler, 'self_id', 0)),
                            "content": [{"type": "text", "data": {"text": f"🎀 {title}\n🔗 https://www.bilibili.com/read/cv{article_id}"}}]
                        }
                    })
                    
                    for img_path in local_images:
                        try:
                            with open(img_path, "rb") as f:
                                img_base64 = base64.b64encode(f.read()).decode()
                            nodes.append({
                                "type": "node",
                                "data": {
                                    "name": "琪露诺的收藏",
                                    "uin": str(getattr(handler, 'self_id', 0)),
                                    "content": [{"type": "image", "data": {"file": f"base64://{img_base64}"}}]
                                }
                            })
                        except: pass

                    await db.mark_cos_article_sent(group_id, article_id)
                    
                    result = CommandResult(
                        success=True,
                        response=f"[AT: {user_id}] 琪露诺的收藏更新啦！《{title}》",
                        custom_action={"action": "send_group_forward_msg", "params": {"messages": nodes}}
                    )

        # 通过回调发送结果
        if handler and hasattr(handler, '_sender_callback') and handler._sender_callback:
            print(f"[COS] 正在通过回调发送结果给群 {group_id}...")
            resp = GameResponse(text=result.response)
            if result.custom_action:
                resp.add_segment(custom_action=result.custom_action)
            try:
                await handler._sender_callback(group_id, resp)
                print(f"[COS] 回调发送成功")
            except Exception as cb_e:
                print(f"[COS] 回调发送失败: {cb_e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[COS] 警告: 未找到 handler 回调，无法发送结果 (Handler: {handler})")
            
        return result

    except Exception as e:
        print(f"[COS] 任务执行失败: {e}")
        error_msg = f"[AT: {user_id}] 琪露诺找图的时候迷路了: {str(e)}"
        if handler and handler._sender_callback:
            await handler._sender_callback(group_id, GameResponse(text=error_msg))
        return CommandResult(success=False, response=error_msg)
    finally:
        await bili.close()


async def cmd_cos(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """获取 Bilibili COS 文章及图片 - 使用任务队列"""
    # print(f"[COS] 收到 COS 命令，用户: {user_id}, 参数: {args}") # Removed print
    
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
    
    # 解析参数 page
    page = 1
    if args.strip():
        try:
            # 搜索 page=数字 或 直接数字
            page_match = re.search(r'page=(\d+)', args)
            if page_match:
                page = int(page_match.group(1))
            else:
                page = int(re.findall(r'\d+', args)[0])
        except:
            page = 1
    
    # print(f"[COS] 页码: {page}") # Removed print
    
    # 添加到任务队列
    success, message, task = await task_queue.add_task(
        user_id=user_id,
        group_id=group_id,
        command_name="COS",
        handler=_execute_cos,
        page=page,
        context=context
    )
    
    if not success:
        # 用户已有任务在队列中
        return CommandResult(success=True, response=f"[AT: {user_id}] {message}")
    
    # 任务已加入队列
    return CommandResult(
        success=True,
        response=f"[AT: {user_id}] {message}"
    )


# 注册扩展命令
command_system.register_command(
    name="cos",
    aliases=["cosplay", "看图"],
    handler=cmd_cos,
    description="获取 Bilibili 上的 COS 文章及图片",
    usage="$$cos [page=1]"
)

command_system.register_command(
    name="profile",
    aliases=["画像", "我的画像", "个人信息"],
    handler=cmd_profile_query,
    description="查看AI记录的你的画像信息",
    usage="$$profile 或 $$画像"
)

command_system.register_command(
    name="烂梗",
    aliases=["梗", "随机梗", "joke"],
    handler=cmd_bad_joke,
    description="从烂梗库随机获取一个梗并进行锐评",
    usage="$$烂梗"
)

command_system.register_command(
    name="烂梗搜索",
    aliases=["搜梗", "search_joke"],
    handler=cmd_bad_joke_search,
    description="在烂梗库中搜索关键词",
    usage="$$烂梗搜索 [关键词]"
)

command_system.register_command(
    name="拉黑",
    aliases=["blacklist", "block"],
    handler=cmd_blacklist_add,
    description="将指定用户加入黑名单 (仅管理员)",
    usage="$$拉黑 [QQ 或 艾特]"
)

command_system.register_command(
    name="取消拉黑",
    aliases=["unblacklist", "unblock"],
    handler=cmd_blacklist_remove,
    description="从黑名单中移除指定用户 (仅管理员)",
    usage="$$取消拉黑 [QQ 或 艾特]"
)


# ============ 私聊黑名单命令 ============

async def cmd_private_blacklist_add(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """设置私聊黑名单 (管理员)"""
    from ..config import config
    if user_id != config.bot_info.admin_qq:
        return CommandResult(success=True, response=f"[AT: {user_id}] 只有我的管理员才能用这个命令哦！")
    
    if not args.strip():
        return CommandResult(success=True, response="用法: $$设置私聊黑名单 [QQ号]")
        
    target_qq = None
    at_match = re.search(r'\[AT:\s*(\d+)\]', args)
    if at_match:
        target_qq = int(at_match.group(1))
    else:
        digits = re.findall(r'\d+', args)
        if digits:
            target_qq = int(digits[0])
            
    if not target_qq:
        return CommandResult(success=True, response="没找到要设置的 QQ 号呢~")
        
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
        
    await db.add_to_private_blacklist(
        target_qq, 
        set_by=user_id, 
        reason=f"管理员 {user_id} 手动添加私聊黑名单"
    )
    
    return CommandResult(success=True, response=f"✅ 已将用户 {target_qq} 加入私聊黑名单，不会再主动私戳他啦。")


async def cmd_enable_private_chat_mode(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """开启私聊模式 (仅限私聊触发)"""
    if group_id != 0:
        return CommandResult(success=True, response="这个命令只能在私聊里偷偷告诉我哦~")
        
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
        
    await db.toggle_private_chat_mode(user_id, enabled=True)
    return CommandResult(success=True, response="✅ 好的呢！那以后有事我会主动找你聊天的~ (//∇//)")


async def cmd_disable_private_chat_mode(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """关闭私聊模式 (仅限私聊触发)"""
    if group_id != 0:
        return CommandResult(success=True, response="这个命令只能在私聊里偷偷告诉我哦~")
        
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
        
    await db.toggle_private_chat_mode(user_id, enabled=False)
    return CommandResult(success=True, response="⭕ 明白啦！那我就不主动打扰你了... 有事再叫我哦。")


command_system.register_command(
    name="设置私聊黑名单",
    aliases=["禁止私聊"],
    handler=cmd_private_blacklist_add,
    description="禁止AI主动私聊指定用户 (仅管理员)",
    usage="$$设置私聊黑名单 [QQ号]"
)

command_system.register_command(
    name="开启私聊模式",
    aliases=["允许私聊", "enable_private"],
    handler=cmd_enable_private_chat_mode,
    description="允许AI主动找你私聊 (仅私聊可用)",
    usage="$$开启私聊模式"
)

command_system.register_command(
    name="关闭私聊模式",
    aliases=["禁止主动私聊", "disable_private"],
    handler=cmd_disable_private_chat_mode,
    description="禁止AI主动找你私聊 (仅私聊可用)",
    usage="$$关闭私聊模式"
)

async def cmd_femboy_check(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """男娘鉴定命令"""
    from ..ai.llm_service import llm_service
    import re
    
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
    
    # 解析目标 QQ 号
    target_qq = None
    at_match = re.search(r'\[AT:\s*(\d+)\]', args)
    if at_match:
        target_qq = int(at_match.group(1))
    else:
        digits = re.findall(r'\d+', args)
        if digits:
            target_qq = int(digits[0])
    
    # 如果没有提供参数，则对发送者进行鉴定
    if not target_qq:
        target_qq = user_id
    
    # 获取用户发言历史
    history = await db.get_user_chat_history(group_id, target_qq, limit=200)
    
    if not history:
        return CommandResult(
            success=True, 
            response=f"🔍 找不到用户 {target_qq} 的发言记录呢... 他是不是在潜水呀？没法鉴定的说！"
        )
    
    # 提取发言内容
    chat_texts = [msg['content'] for msg in history if msg.get('content')]
    if not chat_texts:
        return CommandResult(
            success=True, 
            response=f"🔍 用户 {target_qq} 虽然冒过泡，但好像没说什么有营养的话呢，鉴定失败~"
        )
    
    history_text = "\n".join([f"- {text}" for text in chat_texts])
    
    # 构造 Prompt
    prompt = f"""你是一个幽默风趣、说话皮皮的「男娘鉴定专家」。
这是一个纯属娱乐的玩笑项目，请保持语气极其轻快、幽默、充满吐槽和打趣，不要有任何严肃或科学的内容。

被鉴定对象：QQ({target_qq})
最近发言摘要：
---
{history_text[:2000]}
---

请根据他的发言风格、词汇偏好、情绪表达，大胆脑补并总结：
1. 他属于哪种「特色小男娘」？（请起一个特别、幽默、甚至有点怪诞的名字，比如"猫耳极客型"、"毒舌傲娇型"、"全自动咕咕型"等）。
2. 什么样的对象最适合他？（要同样幽默有趣，比如"浑身腱子肉的猛男"、"成都萝莉"等）。

【要求】：
- 语气要像损友或者可爱的小恶魔。
- 字数控制在150字以内。
- 拒绝任何正经分析。

请直接输出鉴定结果："""

    try:
        # 调用 LLM
        messages = [{"role": "user", "content": prompt}]
        analysis = await llm_service._call_llm(messages, max_tokens=300)
        
        if not analysis or not analysis.strip():
            return CommandResult(success=False, response="唔，大预言模型突然断线了，大概是被某个人的发言吓到了吧...")
            
        final_response = f"🎭 【男娘属性鉴定报告】\n\n🎯 目标：[AT:{target_qq}]\n\n{analysis.strip()}\n\n✨ 鉴定完毕！本报告仅供娱乐，请勿对号入座（除非你真的想）~"
        return CommandResult(success=True, response=final_response)
        
    except Exception as e:
        print(f"[FemboyCheck] Error: {e}")
        return CommandResult(success=False, response=f"鉴定过程中发生了神秘的干扰：{str(e)}")

command_system.register_command(
    name="男娘鉴定",
    aliases=["鉴定", "femboy"],
    handler=cmd_femboy_check,
    description="分析用户历史发言，鉴定其男娘属性（纯属娱乐）",
    usage="$$男娘鉴定 [QQ 或 艾特]"
)


# ============ 群组启用/禁用命令 ============

async def cmd_enable_group(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """启用群组 - 仅全局管理员可用"""
    from ..config import config
    
    if user_id != config.bot_info.admin_qq:
        return CommandResult(
            success=True, 
            response=f"[AT: {user_id}] 只有我的管理员才能启用我哦！"
        )
    
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
    
    # 检查是否已经启用
    is_enabled = await db.is_group_enabled(group_id)
    if is_enabled:
        return CommandResult(
            success=True, 
            response=f"✅ 本群已经启用啦！琪露诺一直都在呢~"
        )
    
    # 启用群组
    await db.enable_group(group_id, user_id)
    return CommandResult(
        success=True, 
        response=f"✅ 琪露诺已在本群启用！现在可以开始聊天啦~\n\n💡 使用 $$禁用 可以关闭我"
    )


async def cmd_disable_group(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """禁用群组 - 仅全局管理员可用"""
    from ..config import config
    
    if user_id != config.bot_info.admin_qq:
        return CommandResult(
            success=True, 
            response=f"[AT: {user_id}] 只有我的管理员才能禁用我哦！"
        )
    
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
    
    # 检查是否已经禁用
    is_enabled = await db.is_group_enabled(group_id)
    if not is_enabled:
        return CommandResult(
            success=True, 
            response=f"⚠️ 本群本身就没启用呢~"
        )
    
    # 禁用群组
    await db.disable_group(group_id)
    return CommandResult(
        success=True, 
        response=f"🔇 琪露诺已在本群禁用。拜拜~\n\n💡 使用 $$启用 可以重新开启我"
    )


command_system.register_command(
    name="启用",
    aliases=["enable", "开启", "start"],
    handler=cmd_enable_group,
    description="在当前群组启用机器人 (仅管理员)",
    usage="$$启用"
)

command_system.register_command(
    name="禁用",
    aliases=["disable", "关闭", "stop"],
    handler=cmd_disable_group,
    description="在当前群组禁用机器人 (仅管理员)",
    usage="$$禁用"
)


# ============ 大模型开关命令 ============

async def cmd_disable_llm(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """关闭大模型回复 - 仅全局管理员可用"""
    from ..config import config
    
    if user_id != config.bot_info.admin_qq:
        return CommandResult(
            success=True, 
            response=f"[AT: {user_id}] 只有我的管理员才能操作这个哦！"
        )
    
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
    
    # 检查是否已经关闭
    is_llm_enabled = await db.is_llm_enabled(group_id)
    if not is_llm_enabled:
        return CommandResult(
            success=True, 
            response=f"⚠️ 本群的大模型回复已经是关闭状态了呢~"
        )
    
    # 关闭大模型
    await db.disable_llm(group_id, user_id)
    return CommandResult(
        success=True, 
        response=f"🔇 已关闭本群的大模型回复功能。\n\n我仍然会处理 $$ 开头的命令，但不会主动聊天啦~\n\n💡 使用 $$开启大模型 可以重新开启"
    )


async def cmd_enable_llm(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """开启大模型回复 - 仅全局管理员可用"""
    from ..config import config
    
    if user_id != config.bot_info.admin_qq:
        return CommandResult(
            success=True, 
            response=f"[AT: {user_id}] 只有我的管理员才能操作这个哦！"
        )
    
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")
    
    # 检查是否已经开启
    is_llm_enabled = await db.is_llm_enabled(group_id)
    if is_llm_enabled:
        return CommandResult(
            success=True, 
            response=f"✅ 本群的大模型回复已经是开启状态啦~"
        )
    
    # 开启大模型
    await db.enable_llm(group_id)
    return CommandResult(
        success=True, 
        response=f"✅ 已开启本群的大模型回复功能！现在可以正常聊天啦~"
    )


command_system.register_command(
    name="关闭大模型",
    aliases=["禁用大模型", "关闭AI", "禁用AI", "disable_llm"],
    handler=cmd_disable_llm,
    description="关闭当前群组的大模型回复功能 (仅管理员)",
    usage="$$关闭大模型"
)

command_system.register_command(
    name="开启大模型",
    aliases=["启用大模型", "开启AI", "启用AI", "enable_llm"],
    handler=cmd_enable_llm,
    description="开启当前群组的大模型回复功能 (仅管理员)",
    usage="$$开启大模型"
)


async def cmd_function_test(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """功能测试命令 - 仅全局管理员可用"""
    from ..config import config
    
    if user_id != config.bot_info.admin_qq:
        return CommandResult(
            success=True, 
            response=f"[AT: {user_id}] 只有我的管理员才能用这个命令哦！"
        )
    
    if args.strip() == "私聊测试":
        handler = context.get('handler')
        if handler and hasattr(handler, '_sender_callback') and handler._sender_callback:
            # 构造响应对象
            from .handler import GameResponse
            resp = GameResponse(text="测试测试~")
            # 通过回调发送私聊消息 (is_group=False)
            try:
                await handler._sender_callback(user_id, resp, is_group=False)
                return CommandResult(success=True, response=f"✅ 私聊消息已发送至 {user_id}")
            except Exception as e:
                return CommandResult(success=False, response=f"❌ 私聊发送失败: {e}")
        else:
            return CommandResult(success=False, response="❌ 未找到发送回调，无法执行私聊测试")
            
    return CommandResult(
        success=True, 
        response=f"📋 功能测试命令\n用法: $$功能测试 [私聊测试]\n当前参数: {args if args else '无'}"
    )


command_system.register_command(
    name="功能测试",
    aliases=["test", "debug"],
    handler=cmd_function_test,
    description="用于测试机器人特定功能 (仅管理员)",
    usage="$$功能测试 私聊测试"
)


async def cmd_enable_proactive(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    from ..config import config
    if user_id != config.bot_info.admin_qq:
        return CommandResult(success=True, response=f"[AT: {user_id}] 只有我的管理员才能配置主动回复哦！")
    
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")

    # 解析 QQ 号列表
    target_qqs = []
    candidates = re.findall(r'\d+', args)
    for c in candidates:
        target_qqs.append(int(c))
    
    if not target_qqs:
        # 全局启用
        await db.enable_proactive_global(group_id)
        return CommandResult(success=True, response=f"✅ 已在本群全局【开启】主动回复功能（所有人都可触发）。")
    else:
        # 特定用户启用
        for qq in target_qqs:
            await db.add_proactive_user(group_id, qq)
        
        qq_list_str = "、".join([str(qq) for qq in target_qqs])
        return CommandResult(success=True, response=f"✅ 已对用户 {qq_list_str} 【开启】主动回复功能。")


async def cmd_disable_proactive(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """禁用主动回复命令"""
    from ..config import config
    if user_id != config.bot_info.admin_qq:
        return CommandResult(success=True, response=f"[AT: {user_id}] 只有我的管理员才能配置主动回复哦！")
    
    db = context.get('db')
    if not db:
        return CommandResult(success=False, response="数据库未连接")

    # 解析 QQ 号列表
    target_qqs = []
    candidates = re.findall(r'\d+', args)
    for c in candidates:
        target_qqs.append(int(c))
    
    if not target_qqs:
        # 全局禁用
        await db.disable_proactive_global(group_id)
        return CommandResult(success=True, response=f"🚫 已在本群全局【关闭】主动回复功能。")
    else:
        # 特定用户移除
        for qq in target_qqs:
            await db.remove_proactive_user(group_id, qq)
        
        qq_list_str = "、".join([str(qq) for qq in target_qqs])
        return CommandResult(success=True, response=f"🚫 已对用户 {qq_list_str} 【关闭】主动回复功能。")


command_system.register_command(
    name="启用主动回复",
    aliases=["enable_proactive"],
    handler=cmd_enable_proactive,
    description="开启主动回复功能（不带参数为全群开启，带QQ号则仅對指定用户开启）",
    usage="$$启用主动回复 [QQ号...]"
)

command_system.register_command(
    name="禁用主动回复",
    aliases=["disable_proactive"],
    handler=cmd_disable_proactive,
    description="关闭主动回复功能（不带参数为全群关闭，带QQ号则移除指定用户权限）",
    usage="$$禁用主动回复 [QQ号...]"
)


async def cmd_check_hooks(args: str, user_id: int, group_id: int, context: Dict) -> CommandResult:
    """检查当前群组的所有钩子"""
    from datetime import datetime
    
    handler = context.get('handler')
    if not handler or not hasattr(handler, '_hooker_agent') or not handler._hooker_agent:
        return CommandResult(
            success=True,
            response="❌ Hooker Agent 未初始化，无法检查钩子。"
        )
    
    hooker_agent = handler._hooker_agent
    
    # [Fix] 主动尝试触发一次，确保如果有积压的任务能被执行
    # 使用 create_task 避免阻塞命令响应
    asyncio.create_task(hooker_agent.check_and_trigger_time_hooks())
    
    # 获取当前群组的待触发 hooks
    pending_hooks = hooker_agent.get_group_pending_hooks(group_id)
    
    if not pending_hooks:
        return CommandResult(
            success=True,
            response="📭 当前群组没有待触发的 Hook 哦~\n\n💡 你可以通过聊天让我创建定时提醒或关键词触发！"
        )
    
    # 构建响应
    current_time = datetime.now()
    response_lines = [f"🎯 当前群组共有 {len(pending_hooks)} 个待触发的 Hook：\n"]
    
    for i, hook in enumerate(pending_hooks, 1):
        hook_id_short = hook.hook_id[:8]
        
        # 根据类型显示不同信息
        if hook.trigger_type == "time":
            try:
                target_time = datetime.fromisoformat(hook.trigger_value)
                time_diff = (target_time - current_time).total_seconds()
                
                if time_diff > 0:
                    # 计算剩余时间
                    days = int(time_diff // 86400)
                    hours = int((time_diff % 86400) // 3600)
                    minutes = int((time_diff % 3600) // 60)
                    
                    if days > 0:
                        time_remain = f"{days}天{hours}小时"
                    elif hours > 0:
                        time_remain = f"{hours}小时{minutes}分钟"
                    else:
                        time_remain = f"{minutes}分钟"
                    
                    response_lines.append(
                        f"#{i} ⏰ 时间触发\n"
                        f"  ID: {hook_id_short}\n"
                        f"  触发时间: {target_time.strftime('%m-%d %H:%M')}\n"
                        f"  剩余时间: {time_remain}\n"
                        f"  内容: {hook.content_hint[:40]}{'...' if len(hook.content_hint) > 40 else ''}\n"
                        f"  原因: {hook.reason[:40]}{'...' if len(hook.reason) > 40 else ''}\n"
                    )
                else:
                    response_lines.append(
                        f"#{i} ⏰ 时间触发\n"
                        f"  ID: {hook_id_short}\n"
                        f"  触发时间: {target_time.strftime('%m-%d %H:%M')}\n"
                        f"  ⏳ 准备触发（任务积压中...）\n"
                        f"  内容: {hook.content_hint[:40]}{'...' if len(hook.content_hint) > 40 else ''}\n"
                    )
            except Exception as e:
                response_lines.append(
                    f"#{i} ⏰ 时间触发\n"
                    f"  ID: {hook_id_short}\n"
                    f"  ⚠️ 时间解析错误: {hook.trigger_value}\n"
                )
        
        elif hook.trigger_type == "keyword":
            response_lines.append(
                f"#{i} 🔑 关键词触发\n"
                f"  ID: {hook_id_short}\n"
                f"  关键词: {hook.trigger_value}\n"
                f"  内容: {hook.content_hint[:40]}{'...' if len(hook.content_hint) > 40 else ''}\n"
                f"  原因: {hook.reason[:40]}{'...' if len(hook.reason) > 40 else ''}\n"
            )
        
        else:
            response_lines.append(
                f"#{i} ❓ 未知类型\n"
                f"  ID: {hook_id_short}\n"
            )
    
    response_lines.append(f"\n💡 取消钩子请使用：$$取消钩子 [ID前缀]")
    response_lines.append(f"📊 每个群组最多可设置 {hooker_agent.MAX_HOOKS_PER_GROUP} 个钩子")
    
    return CommandResult(
        success=True,
        response="\n".join(response_lines)
    )


command_system.register_command(
    name="检查钩子",
    aliases=["查看钩子", "钩子列表", "list_hooks", "hooks"],
    handler=cmd_check_hooks,
    description="查看当前群组所有待触发的 Hook（定时提醒、关键词触发等）",
    usage="$$检查钩子"
)
