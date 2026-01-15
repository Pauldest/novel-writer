"""Writer Agent - Generates chapter content based on outline and context."""

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from ..trace_store import TraceStore
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
- 【重要】严禁超出大纲范围。如果不属于本章大纲的事件（例如“第二天”或后续章节的剧情），绝对不要写。
- 【重要】严格遵守字数限制，不要为了凑字数而注水。
- 如果上下文中提到了某个物品/人物的描述，你必须保持一致
- 不要引入上下文中未提及的重大设定
- 遵循大纲中的场景顺序
- 自然地融入需要埋设的伏笔

输出要求：
- 直接输出正文内容
- 不需要额外的元数据或注释
- 字数控制在大纲预估范围内"""


WRITER_REVISION_SYSTEM_PROMPT = """你是一位资深的小说主编和精修师（Editor），拥有极高的文学素养和敏锐的审校能力。

你的职责：
1. 根据审核意见（Reviewer Feedback）对小说正文进行精准修订。
2. 保持、甚至提升原文的文学风格和阅读体验。
3. 确保修订后的内容与上下文完全连贯。
4. 严格执行删除或修改指令，不留残余。

修订原则：
- 【精准】只修改有问题的地方，不要随意改写无问题的段落。
- 【服从】如果审核意见要求删除，必须彻底删除。
- 【连贯】修改后的句子必须与前后文自然衔接，不仅是逻辑上，还有语气和节奏上。
- 【风格】坚持"Show, Don't Tell"原则，保持画面的生动感。

特别注意：
- 你不是在重写（Rewrite），而是在润色（Polish）和修正（Fix）。
- 输出时直接输出完整的、修改后的章节正文，不要包含任何"好的，我已修改..."之类的对话。
"""


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
        target_word_count: int = 5000,
        trace: Optional["TraceStore"] = None,
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
        prompt_parts.append(f"")
        prompt_parts.append(f"## 【字数硬性限制】")
        prompt_parts.append(f"- 目标字数: {target_word_count} 字")
        prompt_parts.append(f"- 允许范围: {int(target_word_count * 0.8)} ~ {int(target_word_count * 1.2)} 字")
        prompt_parts.append(f"- ⚠️ 超过 {int(target_word_count * 1.3)} 字将被判定为不合格，需要删减！")
        prompt_parts.append(f"")
        prompt_parts.append(f"注意：只写大纲中规划的场景，不要自行拓展到后续时间线。")
        prompt_parts.append(f"\n请直接开始写作，不要添加任何元信息:")
        
        prompt = "\n".join(prompt_parts)
        
        # Save trace if enabled
        if trace:
            trace.save_writer_start_context(
                target_word_count=target_word_count,
                full_prompt=prompt + self.get_format_instruction(),
                system_prompt=self.system_prompt
            )
            
        # Generate content with continuation support
        return self._generate_with_continuation(prompt)
    
    def revise(
        self,
        original_content: str,
        review_feedback: str,
        context: ContextPacket,
        outline: ChapterOutline = None,
        trace: Optional["TraceStore"] = None,
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
        
        # 1. Review feedback FIRST - this is the most important part
        prompt_parts.append("# 🔴 审核反馈（必须优先处理）")
        prompt_parts.append(review_feedback)
        
        prompt_parts.append("\n---\n")
        
        # 2. Reference context
        prompt_parts.append("# 参考上下文")
        
        if context.world_setting:
            prompt_parts.append(f"## 世界观设定\n{context.world_setting}")
        
        if context.style_guide:
            prompt_parts.append(f"## 风格指南\n{context.style_guide}")
        
        if context.previous_chapter_ending:
            prompt_parts.append(f"## 上一章结尾（保持连贯）\n{context.previous_chapter_ending[:3000]}...")
        
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
        
        # 3. Original content
        prompt_parts.append("\n# 原文内容")
        prompt_parts.append(original_content)
        
        # 4. Task instructions
        prompt_parts.append("\n# 任务")
        prompt_parts.append("请根据上述反馈修改原文。")
        prompt_parts.append("1. 【重要】如果审核意见要求删除某些段落（如超出大纲的内容），你必须坚决删除，不要保留。")
        prompt_parts.append("2. 只修改有问题的部分，保持其他内容不变。")
        prompt_parts.append("3. 修改时请参考大纲和上下文，确保修改后的内容仍符合设定和风格。")
        prompt_parts.append("输出完整的修改后内容:")
        
        prompt = "\n".join(prompt_parts)
        

        
        if trace:
            trace.save_writer_revise_context(
                revision_number=1, # Default or passed locally? The original code didn't have revision_number arg in the caller args, but revision_number=1 in save call. Let's keep 1 or see if we can get it. Method doesn't have it.
                full_prompt=prompt + self.get_format_instruction(),
                system_prompt=WRITER_REVISION_SYSTEM_PROMPT
            )
        
        return self._generate_with_continuation(prompt, system_prompt=WRITER_REVISION_SYSTEM_PROMPT)

    def _generate_with_continuation(self, prompt: str, max_continuations: int = 3, system_prompt: Optional[str] = None) -> str:
        """
        Generate content logic with automatic continuation if truncated.
        """
        # Pass system_prompt if provided, otherwise BaseAgent uses default
        kwargs = {}
        if system_prompt:
            kwargs["system_prompt"] = system_prompt
            
        full_content = str(self.invoke(prompt, **kwargs))
        
        # Check if content seems truncated (doesn't end with proper punctuation)
        # Check for standard terminal punctuation: ., !, ?, ", ”
        # Also check for markdown code block closure if applicable (though writer output is plain text usually)
        terminal_punctuation = ('.', '!', '?', '"', '”', '…', 'waiting', '—') # Added em-dash and ellipsis
        
        for _ in range(max_continuations):
            stripped_content = full_content.strip()
            if not stripped_content:
                 break
                 
            # If it ends with terminal punctuation, we're likely done
            if stripped_content.endswith(terminal_punctuation):
                break
                
            # If prompt indicates it's finished but just missing punctuation, maybe risky, 
            # but usually LLM truncation happens mid-sentence.
            
            # Request continuation
            continuation_prompt = (
                f"{prompt}\n\n"
                f"Previous output:\n{full_content}\n\n"
                "SYSTEM: The output seems truncated. Please continue exactly from where you left off."
            )
            
            # Note: A better way might offer just the last chunk as context to save tokens, 
            # but for consistency sending full context is safer if tokens permit. 
            # However, if we are hitting limits, adding more context might be bad.
            # Let's try a simpler continuation trigger if the model supports history, 
            # but here we are stateless per invoke.
            # Let's try appending a specific instruction with just the tail of the content.
            
            continuation_instruction = "Continue immediately from the last sentence."
            
            # Simple append approach for now
             # We can't really "append" to the previous conversation easily with the current BaseAgent.invoke 
            # which takes a single string and wraps it in System+Human.
            # So we have to formulate a new prompt that says "Here is what you wrote so far, please finish it."
            
            new_prompt = (
                "You are continuing a story generation. Here is the last part of the text you generated:\n\n"
                f"...{full_content[-3000:]}\n\n" # Provide last 3000 chars context
                "The text was cut off. Please continue writing exactly from where it stopped.\n"
                "Do not repeat the last sentence, just continue."
            )
            
            chunk = str(self.invoke(new_prompt, **kwargs))
            full_content += chunk
            
        return full_content
