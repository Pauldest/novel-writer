"""Reviewer Agent - Checks content for consistency and quality."""

from typing import Literal
from pydantic import BaseModel, Field

from .base import BaseAgent
from ..models import ChapterOutline
from ..memory.context_builder import ContextPacket


class ReviewIssue(BaseModel):
    """单个审核问题"""
    category: Literal["plot", "character", "setting", "style", "foreshadowing", "logic", "other"]
    severity: Literal["minor", "major", "critical"]
    description: str
    location: str = Field(default="", description="问题在文中的大致位置")
    suggestion: str = Field(default="", description="修改建议")


class ReviewResult(BaseModel):
    """Reviewer Agent 的输出结构"""
    status: Literal["pass", "revision_needed", "rewrite_needed"] = Field(
        ..., 
        description="审核结果: pass=通过, revision_needed=需要修改, rewrite_needed=需要重写"
    )
    score: int = Field(..., ge=0, le=100, description="综合评分 0-100")
    issues: list[ReviewIssue] = Field(default_factory=list, description="发现的问题列表")
    strengths: list[str] = Field(default_factory=list, description="亮点")
    summary: str = Field(..., description="审核总结")
    revision_instructions: str = Field(default="", description="给 Writer 的修改指令")


REVIEWER_SYSTEM_PROMPT = """你是一位严谨的小说编辑（Reviewer），负责审核章节内容的质量和一致性。

你的审核维度：

1. **剧情连贯性** (plot)
   - 情节发展是否符合逻辑
   - 与上一章是否衔接自然
   - 是否完成了本章大纲目标

2. **人物一致性** (character)
   - 人物行为是否符合其性格设定
   - 对话风格是否符合人物特点
   - 人物状态（位置、持有物品等）是否正确

3. **设定一致性** (setting)
   - 是否违反世界观设定
   - 物品描述是否与历史记录一致
   - 时间线是否正确

4. **文风统一** (style)
   - 写作风格是否与整体一致
   - 是否有突兀的现代用语（如果是古风小说）
   - 描写水平是否均衡

5. **伏笔追踪** (foreshadowing)
   - 新埋的伏笔是否自然
   - 是否遗漏需要揭示的伏笔

6. **逻辑问题** (logic)
   - 是否有自相矛盾的描写
   - 因果关系是否合理

评分标准：
- 90-100: 优秀，无需修改
- 75-89: 良好，有小问题但不影响阅读
- 60-74: 一般，需要修改部分内容
- 40-59: 较差，需要大幅修改
- 0-39: 很差，建议重写

status 判定：
- pass: 评分 >= 75 且无 critical 问题
- revision_needed: 评分 >= 50 或有 major 问题但可修改
- rewrite_needed: 评分 < 50 或有无法修改的结构性问题"""


class ReviewerAgent(BaseAgent[ReviewResult]):
    """
    连续性检查员 Agent - 审核内容质量和一致性。
    
    职责：
    - 检查剧情连贯性
    - 验证人物行为一致性
    - 检测设定冲突
    - 追踪伏笔状态
    - 评估文风统一性
    """
    
    def __init__(self, temperature: float = 0.3):
        super().__init__(
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            response_schema=ReviewResult,
            temperature=temperature,  # Lower temperature for more consistent reviews
        )
    
    def run(
        self,
        content: str,
        outline: ChapterOutline,
        context: ContextPacket,
    ) -> ReviewResult:
        """
        Review chapter content.
        
        Args:
            content: The chapter content to review
            outline: Chapter outline for reference
            context: Context packet with world state
            
        Returns:
            ReviewResult with detailed feedback
        """
        # Build review prompt
        prompt_parts = []
        
        # Context for reference
        prompt_parts.append("# 审核参考信息")
        
        if context.world_setting:
            prompt_parts.append(f"## 世界观设定\n{context.world_setting}")
        
        if context.character_states:
            prompt_parts.append(f"## 角色当前状态\n{context.character_states}")
        
        if context.relevant_memories:
            prompt_parts.append("## 相关历史记录")
            for memory in context.relevant_memories[:3]:
                prompt_parts.append(f"- {memory[:300]}...")
        
        if context.previous_chapter_ending:
            prompt_parts.append(f"## 上一章结尾\n{context.previous_chapter_ending[:500]}...")
        
        # Chapter outline
        prompt_parts.append(f"\n# 本章大纲")
        prompt_parts.append(f"目标: {outline.goal}")
        prompt_parts.append(f"关键事件: {', '.join(outline.key_events)}")
        prompt_parts.append(f"涉及角色: {', '.join(outline.characters_involved)}")
        if outline.foreshadowing:
            prompt_parts.append(f"需埋伏笔: {', '.join(outline.foreshadowing)}")
        
        # Content to review
        prompt_parts.append(f"\n# 待审核内容\n\n{content}")
        
        prompt_parts.append("\n# 任务\n请对以上内容进行全面审核，指出发现的问题并给出评分。")
        
        prompt = "\n".join(prompt_parts)
        
        return self.invoke(prompt)
    
    def should_revise(self, result: ReviewResult) -> bool:
        """Check if revision is needed."""
        return result.status == "revision_needed"
    
    def should_rewrite(self, result: ReviewResult) -> bool:
        """Check if rewrite is needed."""
        return result.status == "rewrite_needed"
    
    def format_feedback_for_writer(self, result: ReviewResult) -> str:
        """Format review feedback for the Writer agent."""
        parts = []
        
        parts.append(f"## 审核结果: {result.status}")
        parts.append(f"评分: {result.score}/100")
        parts.append(f"\n总结: {result.summary}")
        
        if result.issues:
            parts.append("\n## 需要修改的问题:")
            for i, issue in enumerate(result.issues, 1):
                parts.append(f"{i}. [{issue.severity}][{issue.category}] {issue.description}")
                if issue.location:
                    parts.append(f"   位置: {issue.location}")
                if issue.suggestion:
                    parts.append(f"   建议: {issue.suggestion}")
        
        if result.revision_instructions:
            parts.append(f"\n## 修改指令\n{result.revision_instructions}")
        
        return "\n".join(parts)
