"""
异步任务队列管理器
用于控制耗时命令（如文生图、COS获取）的并发执行
"""

import asyncio
from typing import Dict, Callable, Any, Optional
from dataclasses import dataclass
from enum import Enum
import time


class TaskStatus(Enum):
    """任务状态"""
    QUEUED = "排队中"
    RUNNING = "执行中"
    COMPLETED = "已完成"
    FAILED = "失败"
    CANCELLED = "已取消"


@dataclass
class Task:
    """任务信息"""
    task_id: str
    user_id: int
    group_id: int
    command_name: str
    handler: Callable
    args: Dict[str, Any]
    status: TaskStatus = TaskStatus.QUEUED
    created_at: float = 0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at == 0:
            self.created_at = time.time()


class TaskQueue:
    """任务队列管理器"""
    
    def __init__(self, max_concurrent: int = 1):
        """
        初始化任务队列
        
        Args:
            max_concurrent: 最大并发任务数
        """
        self.max_concurrent = max_concurrent
        self.queue: asyncio.Queue = asyncio.Queue()
        self.running_tasks: Dict[str, Task] = {}  # task_id -> Task
        self.user_tasks: Dict[int, str] = {}  # user_id -> task_id (每个用户只能有一个任务)
        self.completed_tasks: Dict[str, Task] = {}  # 已完成的任务（保留最近100个）
        self.worker_task: Optional[asyncio.Task] = None
        self.is_running = False
        
        
    async def start(self):
        """启动队列处理器（异步）"""
        if not self.is_running:
            self.is_running = True
            self.worker_task = asyncio.create_task(self._worker())
            print("[TaskQueue] 任务队列处理器已启动")
    
    def stop(self):
        """停止队列处理器"""
        self.is_running = False
        if self.worker_task:
            self.worker_task.cancel()
            print("[TaskQueue] 任务队列处理器已停止")

    
    async def add_task(
        self,
        user_id: int,
        group_id: int,
        command_name: str,
        handler: Callable,
        **kwargs
    ) -> tuple[bool, str, Optional[Task]]:
        """
        添加任务到队列
        
        Args:
            user_id: 用户ID
            group_id: 群ID
            command_name: 命令名称
            handler: 处理函数
            **kwargs: 传递给处理函数的参数
            
        Returns:
            (是否成功, 消息, 任务对象)
        """
        # 检查用户是否已有任务在队列中
        if user_id in self.user_tasks:
            existing_task_id = self.user_tasks[user_id]
            existing_task = self.running_tasks.get(existing_task_id)
            
            if existing_task:
                if existing_task.status == TaskStatus.RUNNING:
                    return False, f"你已有一个 {existing_task.command_name} 任务正在执行中，请稍候~", None
                elif existing_task.status == TaskStatus.QUEUED:
                    return False, f"你已有一个 {existing_task.command_name} 任务在排队中，请稍候~", None
        
        # 创建新任务
        task_id = f"{command_name}_{user_id}_{int(time.time() * 1000)}"
        task = Task(
            task_id=task_id,
            user_id=user_id,
            group_id=group_id,
            command_name=command_name,
            handler=handler,
            args=kwargs
        )
        
        # 添加到队列
        await self.queue.put(task)
        self.running_tasks[task_id] = task
        self.user_tasks[user_id] = task_id
        
        # 计算排队位置
        # 正在运行的任务数
        running_count = len([t for t in self.running_tasks.values() if t.status == TaskStatus.RUNNING])
        # 队列中等待的任务数 (包括当前任务)
        queued_count = self.queue.qsize()
        
        print(f"[TaskQueue] 任务已加入队列: {task_id}, 用户: {user_id}, 运行中: {running_count}, 等待中: {queued_count}")
        
        if running_count == 0 and queued_count <= 1:
            return True, "任务准备就绪，即将开始执行...", task
        else:
            wait_count = queued_count - 1
            if running_count > 0:
                msg = f"已加入队列，当前排在第 {queued_count} 位。前面有 1 个任务正在执行"
                if wait_count > 0:
                    msg += f"，以及 {wait_count} 个任务在排队中。"
                else:
                    msg += "，你是下一个执行对象哦~"
            else:
                msg = f"已加入队列，当前排在第 {queued_count} 位。"
                
            return True, msg, task
    
    async def _worker(self):
        """队列处理工作线程"""
        print("[TaskQueue] Worker 线程已启动")
        
        while self.is_running:
            try:
                # 获取下一个任务
                task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                
                # 更新任务状态
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()
                
                print(f"[TaskQueue] 开始执行任务: {task.task_id}, 用户: {task.user_id}")
                
                try:
                    # 执行任务
                    # 自动注入 user_id 和 group_id 到参数中
                    task_args = task.args.copy()
                    task_args['user_id'] = task.user_id
                    task_args['group_id'] = task.group_id
                    
                    result = await task.handler(**task_args)
                    
                    # 任务成功
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.completed_at = time.time()
                    
                    elapsed = task.completed_at - task.started_at
                    print(f"[TaskQueue] 任务完成: {task.task_id}, 耗时: {elapsed:.2f}s")
                    
                except Exception as e:
                    # 任务失败
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    task.completed_at = time.time()
                    
                    print(f"[TaskQueue] 任务失败: {task.task_id}, 错误: {e}")
                    import traceback
                    traceback.print_exc()
                
                finally:
                    # 清理
                    self.queue.task_done()
                    
                    # 从运行列表移除
                    if task.task_id in self.running_tasks:
                        del self.running_tasks[task.task_id]
                    
                    # 从用户任务映射移除
                    if task.user_id in self.user_tasks:
                        del self.user_tasks[task.user_id]
                    
                    # 添加到已完成列表
                    self.completed_tasks[task.task_id] = task
                    
                    # 限制已完成任务数量
                    if len(self.completed_tasks) > 100:
                        # 删除最旧的任务
                        oldest_task_id = min(
                            self.completed_tasks.keys(),
                            key=lambda k: self.completed_tasks[k].completed_at or 0
                        )
                        del self.completed_tasks[oldest_task_id]
                
            except asyncio.TimeoutError:
                # 队列为空，继续等待
                continue
            except asyncio.CancelledError:
                print("[TaskQueue] Worker 线程被取消")
                break
            except Exception as e:
                print(f"[TaskQueue] Worker 线程错误: {e}")
                import traceback
                traceback.print_exc()
        
        print("[TaskQueue] Worker 线程已停止")
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        return {
            "queue_size": self.queue.qsize(),
            "running_count": len([t for t in self.running_tasks.values() if t.status == TaskStatus.RUNNING]),
            "queued_count": len([t for t in self.running_tasks.values() if t.status == TaskStatus.QUEUED]),
            "completed_count": len(self.completed_tasks),
        }
    
    def get_user_task(self, user_id: int) -> Optional[Task]:
        """获取用户当前任务"""
        task_id = self.user_tasks.get(user_id)
        if task_id:
            return self.running_tasks.get(task_id)
        return None


# 全局任务队列实例
task_queue = TaskQueue(max_concurrent=1)
