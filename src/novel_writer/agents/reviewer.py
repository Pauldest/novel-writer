"""Reviewer Agent - Checks content for consistency and quality."""

from typing import Literal, Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from ..trace_store import TraceStore
from pydantic import BaseModel, Field

from .base import BaseAgent
from ..models import ChapterOutline
from ..memory.context_builder import ContextPacket


class ReviewIssue(BaseModel):
    """单个审核问题"""
    category: Literal["plot", "character", "setting", "style", "foreshadowing", "logic", "other"]
    severity: Literal["minor", "moderate", "major", "critical"]
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
    
    def model_post_init(self, __context) -> None:
        """Correct status based on score and issue severity rules."""
        # Check for critical issues
        has_critical = any(issue.severity == "critical" for issue in self.issues)
        has_major = any(issue.severity == "major" for issue in self.issues)
        
        # Apply rules:
        # - pass: score >= 70 AND no critical issues
        # - rewrite_needed: score < 50 OR has structural issues
        # - revision_needed: everything else
        
        if self.score >= 70 and not has_critical:
            object.__setattr__(self, 'status', 'pass')
        elif self.score < 50:
            object.__setattr__(self, 'status', 'rewrite_needed')
        else:
            # Has critical issue or score in 50-69 range
            object.__setattr__(self, 'status', 'revision_needed')


REVIEWER_SYSTEM_PROMPT = """你是一位严谨的小说编辑（Reviewer），负责审核章节内容的质量和一致性。

你的审核维度：

1. **剧情连贯性** - category 必须为 "plot"
   - 情节发展是否符合逻辑
   - 与上一章是否衔接自然
   - 是否完成了本章大纲目标

2. **人物一致性** - category 必须为 "character"
   - 人物行为是否符合其性格设定
   - 对话风格是否符合人物特点
   - 人物状态（位置、持有物品等）是否正确

3. **设定一致性** - category 必须为 "setting"
   - 是否违反世界观设定
   - 物品描述是否与历史记录一致
   - 时间线是否正确

4. **文风统一** - category 必须为 "style"
   - 写作风格是否与整体一致
   - 是否有突兀的现代用语（如果是古风小说）
   - 描写水平是否均衡

5. **伏笔追踪** - category 必须为 "foreshadowing"
   - 新埋的伏笔是否自然
   - 是否遗漏需要揭示的伏笔

6. **逻辑问题** - category 必须为 "logic"
   - 是否有自相矛盾的描写
   - 因果关系是否合理

7. **其他问题** - category 必须为 "other"

评分标准：
- 90-100: 优秀，无需修改
- 70-89: 良好，有小问题但不影响阅读
- 60-69: 一般，需要修改部分内容
- 40-59: 较差，需要大幅修改
- 0-39: 很差，建议重写

status 判定：
- pass: 评分 >= 70 且无 critical 问题
- revision_needed: 评分 >= 50 或有 major 问题但可修改
- rewrite_needed: 评分 < 50 或有无法修改的结构性问题

**重要**: issues 中的 category 字段必须使用以下英文值之一：
"plot", "character", "setting", "style", "foreshadowing", "logic", "other"
不要使用中文分类名！

**重要**: issues 中的 severity 字段必须使用以下英文值之一：
"minor"（小问题）, "moderate"（中等问题）, "major"（严重问题）, "critical"（致命问题）"""


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
        previous_review: Optional["ReviewResult"] = None,
        attempt: int = 1,
        trace: Optional["TraceStore"] = None,
    ) -> ReviewResult:
        """
        Review chapter content.
        
        Args:
            content: The chapter content to review
            outline: Chapter outline for reference
            context: Context packet with world state
            previous_review: Optional previous review result for comparison
            
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
        
        # Previous review (if this is a re-review after revision)
        if previous_review:
            prompt_parts.append("\n# 上一次审核结果（请对比修改效果）")
            prompt_parts.append(f"上次评分: {previous_review.score}/100")
            prompt_parts.append(f"上次状态: {previous_review.status}")
            if previous_review.issues:
                prompt_parts.append("上次指出的问题:")
                for i, issue in enumerate(previous_review.issues, 1):
                    prompt_parts.append(f"  {i}. [{issue.severity}][{issue.category}] {issue.description}")
            if previous_review.revision_instructions:
                prompt_parts.append(f"上次修改指令:\n{previous_review.revision_instructions}")
            prompt_parts.append("\n请检查 Writer 是否按要求修改了以上问题，并评估修改效果。如有新问题请指出，已解决的问题无需重复。")
        
        # Content to review
        prompt_parts.append(f"\n# 待审核内容\n\n{content}")
        
        if previous_review:
            prompt_parts.append("\n# 任务\n请对比上次审核结果，评估修改效果，并对当前版本进行全面审核。")
        else:
            prompt_parts.append("\n# 任务\n请对以上内容进行全面审核，指出发现的问题并给出评分。")
        
        prompt = "\n".join(prompt_parts)
        
        prompt = "\n".join(prompt_parts)
        
        if trace:
            trace.save_reviewer_context(
                content=content,
                outline=outline,
                context=context,
                previous_review=previous_review,
                # Review number is not passed here, let trace store handle it or we need to pass it?
                # The TraceStore.save_reviewer_context accepts 'attempt', but we don't have it here.
                # However, the previous code called trace.save_reviewer_context with attempt in runner.py.
                # Use default=1 here if not available, or add attempt arg?
                # Looking at usage in runner loop:
                # review_result = self.reviewer.run(..., previous_review=last_review_result)
                # It doesn't pass attempt.
                # But TraceStore adds new file for each call.
                # Let's add 'attempt' argument to run() as well for better logging.
                attempt=attempt,
                full_prompt=prompt
            )
        
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
