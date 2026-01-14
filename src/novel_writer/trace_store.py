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
    
    def save_director_context(self, full_prompt: str, system_prompt: str) -> Path:
        """
        Save Director agent input context.
        """
        data = {
            "system_prompt": system_prompt,
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
    
    def save_plotter_context(self, full_prompt: str, system_prompt: str) -> Path:
        """
        Save Plotter agent input context.
        """
        data = {
            "system_prompt": system_prompt,
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
        target_word_count: int,
        full_prompt: str,
        system_prompt: str
    ) -> Path:
        """
        Save Writer agent input context (initial run).
        """
        data = {
            "target_word_count": target_word_count,
            "system_prompt": system_prompt,
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
    
    def save_writer_revision(self, content: str, version: int, review_chance: int) -> Path:
        """
        Save Writer agent revision.
        
        Args:
            content: Revised content
            version: Writer version number
            review_chance: Review attempt interaction
            
        Returns:
            Path to saved file
        """
        return self._save_text(f"writer_v{version}_rev{review_chance}.md", content, "Writer")
    
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
        full_prompt: str,
        system_prompt: str,
        attempt: int = 1
    ) -> Path:
        """
        Save Reviewer agent input context.
        """
        data = {
            "attempt": attempt,
            "system_prompt": system_prompt,
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
    
    def save_archivist_context(self, full_prompt: str, system_prompt: str) -> Path:
        """
        Save Archivist agent input context.
        """
        data = {
            "system_prompt": system_prompt,
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
        revision_number: int,
        full_prompt: str,
        system_prompt: str,
    ) -> Path:
        """
        Save Writer agent revision context for debugging.
        
        This captures everything the Writer sees when doing a revision.
        """
        data = {
            "revision_number": revision_number,
            "system_prompt": system_prompt,
            "full_prompt": full_prompt,
        }
        
        return self._save_json(f"writer_revise_context_{revision_number}.json", data, "Writer")
    
    def save_writer_version(self, content: str, version: int) -> Path:
        """
        Save Writer agent version output.
        
        Args:
            content: Version content
            version: Version number (1, 2, or 3)
            
        Returns:
            Path to saved file
        """
        return self._save_text(f"writer_v{version}.md", content, "Writer")
    
    def save_review_with_version(self, result: Any, version: int, review_chance: int) -> Path:
        """
        Save Reviewer agent output with version info.
        
        Args:
            result: ReviewResult instance
            version: Writer version number
            review_chance: Review attempt within this version
            
        Returns:
            Path to saved file
        """
        data = self._pydantic_to_dict(result)
        data["_version"] = version
        data["_review_chance"] = review_chance
        return self._save_json(f"reviewer_v{version}_r{review_chance}.json", data, "Reviewer")
    
    def save_writer_final_revision(self, content: str) -> Path:
        """
        Save Writer agent final revision (after all versions failed).
        
        Args:
            content: Final revised content
            
        Returns:
            Path to saved file
        """
        return self._save_text("writer_final_revision.md", content, "Writer")
    
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
