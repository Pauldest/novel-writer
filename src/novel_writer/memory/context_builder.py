"""Context Builder - Dynamic context assembly for Writer agent."""

import re
from dataclasses import dataclass, field
from typing import Optional

from .vector_store import VectorStore, Document
from .structured_store import StructuredStore
from ..models import Chapter, ChapterOutline


@dataclass
class ContextPacket:
    """
    上下文包 - 提供给 Writer Agent 的完整上下文信息。
    
    包含三层上下文：
    1. 全局静态层：世界观设定、核心规则
    2. 局部连贯层：上一章摘要 + 最后N字原文
    3. 动态按需层：基于大纲关键词的 RAG 检索结果
    """
    # Global static context
    world_setting: str = ""
    style_guide: str = ""
    
    # Local sliding window
    previous_chapter_summary: str = ""
    previous_chapter_ending: str = ""
    
    # Dynamic RAG context
    relevant_memories: list[str] = field(default_factory=list)
    character_states: str = ""
    
    # Current task
    chapter_outline: str = ""
    
    def to_prompt(self) -> str:
        """Convert context packet to a formatted prompt string."""
        sections = []
        
        # World and style
        if self.world_setting:
            sections.append(f"## 世界观设定\n{self.world_setting}")
        
        if self.style_guide:
            sections.append(f"## 风格指南\n{self.style_guide}")
        
        # Character states
        if self.character_states:
            sections.append(f"## 当前角色状态\n{self.character_states}")
        
        # Previous chapter
        if self.previous_chapter_summary:
            sections.append(f"## 上一章摘要\n{self.previous_chapter_summary}")
        
        if self.previous_chapter_ending:
            sections.append(f"## 上一章结尾（保持连贯）\n{self.previous_chapter_ending}")
        
        # RAG retrieved memories
        if self.relevant_memories:
            memories_text = "\n\n".join(self.relevant_memories)
            sections.append(f"## 相关记忆（保持一致性）\n{memories_text}")
        
        # Current chapter outline
        if self.chapter_outline:
            sections.append(f"## 本章大纲\n{self.chapter_outline}")
        
        return "\n\n---\n\n".join(sections)
    
    def __str__(self) -> str:
        return self.to_prompt()


class ContextBuilder:
    """
    上下文组装器 - 基于大纲预判的 RAG (Outline-based Anticipatory RAG)。
    
    核心功能：
    1. 从大纲中提取关键词和实体
    2. 使用 Vector Store 检索相关历史内容
    3. 从 Structured Store 获取角色当前状态
    4. 组装完整的上下文包
    """
    
    def __init__(self, vector_store: VectorStore, structured_store: StructuredStore):
        """
        Initialize context builder.
        
        Args:
            vector_store: Vector store for RAG retrieval
            structured_store: Structured store for character states
        """
        self.vector_store = vector_store
        self.structured_store = structured_store
    
    def build_context(
        self,
        chapter_outline: ChapterOutline,
        previous_chapter: Optional[Chapter] = None,
        ending_chars: int = 3000,
        max_memories: int = 5
    ) -> ContextPacket:
        """
        Build a complete context packet for the Writer agent.
        
        Args:
            chapter_outline: Current chapter outline
            previous_chapter: Previous chapter (if any)
            ending_chars: Number of characters from previous chapter ending
            max_memories: Maximum number of memory chunks to include
            
        Returns:
            ContextPacket with all necessary context
        """
        packet = ContextPacket()
        
        # Layer 1: Global static context
        novel = self.structured_store.get_novel()
        if novel:
            packet.world_setting = self._format_world_setting(novel.world)
            packet.style_guide = novel.style_guide or "保持文风统一，语言流畅，注意细节描写。"
        
        # Layer 2: Local sliding window
        if previous_chapter:
            packet.previous_chapter_summary = previous_chapter.summary or f"第{previous_chapter.chapter_number}章：{previous_chapter.title}"
            packet.previous_chapter_ending = previous_chapter.content[-ending_chars:] if previous_chapter.content else ""
        
        # Layer 3: Dynamic RAG context
        # Extract keywords from outline
        keywords = self._extract_keywords(chapter_outline)
        
        # Search for relevant memories
        if keywords:
            memories = self._search_relevant_memories(keywords, max_memories)
            packet.relevant_memories = [self._format_memory(m) for m in memories]
        
        # Get character states for involved characters
        if chapter_outline.characters_involved:
            packet.character_states = self._get_character_states(chapter_outline.characters_involved)
        
        # Format current chapter outline
        packet.chapter_outline = self._format_outline(chapter_outline)
        
        return packet
    
    def _format_world_setting(self, world) -> str:
        """Format world setting for prompt."""
        parts = [f"世界: {world.name}", f"类型: {world.genre}"]
        if world.era:
            parts.append(f"时代: {world.era}")
        if world.magic_system:
            parts.append(f"体系: {world.magic_system}")
        if world.core_rules:
            parts.append(f"规则: {'; '.join(world.core_rules)}")
        return "\n".join(parts)
    
    def _extract_keywords(self, outline: ChapterOutline) -> list[str]:
        """
        Extract keywords and entities from chapter outline.
        
        This uses a simple approach - in production, you might use
        NER or LLM-based extraction.
        """
        keywords = set()
        
        # Add explicitly mentioned characters
        keywords.update(outline.characters_involved)
        
        # Extract from goal and scenes
        text = f"{outline.goal} {' '.join(outline.scenes)} {' '.join(outline.key_events)}"
        
        # Simple keyword extraction (Chinese and English)
        # Look for quoted terms
        quoted = re.findall(r'[「」""\'\'](.*?)[「」""\'\']', text)
        keywords.update(quoted)
        
        # Look for proper nouns (simplified - words that appear important)
        # In Chinese, proper nouns often appear with specific patterns
        potential_names = re.findall(r'[\u4e00-\u9fa5]{2,4}(?:的|是|在|说|道|问|答)', text)
        for match in potential_names:
            name = match[:-1]  # Remove the trailing particle
            if len(name) >= 2:
                keywords.add(name)
        
        return list(keywords)
    
    def _search_relevant_memories(self, keywords: list[str], max_results: int) -> list[Document]:
        """Search vector store for relevant memories."""
        all_memories = []
        
        # Search by each keyword/entity
        for keyword in keywords[:5]:  # Limit to avoid too many queries
            docs = self.vector_store.search(keyword, top_k=3)
            all_memories.extend(docs)
        
        # Deduplicate by content
        seen = set()
        unique_memories = []
        for doc in all_memories:
            content_hash = hash(doc.content[:100])
            if content_hash not in seen:
                seen.add(content_hash)
                unique_memories.append(doc)
        
        # Sort by relevance (lower distance = more relevant)
        unique_memories.sort(key=lambda x: x.distance)
        
        return unique_memories[:max_results]
    
    def _format_memory(self, doc: Document) -> str:
        """Format a memory document for the prompt."""
        header = f"[第{doc.chapter_id}章相关段落]"
        if doc.entities:
            header += f" 涉及: {', '.join(doc.entities[:3])}"
        return f"{header}\n{doc.content}"
    
    def _get_character_states(self, character_names: list[str]) -> str:
        """Get current states of specified characters."""
        states = []
        for name in character_names:
            char = self.structured_store.get_character(name)
            if char:
                state_parts = [f"【{name}】"]
                
                # 境界/等级（优先显示）
                if char.power_level:
                    state_parts.append(f"境界: {char.power_level}")
                
                # 技能
                if char.skills:
                    skills_str = ", ".join([f"{k}({v})" for k, v in list(char.skills.items())[:5]])
                    state_parts.append(f"技能: {skills_str}")
                
                # 特殊能力
                if char.abilities:
                    state_parts.append(f"能力: {', '.join(char.abilities[:5])}")
                
                # 装备
                if char.equipment:
                    state_parts.append(f"装备: {', '.join(char.equipment[:5])}")
                
                # 物品（消耗品）
                if char.inventory:
                    state_parts.append(f"物品: {', '.join(char.inventory[:5])}")
                
                # 状态和位置
                status_loc = f"状态: {char.status}"
                if char.location != "unknown":
                    status_loc += f" | 位置: {char.location}"
                state_parts.append(status_loc)
                
                # 关系（简略）
                if char.relationships:
                    rel_strs = [f"{k}({v})" for k, v in list(char.relationships.items())[:3]]
                    state_parts.append(f"关系: {', '.join(rel_strs)}")
                
                states.append("\n".join(state_parts))
        
        return "\n\n".join(states) if states else ""
    
    def _format_outline(self, outline: ChapterOutline) -> str:
        """Format chapter outline for the prompt."""
        parts = [f"第{outline.chapter_number}章"]
        if outline.title:
            parts[0] += f": {outline.title}"
        
        parts.append(f"目标: {outline.goal}")
        
        if outline.scenes:
            parts.append("场景序列:")
            for i, scene in enumerate(outline.scenes, 1):
                parts.append(f"  {i}. {scene}")
        
        if outline.key_events:
            parts.append(f"关键事件: {', '.join(outline.key_events)}")
        
        if outline.foreshadowing:
            parts.append(f"伏笔: {', '.join(outline.foreshadowing)}")
        
        return "\n".join(parts)
