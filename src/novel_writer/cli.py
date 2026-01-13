"""Novel Writer CLI - Command-line interface for the novel writing system."""

import typer
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
import uuid

from .workflow.runner import ChapterRunner
from .memory.structured_store import StructuredStore
from .models import Character


app = typer.Typer(
    name="novel-writer",
    help="多智能体小说写作系统 - 让 AI 帮你写出逻辑自洽的长篇小说",
    add_completion=False,
)
console = Console()


def get_runner(novel_id: str) -> ChapterRunner:
    """Get or create a chapter runner for the novel."""
    return ChapterRunner(novel_id)


@app.command()
def init(
    title: str = typer.Argument(..., help="小说标题"),
    genre: str = typer.Option("fantasy", "--genre", "-g", help="类型: fantasy/scifi/wuxia/modern"),
    synopsis: str = typer.Option("", "--synopsis", "-s", help="小说简介"),
):
    """
    创建新的小说项目。
    
    Examples:
        novel-writer init "我的奇幻小说" --genre fantasy
        novel-writer init "星际冒险" -g scifi -s "一个关于太空探索的故事"
    """
    # Generate novel ID
    novel_id = str(uuid.uuid4())[:8]
    
    console.print(Panel(f"[bold]创建小说项目[/bold]\n标题: {title}\n类型: {genre}\nID: {novel_id}"))
    
    runner = get_runner(novel_id)
    novel = runner.initialize_novel(
        title=title,
        synopsis=synopsis,
        genre=genre,
    )
    
    console.print(f"\n[green]✓ 小说项目已创建![/green]")
    console.print(f"项目ID: [bold]{novel_id}[/bold]")
    console.print(f"\n[dim]使用以下命令继续:[/dim]")
    console.print(f"  novel-writer add-character {novel_id} '主角名' --desc '角色描述'")
    console.print(f"  novel-writer write {novel_id} '本章目标'")


@app.command()
def add_character(
    novel_id: str = typer.Argument(..., help="小说项目ID"),
    name: str = typer.Argument(..., help="角色名称"),
    description: str = typer.Option("", "--desc", "-d", help="角色描述"),
    location: str = typer.Option("unknown", "--location", "-l", help="初始位置"),
):
    """
    添加角色到小说。
    
    Examples:
        novel-writer add-character abc123 "李白" --desc "一位浪漫的诗人剑客"
    """
    store = StructuredStore(novel_id)
    novel = store.get_novel()
    
    if not novel:
        console.print(f"[red]错误: 找不到小说项目 {novel_id}[/red]")
        raise typer.Exit(1)
    
    character = Character(
        name=name,
        description=description,
        location=location,
    )
    store.add_character(character)
    
    console.print(f"[green]✓ 角色 '{name}' 已添加到《{novel.title}》[/green]")


@app.command()
def write(
    novel_id: str = typer.Argument(..., help="小说项目ID"),
    goal: str = typer.Argument(..., help="本章目标/主题"),
    chapter: Optional[int] = typer.Option(None, "--chapter", "-c", help="指定章节号"),
    max_retries: int = typer.Option(3, "--retries", "-r", help="最大修改次数"),
):
    """
    生成一个章节。
    
    Examples:
        novel-writer write abc123 "主角发现古老的预言"
        novel-writer write abc123 "大战开始" --chapter 5
    """
    console.print(Panel(f"[bold]开始生成章节[/bold]\n目标: {goal}"))
    
    runner = get_runner(novel_id)
    novel = runner.get_novel()
    
    if not novel:
        console.print(f"[red]错误: 找不到小说项目 {novel_id}[/red]")
        raise typer.Exit(1)
    
    console.print(f"小说: 《{novel.title}》 | 已有章节: {len(novel.chapters)}")
    console.print()
    
    try:
        chapter_result = runner.run(
            chapter_goal=goal,
            chapter_number=chapter,
            max_retries=max_retries,
        )
        
        console.print()
        console.print(Panel(
            f"[bold green]第{chapter_result.chapter_number}章 - {chapter_result.title}[/bold green]\n\n"
            f"{chapter_result.content[:500]}...\n\n"
            f"[dim]（共 {chapter_result.word_count} 字）[/dim]",
            title="生成完成"
        ))
        
        # Save location info
        console.print(f"\n章节文件已保存到 data/novels/{novel_id}/chapters/")
        
    except Exception as e:
        console.print(f"[red]生成失败: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def status(
    novel_id: str = typer.Argument(..., help="小说项目ID"),
):
    """
    查看小说项目状态。
    
    Examples:
        novel-writer status abc123
    """
    store = StructuredStore(novel_id)
    novel = store.get_novel()
    
    if not novel:
        console.print(f"[red]错误: 找不到小说项目 {novel_id}[/red]")
        raise typer.Exit(1)
    
    # Novel info
    console.print(Panel(
        f"[bold]{novel.title}[/bold]\n"
        f"类型: {novel.world.genre}\n"
        f"章节数: {len(novel.chapters)}\n"
        f"创建时间: {novel.created_at.strftime('%Y-%m-%d %H:%M')}",
        title=f"小说项目 [{novel_id}]"
    ))
    
    # Characters
    if novel.characters:
        table = Table(title="角色列表")
        table.add_column("名称", style="cyan")
        table.add_column("状态")
        table.add_column("位置")
        table.add_column("物品")
        
        for name, char in novel.characters.items():
            table.add_row(
                name,
                char.status,
                char.location,
                ", ".join(char.inventory[:3]) if char.inventory else "-"
            )
        console.print(table)
    
    # Chapters
    if novel.chapters:
        table = Table(title="章节列表")
        table.add_column("章节", style="bold")
        table.add_column("标题")
        table.add_column("字数")
        table.add_column("摘要")
        
        for ch in novel.chapters[-5:]:  # Last 5 chapters
            table.add_row(
                f"第{ch.chapter_number}章",
                ch.title or "无标题",
                str(ch.word_count),
                (ch.summary[:50] + "...") if ch.summary else "-"
            )
        console.print(table)


@app.command()
def read(
    novel_id: str = typer.Argument(..., help="小说项目ID"),
    chapter: int = typer.Argument(..., help="章节号"),
):
    """
    阅读指定章节内容。
    
    Examples:
        novel-writer read abc123 1
    """
    store = StructuredStore(novel_id)
    novel = store.get_novel()
    
    if not novel:
        console.print(f"[red]错误: 找不到小说项目 {novel_id}[/red]")
        raise typer.Exit(1)
    
    ch = novel.get_chapter(chapter)
    if not ch:
        console.print(f"[red]错误: 找不到第 {chapter} 章[/red]")
        raise typer.Exit(1)
    
    console.print(Panel(
        ch.content,
        title=f"第{ch.chapter_number}章 - {ch.title or '无标题'}",
        subtitle=f"{ch.word_count} 字"
    ))


@app.command()
def set_outline(
    novel_id: str = typer.Argument(..., help="小说项目ID"),
    outline_file: Path = typer.Argument(..., help="大纲文件路径 (txt/md)"),
):
    """
    设置小说总大纲。
    
    Examples:
        novel-writer set-outline abc123 outline.md
    """
    if not outline_file.exists():
        console.print(f"[red]错误: 文件不存在 {outline_file}[/red]")
        raise typer.Exit(1)
    
    outline_content = outline_file.read_text(encoding="utf-8")
    
    store = StructuredStore(novel_id)
    novel = store.get_novel()
    
    if not novel:
        console.print(f"[red]错误: 找不到小说项目 {novel_id}[/red]")
        raise typer.Exit(1)
    
    store.update_novel(total_outline=outline_content)
    
    console.print(f"[green]✓ 大纲已设置 ({len(outline_content)} 字)[/green]")


@app.command()
def set_style(
    novel_id: str = typer.Argument(..., help="小说项目ID"),
    style: str = typer.Argument(..., help="风格指南描述"),
):
    """
    设置写作风格指南。
    
    Examples:
        novel-writer set-style abc123 "古风武侠，对话简洁有力，多用短句"
    """
    store = StructuredStore(novel_id)
    novel = store.get_novel()
    
    if not novel:
        console.print(f"[red]错误: 找不到小说项目 {novel_id}[/red]")
        raise typer.Exit(1)
    
    store.update_novel(style_guide=style)
    
    console.print(f"[green]✓ 风格指南已设置[/green]")


@app.command()
def list_novels():
    """
    列出所有小说项目。
    """
    from .config import settings
    
    novels_dir = settings.novels_dir
    if not novels_dir.exists():
        console.print("[dim]还没有创建任何小说项目[/dim]")
        return
    
    table = Table(title="小说项目列表")
    table.add_column("ID", style="cyan")
    table.add_column("标题")
    table.add_column("类型")
    table.add_column("章节数")
    
    for novel_dir in novels_dir.iterdir():
        if novel_dir.is_dir():
            store = StructuredStore(novel_dir.name)
            novel = store.get_novel()
            if novel:
                table.add_row(
                    novel_dir.name,
                    novel.title,
                    novel.world.genre,
                    str(len(novel.chapters))
                )
    
    console.print(table)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
