"""Data models for novel structure."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Character(BaseModel):
    """角色模型 - 追踪人物状态"""
    
    name: str = Field(..., description="角色名称")
    description: str = Field(default="", description="外貌和性格描述")
    status: str = Field(default="alive", description="当前状态: alive/dead/unknown")
    location: str = Field(default="unknown", description="当前位置")
    inventory: list[str] = Field(default_factory=list, description="持有物品（消耗品）")
    relationships: dict[str, str] = Field(default_factory=dict, description="与其他角色的关系")
    notes: str = Field(default="", description="其他备注")
    last_updated_chapter: int = Field(default=0, description="最后更新的章节号")
    
    # 动态状态追踪
    skills: dict[str, str] = Field(default_factory=dict, description="技能名 -> 等级/描述")
    abilities: list[str] = Field(default_factory=list, description="特殊能力列表")
    power_level: str = Field(default="", description="修炼境界/等级")
    equipment: list[str] = Field(default_factory=list, description="装备列表")


class ChapterOutline(BaseModel):
    """章节大纲"""
    
    chapter_number: int = Field(..., description="章节号")
    title: str = Field(default="", description="章节标题")
    goal: str = Field(..., description="本章目标")
    scenes: list[str] = Field(default_factory=list, description="场景列表")
    key_events: list[str] = Field(default_factory=list, description="关键事件")
    characters_involved: list[str] = Field(default_factory=list, description="涉及角色")
    foreshadowing: list[str] = Field(default_factory=list, description="伏笔")


class Chapter(BaseModel):
    """章节模型"""
    
    chapter_number: int = Field(..., description="章节号")
    title: str = Field(default="", description="章节标题")
    outline: ChapterOutline = Field(..., description="章节大纲")
    content: str = Field(default="", description="正文内容")
    summary: str = Field(default="", description="章节摘要")
    word_count: int = Field(default=0, description="字数")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class WorldSetting(BaseModel):
    """世界观设定"""
    
    name: str = Field(..., description="世界名称")
    genre: str = Field(default="fantasy", description="类型: fantasy/scifi/wuxia/modern")
    era: str = Field(default="", description="时代背景")
    magic_system: str = Field(default="", description="魔法/科技体系")
    core_rules: list[str] = Field(default_factory=list, description="核心规则")
    locations: dict[str, str] = Field(default_factory=dict, description="重要地点")
    factions: dict[str, str] = Field(default_factory=dict, description="势力/组织")


class Novel(BaseModel):
    """小说项目模型"""
    
    novel_id: str = Field(..., description="小说唯一ID")
    title: str = Field(..., description="小说标题")
    author: str = Field(default="AI Writer", description="作者")
    synopsis: str = Field(default="", description="简介")
    world: WorldSetting = Field(default_factory=lambda: WorldSetting(name="Default World"))
    characters: dict[str, Character] = Field(default_factory=dict, description="角色字典")
    chapters: list[Chapter] = Field(default_factory=list, description="章节列表")
    total_outline: str = Field(default="", description="总大纲")
    style_guide: str = Field(default="", description="风格指南")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    def get_latest_chapter(self) -> Optional[Chapter]:
        """获取最新章节"""
        return self.chapters[-1] if self.chapters else None
    
    def get_chapter(self, chapter_number: int) -> Optional[Chapter]:
        """获取指定章节"""
        for chapter in self.chapters:
            if chapter.chapter_number == chapter_number:
                return chapter
        return None


class TimelineEvent(BaseModel):
    """时间线事件"""
    
    chapter_number: int = Field(..., description="发生章节")
    event: str = Field(..., description="事件描述")
    characters_involved: list[str] = Field(default_factory=list, description="涉及角色")
    location: str = Field(default="", description="发生地点")
    importance: str = Field(default="normal", description="重要程度: minor/normal/major/critical")


class Foreshadowing(BaseModel):
    """伏笔追踪"""
    
    id: str = Field(..., description="伏笔ID")
    description: str = Field(..., description="伏笔描述")
    planted_chapter: int = Field(..., description="埋下伏笔的章节")
    resolved_chapter: Optional[int] = Field(default=None, description="揭示伏笔的章节")
    status: str = Field(default="planted", description="状态: planted/hinted/resolved")
