"""Trace Store - Persists Agent outputs for debugging and analysis."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field, asdict

from pydantic import BaseModel


@dataclass
class TraceMetadata:
    """Metadata for a trace entry."""
    timestamp: str
    agent_name: str
    step_number: int
    duration_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


class TraceStore:
    """
    Agent 输出追踪存储器。
    
    负责将各 Agent 的输出保存到章节的 .trace 目录中，
    用于调试和分析生成流程。
    """
    
    def __init__(self, novel_path: Path, chapter_number: int):
        """
        Initialize trace store.
        
        Args:
            novel_path: Path to the novel directory
            chapter_number: Chapter number being generated
        """
        self.chapter_number = chapter_number
        self.trace_dir = novel_path / "chapters" / f"chapter_{chapter_number:03d}" / ".trace"
        self.step_counter = 0
        self._start_times: dict[str, datetime] = {}
        
        # Create trace directory
        self.trace_dir.mkdir(parents=True, exist_ok=True)
    
    def _next_step(self) -> int:
        """Get and increment step counter."""
        self.step_counter += 1
        return self.step_counter
    
    def _save_json(self, filename: str, data: dict, agent_name: str) -> Path:
        """Save data as JSON file with metadata."""
        step = self._next_step()
        filepath = self.trace_dir / f"{step:03d}_{filename}"
        
        # Add metadata
        output = {
            "_metadata": TraceMetadata(
                timestamp=datetime.now().isoformat(),
                agent_name=agent_name,
                step_number=step,
                duration_ms=self._get_duration(agent_name),
            ).to_dict(),
            **data
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        return filepath
    
    def _save_text(self, filename: str, content: str, agent_name: str) -> Path:
        """Save content as text/markdown file."""
        step = self._next_step()
        filepath = self.trace_dir / f"{step:03d}_{filename}"
        
        # Add header with metadata
        header = f"""<!-- 
Agent: {agent_name}
Timestamp: {datetime.now().isoformat()}
Step: {step}
Duration: {self._get_duration(agent_name) or 'N/A'}ms
-->

"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(header + content)
        
        return filepath
    
    def _pydantic_to_dict(self, obj: Any) -> dict:
        """Convert Pydantic model to dict."""
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        return obj
    
    def start_timer(self, agent_name: str):
        """Start timing an agent execution."""
        self._start_times[agent_name] = datetime.now()
    
    def _get_duration(self, agent_name: str) -> Optional[float]:
        """Get duration in milliseconds for an agent."""
        if agent_name in self._start_times:
            delta = datetime.now() - self._start_times[agent_name]
            return delta.total_seconds() * 1000
        return None
    
    def save_director_context(self, novel: Any, next_chapter_number: int, user_goal: str, full_prompt: Optional[str] = None) -> Path:
        """
        Save Director agent input context.
        """
        data = {
            "novel_title": getattr(novel, "title", "Unknown"),
            "next_chapter_number": next_chapter_number,
            "user_goal": user_goal,
            "novel_summary": getattr(novel, "synopsis", ""),
            "full_prompt": full_prompt,
        }
        return self._save_json("director_context.json", data, "Director")

    def save_director(self, output: Any) -> Path:
        """
        Save Director agent output.
        
        Args:
            output: DirectorOutput instance
            
        Returns:
            Path to saved file
        """
        data = self._pydantic_to_dict(output)
        return self._save_json("director.json", data, "Director")
    
    def save_plotter_context(
        self, 
        director_output: Any, 
        novel: Any, 
        previous_chapter_summary: Optional[str],
        full_prompt: Optional[str] = None
    ) -> Path:
        """
        Save Plotter agent input context.
        """
        data = {
            "director_output": self._pydantic_to_dict(director_output),
            "novel_title": getattr(novel, "title", "Unknown"),
            "previous_chapter_summary": previous_chapter_summary,
            "full_prompt": full_prompt,
        }
        return self._save_json("plotter_context.json", data, "Plotter")

    def save_plotter(self, plotter_output: Any, outline: Any) -> Path:
        """
        Save Plotter agent output.
        
        Args:
            plotter_output: PlotterOutput instance (raw LLM output)
            outline: ChapterOutline instance (processed output)
            
        Returns:
            Path to saved file
        """
        data = {
            "plotter_output": self._pydantic_to_dict(plotter_output),
            "chapter_outline": self._pydantic_to_dict(outline),
        }
        return self._save_json("plotter.json", data, "Plotter")
    
    def save_context(self, context: Any) -> Path:
        """
        Save ContextBuilder output.
        
        Args:
            context: ContextPacket instance
            
        Returns:
            Path to saved file
        """
        # ContextPacket is a dataclass, not Pydantic
        if hasattr(context, "__dict__"):
            data = {
                "world_setting": context.world_setting,
                "previous_chapter_summary": context.previous_chapter_summary,
                "previous_chapter_ending": context.previous_chapter_ending,
                "relevant_memories": context.relevant_memories,
                "character_states": context.character_states,
                "chapter_outline": context.chapter_outline,
            }
        else:
            data = {"raw": str(context)}
        
        return self._save_json("context.json", data, "ContextBuilder")
    
    def save_writer_start_context(
        self,
        outline: Any,
        context: Any,
        target_word_count: int,
        full_prompt: Optional[str] = None
    ) -> Path:
        """
        Save Writer agent input context (initial run).
        """
        # Build context data
        context_data = {}
        if hasattr(context, "__dict__"):
            context_data = {
                "world_setting": context.world_setting,
                "style_guide": context.style_guide,
                "previous_chapter_ending": context.previous_chapter_ending,
                "character_states": context.character_states,
                "relevant_memories": context.relevant_memories,
            }

        data = {
            "outline": self._pydantic_to_dict(outline),
            "context": context_data,
            "target_word_count": target_word_count,
            "full_prompt": full_prompt,
        }
        return self._save_json("writer_start_context.json", data, "Writer")

    def save_writer_draft(self, content: str) -> Path:
        """
        Save Writer agent initial draft.
        
        Args:
            content: Draft content
            
        Returns:
            Path to saved file
        """
        return self._save_text("writer_draft.md", content, "Writer")
    
    def save_writer_revision(self, content: str, revision_number: int) -> Path:
        """
        Save Writer agent revision.
        
        Args:
            content: Revised content
            revision_number: Revision attempt number
            
        Returns:
            Path to saved file
        """
        return self._save_text(f"writer_rev{revision_number}.md", content, "Writer")
    
    def save_writer_final(self, content: str) -> Path:
        """
        Save Writer agent final version.
        
        Args:
            content: Final content
            
        Returns:
            Path to saved file
        """
        return self._save_text("writer_final.md", content, "Writer")
    
    def save_reviewer_context(
        self,
        content: str,
        outline: Any,
        context: Any,
        previous_review: Any = None,
        attempt: int = 1,
        full_prompt: Optional[str] = None
    ) -> Path:
        """
        Save Reviewer agent input context.
        """
        context_data = {}
        if hasattr(context, "__dict__"):
            context_data = {
                "world_setting": context.world_setting,
                "style_guide": context.style_guide,
                "character_states": context.character_states,
            }
            
        data = {
            "content_preview": content[:1000] + "..." if len(content) > 1000 else content,
            "content_length": len(content),
            "outline": self._pydantic_to_dict(outline),
            "context": context_data,
            "previous_review": self._pydantic_to_dict(previous_review) if previous_review else None,
            "attempt": attempt,
            "full_prompt": full_prompt,
        }
        return self._save_json(f"reviewer_context_{attempt}.json", data, "Reviewer")

    def save_review(self, result: Any, attempt: int) -> Path:
        """
        Save Reviewer agent output.
        
        Args:
            result: ReviewResult instance
            attempt: Review attempt number
            
        Returns:
            Path to saved file
        """
        data = self._pydantic_to_dict(result)
        return self._save_json(f"reviewer_{attempt}.json", data, "Reviewer")
    
    def save_archivist_context(self, chapter: Any, full_prompt: Optional[str] = None) -> Path:
        """
        Save Archivist agent input context.
        """
        data = {
            "chapter_number": getattr(chapter, "chapter_number", 0),
            "title": getattr(chapter, "title", ""),
            "content_length": getattr(chapter, "word_count", 0),
            "full_prompt": full_prompt,
        }
        return self._save_json("archivist_context.json", data, "Archivist")

    def save_archivist(self, result: Any) -> Path:
        """
        Save Archivist agent output.
        
        Args:
            result: ArchiveResult instance
            
        Returns:
            Path to saved file
        """
        data = self._pydantic_to_dict(result)
        return self._save_json("archivist.json", data, "Archivist")
    
    def save_writer_revise_context(
        self,
        original_content: str,
        review_feedback: str,
        context: Any,
        outline: Any = None,
        revision_number: int = 1,
        full_prompt: Optional[str] = None,
    ) -> Path:
        """
        Save Writer agent revision context for debugging.
        
        This captures everything the Writer sees when doing a revision,
        including the context packet, outline, original content, and feedback.
        
        Args:
            original_content: Original chapter content
            review_feedback: Feedback from Reviewer
            context: ContextPacket instance
            outline: ChapterOutline instance (optional)
            revision_number: Revision attempt number
            
        Returns:
            Path to saved file
        """
        # Build context data
        context_data = {}
        if hasattr(context, "__dict__"):
            context_data = {
                "world_setting": context.world_setting,
                "style_guide": context.style_guide,
                "previous_chapter_ending": context.previous_chapter_ending,
                "character_states": context.character_states,
                "relevant_memories": context.relevant_memories,
            }
        
        # Build outline data
        outline_data = None
        if outline:
            outline_data = self._pydantic_to_dict(outline)
        
        data = {
            "revision_number": revision_number,
            "context": context_data,
            "outline": outline_data,
            "original_content": original_content,
            "review_feedback": review_feedback,
            "full_prompt": full_prompt,
        }
        
        return self._save_json(f"writer_revise_context_{revision_number}.json", data, "Writer")
    
    def get_trace_summary(self) -> dict:
        """
        Get a summary of all trace files.
        
        Returns:
            Dictionary with trace file information
        """
        files = sorted(self.trace_dir.glob("*"))
        return {
            "chapter": self.chapter_number,
            "trace_dir": str(self.trace_dir),
            "files": [f.name for f in files],
            "total_steps": self.step_counter,
        }
