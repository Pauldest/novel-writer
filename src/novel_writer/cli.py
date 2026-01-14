"""Novel Writer CLI - Simplified file-based interface."""

import typer
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from .project import NovelProject, find_novel_project
from .workflow.runner import ChapterRunner


app = typer.Typer(
    name="novel-writer",
    help="多智能体小说写作系统 - 基于文件夹和 Markdown 的工作流",
    add_completion=False,
)
console = Console()


@app.command()
def init(
    path: Path = typer.Argument(
        Path("."), 
        help="项目目录路径，默认为当前目录"
    ),
):
    """
    初始化小说项目 - 创建模板文件。
    
    Usage:
        mkdir 我的小说 && cd 我的小说
        novel-writer init
    
    这会创建 roles.md 和 outline.md 模板文件。
    """
    path = path.resolve()
    
    if not path.exists():
        path.mkdir(parents=True)
        console.print(f"[green]✓ 创建目录: {path.name}[/green]")
    
    # Create template files
    roles_file = path / "roles.md"
    outline_file = path / "outline.md"
    style_file = path / "style.md"
    
    if not roles_file.exists():
        roles_file.write_text(ROLES_TEMPLATE, encoding="utf-8")
        console.print(f"[green]✓ 创建 roles.md[/green]")
    
    if not outline_file.exists():
        outline_file.write_text(OUTLINE_TEMPLATE, encoding="utf-8")
        console.print(f"[green]✓ 创建 outline.md[/green]")
    
    if not style_file.exists():
        style_file.write_text(STYLE_TEMPLATE, encoding="utf-8")
        console.print(f"[green]✓ 创建 style.md[/green]")
    
    console.print(Panel(
        f"[bold]小说项目已初始化![/bold]\n\n"
        f"目录: {path}\n\n"
        f"下一步:\n"
        f"1. 编辑 [cyan]roles.md[/cyan] 添加角色\n"
        f"2. 编辑 [cyan]outline.md[/cyan] 添加大纲\n"
        f"3. 运行 [cyan]novel-writer write[/cyan] 生成章节",
        title="✨ 初始化完成"
    ))


@app.command("write-c")
def write_chapter(
    chapter: int = typer.Argument(..., help="章节号"),
    max_retries: int = typer.Option(
        3, "--retries", "-r",
        help="最大修改次数"
    ),
    path: Path = typer.Option(
        Path("."), "--path", "-p",
        help="项目目录路径"
    ),
):
    """
    生成指定章节。
    
    Usage:
        novel-writer write-c 5        # 写第5章
        novel-writer write-c 10       # 写第10章
    """
    _write_single_chapter(chapter=chapter, max_retries=max_retries, path=path)


@app.command()
def write(
    chapter: Optional[int] = typer.Option(
        None, "--chapter", "-c",
        help="指定要写的章节号，默认写下一章"
    ),
    max_retries: int = typer.Option(
        3, "--retries", "-r",
        help="最大修改次数"
    ),
    path: Path = typer.Option(
        Path("."), "--path", "-p",
        help="项目目录路径"
    ),
):
    """
    生成下一章节。
    
    在小说项目目录中运行此命令，会根据 outline.md 自动生成下一章。
    
    Usage:
        cd 我的小说
        novel-writer write           # 自动写下一章
        novel-writer write -c 5      # 写第5章
    """
    _write_single_chapter(chapter=chapter, max_retries=max_retries, path=path)


def _write_single_chapter(chapter: Optional[int], max_retries: int, path: Path):
    """Internal function for writing a single chapter."""
    # Find project
    project = find_novel_project(path)
    if not project:
        console.print("[red]错误: 找不到小说项目。请确保当前目录包含 outline.md 或 roles.md[/red]")
        raise typer.Exit(1)
    
    console.print(Panel(f"[bold]《{project.title}》[/bold]"))
    
    # Determine which chapter to write
    if chapter is None:
        next_chapter = project.get_next_chapter_to_write()
        if not next_chapter:
            console.print("[yellow]所有章节已完成！[/yellow]")
            console.print("[dim]提示: 在 outline.md 中添加更多章节大纲，然后重新运行。[/dim]")
            raise typer.Exit(0)
        
        chapter_number = next_chapter["chapter_number"]
        chapter_goal = next_chapter["goal"]
        chapter_title = next_chapter.get("title", "")
    else:
        chapter_number = chapter
        # Find the outline for this chapter
        outlines = project.get_chapter_outlines()
        matching = [o for o in outlines if o["chapter_number"] == chapter]
        if matching:
            chapter_goal = matching[0]["goal"]
            chapter_title = matching[0].get("title", "")
        else:
            console.print(f"[red]错误: 在 outline.md 中找不到第 {chapter} 章的大纲[/red]")
            raise typer.Exit(1)
    
    console.print(f"准备写: 第 {chapter_number} 章 - {chapter_title or '无标题'}")
    console.print(f"[dim]目标: {chapter_goal[:100]}...[/dim]" if len(chapter_goal) > 100 else f"[dim]目标: {chapter_goal}[/dim]")
    console.print()
    
    # Create runner with project's stores
    runner = ChapterRunner(
        novel_id=project.novel_id,
        vector_store=project.vector_store,
        structured_store=project.structured_store,
    )
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("生成中...", total=None)
            
            def update_status(msg: str):
                progress.update(task, description=msg)
            
            runner.on_status_update = update_status
            
            result = runner.run(
                chapter_goal=chapter_goal,
                chapter_number=chapter_number,
                max_retries=max_retries,
            )
        
        # Save to chapters directory
        project.save_chapter(
            chapter_number=result.chapter_number,
            title=result.title or chapter_title,
            content=result.content,
        )
        
        console.print()
        console.print(Panel(
            f"[bold green]第{result.chapter_number}章 - {result.title or chapter_title}[/bold green]\n\n"
            f"{result.content[:800]}...\n\n"
            f"[dim]（共 {result.word_count} 字）[/dim]",
            title="✅ 生成完成"
        ))
        
        console.print(f"\n[dim]已保存到: chapters/{result.chapter_number:03d}.md[/dim]")
        
    except Exception as e:
        console.print(f"[red]生成失败: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(1)


@app.command("write-n")
def write_n(
    count: int = typer.Argument(..., help="要生成的章节数量"),
    max_retries: int = typer.Option(
        3, "--retries", "-r",
        help="每章最大修改次数"
    ),
    path: Path = typer.Option(
        Path("."), "--path", "-p",
        help="项目目录路径"
    ),
):
    """
    生成指定数量的章节。
    
    Usage:
        novel-writer write-n 10       # 生成接下来10章
        novel-writer write-n 50       # 生成接下来50章
    """
    _batch_write(count=count, max_retries=max_retries, path=path)


@app.command("write-all")
def write_all(
    max_retries: int = typer.Option(
        3, "--retries", "-r",
        help="每章最大修改次数"
    ),
    path: Path = typer.Option(
        Path("."), "--path", "-p",
        help="项目目录路径"
    ),
):
    """
    生成所有剩余章节。
    
    Usage:
        novel-writer write-all
    """
    _batch_write(count=None, max_retries=max_retries, path=path)


def _batch_write(count: int | None, max_retries: int, path: Path):
    """Internal function for batch writing chapters."""
    project = find_novel_project(path)
    if not project:
        console.print("[red]错误: 找不到小说项目[/red]")
        raise typer.Exit(1)
    
    mode_text = f"批量生成 {count} 章" if count else "批量生成所有章节"
    console.print(Panel(f"[bold]《{project.title}》- {mode_text}[/bold]"))
    
    outlines = project.get_chapter_outlines()
    if not outlines:
        console.print("[yellow]没有找到章节大纲，请先编辑 outline.md[/yellow]")
        raise typer.Exit(0)
    
    generated = set(project.get_generated_chapters())
    pending = [o for o in outlines if o["chapter_number"] not in generated]
    
    if not pending:
        console.print("[green]所有章节已完成！[/green]")
        raise typer.Exit(0)
    
    # Limit to count if specified
    if count is not None:
        pending = pending[:count]
    
    console.print(f"待生成章节: {len(pending)} 章")
    console.print()
    
    # Create runner
    runner = ChapterRunner(
        novel_id=project.novel_id,
        vector_store=project.vector_store,
        structured_store=project.structured_store,
    )
    
    completed = 0
    failed = 0
    
    for chapter_info in pending:
        chapter_number = chapter_info["chapter_number"]
        chapter_title = chapter_info.get("title", "")
        chapter_goal = chapter_info["goal"]
        
        console.print(f"\n{'='*50}")
        console.print(f"[bold]第 {chapter_number} 章: {chapter_title}[/bold]")
        console.print(f"[dim]{chapter_goal[:80]}...[/dim]" if len(chapter_goal) > 80 else f"[dim]{chapter_goal}[/dim]")
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("生成中...", total=None)
                
                def update_status(msg: str):
                    progress.update(task, description=msg)
                
                runner.on_status_update = update_status
                
                result = runner.run(
                    chapter_goal=chapter_goal,
                    chapter_number=chapter_number,
                    max_retries=max_retries,
                )
            
            # Save chapter
            project.save_chapter(
                chapter_number=result.chapter_number,
                title=result.title or chapter_title,
                content=result.content,
            )
            
            console.print(f"[green]✓ 第{chapter_number}章完成 ({result.word_count}字)[/green]")
            completed += 1
            
        except Exception as e:
            console.print(f"[red]✗ 第{chapter_number}章失败: {e}[/red]")
            failed += 1
            # Continue to next chapter instead of stopping
            continue
    
    # Summary
    console.print(f"\n{'='*50}")
    console.print(Panel(
        f"[bold]批量生成完成[/bold]\n\n"
        f"成功: [green]{completed}[/green] 章\n"
        f"失败: [red]{failed}[/red] 章\n"
        f"总计: {len(pending)} 章",
        title="📊 生成统计"
    ))


@app.command()
def status(
    path: Path = typer.Option(
        Path("."), "--path", "-p",
        help="项目目录路径"
    ),
):
    """
    查看项目状态。
    
    显示已完成的章节、待写章节和角色列表。
    """
    project = find_novel_project(path)
    if not project:
        console.print("[red]错误: 找不到小说项目[/red]")
        raise typer.Exit(1)
    
    novel = project.get_novel()
    
    # Project info
    console.print(Panel(
        f"[bold]{project.title}[/bold]\n"
        f"类型: {novel.world.genre if novel else 'unknown'}\n"
        f"目录: {project.project_path}",
        title="📖 小说项目"
    ))
    
    # Characters
    if novel and novel.characters:
        table = Table(title="角色列表")
        table.add_column("名称", style="cyan")
        table.add_column("描述")
        
        for name, char in novel.characters.items():
            desc = char.description[:50] + "..." if len(char.description) > 50 else char.description
            table.add_row(name, desc)
        console.print(table)
    
    # Chapters
    outlines = project.get_chapter_outlines()
    generated = set(project.get_generated_chapters())
    
    if outlines:
        table = Table(title="章节进度")
        table.add_column("章节", style="bold")
        table.add_column("标题")
        table.add_column("状态")
        
        for o in outlines:
            ch_num = o["chapter_number"]
            status = "[green]✓ 已完成[/green]" if ch_num in generated else "[yellow]待写[/yellow]"
            table.add_row(f"第{ch_num}章", o.get("title", ""), status)
        
        console.print(table)
    
    # Next action
    next_ch = project.get_next_chapter_to_write()
    if next_ch:
        console.print(f"\n[dim]下一步: novel-writer write  # 写第{next_ch['chapter_number']}章[/dim]")
    else:
        console.print("\n[green]所有章节已完成！[/green]")


@app.command()
def read(
    chapter: int = typer.Argument(..., help="章节号"),
    path: Path = typer.Option(
        Path("."), "--path", "-p",
        help="项目目录路径"
    ),
):
    """
    阅读已生成的章节。
    
    Usage:
        novel-writer read 1
    """
    project = find_novel_project(path)
    if not project:
        console.print("[red]错误: 找不到小说项目[/red]")
        raise typer.Exit(1)
    
    content = project.read_chapter(chapter)
    if not content:
        console.print(f"[red]错误: 第 {chapter} 章还未生成[/red]")
        raise typer.Exit(1)
    
    console.print(Panel(content, title=f"第{chapter}章"))


# Template files
ROLES_TEMPLATE = """# 角色设定

在这里定义你小说中的角色。每个角色用 `##` 标题，下面写描述。

## 主角名字

角色描述：外貌、性格、背景故事等。
例如：一位年轻的剑客，性格沉稳内敛，背负着家族的秘密...

## 配角名字

配角的描述...

## 反派名字

反派的描述...

---
提示：
- 每个角色用 `## 名字` 开头
- 描述可以包含多行
- 越详细越好，AI 会参考这些设定
"""

OUTLINE_TEMPLATE = """# 小说大纲

## 简介

在这里写你的小说简介，一两段话描述整体故事...

---

## 第一章：开端

本章目标：介绍主角，展示日常生活，暗示即将到来的变化。
主要场景：主角的家乡/日常环境。
关键事件：某个打破平静的事件发生。

## 第二章：变故

本章目标：主角遭遇重大变故，被迫踏上旅程。
主要场景：转折发生的地点。
关键事件：推动主角离开的关键事件。

## 第三章：新世界

本章目标：主角进入新的环境，开始新的生活。
主要场景：新的地点/环境。
关键事件：遇到重要的人物或发现。

---
提示：
- 每章用 `## 第X章：标题` 格式
- 章节描述要详细，包含目标、场景、关键事件
- AI 会根据这些大纲生成正文
- 可以用中文数字（第一章）或阿拉伯数字（第1章）
"""

STYLE_TEMPLATE = """# 风格指南

在这里定义你想要的写作风格。

## 整体风格

描述你想要的整体风格，例如：
- 古风武侠，对话简洁有力
- 现代都市，轻松幽默
- 玄幻史诗，气势恢宏

## 叙事视角

- 第一人称 / 第三人称
- 全知视角 / 限制视角

## 语言特点

- 句子长短偏好
- 是否使用方言/古语
- 对话风格

## 禁忌事项

- 不要出现的元素
- 需要避免的表达方式

---
提示：风格指南越具体，AI 生成的内容越符合你的预期。
"""


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
