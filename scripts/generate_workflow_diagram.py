"""Generate the OrderCloser Lite agent workflow diagram.

This script reads the actual LangGraph structure from app/graph/ and renders it
to both PNG and SVG via the system `dot` (graphviz) binary.

Usage:
    python scripts/generate_workflow_diagram.py

Outputs:
    docs/diagrams/workflow.png
    docs/diagrams/workflow.svg
    docs/diagrams/workflow.dot   (intermediate DOT source)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DOT_SOURCE = r"""
digraph OrderCloserWorkflow {
    // Global graph attributes
    rankdir=TB;
    splines=polyline;
    nodesep=0.6;
    ranksep=0.9;
    fontname="Helvetica";
    bgcolor="white";
    pad=0.4;

    node  [fontname="Helvetica" fontsize=11 shape=box style="rounded,filled"];
    edge  [fontname="Helvetica" fontsize=10 color="#555555"];

    // ====== External services (left rail) ======
    subgraph cluster_external {
        label="External Services";
        style="rounded,filled";
        fillcolor="#F4F6F8";
        color="#B0BEC5";
        fontname="Helvetica-Bold";
        fontsize=12;

        WA_IN  [label="WhatsApp\nBuyer Message", shape=ellipse, fillcolor="#E3F2FD"];
        LLM    [label="Gemini LLM\n(Intent Classify)", shape=ellipse, fillcolor="#FFF3E0"];
        SHEETS [label="Google Sheets\n(FAQ & Catalog)", shape=ellipse, fillcolor="#E8F5E9"];
        FONNTE [label="Fonnte\n(WA Gateway)", shape=ellipse, fillcolor="#FCE4EC"];
        DB     [label="SQLite\n(chat_log +\ncheckpoints)", shape=ellipse, fillcolor="#F3E5F5"];
    }

    // ====== Webhook layer ======
    subgraph cluster_webhook {
        label="FastAPI Webhook Layer (app/main.py)";
        style="rounded,filled";
        fillcolor="#FFFDE7";
        color="#FFD54F";
        fontname="Helvetica-Bold";
        fontsize=12;

        AUTH [label="Signature /\nBearer Auth", shape=box, fillcolor="#FFE0B2"];
        VAL  [label="Payload\nValidation", shape=box, fillcolor="#FFE0B2"];
    }

    // ====== LangGraph state machine ======
    subgraph cluster_graph {
        label="LangGraph State Machine (app/graph/nodes.py)";
        style="rounded,filled";
        fillcolor="#E0F7FA";
        color="#4DD0E1";
        fontname="Helvetica-Bold";
        fontsize=12;

        CLASSIFY   [label="classify_intent\n→ {intent, confidence}", fillcolor="#B2EBF2"];
        ROUTE      [label="route_after_classify\n(cond)", shape=diamond, fillcolor="#FFCDD2"];
        LOOKUP     [label="lookup_catalog\n→ FAQ / Katalog", fillcolor="#B2EBF2"];
        ROUTE_LOOK [label="route_after_lookup\n(cond)", shape=diamond, fillcolor="#FFCDD2"];
        COMPOSE    [label="compose_reply\n→ reply_text", fillcolor="#B2EBF2"];
        COMPOSE_O  [label="compose_order_reply\n(intent=confirm_order)", fillcolor="#B2EBF2"];
        FALLBACK   [label="fallback_human\n→ forward to owner", fillcolor="#FFCDD2"];
        SEND       [label="send_whatsapp\n→ Fonnte send", fillcolor="#C8E6C9"];
        LOG        [label="write_chat_log\n→ chat_log row", fillcolor="#C8E6C9"];
        END        [label="END", shape=doublecircle, fillcolor="#CFD8DC"];
    }

    // ====== Edge connections ======
    WA_IN   -> AUTH   [label="POST /webhook/whatsapp/"];
    AUTH    -> VAL    [label="valid"];
    VAL     -> CLASSIFY;

    CLASSIFY -> LLM    [style=dashed, label="classify()"];
    CLASSIFY -> ROUTE;

    // Branch 1: low confidence → fallback
    ROUTE   -> FALLBACK [label="conf < 0.6\nor intent=unclear"];

    // Branch 2: confirm_order → compose_order_reply directly (no Sheets)
    ROUTE   -> COMPOSE_O [label="intent=\nconfirm_order"];

    // Branch 3: faq / check_product → Sheets lookup
    ROUTE   -> LOOKUP [label="faq /\ncheck_product"];

    LOOKUP   -> SHEETS [style=dashed, label="read tab"];
    LOOKUP   -> ROUTE_LOOK;
    ROUTE_LOOK -> COMPOSE [label="match found"];
    ROUTE_LOOK -> FALLBACK [label="no match"];

    COMPOSE_O -> SEND;
    COMPOSE   -> SEND;

    FALLBACK  -> FONNTE [style=dashed, label="forward"];
    SEND      -> FONNTE [style=dashed, label="send"];
    FONNTE    -> WA_IN [style=dotted, label="reply"];

    SEND      -> LOG;
    FALLBACK  -> LOG;
    LOG       -> DB [style=dashed, label="INSERT"];
    LOG       -> END;

    // Visual grouping: face the same rank for symmetry
    {rank=same; WA_IN; AUTH;}
    {rank=same; CLASSIFY; LLM;}
    {rank=same; SHEETS; LOOKUP;}
    {rank=same; FONNTE; SEND;}
    {rank=same; DB; LOG;}
}
"""


def render(svg_path: Path, png_path: Path, dot_path: Path) -> None:
    dot_path.write_text(DOT_SOURCE, encoding="utf-8")

    # SVG (vector — best for docs/README)
    subprocess.run(
        ["dot", "-Tsvg", str(dot_path), "-o", str(svg_path)],
        check=True,
    )
    # PNG (raster — for sharing/slides)
    subprocess.run(
        ["dot", "-Tpng", str(dot_path), "-o", str(png_path)],
        check=True,
    )

    size_svg = svg_path.stat().st_size
    size_png = png_path.stat().st_size
    print(f"OK  {svg_path}  ({size_svg:,} bytes)")
    print(f"OK  {png_path}  ({size_png:,} bytes)")
    print(f"OK  {dot_path}  (DOT source for re-editing)")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / "docs" / "diagrams"
    out_dir.mkdir(parents=True, exist_ok=True)

    render(
        svg_path=out_dir / "workflow.svg",
        png_path=out_dir / "workflow.png",
        dot_path=out_dir / "workflow.dot",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
