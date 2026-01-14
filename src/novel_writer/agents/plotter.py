"""Plotter Agent - Generates detailed chapter outlines."""

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from ..trace_store import TraceStore
from pydantic import BaseModel, Field

from .base import BaseAgent
from .director import DirectorOutput
from ..models import Novel, ChapterOutline


class PlotterOutput(BaseModel):
    """Plotter Agent 的输出结构"""
    chapter_number: int = Field(..., description="章节号")
    title: str = Field(..., description="章节标题")
    scenes: list[str] = Field(..., description="场景序列，按顺序排列")
    beat_sheet: list[str] = Field(..., description="情节节拍，每个节拍描述一个关键moment")
    estimated_word_count: int = Field(default=3000, description="预估字数")
    pov_character: str = Field(default="", description="本章视角人物")
    mood: str = Field(default="neutral", description="章节基调：tense/relaxed/mysterious/romantic/action等")
    hooks: list[str] = Field(default_factory=list, description="钩子/悬念，用于吸引读者")


PLOTTER_SYSTEM_PROMPT = """你是一位专业的小说大纲规划师（Plotter），负责将章节目标转化为详细的写作蓝图。

你的职责：
1. 将 Director 的章节指令转化为具体的场景序列
2. 设计情节节拍（Beat Sheet），控制章节节奏
3. 确定本章的叙事视角
4. 设置钩子和悬念

Beat Sheet 格式：
- 开场：如何开始这一章
- 触发事件：推动情节的关键事件
- 上升动作：冲突如何升级
- 高潮：章节的最高潮点
- 下降动作：高潮后的收尾
- 结尾钩子：如何勾住读者继续阅读

你必须：
- 场景之间要有逻辑过渡
- 节奏要有起伏变化
- 每个场景要有明确目的
- 考虑读者的情绪曲线

输出要求：
- 场景描述要具体但简洁
- 情节节拍要清晰可执行
- 预估字数要合理"""


class PlotterAgent(BaseAgent[PlotterOutput]):
    """
    大纲规划师 Agent - 生成详细的章节大纲。
    
    职责：
    - 将 Director 的高层指令转化为可执行的写作蓝图
    - 设计场景序列和情节节拍
    - 控制章节内的节奏起伏
    """
    
    def __init__(self, temperature: float = 0.6):
        super().__init__(
            system_prompt=PLOTTER_SYSTEM_PROMPT,
            response_schema=PlotterOutput,
            temperature=temperature,
        )
    
    def run(
        self,
        director_output: DirectorOutput,
        novel: Novel,
        previous_chapter_summary: Optional[str] = None,
        trace: Optional["TraceStore"] = None,
    ) -> tuple[PlotterOutput, "ChapterOutline"]:
        """
        Generate detailed chapter outline from director's instructions.
        
        Args:
            director_output: Instructions from Director agent
            novel: The novel object for context
            previous_chapter_summary: Summary of previous chapter
            
        Returns:
            Tuple of (PlotterOutput, ChapterOutline):
            - PlotterOutput: Raw LLM output with all Plotter-specific fields (for tracing)
            - ChapterOutline: Processed outline ready for Writer agent
        """
        # Build context
        context_parts = []
        
        # Director's instructions
        context_parts.append("# Director 的章节指令")
        context_parts.append(f"章节号: 第{director_output.chapter_number}章")
        context_parts.append(f"标题: {director_output.chapter_title}")
        context_parts.append(f"核心目标: {director_output.chapter_goal}")
        context_parts.append(f"关键事件: {', '.join(director_output.key_events)}")
        context_parts.append(f"涉及角色: {', '.join(director_output.characters_involved)}")
        if director_output.scene_hints:
            context_parts.append(f"场景提示: {', '.join(director_output.scene_hints)}")
        if director_output.notes:
            context_parts.append(f"额外指示: {director_output.notes}")
        
        # World setting
        context_parts.append(f"\n# 世界观")
        context_parts.append(f"类型: {novel.world.genre}")
        if novel.world.magic_system:
            context_parts.append(f"体系: {novel.world.magic_system}")
        
        # Character info for involved characters
        context_parts.append("\n# 本章角色信息")
        for char_name in director_output.characters_involved:
            if char_name in novel.characters:
                char = novel.characters[char_name]
                context_parts.append(f"- {char_name}: {char.description[:200] if char.description else '暂无描述'}")
        
        # Previous chapter context
        if previous_chapter_summary:
            context_parts.append(f"\n# 上一章摘要\n{previous_chapter_summary}")
        
        context_parts.append("\n# 任务\n请根据以上信息，生成详细的章节大纲。")
        
        # Invoke LLM
        prompt = "\n".join(context_parts)
        
        if trace:
            trace.save_plotter_context(
                full_prompt=prompt,
                system_prompt=self.system_prompt
            )
            
        plotter_output: PlotterOutput = self.invoke(prompt)
        
        # Convert to ChapterOutline
        chapter_outline = ChapterOutline(
            chapter_number=director_output.chapter_number,
            title=plotter_output.title,
            goal=director_output.chapter_goal,
            scenes=plotter_output.scenes,
            key_events=director_output.key_events,
            characters_involved=director_output.characters_involved,
            foreshadowing=director_output.foreshadowing_to_plant,
        )
        
        return plotter_output, chapter_outline
