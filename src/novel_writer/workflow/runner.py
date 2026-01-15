"""Chapter Runner - Executes the chapter generation workflow."""

import logging
import time
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

# Configure logging
logger = logging.getLogger(__name__)

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
        max_review_attempts: int = 3,
        max_retries: Optional[int] = None,  # Alias for max_review_attempts (CLI compatibility)
    ) -> Chapter:
        """
        Generate a chapter.
        
        Args:
            chapter_goal: The goal/theme for this chapter
            chapter_number: Optional chapter number (auto-incremented if not provided)
            max_review_attempts: Maximum review/revision cycles (default: 3)
            max_retries: Alias for max_review_attempts (for CLI compatibility)
            
        Returns:
            The completed Chapter
        """
        # Support max_retries as alias
        if max_retries is not None:
            max_review_attempts = max_retries
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
            max_retries=max_review_attempts,
        )
        
        # Step 1: Director generates chapter directive
        self._update_status("Director 正在规划章节...")
        if trace:
            trace.start_timer("Director")
        
        step_start = time.time()
        logger.info(f"[Workflow] Step 1: Director 开始 - 第{chapter_number}章")
        try:
            director_output = self.director.run(
                novel=novel,
                next_chapter_number=chapter_number,
                target_word_count=settings.default_chapter_length,
                user_goal=chapter_goal,
                trace=trace,
            )
            logger.info(f"[Workflow] Step 1: Director 完成 - 耗时: {time.time() - step_start:.1f}s")
        except Exception as e:
            logger.error(f"[Workflow] Step 1: Director 失败 - 耗时: {time.time() - step_start:.1f}s, 错误: {e}")
            raise
        
        if trace:
            trace.save_director(director_output)
        
        # Step 2: Plotter generates detailed outline
        self._update_status("Plotter 正在生成大纲...")
        previous_chapter = novel.get_latest_chapter()
        if trace:
            trace.start_timer("Plotter")
        
        step_start = time.time()
        logger.info(f"[Workflow] Step 2: Plotter 开始 - 第{chapter_number}章")
        try:
            plotter_output, outline = self.plotter.run(
                director_output=director_output,
                novel=novel,
                previous_chapter_summary=previous_chapter.summary if previous_chapter else None,
                trace=trace,
            )
            logger.info(f"[Workflow] Step 2: Plotter 完成 - 耗时: {time.time() - step_start:.1f}s")
        except Exception as e:
            logger.error(f"[Workflow] Step 2: Plotter 失败 - 耗时: {time.time() - step_start:.1f}s, 错误: {e}")
            raise
        
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
        
        # Step 4 & 5: Two-tier version/review loop
        # Outer loop: Writer versions (max 3)
        # Inner loop: Review chances per version (max 2, no revision between reviews)
        max_versions = 3
        max_reviews_per_version = 2
        
        current_content = None
        final_review_result = None
        passed = False
        
        for version in range(1, max_versions + 1):
            # Generate content for this version
            if version == 1:
                self._update_status("Writer 正在撰写正文...")
            else:
                self._update_status(f"Writer 正在重写第 {version} 版...")
            
            if trace:
                trace.start_timer("Writer")
            
            step_start = time.time()
            logger.info(f"[Workflow] Step 4: Writer 开始 - 第{chapter_number}章 版本{version}")
            try:
                current_content = self.writer.run(
                    outline=outline,
                    context=context,
                    target_word_count=settings.default_chapter_length,
                    trace=trace,
                )
                logger.info(f"[Workflow] Step 4: Writer 完成 - 版本{version}, 耗时: {time.time() - step_start:.1f}s, 字数: {len(current_content)}")
            except Exception as e:
                logger.error(f"[Workflow] Step 4: Writer 失败 - 版本{version}, 耗时: {time.time() - step_start:.1f}s, 错误: {e}")
                raise
            
            if trace:
                trace.save_writer_version(current_content, version)
            
            state["draft"] = current_content
            
            # Double Review Logic (Two independent reviews per version)
            reviews = []
            
            # 1. First Review
            self._update_status(f"版本 {version} 第 1 次审核...")
            if trace:
                trace.start_timer("Reviewer")
            
            step_start = time.time()
            logger.info(f"[Workflow] Step 5: Reviewer 开始 - 版本{version} 第1次审核")
            try:
                review1 = self.reviewer.run(
                    content=current_content,
                    outline=outline,
                    context=context,
                    target_word_count=settings.default_chapter_length,
                    attempt=1,
                    trace=trace,
                )
                logger.info(f"[Workflow] Step 5: Reviewer 完成 - 版本{version} 第1次, 耗时: {time.time() - step_start:.1f}s, 评分: {review1.score}")
            except Exception as e:
                logger.error(f"[Workflow] Step 5: Reviewer 失败 - 版本{version} 第1次, 耗时: {time.time() - step_start:.1f}s, 错误: {e}")
                raise
            
            reviews.append(review1)
            if trace:
                trace.save_review_with_version(review1, version, 1)
            
            console.print(f"  版本 {version} 第一次审核: 评分 {review1.score}/100, 状态: {review1.status}")
            
            if review1.status == "pass":
                self._update_status(f"版本 {version} 审核通过!")
                passed = True
                state["review_result"] = review1
                break
            
            # 2. Second Review (if first failed)
            self._update_status(f"版本 {version} 第 1 次审核未通过，尝试第 2 次审核...")
            if trace:
                trace.start_timer("Reviewer")
            
            step_start = time.time()
            logger.info(f"[Workflow] Step 5: Reviewer 开始 - 版本{version} 第2次审核")
            try:
                review2 = self.reviewer.run(
                    content=current_content,
                    outline=outline,
                    context=context,
                    target_word_count=settings.default_chapter_length,
                    attempt=2,
                    trace=trace,
                )
                logger.info(f"[Workflow] Step 5: Reviewer 完成 - 版本{version} 第2次, 耗时: {time.time() - step_start:.1f}s, 评分: {review2.score}")
            except Exception as e:
                logger.error(f"[Workflow] Step 5: Reviewer 失败 - 版本{version} 第2次, 耗时: {time.time() - step_start:.1f}s, 错误: {e}")
                raise
            
            reviews.append(review2)
            if trace:
                trace.save_review_with_version(review2, version, 2)
            
            console.print(f"  版本 {version} 第二次审核: 评分 {review2.score}/100, 状态: {review2.status}")
            
            if review2.status == "pass":
                self._update_status(f"版本 {version} 审核通过!")
                passed = True
                state["review_result"] = review2
                break
            
            # 3. Both failed - Select best review for revision
            console.print(f"  [yellow]两次审核均未通过，择优修改...[/yellow]")
            
            # Selection logic: Higher score wins
            best_review = max(reviews, key=lambda r: r.score)
            state["review_result"] = best_review
            
            if best_review.status == "rewrite_needed":
                console.print(f"  [red]最佳审核结果仍判定需要重写 (Score: {best_review.score})[/red]")
                final_review_result = best_review
                continue # Next version loop
            
            # If revision_needed, execute revision
            if best_review.status == "revision_needed":
                self._update_status(f"根据评分较高 ({best_review.score}) 的意见进行修订...")
                feedback = self.reviewer.format_feedback_for_writer(best_review)
                
                if trace:
                    trace.start_timer("Writer")
                
                step_start = time.time()
                logger.info(f"[Workflow] Step 6: Writer 开始修订 - 版本{version}")
                try:
                    # Revise
                    current_content = self.writer.revise(
                        original_content=current_content,
                        review_feedback=feedback,
                        context=context,
                        outline=outline,
                        trace=trace,
                    )
                    logger.info(f"[Workflow] Step 6: Writer 修订完成 - 版本{version}, 耗时: {time.time() - step_start:.1f}s, 字数: {len(current_content)}")
                except Exception as e:
                    logger.error(f"[Workflow] Step 6: Writer 修订失败 - 版本{version}, 耗时: {time.time() - step_start:.1f}s, 错误: {e}")
                    raise
                
                state["draft"] = current_content
                
                if trace:
                    trace.save_writer_revision(current_content, version, 1)
                
                # Treat this revised version as the final output of this version cycle
                # We do NOT review it again in this version loop (as per user request "Execute corresponding modification" then implicit end or next version?)
                # Actually, usually we should verify revision, but user says "until two reviews fail, then execute modification".
                # It implies the modification is the result.
                # Use this result as the potential final if we run out of versions.
                # We clear final_review_result to prevent the fallback logic from re-revising this already-revised content
                final_review_result = None
                
                console.print(f"  [dim]版本 {version} 修订完成。[/dim]")
                continue

        
        # If all versions failed (3 versions x 3 reviews each), do final revision
        if not passed and final_review_result:
            self._update_status("所有版本审核失败，进行最后一次尽力修订...")
            feedback = self.reviewer.format_feedback_for_writer(final_review_result)
            
            if trace:
                trace.start_timer("Writer")
            
            current_content = self.writer.revise(
                original_content=current_content,
                review_feedback=feedback,
                context=context,
                outline=outline,
                trace=trace,
            )
            
            if trace:
                trace.save_writer_final_revision(current_content)
            
            console.print("  [dim]已完成最终修订，强制接受[/dim]")
        
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
            trace=trace,
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
