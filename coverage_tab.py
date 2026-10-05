from __future__ import annotations

from pathlib import Path
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coverage_data import (
    build_report_data,
    infer_operation_start,
    load_coverage_directory,
    load_planning,
)
from coverage_ppt import generate_coverage_pptx


BASE_DIR = Path(__file__).resolve().parent
PLANNING_PATH = BASE_DIR / "data" / "Planificacion.xlsx"
ASSETS_DIR = BASE_DIR / "assets"


@st.cache_data(show_spinner=False)
def _directory_preview(content: bytes, filename: str):
    directory, warnings, controls = load_coverage_directory(content, filename=filename)
    return directory, warnings, controls


@st.cache_data(show_spinner=False)
def _build_report_cached(
    directory_content: bytes,
    directory_filename: str,
    progress_content: bytes,
    progress_filename: str,
    selected_week: int,
    cutoff_iso: str,
    operation_start_iso: str,
    planning_modified: float,
):
    del planning_modified
    return build_report_data(
        directory_source=directory_content,
        directory_filename=directory_filename,
        progress_source=progress_content,
        progress_filename=progress_filename,
        planning_path=PLANNING_PATH,
        selected_week=selected_week,
        cutoff=pd.Timestamp(cutoff_iso),
        operation_start=pd.Timestamp(operation_start_iso),
    )


@st.cache_data(show_spinner=False)
def _ppt_cached(report, report_month: int, report_year: int, assets_signature: tuple[float, ...]) -> bytes:
    del assets_signature
    return generate_coverage_pptx(
        report,
        assets_dir=ASSETS_DIR,
        report_month=report_month,
        report_year=report_year,
    )


def _chart(frame: pd.DataFrame, executed_column: str, title: str) -> go.Figure:
    figure = go.Figure()
    figure.add_trace(go.Scatter(
        x=frame["Semana"],
        y=frame["Muestra pendiente según planificación"],
        name="Muestra pendiente",
        mode="lines",
        fill="tozeroy",
        line=dict(color="#D8E2F0", width=1.4),
        fillcolor="rgba(216,226,240,.52)",
    ))
    figure.add_trace(go.Scatter(
        x=frame["Semana"],
        y=frame["Planificado acumulado"],
        name="Planificado acumulado",
        mode="lines",
        fill="tozeroy",
        line=dict(color="#00A6C8", width=2.0),
        fillcolor="rgba(0,166,200,.20)",
    ))
    figure.add_trace(go.Scatter(
        x=frame["Semana"],
        y=frame[executed_column],
        name="Ejecutado acumulado",
        mode="lines+markers",
        line=dict(color="#2C70E7", width=3.0),
        marker=dict(size=5),
    ))
    figure.update_layout(
        title=title,
        height=390,
        margin=dict(l=20, r=20, t=55, b=30),
        xaxis_title="Semana operativo",
        yaxis_title="Empresas",
        legend_title_text="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial", color="#17365D"),
    )
    figure.update_xaxes(dtick=1, gridcolor="#E9EEF5")
    figure.update_yaxes(gridcolor="#E9EEF5", rangemode="tozero")
    return figure


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")


def render_coverage_tab(
    directory_content: bytes,
    directory_filename: str,
    default_cutoff: object,
) -> None:
    st.subheader("Reporte de cobertura")
    st.markdown(
        "<div class='method-note'>El reporte utiliza el Directorio completo y el Reporte de Avance.</div>",
        unsafe_allow_html=True,
    )

    if not PLANNING_PATH.exists():
        st.error("No se encontró `data/Planificacion.xlsx`. Agrega el archivo al repositorio.")
        return
    try:
        directory, source_warnings, source_controls = _directory_preview(
            directory_content, directory_filename
        )
        planning, _ = load_planning(PLANNING_PATH)
    except Exception as exc:
        st.error(f"No fue posible preparar el Directorio para el reporte: {exc}")
        return

    inferred_start = infer_operation_start(directory)
    max_week = int(planning["week"].max())
    default_cutoff_ts = pd.Timestamp(default_cutoff).normalize()
    inferred_week = int((default_cutoff_ts - inferred_start).days // 7 + 1)
    inferred_week = min(max(inferred_week, 1), max_week)

    st.markdown("#### Parámetros")
    upload_col, status_col = st.columns([2, 1])
    with upload_col:
        progress_file = st.file_uploader(
            "Reporte de avance",
            type=["xlsx", "xls"],
            key="coverage_progress_file",
            help="Debe contener Identificador Empresa y los 22 capítulos del formulario.",
        )
    with status_col:
        st.success(f"Directorio cargado: {directory_filename}")
        st.caption("Planificación zonal: 5/10/2026")

    p1, p2, p3 = st.columns(3)
    cutoff = p1.date_input(
        "Fecha del reporte",
        value=default_cutoff_ts.date(),
        key="coverage_cutoff",
    )
    selected_week = int(p2.number_input(
        "Semana operativo",
        min_value=1,
        max_value=max_week,
        value=inferred_week,
        step=1,
        key="coverage_week",
    ))
    operation_start = p3.date_input(
        "Inicio de la semana 1",
        value=inferred_start.date(),
        key="coverage_operation_start",
        help="Solo se usa para cuando COB_CAMP o COB/CRIT no existen.",
    )

    source_cards = st.columns(4)
    source_cards[0].metric("Empresas", f"{source_controls['companies_used']:,}")
    source_cards[1].metric("ID excluido", f"{source_controls['excluded_special_id']:,}")
    source_cards[2].metric("Semana máxima planificada", f"{max_week}")
    source_cards[3].metric("Inicio operativo", f"{pd.Timestamp(operation_start):%d/%m/%Y}")

    if source_warnings:
        with st.expander("Advertencias"):
            for warning in source_warnings:
                st.warning(warning)

    if progress_file is None:
        st.info("Carga el Reporte de avance para calcular las láminas y habilitar la descarga.")
        return

    try:
        with st.spinner("Calculando las láminas del reporte..."):
            report = _build_report_cached(
                directory_content,
                directory_filename,
                progress_file.getvalue(),
                progress_file.name,
                selected_week,
                pd.Timestamp(cutoff).isoformat(),
                pd.Timestamp(operation_start).isoformat(),
                PLANNING_PATH.stat().st_mtime,
            )
    except Exception as exc:
        st.error(f"No fue posible construir el reporte: {exc}")
        return

    validation_cards = st.columns(4)
    validation_cards[0].metric("Empresas Utilizadas", f"{report.controls['companies_used']:,}")
    validation_cards[1].metric("Registros en reporte", f"{report.controls['progress_rows']:,}")
    validation_cards[2].metric("Sin avance", f"{report.controls['missing_progress']:,}")
    validation_cards[3].metric("Semana del reporte", f"{report.selected_week}")

    if report.warnings:
        with st.expander("Advertencias", expanded=True):
            for warning in report.warnings:
                st.warning(warning)

    preview_tabs = st.tabs([
        "Socialización",
        "Campo",
        "Crítica",
        "Estado de avance",
        "Novedades",
    ])
    with preview_tabs[0]:
        st.markdown("##### Cobertura de socialización y diligenciamiento")
        st.dataframe(report.socialization, hide_index=True, use_container_width=True)
        st.markdown("##### Empresas que informan en otra Coordinación Zonal")
        st.dataframe(report.transfers, hide_index=True, use_container_width=True)

    with preview_tabs[1]:
        st.dataframe(report.field_coverage, hide_index=True, use_container_width=True)
        st.dataframe(
            report.field_indicators,
            hide_index=True,
            use_container_width=True,
            column_config={
                column: st.column_config.ProgressColumn(column, min_value=0, max_value=1, format="percent")
                for column in report.field_indicators.columns[1:]
            },
        )
        st.plotly_chart(
            _chart(report.field_chart, "Ejecutadas acumuladas", "Cobertura acumulada de levantamiento"),
            use_container_width=True,
            key="coverage_field_chart",
        )

    with preview_tabs[2]:
        st.dataframe(report.critique_coverage, hide_index=True, use_container_width=True)
        st.dataframe(
            report.critique_indicators,
            hide_index=True,
            use_container_width=True,
            column_config={
                column: st.column_config.ProgressColumn(column, min_value=0, max_value=1, format="percent")
                for column in report.critique_indicators.columns[1:]
            },
        )
        st.plotly_chart(
            _chart(report.critique_chart, "Criticadas acumuladas", "Cobertura acumulada de crítica"),
            use_container_width=True,
            key="coverage_crit_chart",
        )

    with preview_tabs[3]:
        left, right = st.columns(2)
        left.dataframe(report.progress_status, hide_index=True, use_container_width=True)
        right.dataframe(report.progress_bands, hide_index=True, use_container_width=True)

    with preview_tabs[4]:
        if report.novelties.empty:
            st.info("No existen novedades para la semana seleccionada.")
        else:
            st.dataframe(report.novelties, hide_index=True, use_container_width=True)

    st.markdown("#### Generar archivo")
    st.caption(
        "ENESEM"
        ""
    )
    try:
        assets_signature = tuple(
            path.stat().st_mtime for path in sorted(ASSETS_DIR.glob("*.png"))
        )
        pptx = _ppt_cached(
            report,
            pd.Timestamp(cutoff).month,
            pd.Timestamp(cutoff).year,
            assets_signature,
        )
    except Exception as exc:
        st.error(f"No fue posible generar la presentación: {exc}")
        return

    file_name = _safe_filename(
        f"Reporte_cobertura_ENESEM_{pd.Timestamp(cutoff).year - 1}_semana_{selected_week}_{pd.Timestamp(cutoff):%Y%m%d}"
    ) + ".pptx"
    st.download_button(
        "Descargar reporte de cobertura",
        data=pptx,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        type="primary",
        key="download_coverage_pptx",
    )
