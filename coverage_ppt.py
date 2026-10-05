    _add_text(
        separator,
        f"Reporte de cobertura\ncon corte al {date_text}",
        3.05, 2.65, 7.45, 1.55,
        size=27, color=WHITE, bold=True, align=PP_ALIGN.CENTER,
    )

    slide = presentation.slides.add_slide(blank)
    _background(slide, _asset(assets_dir, "content_enesem.png"))
    _add_content_title(slide, "Cobertura de socialización y diligenciamiento")
    left = report.socialization[[
        "Coordinación Zonal", "Muestra original", "Enviadas", "Recibidas", "Muestra actual", "% muestra",
    ]]
    right = report.socialization[[
        "Coordinación Zonal", "Socializadas", "% socialización", "Diligenciadas", "% diligenciamiento", "Por socializar",
    ]]
    _add_table(
        slide, left, 0.52, 1.18, 6.15, 2.10,
        percent_columns=["% muestra"], first_column_width=1.35,
        title="Distribución de la muestra",
    )
    _add_table(
        slide, right, 6.82, 1.18, 6.0, 2.10,
        percent_columns=["% socialización", "% diligenciamiento"], first_column_width=1.35,
        title="Avance de socialización y diligenciamiento",
    )
    _add_table(
        slide, report.transfers, 0.52, 3.72, 12.26, 2.55,
        first_column_width=2.25, title="Empresas que informan en otra Coordinación Zonal",
    )
    _add_text(
        slide,
        f"Semana operativa seleccionada: {report.selected_week}",
        0.55, 6.98, 4.8, 0.22, size=8, color=SLATE,
    )

    for title, coverage, indicators, chart, executed, effective in (
        (
            "Cobertura de levantamiento", report.field_coverage, report.field_indicators,
            report.field_chart, "Ejecutadas", "Efectivas",
        ),
        (
            "Cobertura de crítica", report.critique_coverage, report.critique_indicators,
            report.critique_chart, "Criticadas", "Efectivas criticadas",
        ),
    ):
        phase_slide = presentation.slides.add_slide(blank)
        _background(phase_slide, _asset(assets_dir, "content_enesem.png"))
        _add_content_title(phase_slide, title)
        coverage_display = _coverage_table_for_slide(coverage, executed, effective)
        _add_table(
            phase_slide, coverage_display, 0.52, 1.22, 7.75, 1.72,
            percent_columns=["% planif. nac.", "% ejec. nac.", "% efect. nac."],
            first_column_width=1.55, title="Cobertura acumulada por Coordinación Zonal",
            header_size=6.5, body_size=6.9,
        )
        _add_table(
            phase_slide, indicators, 8.45, 1.22, 4.35, 1.72,
            percent_columns=list(indicators.columns[1:]), first_column_width=1.25,
            title="Indicadores de cobertura", header_size=6.2, body_size=6.9,
        )
        executed_chart_column = executed + " acumuladas"
        chart_title = (
            "Cobertura acumulada de levantamiento nacional"
            if executed == "Ejecutadas"
            else "Cobertura acumulada de crítica nacional"
        )
        _add_coverage_chart(
            phase_slide, chart, 0.72, 3.20, 11.95, 3.45,
            executed_chart_column, chart_title,
        )
        _add_text(
            phase_slide,
            f"Planificación acumulada y resultados observados hasta la semana {report.selected_week}.",
            0.72, 6.76, 8.4, 0.25, size=8.5, color=SLATE,
        )

    progress_slide = presentation.slides.add_slide(blank)
    _background(progress_slide, _asset(assets_dir, "content_enesem.png"))
    _add_content_title(progress_slide, "Estado de avance de cobertura")
    status_display = report.progress_status.copy()
    if int(status_display["Sin registro de avance"].sum()) == 0:
        status_display = status_display.drop(columns="Sin registro de avance")
    _add_table(
        progress_slide, status_display, 0.75, 1.42, 5.75, 3.55,
        first_column_width=1.35, title="Estado de llenado",
    )
    _add_table(
        progress_slide, report.progress_bands, 6.85, 1.42, 5.70, 3.55,
        first_column_width=1.35, title="Avance de las empresas en proceso",
    )

    novelty_display = _novelty_display(report.novelties, report.zones)
    page_size = 17
    pages = max(1, int(np.ceil(len(novelty_display) / page_size)))
    for page in range(pages):
        novelty_slide = presentation.slides.add_slide(blank)
        _background(novelty_slide, _asset(assets_dir, "content_enesem.png"))
        page_title = "Novedades" if page == 0 else "Novedades (continuación)"
        _add_content_title(novelty_slide, page_title)
        part = novelty_display.iloc[page * page_size:(page + 1) * page_size].copy()
        _add_novelty_table(novelty_slide, part, 0.65, 1.22, 12.0, 5.65)
        _add_text(
            novelty_slide,
            ""
            "",
            0.70, 6.98, 11.5, 0.23, size=8.2, color=SLATE,
        )

    closing = presentation.slides.add_slide(blank)
    _background(closing, _asset(assets_dir, "closing_enesem.png"))
    _add_text(closing, "Gracias", 7.25, 2.55, 3.85, 0.75, size=34, color=NAVY, bold=True, align=PP_ALIGN.CENTER)
    _add_text(
        closing,
        "Encuesta Estructural Empresarial",
        6.72, 3.38, 4.90, 0.42, size=17, color=PRIMARY, bold=True, align=PP_ALIGN.CENTER,
    )

    output = BytesIO()
    presentation.save(output)
    return output.getvalue()
