from typing import List, Optional, Sequence, Union
import shutil
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich.table import Table

# --- COLOR PALETTE ---
BG_COLOR = "#121212"       # Deep dark background
PRIMARY_RED = "#d63c4e"    # The "LOGO" red color
DIM_RED = "#8a2632"        # Darker red for borders/dim text
TEXT_GREY = "#a3a3a3"      # Main text color
HIGHLIGHT_CYAN = "#4ec9b0" # The cyan used for "help"
WHITE = "#ffffff"

# --- LOGO: "LY-RIC" with hyphen blocks in the middle ---
LOGO = r"""
██╗     ██╗   ██╗      ██████╗ ██╗ ██████╗
██║     ╚██╗ ██╔╝      ██╔══██╗██║██╔════╝
██║      ╚████╔╝  ██╗  ██████╔╝██║██║     
██║       ╚██╔╝   ╚═╝  ██╔══██╗██║██║     
███████╗   ██║         ██║  ██║██║╚██████╗
╚══════╝   ╚═╝         ╚═╝  ╚═╝╚═╝ ╚═════╝
""".strip("\n")

def _format_time(seconds: Optional[float]) -> str:
    if seconds is None:
        seconds = 0
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"

def _progress_bar(elapsed: float, duration: float, width: int = 50) -> Text:
    duration = duration or 1
    ratio = max(0.0, min(1.0, elapsed / duration))
    filled = int(width * ratio)
    bar = "█" * filled + "░" * (width - filled)
    
    t = Text()
    t.append(f" {_format_time(elapsed)} ", style=f"bold {HIGHLIGHT_CYAN}")
    t.append(bar, style=PRIMARY_RED)
    t.append(f" {_format_time(duration)} ", style=f"bold {TEXT_GREY}")
    return t

def render(
    *,
    track_title: str,
    track_uploader: str,
    elapsed: float,
    duration: float,
    paused: bool,
    lyric_lines: Optional[Sequence[Union[str, "LyricLine"]]],
    current_index: int,
    context_size: int = 4,
    status_msg: str = "",
) -> Panel:
    
    term_height = shutil.get_terminal_size().lines
    
    # 1. HEADER (Logo Only)
    header_group = Group(
        Text(LOGO, style=f"bold {PRIMARY_RED}"), # Red Logo
        Text(""), # Spacer
        Text(f"SHELL v2.0 — LY-RIC Term", style=f"dim {TEXT_GREY}"),
        Text(f"Operator: {track_uploader} · {track_title}", style=TEXT_GREY),
        Text(""),
    )

    # 2. STATUS & PROGRESS
    status = "PAUSED" if paused else "PLAYING"
    status_color = HIGHLIGHT_CYAN if paused else PRIMARY_RED
    
    progress_row = Table.grid(padding=(0, 1))
    progress_row.add_column()
    progress_row.add_column()
    progress_row.add_row(
        Text(f"[{status}]", style=f"bold {status_color}"),
        _progress_bar(elapsed, duration)
    )

    # 3. LYRICS - LEFT ALIGNED SCROLL
    lyric_block = Text(justify="left") #left
    
    if not lyric_lines:
        lyric_block.append("\n  (awaiting lyrics data...)\n", style=f"dim {TEXT_GREY}")
    else:
        # Calculate window
        lo = max(0, current_index - context_size)
        hi = min(len(lyric_lines), current_index + context_size + 1)
        
        lyric_block.append("\n") # Top padding
        
        for i in range(lo, hi):
            raw = lyric_lines[i]
            text = raw.text if hasattr(raw, "text") else raw
            
            if i == current_index:
                # Active line: Cyan highlight, bold, with a marker
                lyric_block.append(f"  > {text}\n", style=f"bold {HIGHLIGHT_CYAN} on {BG_COLOR}")
            elif i < current_index:
                # Past lines: Very dim
                lyric_block.append(f"    {text}\n", style=f"dim {DIM_RED}")
            else:
                # Future lines: Standard grey
                lyric_block.append(f"    {text}\n", style=TEXT_GREY)

    # 4. FOOTER 
    footer_text = Text()
    if status_msg:
        footer_text.append(f"> {status_msg}\n", style=f"bold {PRIMARY_RED}")
    footer_text.append(
        "[space]pause  [←/→]seek  [k]prev  [j]next  [r]replay  [f]search  [q]quit",
        style=f"dim {TEXT_GREY}",
    )   

    # 5. ASSEMBLE LAYOUT
    layout_table = Table.grid(expand=True)
    layout_table.add_column(ratio=1) # Takes all space
    
    layout_table.add_row(header_group)
    layout_table.add_row(Text("")) # Spacer
    layout_table.add_row(progress_row)
    layout_table.add_row(Text("")) # Spacer
    layout_table.add_row(lyric_block)
    
    body = Group(
        layout_table,
        Text(""), # Spacer before footer
        footer_text
    )

    return Panel(
        body,
        border_style=DIM_RED, # Dim red border
        padding=(1, 2),
        title=None, # Remove top title to look cleaner 
        expand=True,
        height=term_height,
        style=f"on {BG_COLOR}", # Set background color explicitly
    )

def make_console() -> Console:
    return Console()

def render_search(
    *,
    query: str,
    results: list,
    selected_idx: int,
    searching: bool = False,
    error: str = "",
) -> Panel:
    term_height = shutil.get_terminal_size().lines

    header = Group(
        Text(LOGO, style=f"bold {PRIMARY_RED}"),
        Text(""),
        Text("SHELL v2.0 — LY-RIC Term", style=f"dim {TEXT_GREY}"),
        Text("Type to search, Enter to submit / select, j/k to navigate, q to quit", style=f"dim {TEXT_GREY}"),
        Text(""),
    )

    search_line = Text()
    search_line.append("search> ", style=f"bold {PRIMARY_RED}")
    search_line.append(query, style=f"bold {WHITE}")
    search_line.append("▌", style=f"blink {HIGHLIGHT_CYAN}")

    body_parts = [header, search_line, Text("")]

    if searching:
        body_parts.append(Text("searching YouTube Music...", style=f"italic {HIGHLIGHT_CYAN}"))
    elif error:
        body_parts.append(Text(f"Error: {error}", style=f"bold {PRIMARY_RED}"))
    elif results:
        table = Table(border_style=PRIMARY_RED, header_style=f"bold {PRIMARY_RED}", expand=True)
        table.add_column("#", justify="right", style=TEXT_GREY, width=4)
        table.add_column("Title", style=WHITE, no_wrap=True, ratio=3)
        table.add_column("Channel", style=TEXT_GREY, no_wrap=True, ratio=2)
        table.add_column("Duration", style=TEXT_GREY, justify="right", width=8)

        for i, t in enumerate(results):
            row_style = f"bold {HIGHLIGHT_CYAN} on {BG_COLOR}" if i == selected_idx else ""
            table.add_row(str(i + 1), t.title, t.uploader, t.duration_str, style=row_style)

        body_parts.append(table)
    else:
        hint = "Press Enter to search" if query else "Start typing to search for a song..."
        body_parts.append(Text(hint, style=f"dim {TEXT_GREY}"))

    footer = Text(
        "[type] search  [Enter] submit/select  [j/k] navigate  [Esc] clear  [q] quit",
        style=f"dim {TEXT_GREY}",
    )

    body = Group(*body_parts, Text(""), footer)

    return Panel(
        body,
        border_style=DIM_RED,
        padding=(1, 2),
        expand=True,
        height=term_height,
        style=f"on {BG_COLOR}",
    )
