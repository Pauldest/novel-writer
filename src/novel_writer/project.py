"""Novel Project - File-based novel project management."""

import re
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime

from .models import Novel, Character, ChapterOutline, WorldSetting
from .memory.structured_store import StructuredStore
from .memory.vector_store import VectorStore


class NovelProject:
    """
    基于文件的小说项目管理。
    
    项目结构：
    ```
    我的小说/               # 文件夹名 = 小说标题
    ├── roles.md           # 角色设定
    ├── outline.md         # 大纲（包含章节概括）
    ├── style.md           # 风格指南（可选）
    ├── world.md           # 世界观设定（可选）
    ├── chapters/          # 生成的章节
    │   ├── 001.md
    │   ├── 002.md
    │   └── ...
    └── .novel/            # 系统数据（自动生成）
        ├── novel.json
        ├── chroma_db/
        └── ...
    ```
    """
    
    def __init__(self, project_path: Path | str):
        """
        Initialize from a project directory.
        
        Args:
            project_path: Path to the novel project folder
        """
        self.project_path = Path(project_path).resolve()
        
        if not self.project_path.exists():
            raise ValueError(f"项目目录不存在: {self.project_path}")
        
        # Derive novel title from folder name
        self.title = self.project_path.name
        
        # File paths
        self.roles_file = self.project_path / "roles.md"
        self.outline_file = self.project_path / "outline.md"
        self.style_file = self.project_path / "style.md"
        self.world_file = self.project_path / "world.md"
        self.chapters_dir = self.project_path / "chapters"
        self.data_dir = self.project_path / ".novel"
        
        # Ensure directories exist
        self.chapters_dir.mkdir(exist_ok=True)
        self.data_dir.mkdir(exist_ok=True)
        
        # Novel ID: use hash of absolute path for unique ASCII-only identifier
        # ChromaDB requires collection names to be ASCII only
        path_hash = hashlib.md5(str(self.project_path).encode()).hexdigest()[:12]
        self.novel_id = f"novel_{path_hash}"
        
        # Initialize stores
        self.structured_store = StructuredStore(
            self.novel_id, 
            data_dir=self.data_dir
        )
        self.vector_store = VectorStore(
            self.novel_id,
            persist_directory=str(self.data_dir / "chroma_db")
        )
        
        # Load or create novel
        self._load_or_create_novel()
    
    def _load_or_create_novel(self):
        """Load existing novel or create from markdown files."""
        novel = self.structured_store.get_novel()
        
        if not novel:
            # Create new novel from folder
            novel = self.structured_store.create_novel(
                title=self.title,
                synopsis=self._read_synopsis(),
                genre=self._detect_genre(),
                style_guide=self._read_style(),
            )
        
        # Sync characters from roles.md
        self._sync_characters()
        
        # Sync outline from outline.md
        self._sync_outline()
        
        # Sync world from world.md
        self._sync_world()
    
    def _read_synopsis(self) -> str:
        """Read synopsis from outline.md header."""
        if not self.outline_file.exists():
            return ""
        
        content = self.outline_file.read_text(encoding="utf-8")
        # Look for synopsis section
        match = re.search(r'##\s*简介\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # Or just use the first paragraph
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                return line
        
        return ""
    
    def _detect_genre(self) -> str:
        """Detect genre from content or default to fantasy."""
        if not self.outline_file.exists():
            return "fantasy"
        
        content = self.outline_file.read_text(encoding="utf-8").lower()
        
        genre_keywords = {
            "wuxia": ["武侠", "江湖", "剑", "武功", "门派"],
            "xianxia": ["修仙", "修真", "灵气", "飞升", "仙"],
            "scifi": ["科幻", "太空", "星际", "机器人", "未来"],
            "modern": ["现代", "都市", "公司", "办公室"],
            "fantasy": ["奇幻", "魔法", "精灵", "龙"],
        }
        
        for genre, keywords in genre_keywords.items():
            if any(kw in content for kw in keywords):
                return genre
        
        return "fantasy"
    
    def _read_style(self) -> str:
        """Read style guide from style.md."""
        if not self.style_file.exists():
            return "保持文风统一，语言流畅，注意细节描写。"
        
        return self.style_file.read_text(encoding="utf-8").strip()
    
    def _sync_characters(self):
        """Sync characters from roles.md."""
        if not self.roles_file.exists():
            return
        
        content = self.roles_file.read_text(encoding="utf-8")
        characters = self._parse_roles_md(content)
        
        for char in characters:
            existing = self.structured_store.get_character(char.name)
            if not existing:
                self.structured_store.add_character(char)
            elif existing.description != char.description:
                # Update if description changed
                self.structured_store.update_character(
                    char.name, 
                    {"description": char.description}
                )
    
    def _parse_roles_md(self, content: str) -> list[Character]:
        """
        Parse roles.md file.
        
        Expected format:
        ```
        # 角色设定
        
        ## 李白
        一位浪漫的诗人剑客，性格洒脱不羁。
        
        ## 杜甫
        忧国忧民的诗人，性格沉稳内敛。
        ```
        """
        characters = []
        
        # Split by ## headers
        sections = re.split(r'\n##\s+', content)
        
        for section in sections[1:]:  # Skip the first part before any ##
            lines = section.strip().split('\n')
            if not lines:
                continue
            
            name = lines[0].strip()
            description = '\n'.join(lines[1:]).strip()
            
            if name:
                characters.append(Character(
                    name=name,
                    description=description,
                ))
        
        return characters
    
    def _sync_outline(self):
        """Sync outline from outline.md."""
        if not self.outline_file.exists():
            return
        
        content = self.outline_file.read_text(encoding="utf-8")
        self.structured_store.update_novel(total_outline=content)
    
    def _sync_world(self):
        """Sync world settings from world.md."""
        if not self.world_file.exists():
            return
        
        content = self.world_file.read_text(encoding="utf-8")
        
        # Parse world settings
        world = self.structured_store.get_world()
        if world:
            # Extract magic/power system
            match = re.search(r'##\s*(?:体系|力量体系|魔法体系)\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
            if match:
                world.magic_system = match.group(1).strip()
            
            # Extract core rules
            match = re.search(r'##\s*(?:规则|核心规则)\s*\n(.*?)(?=\n##|\Z)', content, re.DOTALL)
            if match:
                rules_text = match.group(1).strip()
                world.core_rules = [
                    r.strip().lstrip('-').strip() 
                    for r in rules_text.split('\n') 
                    if r.strip() and r.strip().startswith('-')
                ]
            
            self.structured_store.update_world(**world.model_dump())
    
    def get_novel(self) -> Optional[Novel]:
        """Get the novel object."""
        return self.structured_store.get_novel()
    
    def get_chapter_outlines(self) -> list[dict]:
        """
        Parse chapter outlines from outline.md.
        
        Expected format:
        ```
        # 大纲
        
        ## 第一章：初入江湖
        主角离开家乡，踏上修仙之路...
        
        ## 第二章：奇遇
        在山洞中发现古老的传承...
        ```
        """
        if not self.outline_file.exists():
            return []
        
        content = self.outline_file.read_text(encoding="utf-8")
        chapters = []
        
        # Match chapter headers: must start with "第X章" format
        # E.g.: ## 第一章：初入江湖 or ## 第1章：开端
        pattern = r'##\s*第([一二三四五六七八九十百千\d]+)章[：:.\s]*(.+?)\n(.*?)(?=\n##\s*第|$)'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches:
            num_str, title, description = match
            
            # Parse chapter number
            try:
                chapter_num = self._parse_chinese_number(num_str)
            except:
                chapter_num = 1
            
            chapters.append({
                "chapter_number": chapter_num,
                "title": title.strip(),
                "goal": description.strip(),
            })
        
        return chapters
    
    def _parse_chinese_number(self, s: str) -> int:
        """Parse Chinese number to integer."""
        # Try direct int first
        try:
            return int(s)
        except ValueError:
            pass
        
        # Chinese numerals
        chinese_nums = {
            '零': 0, '一': 1, '二': 2, '三': 3, '四': 4,
            '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
            '十': 10, '百': 100, '千': 1000
        }
        
        result = 0
        temp = 0
        
        for char in s:
            if char in chinese_nums:
                num = chinese_nums[char]
                if num >= 10:
                    if temp == 0:
                        temp = 1
                    result += temp * num
                    temp = 0
                else:
                    temp = num
        
        return result + temp if result or temp else 1
    
    def get_generated_chapters(self) -> list[int]:
        """Get list of already generated chapter numbers."""
        if not self.chapters_dir.exists():
            return []
        
        chapters = []
        for f in self.chapters_dir.glob("*.md"):
            match = re.match(r'(\d+)', f.stem)
            if match:
                chapters.append(int(match.group(1)))
        
        return sorted(chapters)
    
    def get_next_chapter_to_write(self) -> Optional[dict]:
        """Get the next chapter that needs to be written."""
        outlines = self.get_chapter_outlines()
        generated = set(self.get_generated_chapters())
        
        for outline in outlines:
            if outline["chapter_number"] not in generated:
                return outline
        
        return None
    
    def save_chapter(self, chapter_number: int, title: str, content: str):
        """Save a generated chapter to the chapters directory."""
        filename = f"{chapter_number:03d}.md"
        filepath = self.chapters_dir / filename
        
        full_content = f"# 第{chapter_number}章：{title}\n\n{content}"
        filepath.write_text(full_content, encoding="utf-8")
    
    def read_chapter(self, chapter_number: int) -> Optional[str]:
        """Read a generated chapter."""
        filename = f"{chapter_number:03d}.md"
        filepath = self.chapters_dir / filename
        
        if filepath.exists():
            return filepath.read_text(encoding="utf-8")
        return None
    
    def get_previous_chapter_content(self) -> Optional[str]:
        """Get the content of the most recently written chapter."""
        generated = self.get_generated_chapters()
        if generated:
            return self.read_chapter(generated[-1])
        return None
    
    def delete_chapter(self, chapter_number: int) -> bool:
        """
        Delete a generated chapter and its associated data.
        
        This deletes:
        - Chapter markdown file
        - Trace files
        - StructuredStore data (chapter JSON, timeline events, foreshadowing)
        - VectorStore embeddings
        
        Args:
            chapter_number: The chapter number to delete
            
        Returns:
            True if deleted, False if chapter didn't exist
        """
        import shutil
        
        deleted = False
        
        # Delete from StructuredStore (JSON data, timeline, foreshadowing)
        if self.structured_store.delete_chapter(chapter_number):
            deleted = True
        
        # Delete from VectorStore (Chroma embeddings)
        self.vector_store.delete_chapter(chapter_number)
        
        # Delete chapter markdown file
        filename = f"{chapter_number:03d}.md"
        filepath = self.chapters_dir / filename
        if filepath.exists():
            filepath.unlink()
            deleted = True
        
        # Delete trace directory if exists
        trace_dir = self.chapters_dir / f"chapter_{chapter_number:03d}" / ".trace"
        if trace_dir.exists():
            shutil.rmtree(trace_dir)
        
        # Delete chapter directory if empty
        chapter_dir = self.chapters_dir / f"chapter_{chapter_number:03d}"
        if chapter_dir.exists() and not any(chapter_dir.iterdir()):
            chapter_dir.rmdir()
        
        return deleted


def find_novel_project(start_path: Path = None) -> Optional[NovelProject]:
    """
    Find a novel project from the current directory upward.
    
    Looks for outline.md or roles.md to identify a novel project.
    """
    if start_path is None:
        start_path = Path.cwd()
    
    current = start_path.resolve()
    
    while current != current.parent:
        if (current / "outline.md").exists() or (current / "roles.md").exists():
            return NovelProject(current)
        current = current.parent
    
    # Check if start_path itself is a project
    if (start_path / "outline.md").exists() or (start_path / "roles.md").exists():
        return NovelProject(start_path)
    
    return None
