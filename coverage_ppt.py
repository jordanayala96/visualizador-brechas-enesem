from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from pptx import Presentation
from pptx.chart.data import ChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from coverage_data import ReportData


PRIMARY = "2C70E7"
NAVY = "17365D"
CYAN = "00A6C8"
AMBER = "D99A2B"
CORAL = "C75252"
SLATE = "5F6B7A"
PALE_BLUE = "EAF2FF"
PALE_CYAN = "E8F7FA"
LIGHT = "F5F7FA"
GRID = "D7E0EA"
WHITE = "FFFFFF"
BLACK = "1F2937"

FONT = "Century Gothic"
SLIDE_W = 13.333
SLIDE_H = 7.5


MONTHS_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre",
    11: "noviembre", 12: "diciembre",
}


def _rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value.replace("#", ""))


def _asset(assets_dir: str | Path, name: str) -> Path:
    path = Path(assets_dir) / name
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el recurso gráfico {path}.")
    return path


def _background(slide, image_path: Path) -> None:
    slide.shapes.add_picture(str(image_path), 0, 0, width=Inches(SLIDE_W), height=Inches(SLIDE_H))


def _add_text(
    slide,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    size: float = 18,
    color: str = BLACK,
    bold: bool = False,
    align: PP_ALIGN = PP_ALIGN.LEFT,
    valign: MSO_ANCHOR = MSO_ANCHOR.MIDDLE,
    margin: float = 0.04,
) -> object:
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = shape.text_frame
    frame.clear()
    frame.margin_left = Inches(margin)
    frame.margin_right = Inches(margin)
    frame.margin_top = Inches(margin)
    frame.margin_bottom = Inches(margin)
    frame.vertical_anchor = valign
    paragraph = frame.paragraphs[0]
    paragraph.text = str(text)
    paragraph.alignment = align
    paragraph.font.name = FONT
    paragraph.font.size = Pt(size)
    paragraph.font.bold = bold
    paragraph.font.color.rgb = _rgb(color)
    return shape


def _add_content_title(slide, title: str) -> None:
    _add_text(slide, title, 1.18, 0.30, 10.35, 0.46, size=24, color=BLACK, bold=True)
    line = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(1.18), Inches(0.84), Inches(1.1), Inches(0.055)
    )
    line.fill.solid()
    line.fill.fore_color.rgb = _rgb(PRIMARY)
    line.line.fill.background()


def _format_number(value: object, percent: bool = False) -> str:
    if pd.isna(value):
        return "—"
    if percent:
        return f"{float(value):.1%}"
    if isinstance(value, (float, np.floating)) and not float(value).is_integer():
        return f"{float(value):,.1f}"
    return f"{int(round(float(value))):,}"


def _cell_fill(cell, color: str) -> None:
    cell.fill.solid()
    cell.fill.fore_color.rgb = _rgb(color)


def _cell_text(
    cell,
    text: object,
    *,
    size: float,
    color: str,
    bold: bool = False,
    align: PP_ALIGN = PP_ALIGN.CENTER,
) -> None:
    cell.text = str(text)
    cell.margin_left = Inches(0.025)
    cell.margin_right = Inches(0.025)
    cell.margin_top = Inches(0.015)
    cell.margin_bottom = Inches(0.015)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    for paragraph in cell.text_frame.paragraphs:
        paragraph.alignment = align
        paragraph.font.name = FONT
        paragraph.font.size = Pt(size)
        paragraph.font.bold = bold
        paragraph.font.color.rgb = _rgb(color)


def _add_table(
    slide,
    frame: pd.DataFrame,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    percent_columns: Iterable[str] = (),
    header_size: float = 8.0,
    body_size: float = 8.0,
    first_column_width: float | None = None,
    title: str | None = None,
) -> object:
    if title:
        _add_text(slide, title, x, y - 0.30, w, 0.26, size=11, color=NAVY, bold=True)
    rows, cols = len(frame) + 1, len(frame.columns)
    shape = slide.shapes.add_table(rows, cols, Inches(x), Inches(y), Inches(w), Inches(h))
    table = shape.table
    if first_column_width is not None and cols > 1:
