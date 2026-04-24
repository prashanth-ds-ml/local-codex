
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from rich.console import Console
from rich.panel import Panel
from rich.align import Align
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from app.llm import get_agent_llm, get_chat_llm
from app.prompts import SYSTEM_PROMPT
from app.agents import filesystem
from app.agents.response import render


console = Console()

try:
    # prefer direct import
    from misc.ascii import generate_ascii_art
except Exception:
    # ensure project root is on sys.path when running as script
    import sys
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.append(str(root))
    from misc.ascii import generate_ascii_art


def show_banner():
    try:
        import pathlib

        img_path = pathlib.Path(__file__).resolve().parents[1] / "misc" / "monkey2.webp"
        if not img_path.exists():
            img_path = pathlib.Path(__file__).resolve().parents[1] / "misc" / "monkey.jpg"

        avatar = generate_ascii_art(str(img_path), size=(40, 20))
    except Exception:
        avatar = r"""
       ▣
       │
   ┌─────────┐
   │  ■   ■  │
   │    ‿    │
   └─────────┘
     ╭─┴─╮
    ┌┤</>├┐
     ╰───╯
     █   █
"""
    info = "\n".join([
        "[bold cyan]CodeMitra[/bold cyan]",
        "[dim]─────────────────────────────[/dim]",
        "[dim]Your local AI coding companion[/dim]",
        "",
        "  [cyan]✦[/cyan]  Powered by Ollama",
        "  [cyan]✦[/cyan]  Runs 100% offline",
        "  [cyan]✦[/cyan]  No data leaves your machine",
        "",
        "[dim]Type [/dim][cyan]exit[/cyan][dim] or [/dim][cyan]quit[/cyan][dim] to leave[/dim]",
    ])

    layout = Table.grid(padding=(0, 3))
    layout.add_column(no_wrap=True)
    layout.add_column(vertical="middle")
    layout.add_row(f"[cyan]{avatar}[/cyan]", info)

    console.print(
        Align.center(
            Panel(
                Align.center(layout),
                border_style="cyan",
                title="[bold green]CodeMitra[/bold green]",
                padding=(1, 2),
                width=90,
            )
        )
    )


def main():
    show_banner()

    chat_llm = get_chat_llm()
    agent_llm = get_agent_llm()
    setup_tool = filesystem.make_routing_tool(agent_llm)
    main_llm = chat_llm.bind_tools([setup_tool])

    session = PromptSession(history=InMemoryHistory())
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    while True:
        user_input = session.prompt("\ncodemitra> ")

        if user_input.strip() in ["/exit", "exit", "quit"]:
            console.print("[yellow]Goodbye.[/yellow]")
            break

        if not user_input.strip():
            continue

        messages.append(HumanMessage(content=user_input))

        try:
            with console.status("[bold green]Thinking...[/bold green]"):
                response = main_llm.invoke(messages)

            messages.append(response)

            if response.tool_calls:
                for tc in response.tool_calls:
                    request = tc["args"].get("request", user_input)
                    with console.status("[bold green]Setup agent working...[/bold green]"):
                        agent_resp = filesystem.run(agent_llm, request)
                    messages.append(ToolMessage(content=agent_resp.summary, tool_call_id=tc["id"]))
                    console.print(render(agent_resp))

                follow_up = main_llm.invoke(messages)
                messages.append(follow_up)
                if follow_up.content.strip():
                    console.print(
                        Panel(follow_up.content, title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan")
                    )

            elif response.content.strip():
                console.print(
                    Panel(response.content, title="[bold cyan]CodeMitra[/bold cyan]", border_style="cyan")
                )

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")


if __name__ == "__main__":
    main()