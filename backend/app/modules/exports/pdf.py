"""Ограниченная безопасная трансляция TipTap XML в ReportLab, без HTML пользователя."""

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from pycrdt import Doc, XmlElement, XmlFragment, XmlText
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer


def register_fonts(directory: Path) -> None:
    for name, filename in (
        ("DejaVu", "DejaVuSans.ttf"),
        ("DejaVu-Bold", "DejaVuSans-Bold.ttf"),
        ("DejaVu-Italic", "DejaVuSans-Oblique.ttf"),
        ("DejaVu-BoldItalic", "DejaVuSans-BoldOblique.ttf"),
    ):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(directory / filename)))
    pdfmetrics.registerFontFamily(
        "DejaVu",
        normal="DejaVu",
        bold="DejaVu-Bold",
        italic="DejaVu-Italic",
        boldItalic="DejaVu-BoldItalic",
    )


def inline(node: XmlElement | XmlText | XmlFragment) -> str:
    if isinstance(node, XmlText):
        chunks = []
        for text, attributes in node.diff():
            value = escape(text) if isinstance(text, str) else ""
            if attributes and "bold" in attributes:
                value = f"<b>{value}</b>"
            if attributes and "italic" in attributes:
                value = f"<i>{value}</i>"
            chunks.append(value.replace("\n", "<br/>"))
        return "".join(chunks)
    if isinstance(node, XmlElement) and node.tag == "hardBreak":
        return "<br/>"
    return "".join(inline(child) for child in node.children)


def render_pdf(state: bytes, title: str, path: Path, fonts: Path) -> None:
    register_fonts(fonts)
    doc: Doc[Any] = Doc()
    doc.apply_update(state)
    fragment = doc.get("default", type=XmlFragment)
    normal = ParagraphStyle(
        "Body",
        fontName="DejaVu",
        fontSize=11,
        leading=15,
        spaceAfter=8,
        alignment=TA_LEFT,
        splitLongWords=True,
    )
    story: list[Flowable] = [
        Paragraph(
            escape(title),
            ParagraphStyle("Title", parent=normal, fontName="DejaVu-Bold", fontSize=20, leading=25),
        ),
        Spacer(1, 8 * mm),
    ]

    def blocks(node: XmlElement | XmlText | XmlFragment, depth: int = 0) -> None:
        if isinstance(node, XmlElement) and node.tag in ("bulletList", "orderedList"):
            for index, child in enumerate(node.children, 1):
                prefix = f"{index}. " if node.tag == "orderedList" else "• "
                story.append(
                    Paragraph(
                        escape(prefix) + inline(child),
                        ParagraphStyle("List", parent=normal, leftIndent=(depth + 1) * 6 * mm),
                    )
                )
            return
        if isinstance(node, XmlElement) and node.tag == "heading":
            level = str(node.attributes.get("level") or "1")
            size = {"1": 18, "2": 15, "3": 13}.get(level, 13)
            story.append(
                Paragraph(
                    inline(node),
                    ParagraphStyle(
                        "Heading",
                        parent=normal,
                        fontName="DejaVu-Bold",
                        fontSize=size,
                        leading=size + 5,
                    ),
                )
            )
        else:
            story.append(Paragraph(inline(node) or "<br/>", normal))

    for child in fragment.children:
        blocks(child)
    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    ).build(story)
