"""Structured Store - JSON-based storage for character states and world data."""

import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from ..models import Novel, Character, WorldSetting, TimelineEvent, Foreshadowing, Chapter, ChapterOutline
from ..config import settings


class StructuredStore:
    """
    结构化存储 - 维护人物状态、物品、关系等结构化数据。
    
    使用 JSON 文件存储，便于持久化和调试。
    每个小说项目有独立的存储目录。
    """
    
    def __init__(self, novel_id: str, data_dir: Optional[Path] = None):
        """
        Initialize structured store for a specific novel.
        
        Args:
            novel_id: Unique identifier for the novel
            data_dir: Base data directory
        """
        self.novel_id = novel_id
        base_dir = data_dir or settings.novels_dir
        self.novel_dir = base_dir / novel_id
        self.novel_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.novel_file = self.novel_dir / "novel.json"
        self.timeline_file = self.novel_dir / "timeline.json"
        self.foreshadowing_file = self.novel_dir / "foreshadowing.json"
        self.chapters_dir = self.novel_dir / "chapters"
        self.chapters_dir.mkdir(exist_ok=True)
        
        # Initialize or load novel
        self._novel: Optional[Novel] = None
        self._timeline: list[TimelineEvent] = []
        self._foreshadowing: list[Foreshadowing] = []
        
        self._load()
    
    def _load(self):
        """Load data from files."""
        # Load novel
        if self.novel_file.exists():
            with open(self.novel_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._novel = Novel.model_validate(data)
        
        # Load timeline
        if self.timeline_file.exists():
            with open(self.timeline_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._timeline = [TimelineEvent.model_validate(e) for e in data]
        
        # Load foreshadowing
        if self.foreshadowing_file.exists():
            with open(self.foreshadowing_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._foreshadowing = [Foreshadowing.model_validate(e) for e in data]
    
    def _save(self):
        """Save data to files."""
        if self._novel:
            with open(self.novel_file, "w", encoding="utf-8") as f:
                json.dump(self._novel.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        
        with open(self.timeline_file, "w", encoding="utf-8") as f:
            json.dump([e.model_dump(mode="json") for e in self._timeline], f, ensure_ascii=False, indent=2)
        
        with open(self.foreshadowing_file, "w", encoding="utf-8") as f:
            json.dump([e.model_dump(mode="json") for e in self._foreshadowing], f, ensure_ascii=False, indent=2)
    
    # Novel operations
    def create_novel(
        self, 
        title: str, 
        synopsis: str = "",
        genre: str = "fantasy",
        style_guide: str = ""
    ) -> Novel:
        """Create a new novel project."""
        self._novel = Novel(
            novel_id=self.novel_id,
            title=title,
            synopsis=synopsis,
            world=WorldSetting(name=title, genre=genre),
            style_guide=style_guide,
        )
        self._save()
        return self._novel
    
    def get_novel(self) -> Optional[Novel]:
        """Get the novel data."""
        return self._novel
    
    def update_novel(self, **updates) -> Optional[Novel]:
        """Update novel fields."""
        if self._novel:
            for key, value in updates.items():
                if hasattr(self._novel, key):
                    setattr(self._novel, key, value)
            self._novel.updated_at = datetime.now()
            self._save()
        return self._novel
    
    # Character operations
    def add_character(self, character: Character) -> Character:
        """Add or update a character."""
        if not self._novel:
            raise ValueError("Novel not initialized")
        
        self._novel.characters[character.name] = character
        self._save()
        return character
    
    def get_character(self, name: str) -> Optional[Character]:
        """Get a character by name."""
        if not self._novel:
            return None
        return self._novel.characters.get(name)
    
    def update_character(self, name: str, updates: dict, chapter_number: int = 0) -> Optional[Character]:
        """Update character fields."""
        if not self._novel or name not in self._novel.characters:
            return None
        
        character = self._novel.characters[name]
        for key, value in updates.items():
            if hasattr(character, key):
                setattr(character, key, value)
        character.last_updated_chapter = chapter_number
        self._save()
        return character
    
    def get_all_characters(self) -> dict[str, Character]:
        """Get all characters."""
        if not self._novel:
            return {}
        return self._novel.characters
    
    # World operations
    def update_world(self, **updates) -> Optional[WorldSetting]:
        """Update world settings."""
        if not self._novel:
            return None
        
        world = self._novel.world
        for key, value in updates.items():
            if hasattr(world, key):
                setattr(world, key, value)
        self._save()
        return world
    
    def get_world(self) -> Optional[WorldSetting]:
        """Get world settings."""
        if not self._novel:
            return None
        return self._novel.world
    
    # Chapter operations
    def save_chapter(self, chapter: Chapter):
        """Save a chapter to disk."""
        if not self._novel:
            raise ValueError("Novel not initialized")
        
        # Update in novel
        existing = self._novel.get_chapter(chapter.chapter_number)
        if existing:
            idx = self._novel.chapters.index(existing)
            self._novel.chapters[idx] = chapter
        else:
            self._novel.chapters.append(chapter)
            self._novel.chapters.sort(key=lambda c: c.chapter_number)
        
        # Save chapter file
        chapter_file = self.chapters_dir / f"chapter_{chapter.chapter_number:03d}.json"
        with open(chapter_file, "w", encoding="utf-8") as f:
            json.dump(chapter.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        
        self._save()
    
    def get_chapter(self, chapter_number: int) -> Optional[Chapter]:
        """Get a chapter by number."""
        if not self._novel:
            return None
        return self._novel.get_chapter(chapter_number)
    
    def get_latest_chapter(self) -> Optional[Chapter]:
        """Get the most recent chapter."""
        if not self._novel:
            return None
        return self._novel.get_latest_chapter()
    
    def get_chapter_count(self) -> int:
        """Get the number of chapters."""
        if not self._novel:
            return 0
        return len(self._novel.chapters)
    
    # Timeline operations
    def add_timeline_event(self, event: TimelineEvent):
        """Add a timeline event."""
        self._timeline.append(event)
        self._timeline.sort(key=lambda e: e.chapter_number)
        self._save()
    
    def get_timeline(self, chapter_range: Optional[tuple[int, int]] = None) -> list[TimelineEvent]:
        """Get timeline events, optionally filtered by chapter range."""
        if chapter_range is None:
            return self._timeline
        
        start, end = chapter_range
        return [e for e in self._timeline if start <= e.chapter_number <= end]
    
    # Foreshadowing operations
    def add_foreshadowing(self, foreshadowing: Foreshadowing):
        """Add a new foreshadowing element."""
        self._foreshadowing.append(foreshadowing)
        self._save()
    
    def resolve_foreshadowing(self, foreshadowing_id: str, resolved_chapter: int):
        """Mark a foreshadowing as resolved."""
        for f in self._foreshadowing:
            if f.id == foreshadowing_id:
                f.resolved_chapter = resolved_chapter
                f.status = "resolved"
                break
        self._save()
    
    def get_unresolved_foreshadowing(self) -> list[Foreshadowing]:
        """Get all unresolved foreshadowing elements."""
        return [f for f in self._foreshadowing if f.status != "resolved"]
    
    def get_all_foreshadowing(self) -> list[Foreshadowing]:
        """Get all foreshadowing elements."""
        return self._foreshadowing
    
    # Utility methods
    def get_summary_for_context(self) -> str:
        """
        Generate a summary suitable for injecting into prompts.
        Includes key character states and recent events.
        """
        if not self._novel:
            return ""
        
        summary_parts = []
        
        # World setting
        world = self._novel.world
        summary_parts.append(f"## 世界观\n- 类型: {world.genre}\n- 背景: {world.era or '未设定'}")
        if world.core_rules:
            summary_parts.append(f"- 核心规则: {'; '.join(world.core_rules[:3])}")
        
        # Active characters
        if self._novel.characters:
            summary_parts.append("\n## 主要角色状态")
            for name, char in list(self._novel.characters.items())[:5]:  # Top 5 characters
                status_line = f"- {name}: {char.status}"
                if char.location != "unknown":
                    status_line += f", 位于{char.location}"
                if char.inventory:
                    status_line += f", 持有[{', '.join(char.inventory[:3])}]"
                summary_parts.append(status_line)
        
        # Recent timeline events
        recent_events = self._timeline[-5:] if self._timeline else []
        if recent_events:
            summary_parts.append("\n## 近期事件")
            for event in recent_events:
                summary_parts.append(f"- 第{event.chapter_number}章: {event.event}")
        
        # Unresolved foreshadowing
        unresolved = self.get_unresolved_foreshadowing()[:3]
        if unresolved:
            summary_parts.append("\n## 待揭示的伏笔")
            for f in unresolved:
                summary_parts.append(f"- [{f.id}] {f.description} (埋于第{f.planted_chapter}章)")
        
        return "\n".join(summary_parts)
