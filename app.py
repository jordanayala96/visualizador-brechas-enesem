from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from io import BytesIO

from enesem_data import (
    ALERT_ORDER,
    CAUSE_OPTIONS,
    add_gap_metrics,
    activity_weekly_summary,
    company_case_table,
    filter_directory,
    infer_cutoff,
    interviewer_activity_summary,
    interviewer_totals,
    load_directory,
    quality_case_table,
    quality_summary,
    weekly_summary,
    zonal_summary,
)


st.set_page_config(
    page_title="Brechas ENESEM 2026",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root { --enesem-navy:#17365D; --enesem-teal:#008FA8; --enesem-pale:#EAF3F8; }
      .block-container { padding-top: 1.35rem; padding-bottom: 2.5rem; }
      h1, h2, h3 { color: var(--enesem-navy); }
      [data-testid="stMetric"] { background:#FFFFFF; border:1px solid #D6E2EA; border-radius:10px; padding:12px 14px; }
      [data-testid="stMetricLabel"] { color:#40566B; }
      .enesem-banner { background:linear-gradient(90deg,#17365D,#008FA8); color:white; padding:20px 24px; border-radius:12px; margin-bottom:16px; }
      .enesem-banner h1 { color:white; margin:0; font-size:1.9rem; }
      .enesem-banner p { margin:6px 0 0 0; opacity:.92; }
      .method-note { background:#EAF3F8; border-left:5px solid #008FA8; padding:12px 14px; border-radius:6px; }
      .privacy-note { background:#F2F2F2; border-left:5px solid #548235; padding:10px 13px; border-radius:6px; font-size:.92rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_from_bytes(content: bytes, filename: str) -> pd.DataFrame:
    return load_directory(content, filename=filename)


@st.cache_data(show_spinner=False)
def load_from_path(path: str, modified: float) -> pd.DataFrame:
    del modified
    return load_directory(path)


def default_file() -> Path | None:
    candidates = [
        Path("data/Directorio.xlsx"),
        Path("data/Directorio(1).xlsx"),
        Path("Directorio.xlsx"),
        Path("Directorio(1).xlsx"),
    ]
    return next((path for path in candidates if path.exists()), None)


def sorted_options(frame: pd.DataFrame, column: str) -> list[str]:
    return sorted(value for value in frame[column].dropna().astype(str).unique() if value != "Sin dato")


def pct(value: float | int) -> str:
    return f"{float(value):.1%}"


def days(value: float | int | None) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):.0f} días"


def vega_bar(data: pd.DataFrame, x: str, y: str, color: str | None = None, sort: list[str] | str | None = None) -> dict:
    encoding: dict = {
        "x": {"field": x, "type": "nominal", "sort": sort, "axis": {"labelAngle": 0}},
        "y": {"field": y, "type": "quantitative", "title": "Casos"},
        "tooltip": [
            {"field": x, "type": "nominal"},
            {"field": y, "type": "quantitative", "format": ",.0f"},
        ],
    }
    if color:
        encoding["color"] = {
            "field": color,
            "type": "nominal",
            "sort": ALERT_ORDER,
            "scale": {
                "domain": ALERT_ORDER,
                "range": ["#70AD47", "#FFC000", "#ED7D31", "#C00000", "#A5A5A5"],
            },
        }
        encoding["tooltip"].insert(1, {"field": color, "type": "nominal"})
    return {
        "mark": {"type": "bar", "cornerRadiusTopLeft": 3, "cornerRadiusTopRight": 3},
        "encoding": encoding,
        "height": 330,
    }


st.markdown(
    """
    <div class="enesem-banner">
      <h1>Brecha entre socialización y diligenciamiento</h1>
      <p>Tablero para la V Reunión nacional de evaluación y planificación de la ENESEM · Versión 2.1</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Fuente de información")
    st.success("Directorio de Empresas - ENESEM")
    uploaded = st.file_uploader(
        "Directorio ENESEM",
        type=["xlsx", "xls", "csv", "txt"],
        help="La aplicación lee los id de cada empresa y las columnas necesarias.",
    )
    local_file = default_file()

try:
    if uploaded is not None:
        base = load_from_bytes(uploaded.getvalue(), uploaded.name)
        source_label = f"Archivo cargado: {uploaded.name}"
    elif local_file is not None:
        base = load_from_path(str(local_file), local_file.stat().st_mtime)
        source_label = f"Archivo local: {local_file.name}"
    else:
        st.info(
            "Carga el directorio desde la barra lateral o coloca el archivo como "
            "`data/Directorio.xlsx`. La base no está incluida en este proyecto."
        )
        st.stop()
except Exception as exc:
    st.error(f"No fue posible leer el directorio: {exc}")
    st.stop()

default_cutoff = infer_cutoff(base)

with st.sidebar:
    st.caption(source_label)
    st.divider()
    st.header("Parámetros")
    cutoff = st.date_input(
        "Fecha de corte",
        value=default_cutoff.date(),
        help="Para una base histórica conviene usar la última fecha registrada, no la fecha actual.",
    )
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        threshold_1 = int(st.number_input("Inicial", min_value=1, value=15, step=1))
    with col_b:
        threshold_2 = int(st.number_input("Alta", min_value=2, value=30, step=1))
    with col_c:
        threshold_3 = int(st.number_input("Crítica", min_value=3, value=60, step=1))
    thresholds = (threshold_1, threshold_2, threshold_3)
    if not threshold_1 < threshold_2 < threshold_3:
        st.error("Los umbrales deben cumplir: Inicial < Alta < Crítica.")
        st.stop()

data = add_gap_metrics(base, cutoff, thresholds)

with st.sidebar:
    st.divider()
    st.header("Filtros")
    zones = st.multiselect("Coordinación Zonal", sorted_options(data, "zonal"))
    provinces = st.multiselect("Provincia", sorted_options(data, "provincia"))
    sizes = st.multiselect("Tamaño", sorted_options(data, "tamano"))
    interviewers = st.multiselect("Encuestador/a", sorted_options(data, "encuestador"))
    sectors = st.multiselect("Sector", sorted_options(data, "sector"))
    company_query = st.text_input(
        "Buscar empresa",
        placeholder="Identificador, RUC o nombre",
        help="Busca coincidencias parciales en el identificador, RUC, razón social y nombre comercial.",
    )
    scope = st.selectbox(
        "Estado de la brecha",
        ["Todas", "Pendientes de diligenciamiento", "Diligenciadas", "Con inconsistencia de fechas"],
    )
    st.markdown(
        "<div class='privacy-note'><strong>Uso interno:</strong> el tablero carga y muestra el Directorio de Empresas.</div>",
        unsafe_allow_html=True,
    )

filtered = filter_directory(
    data,
    zones=zones,
    provinces=provinces,
    sizes=sizes,
    interviewers=interviewers,
    sectors=sectors,
    company_query=company_query,
    scope=scope,
)

if filtered.empty:
    st.warning("La combinación de filtros no contiene empresas.")
    st.stop()

valid_completed = filtered.loc[filtered["sd_completada"], "dias_sd"].dropna()
tracked = filtered["dias_sd"].dropna()

tabs = st.tabs([
    "Resumen",
    "Comparación zonal",
    "Casos críticos",
    "Evolución",
    "Por encuestador",
    "Calidad de datos",
    "Guía para la mesa",
])

with tabs[0]:
    st.caption(f"Fecha de corte seleccionada: {pd.Timestamp(cutoff):%d/%m/%Y} · {len(filtered):,} empresas filtradas")
    cards = st.columns(6)
    cards[0].metric("Empresas", f"{len(filtered):,}")
    cards[1].metric("Diligenciadas válidas", f"{int(filtered['sd_completada'].sum()):,}")
    cards[2].metric("Pendientes", f"{int(filtered['sd_pendiente'].sum()):,}")
    cards[3].metric("Mediana S→D", days(valid_completed.median() if len(valid_completed) else None))
    cards[4].metric("P90 S→D", days(valid_completed.quantile(.90) if len(valid_completed) else None))
    cards[5].metric("Fechas inconsistentes", f"{int(filtered['sd_inconsistente'].sum()):,}")

    threshold_cards = st.columns(3)
    threshold_cards[0].metric(
        f"Casos {threshold_1 + 1}–{threshold_2} días",
        f"{int((tracked.gt(threshold_1) & tracked.le(threshold_2)).sum()):,}"
    )
    threshold_cards[1].metric(
        f"Casos {threshold_2 + 1}–{threshold_3} días",
        f"{int((tracked.gt(threshold_2) & tracked.le(threshold_3)).sum()):,}"
    )
    threshold_cards[2].metric(
        f"Casos >{threshold_3} días",
        f"{int(tracked.gt(threshold_3).sum()):,}"
    )

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("Distribución de días S→D")
        histogram = filtered.loc[
            filtered["dias_sd"].notna(), ["dias_sd", "estado_sd"]
        ].rename(columns={"dias_sd": "Días", "estado_sd": "Estado"})

        st.vega_lite_chart(
            histogram,
            {
                "mark": {"type": "bar", "opacity": 0.82},
                "encoding": {
                    "x": {
                        "bin": {"step": 5},
                        "field": "Días",
                        "type": "quantitative",
                        "title": "Días entre socialización y diligenciamiento / corte"
                    },
                    "y": {
                        "aggregate": "count",
                        "type": "quantitative",
                        "title": "Empresas"
                    },
                    "color": {
                        "field": "Estado",
                        "type": "nominal",
                        "scale": {"range": ["#008FA8", "#ED7D31", "#C00000"]}
                    },
                    "tooltip": [
                        {
                            "field": "Días",
                            "bin": {"step": 5},
                            "type": "quantitative",
                            "title": "Intervalo de días"
                        },
                        {
                            "aggregate": "count",
                            "type": "quantitative",
                            "title": "Empresas"
                        }
                    ],
                },
                "height": 340,
            },
            use_container_width=True,
        )
    with right:
        st.subheader("Alertas por Coordinación Zonal")
        alert_counts = (
            filtered.groupby(["zonal", "alerta_sd"], observed=True)
            .size()
            .reset_index(name="Casos")
            .rename(columns={"zonal": "Coordinación Zonal", "alerta_sd": "Alerta"})
        )
        st.vega_lite_chart(
            alert_counts,
            vega_bar(alert_counts, "Coordinación Zonal", "Casos", "Alerta"),
            use_container_width=True,
        )

    st.subheader("Contexto del ciclo completo")
    context_cols = st.columns(4)
    dl_complete = filtered.loc[filtered["dl_completada"], "dias_dl"].dropna()
    sl_complete = filtered.loc[filtered["sl_completada"], "dias_sl"].dropna()
    context_cols[0].metric("Levantadas", f"{int(filtered['levantada'].sum()):,}")
    context_cols[1].metric("Mediana D→L", days(dl_complete.median() if len(dl_complete) else None))
    context_cols[2].metric("Mediana S→L", days(sl_complete.median() if len(sl_complete) else None))
    context_cols[3].metric("Diligenciadas sin levantar", f"{int(filtered['dl_pendiente'].sum()):,}")

with tabs[1]:
    st.subheader("Indicadores comparables por Coordinación Zonal")
    zonal = zonal_summary(filtered, thresholds)
    st.dataframe(
        zonal,
        hide_index=True,
        use_container_width=True,
        column_config={
            "% diligenciadas": st.column_config.ProgressColumn("% diligenciadas", min_value=0, max_value=1, format="percent"),
            "Mediana S→D": st.column_config.NumberColumn("Mediana S→D", format="%.1f días"),
            "P90 S→D": st.column_config.NumberColumn("P90 S→D", format="%.1f días"),
        },
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Mediana de días completados")
        chart = zonal[["Coordinación Zonal", "Mediana S→D"]].dropna()
        st.vega_lite_chart(
            chart,
            {
                "mark": {"type": "bar", "color": "#008FA8", "cornerRadiusEnd": 4},
                "encoding": {
                    "y": {"field": "Coordinación Zonal", "type": "nominal", "sort": "-x"},
                    "x": {"field": "Mediana S→D", "type": "quantitative", "title": "Días"},
                    "tooltip": [
                        {"field": "Coordinación Zonal", "type": "nominal"},
                        {"field": "Mediana S→D", "type": "quantitative", "format": ".1f"},
                    ],
                },
                "height": 310,
            },
            use_container_width=True,
        )
    with col2:
        st.subheader("Dispersión de la brecha")
        box = filtered.loc[filtered["sd_completada"], ["zonal", "dias_sd"]].rename(
            columns={"zonal": "Coordinación Zonal", "dias_sd": "Días"}
        )
        st.vega_lite_chart(
            box,
            {
                "mark": {"type": "boxplot", "extent": 1.5, "color": "#17365D"},
                "encoding": {
                    "x": {"field": "Coordinación Zonal", "type": "nominal", "axis": {"labelAngle": 0}},
                    "y": {"field": "Días", "type": "quantitative"},
                },
                "height": 310,
            },
            use_container_width=True,
        )

with tabs[2]:
    st.subheader("Priorización y clasificación de casos")
    st.markdown(
        "<div class='method-note'>Los días de las empresas ya diligenciadas corresponden al tiempo observado. Para las pendientes, se calculan desde la socialización hasta la fecha de corte.</div>",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    minimum_days = int(c1.number_input("Mostrar desde", min_value=0, value=threshold_1 + 1, step=1))
    status_choice = c2.selectbox("Tipo de caso", ["Todos", "Solo pendientes", "Solo diligenciados"])
    limit = int(c3.number_input("Número de casos", min_value=10, max_value=500, value=50, step=10))

    critical = filtered.loc[filtered["dias_sd"].ge(minimum_days)].copy()
    if status_choice == "Solo pendientes":
        critical = critical.loc[critical["sd_pendiente"]]
    elif status_choice == "Solo diligenciados":
        critical = critical.loc[critical["sd_completada"]]
    critical = critical.sort_values(["dias_sd", "zonal"], ascending=[False, True]).head(limit)

    if critical.empty:
        st.info("No existen casos para los criterios seleccionados.")
    else:
        work = company_case_table(critical)
        work["Causa preliminar"] = "Por determinar"
        work["Acción propuesta"] = ""
        work["¿Requiere escalamiento?"] = "Por determinar"
        edited = st.data_editor(
            work,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "Identificador empresa": st.column_config.TextColumn("Identificador empresa"),
                "RUC": st.column_config.TextColumn("RUC"),
                "Causa preliminar": st.column_config.SelectboxColumn("Causa preliminar", options=CAUSE_OPTIONS, required=True),
                "¿Requiere escalamiento?": st.column_config.SelectboxColumn("¿Requiere escalamiento?", options=["Por determinar", "Sí", "No"], required=True),
                "Fecha socialización": st.column_config.DateColumn("Fecha socialización", format="DD/MM/YYYY"),
                "Fecha diligenciamiento": st.column_config.DateColumn("Fecha diligenciamiento", format="DD/MM/YYYY"),
                "Días S→D": st.column_config.NumberColumn("Días S→D", format="%d"),
            },
            key="critical_editor",
        )
        excel = BytesIO()
        with pd.ExcelWriter(excel, engine="openpyxl") as writer:
            edited.to_excel(writer, sheet_name="Clasificación de casos", index=False)

        st.download_button(
            "Descargar clasificación de casos",
            data=excel.getvalue(),
            file_name="clasificacion_brechas_enesem.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with tabs[3]:
    st.subheader("Evolución del operativo")
    evolution_tabs = st.tabs(["Cohortes de socialización", "Actividad semanal"])

    with evolution_tabs[0]:
        st.markdown(
            f"<div class='method-note'>Cada cohorte reúne las empresas socializadas de lunes a domingo. "
            f"El porcentaje oportuno divide las empresas diligenciadas en un máximo de {threshold_1} días "
            f"para todas las empresas socializadas de la cohorte. Solo se calcula cuando toda la cohorte "
            f"ya tuvo al menos {threshold_1} días de observación.</div>",
            unsafe_allow_html=True,
        )
        weekly = weekly_summary(filtered, threshold_1, cutoff)
        if weekly.empty:
            st.info("No existen fechas de socialización para construir las cohortes.")
        else:
            week_order = (
                weekly.sort_values("Inicio semana")["Semana"].drop_duplicates().tolist()
            )
            metric_name = f"% dentro de {threshold_1} días"
            c1, c2 = st.columns(2)
            with c1:
                st.caption("Mediana de días entre las empresas que ya fueron diligenciadas")
                st.vega_lite_chart(
                    weekly,
                    {
                        "mark": {"type": "line", "point": True},
                        "encoding": {
                            "x": {
                                "field": "Semana",
                                "type": "ordinal",
                                "sort": week_order,
                                "scale": {"domain": week_order},
                                "axis": {"labelAngle": -45, "labelLimit": 130},
                                "title": "Semana de socialización (lunes a domingo)",
                            },
                            "y": {"field": "Mediana S→D", "type": "quantitative", "title": "Mediana de días"},
                            "color": {"field": "Coordinación Zonal", "type": "nominal"},
                            "tooltip": [
                                {"field": "Semana", "type": "ordinal"},
                                {"field": "Coordinación Zonal", "type": "nominal"},
                                {"field": "Socializadas", "type": "quantitative", "format": ",.0f"},
                                {"field": "Diligenciadas", "type": "quantitative", "format": ",.0f"},
                                {"field": "Mediana S→D", "type": "quantitative", "format": ".1f"},
                            ],
                        },
                        "height": 360,
                    },
                    use_container_width=True,
                )
            with c2:
                st.caption(f"Empresas diligenciadas en un máximo de {threshold_1} días sobre todas las socializadas")
                st.vega_lite_chart(
                    weekly,
                    {
                        "mark": {"type": "line", "point": True},
                        "encoding": {
                            "x": {
                                "field": "Semana",
                                "type": "ordinal",
                                "sort": week_order,
                                "scale": {"domain": week_order},
                                "axis": {"labelAngle": -45, "labelLimit": 130},
                                "title": "Semana de socialización (lunes a domingo)",
                            },
                            "y": {
                                "field": metric_name,
                                "type": "quantitative",
                                "axis": {"format": ".0%"},
                                "scale": {"domain": [0, 1]},
                                "title": f"% dentro de {threshold_1} días",
                            },
                            "color": {"field": "Coordinación Zonal", "type": "nominal"},
                            "tooltip": [
                                {"field": "Semana", "type": "ordinal"},
                                {"field": "Coordinación Zonal", "type": "nominal"},
                                {"field": "Estado cohorte", "type": "nominal"},
                                {"field": "Socializadas", "type": "quantitative", "format": ",.0f"},
                                {"field": f"Diligenciadas ≤ {threshold_1} días", "type": "quantitative", "format": ",.0f"},
                                {"field": metric_name, "type": "quantitative", "format": ".1%"},
                            ],
                        },
                        "height": 360,
                    },
                    use_container_width=True,
                )

            st.dataframe(
                weekly,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Inicio semana": st.column_config.DateColumn("Inicio semana", format="DD/MM/YYYY"),
                    "Fin semana": st.column_config.DateColumn("Fin semana", format="DD/MM/YYYY"),
                    "% diligenciadas": st.column_config.ProgressColumn("% diligenciadas", min_value=0, max_value=1, format="percent"),
                    metric_name: st.column_config.ProgressColumn(metric_name, min_value=0, max_value=1, format="percent"),
                    "Mediana S→D": st.column_config.NumberColumn("Mediana S→D", format="%.1f días"),
                },
            )

    with evolution_tabs[1]:
        st.markdown(
            "<div class='method-note'>Esta vista ubica cada evento en la semana calendario en la que ocurrió. "
            "Por eso puede continuar después de la última semana de socialización y mostrar actividad de "
            "diligenciamiento y levantamiento hasta la fecha de corte.</div>",
            unsafe_allow_html=True,
        )
        activity = activity_weekly_summary(filtered, cutoff)
        if activity.empty:
            st.info("No existen fechas operativas para construir la actividad semanal.")
        else:
            activity_zones = sorted(activity["Coordinación Zonal"].unique())
            activity_choice = st.selectbox(
                "Coordinación Zonal para visualizar",
                ["Total filtrado", *activity_zones],
                key="activity_zone",
            )
            if activity_choice == "Total filtrado":
                activity_view = (
                    activity.groupby(["Inicio semana", "Fin semana", "Semana"], as_index=False)[
                        ["Socializadas", "Diligenciadas", "Levantadas"]
                    ]
                    .sum()
                    .sort_values("Inicio semana")
                )
                activity_view["Coordinación Zonal"] = "Total filtrado"
            else:
                activity_view = activity.loc[
                    activity["Coordinación Zonal"].eq(activity_choice)
                ].sort_values("Inicio semana")

            activity_order = activity_view["Semana"].drop_duplicates().tolist()
            activity_view = activity_view.reset_index(drop=True)
            activity_long = activity_view.melt(
                id_vars=["Semana"],
                value_vars=["Socializadas", "Diligenciadas", "Levantadas"],
                var_name="Actividad",
                value_name="Empresas",
            )

            totals = st.columns(3)
            totals[0].metric("Socializaciones en el periodo", f"{int(activity_view['Socializadas'].sum()):,}")
            totals[1].metric("Diligenciamientos en el periodo", f"{int(activity_view['Diligenciadas'].sum()):,}")
            totals[2].metric("Levantamientos en el periodo", f"{int(activity_view['Levantadas'].sum()):,}")

            activity_figure = px.line(
                activity_long,
                x="Semana",
                y="Empresas",
                color="Actividad",
                markers=True,
                category_orders={"Semana": activity_order},
                color_discrete_map={
                    "Socializadas": "#008FA8",
                    "Diligenciadas": "#ED7D31",
                    "Levantadas": "#548235",
                },
            )
            activity_figure.update_layout(
                height=440,
                xaxis_title="Semana calendario (lunes a domingo)",
                yaxis_title="Empresas",
                legend_title_text="Actividad",
                margin=dict(l=20, r=20, t=20, b=90),
            )
            activity_figure.update_xaxes(tickangle=-45, categoryorder="array", categoryarray=activity_order)
            st.plotly_chart(
                activity_figure,
                use_container_width=True,
                key=f"activity_weekly_{activity_choice}",
            )
            st.dataframe(
                activity_view,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Inicio semana": st.column_config.DateColumn("Inicio semana", format="DD/MM/YYYY"),
                    "Fin semana": st.column_config.DateColumn("Fin semana", format="DD/MM/YYYY"),
                },
            )

with tabs[4]:
    st.subheader("Seguimiento de la actividad por encuestador/a")
    st.markdown(
        "<div class='method-note'>Los conteos corresponden a la fecha en que ocurrió cada evento. "
        "La atribución se realiza con el encuestador registrado actualmente para cada empresa. "
        "Utilice este análisis para seguimiento operativo, considerando diferencias de cargas, "
        "complejidad, ubicación y modalidad de levantamiento.</div>",
        unsafe_allow_html=True,
    )

    person_zones = sorted_options(filtered, "zonal")
    person_zone = st.selectbox(
        "Coordinación Zonal",
        ["Total filtrado", *person_zones],
        key="interviewer_zone",
    )
    if person_zone == "Total filtrado":
        person_frame = filtered.copy()
    else:
        person_frame = filtered.loc[filtered["zonal"].eq(person_zone)].copy()

    summary_people = interviewer_totals(person_frame, cutoff)
    st.markdown("#### Matriz comparativa del periodo")
    st.dataframe(
        summary_people,
        hide_index=True,
        use_container_width=True,
        column_config={
            "% D/S": st.column_config.ProgressColumn(
                "% diligenciadas / socializadas", min_value=0, max_value=1, format="percent"
            ),
            "% L/D": st.column_config.ProgressColumn(
                "% levantadas / diligenciadas", min_value=0, max_value=1, format="percent"
            ),
        },
    )

    available_people = summary_people["Encuestador/a"].astype(str).tolist()
    if not available_people:
        st.info("No existen encuestadores para los filtros seleccionados.")
    else:
        c_person, c_period = st.columns([2, 1])
        selected_person = c_person.selectbox(
            "Encuestador/a para visualizar",
            available_people,
            key="selected_interviewer",
        )
        granularity = c_period.radio(
            "Periodicidad",
            ["Semanal", "Diaria"],
            horizontal=True,
            key="interviewer_granularity",
        )

        person_activity = interviewer_activity_summary(person_frame, cutoff, granularity)
        person_view = person_activity.loc[
            person_activity["Encuestador/a"].eq(selected_person)
        ].sort_values("Inicio periodo").reset_index(drop=True)

        if person_view.empty:
            st.info("El encuestador seleccionado no registra fechas operativas en el periodo.")
        else:
            person_cards = st.columns(4)
            assigned = int(
                person_frame.loc[person_frame["encuestador"].astype(str).eq(selected_person)].shape[0]
            )
            person_cards[0].metric("Empresas asignadas", f"{assigned:,}")
            person_cards[1].metric("Socializadas", f"{int(person_view['Socializadas'].sum()):,}")
            person_cards[2].metric("Diligenciadas", f"{int(person_view['Diligenciadas'].sum()):,}")
            person_cards[3].metric("Levantadas", f"{int(person_view['Levantadas'].sum()):,}")

            person_order = person_view["Periodo"].tolist()
            person_long = person_view.melt(
                id_vars=["Periodo"],
                value_vars=["Socializadas", "Diligenciadas", "Levantadas"],
                var_name="Actividad",
                value_name="Empresas",
            )
            person_figure = px.line(
                person_long,
                x="Periodo",
                y="Empresas",
                color="Actividad",
                markers=True,
                category_orders={"Periodo": person_order},
                color_discrete_map={
                    "Socializadas": "#008FA8",
                    "Diligenciadas": "#ED7D31",
                    "Levantadas": "#548235",
                },
            )
            person_figure.update_layout(
                height=440,
                xaxis_title=(
                    "Semana calendario (lunes a domingo)"
                    if granularity == "Semanal"
                    else "Día calendario"
                ),
                yaxis_title="Empresas",
                legend_title_text="Actividad",
                margin=dict(l=20, r=20, t=25, b=90),
            )
            person_figure.update_xaxes(
                tickangle=-45,
                categoryorder="array",
                categoryarray=person_order,
            )
            st.plotly_chart(
                person_figure,
                use_container_width=True,
                key=f"interviewer_chart_{person_zone}_{selected_person}_{granularity}",
            )

            matrix_columns = [
                "Inicio periodo",
                "Fin periodo",
                "Periodo",
                "Socializadas",
                "Diligenciadas",
                "Levantadas",
            ]
            st.markdown(f"#### Matriz {granularity.lower()} de {selected_person}")
            st.dataframe(
                person_view[matrix_columns],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Inicio periodo": st.column_config.DateColumn("Inicio", format="DD/MM/YYYY"),
                    "Fin periodo": st.column_config.DateColumn("Fin", format="DD/MM/YYYY"),
                },
            )
            person_csv = person_view[matrix_columns].to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Descargar matriz del encuestador",
                data=person_csv,
                file_name=f"actividad_{selected_person}_{granularity.lower()}.csv",
                mime="text/csv",
                key="download_interviewer_matrix",
            )

with tabs[5]:
    st.subheader("Controles de calidad de las fechas")
    checks = quality_summary(filtered, cutoff)
    total_issues = int(checks["Casos"].sum())
    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Incidencias detectadas", f"{total_issues:,}")
        st.dataframe(checks, hide_index=True, use_container_width=True)
    with c2:
        st.vega_lite_chart(
            checks,
            {
                "mark": {"type": "bar", "color": "#C65911", "cornerRadiusEnd": 4},
                "encoding": {
                    "y": {"field": "Control", "type": "nominal", "sort": "-x"},
                    "x": {"field": "Casos", "type": "quantitative"},
                    "tooltip": [
                        {"field": "Control", "type": "nominal"},
                        {"field": "Casos", "type": "quantitative", "format": ",.0f"},
                    ],
                },
                "height": 330,
            },
            use_container_width=True,
        )
    problem_cases = quality_case_table(filtered, cutoff)
    with st.expander("Ver casos que requieren corrección"):
        st.dataframe(problem_cases, hide_index=True, use_container_width=True)

with tabs[6]:
    st.subheader("Cómo utilizar el tablero durante la mesa")
    st.markdown(
        f"""
        1. **Acordar la fecha de corte y los umbrales.** Los valores iniciales son {threshold_1}, {threshold_2} y {threshold_3} días.
        2. **Comparar coordinaciones sin convertirlo en un ranking de personas.** Revisar diferencias de carga, ubicación, tipo de informante, seguimiento y funcionamiento del SIPE.
        3. **Examinar los casos extremos.** Clasificar su causa y registrar la acción que habría evitado o reducido la brecha.
        4. **Distinguir tiempos observados y casos abiertos.** Una empresa pendiente continúa acumulando días hasta la fecha de corte.
        5. **Definir reglas comunes.** Frecuencia de seguimiento, tiempo máximo por fase, responsable de escalar y evidencia mínima.

        **Preguntas para la discusión**

        - ¿Cuántos días deberían transcurrir como máximo entre socialización y primer diligenciamiento?
        - ¿Cada cuánto debe realizarse seguimiento a una empresa socializada que no inicia el proceso?
        - ¿Qué causas dependen del informante y cuáles pueden corregirse internamente?
        - ¿En qué momento debe intervenir el responsable zonal o Planta Central?
        - ¿Qué alerta debería producir una acción automática en el SIPE?

        **Producto esperado:** protocolo de seguimiento y tablero de alertas tempranas, con tiempos máximos, acciones, responsables y criterios de escalamiento.
        """
    )

st.divider()
st.caption(
    "Uso interno ENESEM · Los resultados dependen de la fecha de corte y de la calidad de las fechas registradas. "
    "Revise las inconsistencias antes de presentar conclusiones definitivas."
)
