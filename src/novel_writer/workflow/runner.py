"""Chapter Runner - Executes the chapter generation workflow."""

from typing import Optional, Callable
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .graph import ChapterState, create_initial_state
from ..models import Novel, Chapter, ChapterOutline
from ..memory.vector_store import VectorStore
from ..memory.structured_store import StructuredStore
from ..memory.context_builder import ContextBuilder, ContextPacket
from ..agents.director import DirectorAgent, DirectorOutput
from ..agents.plotter import PlotterAgent, PlotterOutput
from ..agents.writer import WriterAgent
from ..agents.reviewer import ReviewerAgent, ReviewResult
from ..agents.archivist import ArchivistAgent
from ..config import settings
from ..trace_store import TraceStore


console = Console()


class ChapterRunner:
    """
    Runs the chapter generation workflow.
    
    This is the main entry point for generating chapters. It coordinates
    all agents and manages the workflow state.
    """
    
    def __init__(
        self,
        novel_id: str,
        novel_path: Optional["Path"] = None,
        vector_store: Optional[VectorStore] = None,
        structured_store: Optional[StructuredStore] = None,
        on_status_update: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the chapter runner.
        
        Args:
            novel_id: The novel ID to work with
            novel_path: Path to the novel directory (for trace storage)
            vector_store: Optional pre-initialized vector store
            structured_store: Optional pre-initialized structured store
            on_status_update: Optional callback for status updates
        """
        self.novel_id = novel_id
        self.novel_path = novel_path
        self.on_status_update = on_status_update or (lambda x: None)
        self.trace_enabled = settings.trace_enabled
        
        # Use provided stores or create new ones
        self.vector_store = vector_store or VectorStore(novel_id)
        self.structured_store = structured_store or StructuredStore(novel_id)
        self.context_builder = ContextBuilder(self.vector_store, self.structured_store)
        
        # Initialize agents
        self.director = DirectorAgent()
        self.plotter = PlotterAgent()
        self.writer = WriterAgent()
        self.reviewer = ReviewerAgent()
        self.archivist = ArchivistAgent()
    
    def _update_status(self, message: str):
        """Update status via callback."""
        self.on_status_update(message)
        console.print(f"[dim]→ {message}[/dim]")
    
    def run(
        self,
        chapter_goal: str,
        chapter_number: Optional[int] = None,
        max_retries: int = 3,
    ) -> Chapter:
        """
        Generate a chapter.
        
        Args:
            chapter_goal: The goal/theme for this chapter
            chapter_number: Optional chapter number (auto-incremented if not provided)
            max_retries: Maximum revision attempts
            
        Returns:
            The completed Chapter
        """
        # Get novel
        novel = self.structured_store.get_novel()
        if not novel:
            raise ValueError("Novel not found. Please initialize the novel first.")
        
        # Determine chapter number
        if chapter_number is None:
            chapter_number = len(novel.chapters) + 1
        
        self._update_status(f"开始生成第 {chapter_number} 章...")
        
        # Initialize trace store if enabled
        trace: Optional[TraceStore] = None
        if self.trace_enabled and self.novel_path:
            trace = TraceStore(self.novel_path, chapter_number)
            console.print(f"[dim]📝 Trace 已启用: {trace.trace_dir}[/dim]")
        
        # Initialize state
        state = create_initial_state(
            novel_id=self.novel_id,
            chapter_number=chapter_number,
            chapter_goal=chapter_goal,
            max_retries=max_retries,
        )
        
        # Step 1: Director generates chapter directive
        self._update_status("Director 正在规划章节...")
        if trace:
            trace.start_timer("Director")
        director_output = self.director.run(
            novel=novel,
            next_chapter_number=chapter_number,
            user_goal=chapter_goal,
        )
        if trace:
            trace.save_director(director_output)
        
        # Step 2: Plotter generates detailed outline
        self._update_status("Plotter 正在生成大纲...")
        if trace:
            trace.start_timer("Plotter")
        previous_chapter = novel.get_latest_chapter()
        plotter_output, outline = self.plotter.run(
            director_output=director_output,
            novel=novel,
            previous_chapter_summary=previous_chapter.summary if previous_chapter else None,
        )
        state["outline"] = outline
        if trace:
            trace.save_plotter(plotter_output, outline)
        
        # Step 3: Build context
        self._update_status("Context Builder 正在组装上下文...")
        if trace:
            trace.start_timer("ContextBuilder")
        context = self.context_builder.build_context(
            chapter_outline=outline,
            previous_chapter=previous_chapter,
        )
        state["context"] = context
        if trace:
            trace.save_context(context)
        
        # Step 4: Writer generates content
        self._update_status("Writer 正在撰写正文...")
        if trace:
            trace.start_timer("Writer")
        draft = self.writer.run(
            outline=outline,
            context=context,
            target_word_count=settings.default_chapter_length,
        )
        state["draft"] = draft
        if trace:
            trace.save_writer_draft(draft)
        
        # Step 5: Review loop
        retry_count = 0
        current_content = draft
        review_attempt = 0
        last_review_result = None  # Track previous review for comparison
        
        while retry_count < max_retries:
            self._update_status(f"Reviewer 正在审核... (尝试 {retry_count + 1}/{max_retries})")
            review_attempt += 1
            
            if trace:
                trace.start_timer("Reviewer")
            review_result = self.reviewer.run(
                content=current_content,
                outline=outline,
                context=context,
                previous_review=last_review_result,  # Pass previous review for comparison
            )
            state["review_result"] = review_result
            if trace:
                trace.save_review(review_result, review_attempt)
            
            console.print(f"  审核评分: {review_result.score}/100, 状态: {review_result.status}")
            
            if review_result.status == "pass":
                self._update_status("审核通过!")
                break
            
            if review_result.status == "rewrite_needed":
                self._update_status("需要重写，重新生成...")
                if trace:
                    trace.start_timer("Writer")
                current_content = self.writer.run(
                    outline=outline,
                    context=context,
                    target_word_count=settings.default_chapter_length,
                )
                if trace:
                    trace.save_writer_revision(current_content, retry_count + 1)
            else:
                # Revision needed
                self._update_status("正在根据反馈修改...")
                feedback = self.reviewer.format_feedback_for_writer(review_result)
                if trace:
                    trace.start_timer("Writer")
                    # Save revise context before calling revise
                    trace.save_writer_revise_context(
                        original_content=current_content,
                        review_feedback=feedback,
                        context=context,
                        outline=outline,
                        revision_number=retry_count + 1,
                    )
                current_content = self.writer.revise(
                    original_content=current_content,
                    review_feedback=feedback,
                    context=context,
                    outline=outline,
                )
                if trace:
                    trace.save_writer_revision(current_content, retry_count + 1)
            
            # Save current review for next iteration
            last_review_result = review_result
            retry_count += 1
            state["retry_count"] = retry_count
        
        # Save final writer output
        if trace:
            trace.save_writer_final(current_content)
        
        # Step 6: Create chapter object
        chapter = Chapter(
            chapter_number=chapter_number,
            title=outline.title,
            outline=outline,
            content=current_content,
            word_count=len(current_content),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        
        # Step 7: Archive
        self._update_status("Archivist 正在归档...")
        if trace:
            trace.start_timer("Archivist")
        archive_result = self.archivist.run(
            chapter=chapter,
            vector_store=self.vector_store,
            structured_store=self.structured_store,
        )
        if trace:
            trace.save_archivist(archive_result)
        
        # Update chapter with summary
        chapter.summary = archive_result.chapter_summary
        
        # Log trace summary
        if trace:
            summary = trace.get_trace_summary()
            console.print(f"[dim]📊 Trace 完成: {summary['total_steps']} 个步骤已保存[/dim]")
        
        self._update_status(f"第 {chapter_number} 章完成! ({chapter.word_count} 字)")
        
        return chapter
    
    def get_novel(self) -> Optional[Novel]:
        """Get the current novel."""
        return self.structured_store.get_novel()
    
    def initialize_novel(
        self,
        title: str,
        synopsis: str = "",
        genre: str = "fantasy",
        style_guide: str = "",
    ) -> Novel:
        """
        Initialize a new novel project.
        
        Args:
            title: Novel title
            synopsis: Novel synopsis
            genre: Genre (fantasy/scifi/wuxia/modern)
            style_guide: Style guidelines for writing
            
        Returns:
            Created Novel object
        """
        novel = self.structured_store.create_novel(
            title=title,
            synopsis=synopsis,
            genre=genre,
            style_guide=style_guide,
        )
        console.print(f"[green]✓ 小说项目 '{title}' 已创建[/green]")
        return novel
