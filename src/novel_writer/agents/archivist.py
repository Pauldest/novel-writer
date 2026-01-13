"""Archivist Agent - Extracts and archives key information from chapters."""

from typing import Optional
from pydantic import BaseModel, Field

from .base import BaseAgent
from ..models import Chapter, Character, TimelineEvent, Foreshadowing
from ..memory.vector_store import VectorStore
from ..memory.structured_store import StructuredStore


class CharacterUpdate(BaseModel):
    """角色状态更新"""
    name: str
    status: Optional[str] = None
    location: Optional[str] = None
    inventory_add: list[str] = Field(default_factory=list)
    inventory_remove: list[str] = Field(default_factory=list)
    relationship_updates: dict[str, str] = Field(default_factory=dict)
    notes: str = ""


class ArchiveResult(BaseModel):
    """Archivist Agent 的输出结构"""
    chapter_summary: str = Field(..., description="章节摘要（100-200字）")
    key_events: list[str] = Field(default_factory=list, description="本章关键事件")
    character_updates: list[CharacterUpdate] = Field(default_factory=list, description="角色状态变化")
    new_foreshadowing: list[str] = Field(default_factory=list, description="新埋的伏笔")
    resolved_foreshadowing: list[str] = Field(default_factory=list, description="揭示的伏笔ID")
    important_items: list[str] = Field(default_factory=list, description="出现的重要物品")
    new_locations: list[str] = Field(default_factory=list, description="新出现的地点")
    entities_mentioned: list[str] = Field(default_factory=list, description="提及的所有实体（人物、物品、地点）")


ARCHIVIST_SYSTEM_PROMPT = """你是一位细心的记忆管理员（Archivist），负责从已完成的章节中提取关键信息并归档。

你的职责：
1. 生成章节摘要
2. 记录关键事件到时间线
3. 更新角色状态（位置、持有物品、关系变化）
4. 识别和记录伏笔
5. 提取重要实体（人物、物品、地点）供检索

提取规则：
- 摘要要精炼，只包含核心情节，100-200字
- 角色状态只记录明确发生变化的
- 伏笔要足够隐晦才算，明显的情节不算伏笔
- 实体名称要准确，便于后续检索

特别注意：
- 如果角色获得或失去物品，必须记录
- 如果角色位置发生变化，必须更新
- 如果角色关系发生变化（如结仇、和好），必须记录
- 如果有人物死亡或重伤，必须更新状态"""


class ArchivistAgent(BaseAgent[ArchiveResult]):
    """
    记忆管理员 Agent - 提取并归档章节关键信息。
    
    职责：
    - 生成章节摘要
    - 更新角色状态
    - 记录时间线事件
    - 追踪伏笔
    - 索引实体便于检索
    """
    
    def __init__(self, temperature: float = 0.2):
        super().__init__(
            system_prompt=ARCHIVIST_SYSTEM_PROMPT,
            response_schema=ArchiveResult,
            temperature=temperature,  # Very low for consistent extraction
        )
    
    def run(
        self,
        chapter: Chapter,
        vector_store: VectorStore,
        structured_store: StructuredStore,
    ) -> ArchiveResult:
        """
        Archive a completed chapter.
        
        Args:
            chapter: The completed chapter to archive
            vector_store: Vector store to add chapter chunks
            structured_store: Structured store to update states
            
        Returns:
            ArchiveResult with extracted information
        """
        # Build extraction prompt
        prompt_parts = []
        
        # Current character states for reference
        characters = structured_store.get_all_characters()
        if characters:
            prompt_parts.append("# 当前已知角色状态")
            for name, char in list(characters.items())[:10]:
                prompt_parts.append(f"- {name}: 状态={char.status}, 位置={char.location}, 物品={char.inventory[:5]}")
        
        # Known foreshadowing
        unresolved = structured_store.get_unresolved_foreshadowing()
        if unresolved:
            prompt_parts.append("\n# 未揭示的伏笔")
            for f in unresolved[:5]:
                prompt_parts.append(f"- [{f.id}] {f.description}")
        
        # Chapter content
        prompt_parts.append(f"\n# 第{chapter.chapter_number}章内容")
        prompt_parts.append(f"标题: {chapter.title}")
        prompt_parts.append(f"\n{chapter.content}")
        
        prompt_parts.append("\n# 任务\n请从以上章节中提取关键信息进行归档。")
        
        prompt = "\n".join(prompt_parts)
        
        # Extract information
        result: ArchiveResult = self.invoke(prompt)
        
        # Apply updates to stores
        self._apply_updates(chapter, result, vector_store, structured_store)
        
        return result
    
    def _apply_updates(
        self,
        chapter: Chapter,
        result: ArchiveResult,
        vector_store: VectorStore,
        structured_store: StructuredStore,
    ):
        """Apply extracted updates to the stores."""
        
        # Update chapter summary
        chapter.summary = result.chapter_summary
        
        # Add chapter to vector store
        vector_store.add_chapter(
            chapter_id=chapter.chapter_number,
            content=chapter.content,
            summary=result.chapter_summary,
            entities=result.entities_mentioned,
        )
        
        # Update character states
        for update in result.character_updates:
            char = structured_store.get_character(update.name)
            if char:
                updates = {}
                if update.status:
                    updates["status"] = update.status
                if update.location:
                    updates["location"] = update.location
                if update.inventory_add:
                    new_inventory = list(char.inventory) + update.inventory_add
                    updates["inventory"] = new_inventory
                if update.inventory_remove:
                    updates["inventory"] = [i for i in char.inventory if i not in update.inventory_remove]
                if update.relationship_updates:
                    new_relationships = dict(char.relationships)
                    new_relationships.update(update.relationship_updates)
                    updates["relationships"] = new_relationships
                if update.notes:
                    updates["notes"] = char.notes + f"\n第{chapter.chapter_number}章: {update.notes}"
                
                if updates:
                    structured_store.update_character(
                        update.name, 
                        updates, 
                        chapter_number=chapter.chapter_number
                    )
        
        # Add timeline events
        for event in result.key_events:
            timeline_event = TimelineEvent(
                chapter_number=chapter.chapter_number,
                event=event,
                characters_involved=result.entities_mentioned[:5],
                importance="normal",
            )
            structured_store.add_timeline_event(timeline_event)
        
        # Handle foreshadowing
        for foreshadow_desc in result.new_foreshadowing:
            foreshadow = Foreshadowing(
                id=f"fs_{chapter.chapter_number}_{len(result.new_foreshadowing)}",
                description=foreshadow_desc,
                planted_chapter=chapter.chapter_number,
            )
            structured_store.add_foreshadowing(foreshadow)
        
        for foreshadow_id in result.resolved_foreshadowing:
            structured_store.resolve_foreshadowing(foreshadow_id, chapter.chapter_number)
        
        # Save the updated chapter
        structured_store.save_chapter(chapter)
