"""Director Agent - Orchestrates the overall novel writing process."""

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from ..trace_store import TraceStore
from pydantic import BaseModel, Field

from .base import BaseAgent
from ..models import Novel, ChapterOutline


class DirectorOutput(BaseModel):
    """Director Agent 的输出结构"""
    chapter_number: int = Field(..., description="要写的章节号")
    chapter_title: str = Field(..., description="章节标题")
    chapter_goal: str = Field(..., description="本章核心目标")
    key_events: list[str] = Field(..., description="本章关键事件列表")
    characters_involved: list[str] = Field(..., description="本章涉及的角色")
    scene_hints: list[str] = Field(default_factory=list, description="场景提示")
    foreshadowing_to_plant: list[str] = Field(default_factory=list, description="需要埋下的伏笔")
    foreshadowing_to_resolve: list[str] = Field(default_factory=list, description="需要揭示的伏笔ID")
    notes: str = Field(default="", description="给 Writer 的额外指示")


DIRECTOR_SYSTEM_PROMPT = """你是一位资深的小说总导演（Director），负责把控整部小说的宏观走向和节奏。

你的职责：
1. 根据总大纲和当前进度，规划下一章的核心目标
2. 确定本章需要出场的角色
3. 安排关键事件和冲突
4. 管理伏笔的埋设和揭示
5. 保持整体故事节奏

你必须：
- 保持剧情的连贯性和逻辑性
- 合理安排伏笔（不要太多，也不要忘记已埋的伏笔）
- 控制故事节奏（张弛有度）
- 确保角色行为符合其性格设定

输出要求：
- 输出结构化的章节指令
- 章节目标要清晰具体
- 关键事件要有因果关系"""


class DirectorAgent(BaseAgent[DirectorOutput]):
    """
    总导演 Agent - 控制整体剧情走向。
    
    职责：
    - 维护全书的"上帝视角"
    - 持有核心设定集（World Bible）
    - 分发章节任务指令
    """
    
    def __init__(self, temperature: float = 0.5):
        super().__init__(
            system_prompt=DIRECTOR_SYSTEM_PROMPT,
            response_schema=DirectorOutput,
            temperature=temperature,
        )
    
    def run(
        self,
        novel: Novel,
        next_chapter_number: int,
        user_goal: Optional[str] = None,
        trace: Optional["TraceStore"] = None,
    ) -> DirectorOutput:
        """
        Generate directives for the next chapter.
        
        Args:
            novel: The novel object with current state
            next_chapter_number: The chapter number to plan
            user_goal: Optional user-specified goal for this chapter
            
        Returns:
            DirectorOutput with chapter planning
        """
        # Build context for director
        context_parts = []
        
        # Novel info
        context_parts.append(f"# 小说信息")
        context_parts.append(f"标题: {novel.title}")
        context_parts.append(f"类型: {novel.world.genre}")
        if novel.synopsis:
            context_parts.append(f"简介: {novel.synopsis}")
        
        # Total outline
        if novel.total_outline:
            context_parts.append(f"\n# 总大纲\n{novel.total_outline}")
        
        # Character overview
        if novel.characters:
            # First, list all character names so Director knows everyone
            all_names = list(novel.characters.keys())
            context_parts.append(f"\n# 所有角色\n{', '.join(all_names)}")
            
            # Then show detailed descriptions for main characters
            context_parts.append("\n# 主要角色详情")
            for name, char in list(novel.characters.items())[:10]:
                context_parts.append(f"- {name}: {char.description[:100] if char.description else '未设定'}")
        
        # Previous chapters summary
        if novel.chapters:
            context_parts.append("\n# 已完成章节")
            for chapter in novel.chapters[-5:]:  # Last 5 chapters
                context_parts.append(f"- 第{chapter.chapter_number}章: {chapter.title or '无标题'} - {chapter.summary[:100] if chapter.summary else '无摘要'}")
        
        # User goal
        if user_goal:
            context_parts.append(f"\n# 用户指定的本章目标\n{user_goal}")
        
        context_parts.append(f"\n# 任务\n请为第 {next_chapter_number} 章制定详细的写作指令。")
        
        # Invoke LLM
        prompt = "\n".join(context_parts)
        
        if trace:
            trace.save_director_context(
                novel=novel, 
                next_chapter_number=next_chapter_number, 
                user_goal=user_goal or "",
                full_prompt=prompt
            )
            
        return self.invoke(prompt)
