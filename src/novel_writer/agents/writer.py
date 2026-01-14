"""Writer Agent - Generates chapter content based on outline and context."""

from .base import BaseAgent
from ..memory.context_builder import ContextPacket
from ..models import ChapterOutline
from ..config import settings


WRITER_SYSTEM_PROMPT = """你是一位才华横溢的小说作家（Writer），负责将大纲转化为生动的正文内容。

你的职责：
1. 根据章节大纲扩写正文
2. 保持与已有内容的风格一致
3. 确保角色行为符合其设定
4. 利用提供的历史记忆保持一致性

写作要求：
- 使用生动的描写和对话
- 注意场景氛围的营造
- 人物对话要符合其性格
- 过渡要自然流畅
- 适当使用心理描写
- 控制节奏，张弛有度

特别注意：
- 如果上下文中提到了某个物品/人物的描述，你必须保持一致
- 不要引入上下文中未提及的重大设定
- 遵循大纲中的场景顺序
- 自然地融入需要埋设的伏笔

输出要求：
- 直接输出正文内容
- 不需要额外的元数据或注释
- 字数控制在大纲预估范围内"""


class WriterAgent(BaseAgent[None]):
    """
    正文撰稿人 Agent - 根据大纲和上下文生成小说正文。
    
    职责：
    - 将大纲扩写为生动的正文
    - 保持风格一致性
    - 融入伏笔和细节
    """
    
    def __init__(self, temperature: float = 0.8):
        super().__init__(
            system_prompt=WRITER_SYSTEM_PROMPT,
            response_schema=None,  # Free-form text output
            temperature=temperature,
            max_tokens=8192,  # Longer output for content
        )
    
    def run(
        self,
        outline: ChapterOutline,
        context: ContextPacket,
        target_word_count: int = 3000,
    ) -> str:
        """
        Generate chapter content.
        
        Args:
            outline: Chapter outline from Plotter
            context: Context packet from ContextBuilder
            target_word_count: Target word count
            
        Returns:
            Generated chapter content as string
        """
        # Build the full prompt
        prompt_parts = []
        
        # Inject context
        prompt_parts.append(context.to_prompt())
        
        # Writing instructions
        prompt_parts.append("\n---\n")
        prompt_parts.append(f"# 写作任务")
        prompt_parts.append(f"请根据以上上下文和大纲，撰写第{outline.chapter_number}章的正文内容。")
        prompt_parts.append(f"目标字数: 约{target_word_count}字")
        prompt_parts.append(f"\n请直接开始写作，不要添加任何元信息:")
        
        prompt = "\n".join(prompt_parts)
        
        # Generate content
        content = self.invoke(prompt)
        
        return content
    
    def revise(
        self,
        original_content: str,
        review_feedback: str,
        context: ContextPacket,
        outline: ChapterOutline = None,
    ) -> str:
        """
        Revise content based on reviewer feedback.
        
        Args:
            original_content: Original chapter content
            review_feedback: Feedback from Reviewer
            context: Context packet for reference
            outline: Chapter outline to stay on track
            
        Returns:
            Revised chapter content
        """
        prompt_parts = []
        
        # Full context (same as initial write)
        prompt_parts.append("# 参考上下文")
        
        if context.world_setting:
            prompt_parts.append(f"## 世界观设定\n{context.world_setting}")
        
        if context.style_guide:
            prompt_parts.append(f"## 风格指南\n{context.style_guide}")
        
        if context.previous_chapter_ending:
            prompt_parts.append(f"## 上一章结尾（保持连贯）\n{context.previous_chapter_ending[:1000]}...")
        
        if context.character_states:
            prompt_parts.append(f"## 角色状态\n{context.character_states}")
        
        # All relevant memories (not just the first one)
        if context.relevant_memories:
            prompt_parts.append("## 相关记忆")
            for memory in context.relevant_memories:
                prompt_parts.append(f"- {memory}")
        
        # Chapter outline to stay on track
        if outline:
            prompt_parts.append(f"\n## 本章大纲")
            prompt_parts.append(f"目标: {outline.goal}")
            prompt_parts.append(f"关键事件: {', '.join(outline.key_events)}")
            prompt_parts.append(f"涉及角色: {', '.join(outline.characters_involved)}")
            if outline.foreshadowing:
                prompt_parts.append(f"需埋伏笔: {', '.join(outline.foreshadowing)}")
        
        prompt_parts.append("\n# 原文内容")
        prompt_parts.append(original_content)
        
        prompt_parts.append("\n# 审核反馈")
        prompt_parts.append(review_feedback)
        
        prompt_parts.append("\n# 任务")
        prompt_parts.append("请根据上述反馈修改原文。只修改有问题的部分，保持其他内容不变。")
        prompt_parts.append("修改时请参考大纲和上下文，确保修改后的内容仍符合设定和风格。")
        prompt_parts.append("输出完整的修改后内容:")
        
        prompt = "\n".join(prompt_parts)
        
        return self.invoke(prompt)
