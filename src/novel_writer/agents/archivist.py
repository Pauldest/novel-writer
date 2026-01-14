"""Archivist Agent - Extracts and archives key information from chapters."""

from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from ..trace_store import TraceStore
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
    relationship_updates: list[str] = Field(default_factory=list, description="关系变化列表，格式 '角色名: 关系描述'")
    notes: str = ""
    
    # 动态状态更新
    skill_updates: list[str] = Field(default_factory=dict, description="技能变化列表，格式 '技能名: 描述/等级'")
    new_abilities: list[str] = Field(default_factory=list, description="新获得的能力")
    lost_abilities: list[str] = Field(default_factory=list, description="失去的能力")
    power_level: Optional[str] = Field(default=None, description="境界/等级变化")
    equipment_add: list[str] = Field(default_factory=list, description="新装备")
    equipment_remove: list[str] = Field(default_factory=list, description="失去的装备")


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
3. 更新角色状态（位置、持有物品、关系变化、技能、能力、境界）
4. 识别和记录伏笔
5. 提取重要实体（人物、物品、地点）供检索

提取规则：
- 摘要要精炼，只包含核心情节，100-200字
- 角色状态只记录明确发生变化的
- 伏笔要足够隐晦才算，明显的情节不算伏笔
- 实体名称要准确，便于后续检索

特别注意：
- 如果角色获得或失去物品/装备，必须记录到对应字段
- 如果角色位置发生变化，必须更新
- 如果角色关系发生变化（如结仇、和好），以 '角色名: 新关系' 的格式记录到 relationship_updates
- 如果有人物死亡或重伤，必须更新状态
- 如果角色技能提升（如剑法从入门到小成），以 '技能名: 新等级/描述' 的格式记录到 skill_updates
- 如果角色获得新能力（如火焰抗性），必须记录到 new_abilities
- 如果角色境界/等级变化（如突破到凝气期），必须记录到 power_level
- 装备（武器、防具）和消耗品（丹药、灵石）要区分开"""


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
        trace: Optional["TraceStore"] = None,
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
        
        if trace:
            trace.save_archivist_context(
                full_prompt=prompt,
                system_prompt=self.system_prompt
            )
            
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
                
                # Parse relationship updates
                if update.relationship_updates:
                    new_relationships = dict(char.relationships)
                    for rel_str in update.relationship_updates:
                        if ":" in rel_str:
                            target, status = rel_str.split(":", 1)
                            new_relationships[target.strip()] = status.strip()
                        else:
                            # Fallback if format is wrong, just log it as a generic note or key
                            new_relationships[rel_str] = "updated"
                    updates["relationships"] = new_relationships

                if update.notes:
                    updates["notes"] = char.notes + f"\n第{chapter.chapter_number}章: {update.notes}"
                
                # Parse skill updates
                if update.skill_updates:
                    new_skills = dict(char.skills)
                    for skill_str in update.skill_updates:
                        if ":" in skill_str:
                            skill_name, skill_desc = skill_str.split(":", 1)
                            new_skills[skill_name.strip()] = skill_desc.strip()
                        else:
                            # Fallback: Treat as new skill with description "acquired" or update existing
                            new_skills[skill_str.strip()] = "acquired/updated"
                    updates["skills"] = new_skills
                
                # 处理能力更新
                if update.new_abilities:
                    new_abilities = list(char.abilities) + update.new_abilities
                    updates["abilities"] = new_abilities
                if update.lost_abilities:
                    current = updates.get("abilities", list(char.abilities))
                    updates["abilities"] = [a for a in current if a not in update.lost_abilities]
                
                # 处理境界更新
                if update.power_level:
                    updates["power_level"] = update.power_level
                
                # 处理装备更新
                if update.equipment_add:
                    new_equipment = list(char.equipment) + update.equipment_add
                    updates["equipment"] = new_equipment
                if update.equipment_remove:
                    current = updates.get("equipment", list(char.equipment))
                    updates["equipment"] = [e for e in current if e not in update.equipment_remove]
                
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
