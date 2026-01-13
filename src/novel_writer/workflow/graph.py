"""LangGraph State Machine for Chapter Generation."""

from typing import TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, END

from ..models import ChapterOutline, Chapter
from ..memory.context_builder import ContextPacket
from ..agents.reviewer import ReviewResult
from ..config import settings


class ChapterState(TypedDict):
    """State for the chapter generation workflow."""
    
    # Input
    novel_id: str
    chapter_number: int
    chapter_goal: str  # User-specified goal
    
    # Generated during workflow
    outline: ChapterOutline | None
    context: ContextPacket | None
    draft: str
    
    # Review loop
    review_result: ReviewResult | None
    retry_count: int
    max_retries: int
    
    # Output
    final_content: str
    status: Literal["pending", "writing", "reviewing", "revising", "completed", "failed"]
    error: str | None


def create_initial_state(
    novel_id: str,
    chapter_number: int,
    chapter_goal: str,
    max_retries: int = 3,
) -> ChapterState:
    """Create initial state for a chapter generation workflow."""
    return ChapterState(
        novel_id=novel_id,
        chapter_number=chapter_number,
        chapter_goal=chapter_goal,
        outline=None,
        context=None,
        draft="",
        review_result=None,
        retry_count=0,
        max_retries=max_retries,
        final_content="",
        status="pending",
        error=None,
    )


def should_continue_review(state: ChapterState) -> Literal["revise", "archive", "fail"]:
    """
    Conditional edge: decide whether to revise, archive, or fail.
    
    Returns:
        - "revise": Need to revise the content
        - "archive": Content passed review, archive it
        - "fail": Max retries reached
    """
    review = state.get("review_result")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", settings.max_retry_count)
    
    if review is None:
        return "fail"
    
    # Check if passed
    if review.status == "pass":
        return "archive"
    
    # Check retry limit
    if retry_count >= max_retries:
        return "fail"
    
    # Need revision
    return "revise"


def build_chapter_graph() -> StateGraph:
    """
    Build the LangGraph state machine for chapter generation.
    
    Workflow:
    [start] -> director -> plotter -> context_builder -> writer -> reviewer
                                                           ↑         ↓
                                                           └─ revise ─┤
                                                                      ↓ pass
                                                                  archivist -> [end]
    
    Returns:
        Compiled StateGraph
    """
    # Create the graph
    workflow = StateGraph(ChapterState)
    
    # We'll define the node functions in runner.py and inject them
    # For now, just define the structure
    
    # Add nodes (these will be bound to actual functions in runner.py)
    workflow.add_node("director", lambda x: x)  # Placeholder
    workflow.add_node("plotter", lambda x: x)
    workflow.add_node("context_builder", lambda x: x)
    workflow.add_node("writer", lambda x: x)
    workflow.add_node("reviewer", lambda x: x)
    workflow.add_node("reviser", lambda x: x)
    workflow.add_node("archivist", lambda x: x)
    
    # Define edges
    workflow.set_entry_point("director")
    workflow.add_edge("director", "plotter")
    workflow.add_edge("plotter", "context_builder")
    workflow.add_edge("context_builder", "writer")
    workflow.add_edge("writer", "reviewer")
    
    # Conditional edge after review
    workflow.add_conditional_edges(
        "reviewer",
        should_continue_review,
        {
            "revise": "reviser",
            "archive": "archivist",
            "fail": END,
        }
    )
    
    # Reviser goes back to reviewer
    workflow.add_edge("reviser", "reviewer")
    
    # Archivist ends the workflow
    workflow.add_edge("archivist", END)
    
    return workflow.compile()
