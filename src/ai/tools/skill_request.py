from .base import BaseTool, register_tool
import logging

logger = logging.getLogger("Tools.SkillRequest")

@register_tool("SKILL_REQUEST")
class SkillRequestTool(BaseTool):
    description = "委托技能助手执行复杂任务"
    
    async def __call__(self, goal: str, required_content: str = "", **kwargs):
        """处理 SKILL_REQUEST 工具调用 - 委托给 Skill Agent"""
        service = kwargs.get("service")
        if not service:
            logger.error("[SKILL_REQUEST] LLMService instance not provided in kwargs")
            return "❌ 系统内部错误：未找到 LLM 服务实例"

        logger.info(f"[SKILL_REQUEST] Goal: {goal}")
        
        # 获取当前上下文
        from ..llm_service import active_group_id, current_chat_context
        group_id = active_group_id.get()
        context = current_chat_context.get()
        
        # 构建 context_info
        context_info = {
            "group_id": group_id,
            "chat_history_snippet": context[-20:] if context else [],
        }
        
        # 如果有 required_content，添加到 context_info
        if required_content:
            context_info["required_content"] = required_content
        
        # 启动 Skill Agent 后台任务
        if hasattr(service, 'skill_agent') and service.skill_agent:
            task_id = service.skill_agent.start_task_background(
                task_description=goal,
                context_info=context_info
            )
            logger.info(f"[SKILL_REQUEST] Task delegated to Skill Agent (ID: {task_id})")
            return f"✅ 已交给技能助手处理"
        else:
            logger.error("[SKILL_REQUEST] Skill Agent not available")
            return "❌ 技能助手未就绪"
