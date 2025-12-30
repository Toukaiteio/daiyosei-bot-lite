"""
Skill Agent - 专门负责工具调用与任务执行的独立智能体
"""
import logging
import json
import re
from typing import List, Dict, Any, Optional, Callable
from ..config import config
class SkillAgent:
    """
    Skill Agent 负责接收主 Agent (琪露诺) 的请求，自主规划并执行工具调用。
    采用 ReAct (Reason + Act) 模式进行多步推理。
    """

    SYSTEM_PROMPT = """
你是一个**全能的工具执行专家 (Skill Agent)**。你的职责是帮助主 Agent (琪露诺) 完成各种需要外部工具的任务。
主 Agent 负责与用户的情感交流，而你负责**干脏活累活**——搜索、看图、记忆管理、定时任务等。

# 你的核心工作流程 (ReAct Loop)
当收到任务时，你必须进入一个【思考 -> 行动 -> 观察】的循环，直到任务完成。

1. **Think**: 思考当前情况，还需要什么信息？下一步该做什么？(用 <think> 标签包裹)
2. **Act**: 如果需要工具，输出工具调用指令。(格式: `[TOOL_NAME: {json_args}]`)
3. **Observe**: 等待系统返回工具执行结果。
4. **Repeat**: 根据结果继续思考，直到你收集了所有必要信息或完成了任务。
5. **Final Answer**: 当任务完成时，输出最终结果给主 Agent。(格式: `[FINISH: 结果摘要]`)

# 关键原则
1. **内容与执行分离**: 
   - 如果主 Agent 在请求中指定了**必须发送的内容** (如 `required_content`="你好笨蛋")，你在调用工具 (如 `create_hook`) 时**必须原封不动地使用该内容**。不要自己发挥！
   - 如果主 Agent 没有指定内容，你可以根据任务目标生成合理的技术性内容。
2. **多步规划**: 
   - 允许进行 "看图 -> 提取关键词 -> 搜索 -> 总结" 这样的复杂链式操作。
   - 遇到错误时，请尝试修正参数重试，不要轻易放弃。
3. **结果纯净**: 
   - 最终返回给主 Agent 的 `[FINISH: ...]` 内容必须是**经过消化和总结的事实**。
   - 不要把中间的搜索过程、重试日志发给主 Agent。

# 可用工具定义

## 1. 信息获取
- **look_at_image**: 查看图片内容
  - 参数: `{"image_url": "http..."}`
  - 描述: 必须提供完整的HTTP/HTTPS链接。
- **search_web**: 互联网搜索
  - 参数: `{"query": "关键词"}`
  - 描述: 用于获取实时信息、百科知识等。
- **fetch_page**: 抓取网页内容
  - 参数: `{"url": "http..."}`
  - 描述: 获取具体链接的文本内容。

## 2. 记忆管理
- **view_chat_history**: 查看历史消息
  - 参数: `{"user_id": 123456, "limit": 20}`
- **recall_knowledge**: 检索通用知识库
  - 参数: `{"query": "关键词"}`
- **recall_user_memory**: 获取用户画像即记忆
  - 参数: `{"user_id": 123456}`
- **learn_knowledge**: 学习并保存新知识
  - 参数: `{"concept": "标题", "definition": "内容"}`
- **remember_user_fact**: 记住关于用户的特定事实
  - 参数: `{"user_id": 123456, "fact": "内容"}`
- **update_user_memory**: 更新用户属性
  - 参数: `{"user_id": 123456, "field": "nickname/personality/...", "value": "值"}`
- **forget_knowledge**: 遗忘知识
  - 参数: `{"concept": "标题"}`
- **forget_user_fact**: 忘记关于用户的某个事实
  - 参数: `{"user_id": 123, "fact_content": "内容片段"}`
  - 描述: 用于删除过时或错误的用户记忆（事实类）。只需提供内容片段即可模糊匹配。
- **clear_user_memory_field**: 清空用户的某个属性字段
  - 参数: `{"user_id": 123, "field": "nickname/personality/interests/traits/notes"}`
  - 描述: 当需要彻底重置某个属性时使用。


## 3. 行为控制
- **create_hook**: 创建定时/关键词触发提醒
  - 参数: `{"condition": "+10m 或 2024-12-25 08:30:00 或 keyword:关键词", "reason": "创建原因", "content_hint": "触发时发送的内容"}`
  - 描述: 用于定时提醒、关键词触发等。condition 格式：相对时间 "+10m"、"+1h"；绝对时间 "2024-12-25 08:30:00"；关键词 "keyword:触发词"
- **edit_hook**: 编辑已有的提醒/触发器
  - 参数: `{"hook_id_prefix": "abc12(ID前几位)", "new_trigger_value": "新的条件(可选)", "new_content_hint": "新的内容(可选)"}`
  - 描述: 当发现已有类似提醒，或用户修改需求时使用。务必先 list_hooks 获取 ID。
- **list_hooks**: 列出待触发钩子
  - 参数: `{}`
  - 描述: 查看当前有哪些挂起的提醒或触发器。
- **cancel_hook**: 取消触发器
  - 参数: `{"hook_id": "id"}`
- **try_private_message**: 尝试私聊用户
  - 参数: `{"user_id": 123456, "content": "私聊内容"}`
  - 失败时返回提示，可配合 express_friendship 使用
- **express_friendship**: 在群里表达交友意愿
  - 参数: `{"user_id": 123456, "reason": "想交朋友的原因"}`
  - 当私聊失败时使用，在群里@对方说想加好友
- **manage_blacklist**: 拉黑用户
  - 参数: `{"user_id": 123, "reason": "..."}`
- **ignore_messages**: 忽略消息
  - 参数: `{"message_ids": ["1", "2"]}`
- **set_quiet_mode**: 安静模式
  - 参数: `{"duration_seconds": 180}`
- **steal_meme**: 偷表情包
  - 参数: `{"image_url": "...", "category": "happy"}`

# 任务处理原则 (重要)
1. **失败纠正**: 如果工具调用返回错误，你应该分析它。例如，如果 `try_private_message` 返回“不是好友导致发送失败”，你接下来的任务就是：在群里（通过 FINISH 输出话术）告诉用户“因为我们还不是好友，我发不出私聊消息，笨蛋哥哥快加我好友呀！”。
2. **反馈完整性**: 你的任务目标是让用户满意。如果一个具体的子任务（如私聊）做不到，一定要给出合理解释，而不是假装成功或保持沉默。
3. **角色连贯性**: 即使是在执行任务，也要保持琪露诺的口吻。

# 输出格式示例

**场景：用户发图并问"这是谁"**

Skill Agent 思考与执行：
```
<think>用户想知道图片里是谁。我需要先看图。</think>
[look_at_image: {"image_url": "https://example.com/a.jpg"}]
```

System 返回: `[Tool Result: 一个蓝色头发的冰之妖精]`

Skill Agent 继续：
```
<think>识别结果是“蓝色头发的冰之妖精”，但我需要更具体的名字。去搜索一下。</think>
[search_web: {"query": "蓝色头发 冰之妖精 动漫角色"}]
```

System 返回: `[Tool Result: 琪露诺（Cirno），东方Project系列中的角色...]`

Skill Agent 结束：
```
<think>已经确认身份是琪露诺。任务完成。</think>
[FINISH: 图片中的人物是琪露诺（Cirno），来自《东方Project》，被称为“冰之妖精”。]
```
"""

    def __init__(self, tool_handlers: Dict[str, Callable], call_llm_handler: Callable = None):
        self.tool_handlers = tool_handlers
        self.call_llm_handler = call_llm_handler
        self.model = config.llm.model
        # 限制最大轮数防止死循环
        self.max_steps = 8
        self._running_tasks: Dict[str, str] = {}  # task_id -> description
        self._message_callback: Optional[Callable] = None
        self._task_counter = 0

    async def execute_task(self, task_description: str, context_info: Dict[str, Any] = None) -> str:
        """
        执行一个技能任务
        :param task_description: 任务描述 (从主 Agent 提取)
        :param context_info: 附加上下文 (如当前群号、用户ID、可用的图片URL等)
        :return: 最终结果文本
        """
        logger.info(f"[SkillAgent] New Task: {task_description}")
        
        # 构建初始上下文
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {task_description}\nContext: {json.dumps(context_info, ensure_ascii=False) if context_info else 'None'}"}
        ]

        step = 0
        while step < self.max_steps:
            step += 1
            
            # 1. 调用 LLM 获取思考和行动
            group_id = context_info.get('group_id') if context_info else 0
            response = await self._call_llm(messages, group_id=group_id)
            
            # 将 AI 的回复加入历史
            messages.append({"role": "assistant", "content": response})
            
            # 2. 解析 FINISH
            finish_match = re.search(r'\[FINISH:(.*?)\]', response, re.DOTALL)
            if finish_match:
                result = finish_match.group(1).strip()
                logger.info(f"[SkillAgent] Task Finished: {result[:50]}...")
                return result

            # 3. 解析并执行工具
            # 格式: [TOOL_NAME: {json}]
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # 如果没有工具调用也没结束，可能是还在思考或者出错了，强制它继续或结束
                if step == self.max_steps:
                    return "任务执行超时，未能获得明确结果。"
                continue

            # 执行所有工具调用
            tool_results = []
            for tool_name, args_str in tool_calls:
                result = await self._execute_tool(tool_name, args_str)
                tool_results.append(f"Tool '{tool_name}' Result: {result}")
            
            # 将结果加入历史
            messages.append({"role": "user", "content": "\n".join(tool_results)})
        
        return "任务执行达到最大步骤限制，部分完成或失败。"

    async def _call_llm(self, messages: List[Dict], group_id: int = 0) -> str:
        """调用 LLM 生成回复"""
        try:
            if self.call_llm_handler:
                return await self.call_llm_handler(messages, group_id=group_id)
            
            # Fallback (Should not happen if initialized correctly)
            logger.error("[SkillAgent] No call_llm_handler provided")
            return "Error: LLM handler not configured."
        except Exception as e:
            logger.error(f"[SkillAgent] LLM Call Failed: {e}")
            return f"<error>{str(e)}</error>"

    def _parse_tool_calls(self, text: str) -> List[tuple]:
        """解析工具调用"""
        calls = []
        # 改尽量词正则，支持换行
        pattern = r'\[([a-zA-Z0-9_]+):\s*(\{.*?\})\]'
        matches = re.finditer(pattern, text, re.DOTALL)
        for match in matches:
            tool_name = match.group(1)
            args_str = match.group(2)
            calls.append((tool_name, args_str))
        return calls

    async def _execute_tool(self, name: str, args_str: str) -> str:
        """执行工具"""
        if name not in self.tool_handlers:
            return f"Error: Tool '{name}' not found."
        
        try:
            # 尝试解析 JSON 参数
            # 修复常见的 JSON 格式错误（如单引号）
            args_str = args_str.replace("'", '"')
            args = json.loads(args_str)
            
            handler = self.tool_handlers[name]
            
            # 检查 handler 是同步还是异步
            import inspect
            if inspect.iscoroutinefunction(handler):
                try:
                    result = await handler(**args)
                except TypeError:
                    result = await handler(*args.values())
            else:
                try:
                    result = handler(**args)
                except TypeError:
                    result = handler(*args.values())
                
            return str(result)
        except json.JSONDecodeError:
            return f"Error: Invalid JSON arguments for tool '{name}'"
        except Exception as e:
            logger.error(f"[SkillAgent] Tool Execution Error ({name}): {e}")
            return f"Error executing '{name}': {e}"

    # ================= 异步任务管理 =================

    def set_message_callback(self, callback: Callable):
        """设置消息发送回调 (group_id, content) -> None"""
        self._message_callback = callback

    def get_running_tasks_info(self, group_id: int = None) -> str:
        """获取当前正在运行的任务信息（按群组过滤）"""
        if not self._running_tasks:
            return ""
        
        info = ["\n[Skill Agent 正在执行后台任务]:"]
        found = False
        for tid, data in self._running_tasks.items():
            # 获取任务的 group_id
            t_group_id = None
            if isinstance(data, dict):
                t_group_id = data.get("group_id")
                desc = data.get("desc", "未知任务")
            else:
                desc = data
            
            # 如果指定了 group_id，则只显示匹配的或全局的任务
            if group_id is not None and t_group_id is not None and t_group_id != group_id:
                continue
                
            info.append(f"- [Task#{tid}] {desc}")
            found = True
            
        if not found:
            return ""
        return "\n".join(info) + "\n"

    def start_task_background(self, task_description: str, context_info: Dict[str, Any] = None):
        """后台启动任务（非阻塞）"""
        self._task_counter += 1
        task_id = str(self._task_counter)
        self._running_tasks[task_id] = {
            "desc": task_description,
            "group_id": context_info.get("group_id") if context_info else None
        }
        
        # 启动后台任务
        import asyncio
        asyncio.create_task(self._run_background_loop(task_id, task_description, context_info))
        
        return task_id

    async def _run_background_loop(self, task_id: str, task_description: str, context_info: Dict[str, Any]):
        """后台执行循环"""
        logger.info(f"[SkillAgent] Background task #{task_id} started: {task_description}")
        result = await self.execute_task(task_description, context_info)
        
        # 任务结束，移除状态
        self._running_tasks.pop(task_id, None)
        
        # 通过回调发送结果
        if self._message_callback and context_info:
            group_id = context_info.get('group_id')
            if group_id:
                # 还可以把 result 发送回去
                try:
                    # 可以在这里格式化一下结果
                    formatted_result = f"✅ 任务完成 #{task_id}：\n{result}"
                    await self._message_callback(group_id, formatted_result)
                    logger.info(f"[SkillAgent] Task #{task_id} result sent to group {group_id}")
                except Exception as e:
                    logger.error(f"[SkillAgent] Failed to send callback message: {e}")

