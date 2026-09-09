from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Iterable
import re
import unicodedata

import numpy as np
import pandas as pd


# La aplicación carga los identificadores necesarios para gestionar casos de
# uso interno, pero omite deliberadamente ventas y demás variables económicas.
COLUMN_ALIASES: dict[str, list[str]] = {
    "order": ["Nro. orden", "Nro orden", "orden", "numero de orden"],
    "company_id": [
        "Identificador Empresa",
        "Identificador de empresa",
        "inec_identificador_empresa",
        "id empresa",
    ],
    "ruc": ["RUC", "numero ruc", "número ruc"],
    "legal_name": ["Razón social", "Razon social", "razon_social"],
    "trade_name": ["Nombre Comercial", "Nombre comercial", "nombre_comercial"],
    "zone_initial": ["COORD. Z", "COORD Z", "coordinacion zonal"],
    "zone_final": ["CZ_FINAL", "CZ FINAL", "coordinacion zonal final"],
    "province": ["DESC. PROV.", "DESC PROV", "provincia"],
    "size": ["TAMAÑO", "TAMANO", "tamano empresa"],
    "sector": ["DESC. CIIU_1", "DESC CIIU 1", "sector economico", "SE"],
    "interviewer": ["ENCUESTADOR", "encuestador/a"],
    "collection_mode": ["MODO_LEVANTAMIENTO", "MODO LEVANTAMIENTO"],
    "socialized_flag": ["SOCIALIZACIÓN", "SOCIALIZACION"],
    "diligenced_flag": ["DILIGENCIADA", "DILIGENCIAMIENTO"],
    "lifted_flag": ["LEVANTADA"],
    "criticized_flag": ["CRITICADA"],
    "reviewed_flag": ["REVISADA"],
    "socialization_date": ["FCH_SOCIALIZACIÓN", "FCH SOCIALIZACION", "FECHA SOCIALIZACION"],
    "diligence_date": ["FCH_DILIGENCIAMIENTO", "FCH DILIGENCIAMIENTO", "FECHA DILIGENCIAMIENTO"],
    "lift_date": ["FCH_LEVANTAMIENTO", "FCH LEVANTAMIENTO", "FECHA LEVANTAMIENTO"],
    "criticism_date": ["FCH_CRÍTICA", "FCH CRITICA", "FECHA CRITICA"],
    "review_date": ["FCH_REVISIÓN", "FCH REVISION", "FECHA REVISION"],
}

CAUSE_OPTIONS = [
    "Por determinar",
    "Informante",
    "Encuestador/a",
    "Directorio",
    "SIPE",
    "Falta de seguimiento",
    "Gestión institucional",
    "Cita reprogramada",
    "Seguridad o movilización",
    "Otro motivo documentado",
]

ALERT_ORDER = ["En plazo", "Atención", "Alta", "Crítica", "Sin dato"]

MONTHS_ES = {
    1: "ene",
    2: "feb",
    3: "mar",
    4: "abr",
    5: "may",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "sep",
    10: "oct",
    11: "nov",
    12: "dic",
}


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def resolve_columns(columns: Iterable[object]) -> dict[str, str]:
    normalized = {normalize_name(col): str(col) for col in columns}
    resolved: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            match = normalized.get(normalize_name(alias))
            if match is not None:
                resolved[canonical] = match
                break

    missing = [
        label
        for label in ("socialization_date", "diligence_date")
        if label not in resolved
    ]
    if "zone_final" not in resolved and "zone_initial" not in resolved:
        missing.append("zone_final o zone_initial")
    if missing:
        raise ValueError(
            "No se encontraron las variables indispensables: " + ", ".join(missing)
        )
    return resolved


def _rewind(source: object) -> None:
    if hasattr(source, "seek"):
        source.seek(0)


def _read_minimum_columns(source: str | Path | BinaryIO, filename: str | None = None) -> tuple[pd.DataFrame, dict[str, str]]:
    suffix = Path(filename or str(source)).suffix.lower()
    if suffix == ".csv":
        _rewind(source)
        header = pd.read_csv(source, nrows=0)
        resolved = resolve_columns(header.columns)
        _rewind(source)
        frame = pd.read_csv(source, usecols=sorted(set(resolved.values())))
        return frame, resolved

    _rewind(source)
    header = pd.read_excel(source, sheet_name=0, nrows=0)
    resolved = resolve_columns(header.columns)
    _rewind(source)
    frame = pd.read_excel(source, sheet_name=0, usecols=sorted(set(resolved.values())))
    return frame, resolved


def load_directory(source: str | Path | bytes | BinaryIO, filename: str | None = None) -> pd.DataFrame:
    if isinstance(source, bytes):
        source = BytesIO(source)
    raw, resolved = _read_minimum_columns(source, filename=filename)
    return prepare_directory(raw, resolved)


def _series(raw: pd.DataFrame, resolved: dict[str, str], key: str, default: object = pd.NA) -> pd.Series:
    original = resolved.get(key)
    if original is None:
        return pd.Series(default, index=raw.index, dtype="object")
    return raw[original]


def _clean_text(series: pd.Series, default: str = "Sin dato") -> pd.Series:
    values = series.astype("string").str.strip()
    return values.mask(values.isna() | values.eq(""), default)


def _clean_identifier(series: pd.Series, default: str = "Sin dato") -> pd.Series:
    def format_value(value: object) -> str:
        if pd.isna(value):
            return default
        if isinstance(value, (int, np.integer)):
            return str(int(value))
        if isinstance(value, (float, np.floating)) and float(value).is_integer():
            return str(int(value))
        text = str(value).strip()
        if not text:
            return default
        return re.sub(r"\.0$", "", text)

    return series.map(format_value).astype("string")


def _flag(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").eq(1)


def prepare_directory(raw: pd.DataFrame, resolved: dict[str, str]) -> pd.DataFrame:
    out = pd.DataFrame(index=raw.index)
    row_number = pd.to_numeric(_series(raw, resolved, "order"), errors="coerce")
    fallback = pd.Series(np.arange(1, len(raw) + 1), index=raw.index, dtype="int64")
    row_number = row_number.where(row_number.notna(), fallback).round().astype("int64")
    width = max(4, len(str(int(row_number.max()))) if len(row_number) else 4)
    out["caso"] = "Caso " + row_number.astype(str).str.zfill(width)

    out["identificador_empresa"] = _clean_identifier(_series(raw, resolved, "company_id"))
    out["ruc"] = _clean_identifier(_series(raw, resolved, "ruc"))
    out["razon_social"] = _clean_text(_series(raw, resolved, "legal_name"))
    out["nombre_comercial"] = _clean_text(_series(raw, resolved, "trade_name"))

    out["zonal_inicial"] = _clean_text(_series(raw, resolved, "zone_initial"))
    out["zonal_final"] = _clean_text(_series(raw, resolved, "zone_final"))
    out["zonal"] = out["zonal_final"].where(out["zonal_final"].ne("Sin dato"), out["zonal_inicial"])
    out["provincia"] = _clean_text(_series(raw, resolved, "province"))
    out["tamano"] = _clean_text(_series(raw, resolved, "size"))
    out["sector"] = _clean_text(_series(raw, resolved, "sector"))
    out["encuestador"] = _clean_text(_series(raw, resolved, "interviewer"))

    mode = pd.to_numeric(_series(raw, resolved, "collection_mode"), errors="coerce")
    out["modo_levantamiento"] = mode.map({1: "Presencial", 2: "Telemático"}).fillna("Sin dato")

    date_map = {
        "fecha_socializacion": "socialization_date",
        "fecha_diligenciamiento": "diligence_date",
        "fecha_levantamiento": "lift_date",
        "fecha_critica": "criticism_date",
        "fecha_revision": "review_date",
    }
    for target, key in date_map.items():
        out[target] = pd.to_datetime(_series(raw, resolved, key), errors="coerce", dayfirst=True)

    flag_map = {
        "marca_socializada": "socialized_flag",
        "marca_diligenciada": "diligenced_flag",
        "marca_levantada": "lifted_flag",
        "marca_criticada": "criticized_flag",
        "marca_revisada": "reviewed_flag",
    }
    for target, key in flag_map.items():
        out[target] = _flag(_series(raw, resolved, key))

    out["socializada"] = out["marca_socializada"] | out["fecha_socializacion"].notna()
    out["diligenciada"] = out["marca_diligenciada"] | out["fecha_diligenciamiento"].notna()
    out["levantada"] = out["marca_levantada"] | out["fecha_levantamiento"].notna()
    out["criticada"] = out["marca_criticada"] | out["fecha_critica"].notna()
    out["revisada"] = out["marca_revisada"] | out["fecha_revision"].notna()

    has_company_id = out["identificador_empresa"].ne("Sin dato")
    out["duplicado_caso"] = has_company_id & out["identificador_empresa"].duplicated(keep=False)
    return out.reset_index(drop=True)


def infer_cutoff(frame: pd.DataFrame) -> pd.Timestamp:
    columns = [
        "fecha_socializacion",
        "fecha_diligenciamiento",
        "fecha_levantamiento",
        "fecha_critica",
        "fecha_revision",
    ]
    maxima = [frame[col].max() for col in columns if col in frame and frame[col].notna().any()]
    if not maxima:
        return pd.Timestamp.today().normalize()
    return pd.Timestamp(max(maxima)).normalize()


def _tracked_gap(start: pd.Series, end: pd.Series, cutoff: pd.Timestamp) -> tuple[pd.Series, pd.Series, pd.Series]:
    has_start = start.notna()
    has_end = end.notna()
    inconsistent = has_start & has_end & end.lt(start)
    completed = has_start & has_end & ~inconsistent
    pending = has_start & ~has_end
    days = pd.Series(np.nan, index=start.index, dtype="float64")
    days.loc[completed] = (end.loc[completed] - start.loc[completed]).dt.days.astype(float)
    days.loc[pending] = (cutoff - start.loc[pending]).dt.days.astype(float)
    days = days.mask(days.lt(0))
    return days, completed, pending


def add_gap_metrics(frame: pd.DataFrame, cutoff: object, thresholds: tuple[int, int, int] = (15, 30, 60)) -> pd.DataFrame:
    low, medium, high = thresholds
    if not (0 <= low < medium < high):
        raise ValueError("Los umbrales deben ser crecientes: inicial < alto < crítico.")
    cutoff_ts = pd.Timestamp(cutoff).normalize()
    out = frame.copy()

    sd_days, sd_completed, sd_pending = _tracked_gap(
        out["fecha_socializacion"], out["fecha_diligenciamiento"], cutoff_ts
    )
    out["dias_sd"] = sd_days
    out["sd_completada"] = sd_completed
    out["sd_pendiente"] = sd_pending
    out["sd_inconsistente"] = (
        out["fecha_socializacion"].notna()
        & out["fecha_diligenciamiento"].notna()
        & out["fecha_diligenciamiento"].lt(out["fecha_socializacion"])
    )
    out["estado_sd"] = np.select(
        [out["sd_inconsistente"], sd_completed, sd_pending],
        ["Inconsistencia de fechas", "Diligenciada", "Pendiente de diligenciamiento"],
        default="Sin fecha de socialización",
    )
    out["alerta_sd"] = np.select(
        [
            sd_days.le(low),
            sd_days.gt(low) & sd_days.le(medium),
            sd_days.gt(medium) & sd_days.le(high),
            sd_days.gt(high),
        ],
        ["En plazo", "Atención", "Alta", "Crítica"],
        default="Sin dato",
    )

    dl_days, dl_completed, dl_pending = _tracked_gap(
        out["fecha_diligenciamiento"], out["fecha_levantamiento"], cutoff_ts
    )
    out["dias_dl"] = dl_days
    out["dl_completada"] = dl_completed
    out["dl_pendiente"] = dl_pending

    sl_days, sl_completed, sl_pending = _tracked_gap(
        out["fecha_socializacion"], out["fecha_levantamiento"], cutoff_ts
    )
    out["dias_sl"] = sl_days
    out["sl_completada"] = sl_completed
    out["sl_pendiente"] = sl_pending

    phase = pd.Series("Sin socializar", index=out.index, dtype="string")
    phase = phase.mask(out["socializada"], "Socializada")
    phase = phase.mask(out["diligenciada"], "Diligenciada")
    phase = phase.mask(out["levantada"], "Levantada")
    phase = phase.mask(out["criticada"], "Criticada")
    phase = phase.mask(out["revisada"], "Revisada")
    out["fase_actual"] = phase
    out["fecha_corte"] = cutoff_ts
    return out


def filter_directory(
    frame: pd.DataFrame,
    zones: list[str] | None = None,
    provinces: list[str] | None = None,
    sizes: list[str] | None = None,
    interviewers: list[str] | None = None,
    sectors: list[str] | None = None,
    company_query: str | None = None,
    scope: str = "Todas",
) -> pd.DataFrame:
    mask = pd.Series(True, index=frame.index)
    for column, selected in [
        ("zonal", zones),
        ("provincia", provinces),
        ("tamano", sizes),
        ("encuestador", interviewers),
        ("sector", sectors),
    ]:
        if selected:
            mask &= frame[column].isin(selected)

    query = normalize_name(company_query or "")
    if query:
        company_match = pd.Series(False, index=frame.index)
        for column in ["identificador_empresa", "ruc", "razon_social", "nombre_comercial"]:
            normalized_values = frame[column].fillna("").map(normalize_name)
            company_match |= normalized_values.str.contains(re.escape(query), regex=True)
        mask &= company_match

    scope_masks = {
        "Pendientes de diligenciamiento": frame["sd_pendiente"],
        "Diligenciadas": frame["sd_completada"],
        "Con inconsistencia de fechas": frame["sd_inconsistente"],
    }
    if scope in scope_masks:
        mask &= scope_masks[scope]
    return frame.loc[mask].copy()


def zonal_summary(frame: pd.DataFrame, thresholds: tuple[int, int, int]) -> pd.DataFrame:
    low, medium, high = thresholds
    rows: list[dict[str, object]] = []
    for zone, group in frame.groupby("zonal", dropna=False, sort=True):
        completed_days = group.loc[group["sd_completada"], "dias_sd"].dropna()
        tracked = group["dias_sd"].dropna()
        rows.append(
            {
                "Coordinación Zonal": zone,
                "Empresas": int(len(group)),
                "Diligenciadas": int(group["sd_completada"].sum()),
                "Pendientes": int(group["sd_pendiente"].sum()),
                "Inconsistencias": int(group["sd_inconsistente"].sum()),
                "% diligenciadas": float(group["sd_completada"].mean()) if len(group) else 0.0,
                "Mediana S→D": float(completed_days.median()) if len(completed_days) else np.nan,
                "P90 S→D": float(completed_days.quantile(0.90)) if len(completed_days) else np.nan,
                f">{low} días": int(tracked.gt(low).sum()),
                f">{medium} días": int(tracked.gt(medium).sum()),
                f">{high} días": int(tracked.gt(high).sum()),
            }
        )
    return pd.DataFrame(rows)


def _week_start(series: pd.Series) -> pd.Series:
    dates = pd.to_datetime(series, errors="coerce").dt.normalize()
    return dates - pd.to_timedelta(dates.dt.dayofweek, unit="D")


def _week_label(start: pd.Timestamp) -> str:
    start = pd.Timestamp(start).normalize()
    end = start + pd.Timedelta(days=6)
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {MONTHS_ES[start.month]} {start.year}"
    if start.year == end.year:
        return (
            f"{start.day} {MONTHS_ES[start.month]}–"
            f"{end.day} {MONTHS_ES[end.month]} {start.year}"
        )
    return (
        f"{start.day} {MONTHS_ES[start.month]} {start.year}–"
        f"{end.day} {MONTHS_ES[end.month]} {end.year}"
    )


def weekly_summary(frame: pd.DataFrame, first_threshold: int, cutoff: object) -> pd.DataFrame:
    """Resume cohortes según la semana lunes-domingo de socialización."""
    cutoff_ts = pd.Timestamp(cutoff).normalize()
    eligible = frame.loc[
        frame["fecha_socializacion"].notna() & frame["fecha_socializacion"].le(cutoff_ts)
    ].copy()
    if eligible.empty:
        return pd.DataFrame()

    eligible["semana_inicio"] = _week_start(eligible["fecha_socializacion"])
    first_week = eligible["semana_inicio"].min()
    last_week = eligible["semana_inicio"].max()
    weeks = pd.date_range(first_week, last_week, freq="7D")
    zones = sorted(eligible["zonal"].dropna().astype(str).unique())

    rows: list[dict[str, object]] = []
    for week in weeks:
        week_end = week + pd.Timedelta(days=6)
        for zone in zones:
            group = eligible.loc[
                eligible["semana_inicio"].eq(week) & eligible["zonal"].astype(str).eq(zone)
            ]
            socialized = int(len(group))
            completed = group.loc[group["sd_completada"], "dias_sd"].dropna()
            diligenced = int(group["sd_completada"].sum()) if socialized else 0
            pending = int(group["sd_pendiente"].sum()) if socialized else 0
            timely = int(completed.le(first_threshold).sum()) if socialized else 0
            latest_socialization = group["fecha_socializacion"].max() if socialized else pd.NaT
            evaluable = bool(
                socialized
                and pd.notna(latest_socialization)
                and cutoff_ts >= pd.Timestamp(latest_socialization).normalize() + pd.Timedelta(days=first_threshold)
            )

            if not socialized:
                cohort_status = "Sin socializaciones"
            elif evaluable:
                cohort_status = "Evaluable"
            else:
                cohort_status = "En observación"

            rows.append(
                {
                    "Inicio semana": week,
                    "Fin semana": week_end,
                    "Semana": _week_label(week),
                    "Coordinación Zonal": zone,
                    "Estado cohorte": cohort_status,
                    "Socializadas": socialized,
                    "Diligenciadas": diligenced,
                    "Pendientes": pending,
                    "% diligenciadas": diligenced / socialized if socialized else np.nan,
                    "Mediana S→D": float(completed.median()) if len(completed) else np.nan,
                    f"Diligenciadas ≤ {first_threshold} días": timely,
                    f"% dentro de {first_threshold} días": timely / socialized if evaluable else np.nan,
                }
            )
    return pd.DataFrame(rows)


def activity_weekly_summary(frame: pd.DataFrame, cutoff: object) -> pd.DataFrame:
    """Cuenta eventos por la semana calendario lunes-domingo en la que ocurrieron."""
    cutoff_ts = pd.Timestamp(cutoff).normalize()
    event_columns = {
        "Socializadas": "fecha_socializacion",
        "Diligenciadas": "fecha_diligenciamiento",
        "Levantadas": "fecha_levantamiento",
    }
    valid_dates = []
    for column in event_columns.values():
        dates = frame.loc[frame[column].notna() & frame[column].le(cutoff_ts), column]
        if not dates.empty:
            valid_dates.extend([dates.min(), dates.max()])
    if not valid_dates:
        return pd.DataFrame()

    first_week = pd.Timestamp(min(valid_dates)).normalize()
    first_week -= pd.Timedelta(days=first_week.dayofweek)
    last_week = pd.Timestamp(max(valid_dates)).normalize()
    last_week -= pd.Timedelta(days=last_week.dayofweek)
    weeks = pd.date_range(first_week, last_week, freq="7D")
    zones = sorted(frame["zonal"].dropna().astype(str).unique())

    rows: list[dict[str, object]] = []
    for week in weeks:
        week_end = week + pd.Timedelta(days=6)
        for zone in zones:
            zone_group = frame.loc[frame["zonal"].astype(str).eq(zone)]
            row: dict[str, object] = {
                "Inicio semana": week,
                "Fin semana": week_end,
                "Semana": _week_label(week),
                "Coordinación Zonal": zone,
            }
            for label, column in event_columns.items():
                row[label] = int(
                    (
                        zone_group[column].between(week, week_end, inclusive="both")
                        & zone_group[column].le(cutoff_ts)
                    ).sum()
                )
            rows.append(row)
    return pd.DataFrame(rows)


def quality_summary(frame: pd.DataFrame, cutoff: object) -> pd.DataFrame:
    cutoff_ts = pd.Timestamp(cutoff).normalize()
    checks = [
        ("Identificador de empresa duplicado", frame["duplicado_caso"]),
        ("Marca de socialización sin fecha", frame["marca_socializada"] & frame["fecha_socializacion"].isna()),
        ("Marca de diligenciamiento sin fecha", frame["marca_diligenciada"] & frame["fecha_diligenciamiento"].isna()),
        ("Marca de levantamiento sin fecha", frame["marca_levantada"] & frame["fecha_levantamiento"].isna()),
        ("Diligenciamiento anterior a socialización", frame["sd_inconsistente"]),
        (
            "Levantamiento anterior a diligenciamiento",
            frame["fecha_diligenciamiento"].notna()
            & frame["fecha_levantamiento"].notna()
            & frame["fecha_levantamiento"].lt(frame["fecha_diligenciamiento"]),
        ),
        ("Coordinación Zonal sin dato", frame["zonal"].eq("Sin dato")),
        (
            "Alguna fecha posterior al corte",
            frame[[
                "fecha_socializacion",
                "fecha_diligenciamiento",
                "fecha_levantamiento",
                "fecha_critica",
                "fecha_revision",
            ]].gt(cutoff_ts).any(axis=1),
        ),
    ]
    return pd.DataFrame(
        [{"Control": label, "Casos": int(mask.fillna(False).sum())} for label, mask in checks]
    )


def quality_case_table(frame: pd.DataFrame, cutoff: object) -> pd.DataFrame:
    cutoff_ts = pd.Timestamp(cutoff).normalize()
    problems: list[pd.Series] = []
    labels: list[str] = []

    def add(label: str, mask: pd.Series) -> None:
        labels.append(label)
        problems.append(mask.fillna(False))

    add("Identificador de empresa duplicado", frame["duplicado_caso"])
    add("Socialización marcada sin fecha", frame["marca_socializada"] & frame["fecha_socializacion"].isna())
    add("Diligenciamiento marcado sin fecha", frame["marca_diligenciada"] & frame["fecha_diligenciamiento"].isna())
    add("Levantamiento marcado sin fecha", frame["marca_levantada"] & frame["fecha_levantamiento"].isna())
    add("Diligenciamiento anterior a socialización", frame["sd_inconsistente"])
    add(
        "Levantamiento anterior a diligenciamiento",
        frame["fecha_diligenciamiento"].notna()
        & frame["fecha_levantamiento"].notna()
        & frame["fecha_levantamiento"].lt(frame["fecha_diligenciamiento"]),
    )
    add(
        "Fecha posterior al corte",
        frame[[
            "fecha_socializacion",
            "fecha_diligenciamiento",
            "fecha_levantamiento",
            "fecha_critica",
            "fecha_revision",
        ]].gt(cutoff_ts).any(axis=1),
    )

    any_problem = pd.concat(problems, axis=1).any(axis=1)
    result = frame.loc[any_problem, [
        "caso",
        "identificador_empresa",
        "ruc",
        "razon_social",
        "nombre_comercial",
        "zonal",
        "fecha_socializacion",
        "fecha_diligenciamiento",
        "fecha_levantamiento",
    ]].copy()
    result["Problema"] = [
        "; ".join(label for label, mask in zip(labels, problems) if bool(mask.loc[idx]))
        for idx in result.index
    ]
    return result.rename(
        columns={
            "caso": "Caso",
            "identificador_empresa": "Identificador empresa",
            "ruc": "RUC",
            "razon_social": "Razón social",
            "nombre_comercial": "Nombre comercial",
            "zonal": "Coordinación Zonal",
            "fecha_socializacion": "Fecha socialización",
            "fecha_diligenciamiento": "Fecha diligenciamiento",
            "fecha_levantamiento": "Fecha levantamiento",
        }
    ).reset_index(drop=True)


def company_case_table(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "caso",
        "identificador_empresa",
        "ruc",
        "razon_social",
        "nombre_comercial",
        "zonal",
        "provincia",
        "encuestador",
        "fase_actual",
        "fecha_socializacion",
        "fecha_diligenciamiento",
        "dias_sd",
        "estado_sd",
        "alerta_sd",
    ]
    result = frame.loc[:, columns].copy()
    result["dias_sd"] = result["dias_sd"].round().astype("Int64")
    return result.rename(
        columns={
            "caso": "Caso",
            "identificador_empresa": "Identificador empresa",
            "ruc": "RUC",
            "razon_social": "Razón social",
            "nombre_comercial": "Nombre comercial",
            "zonal": "Coordinación Zonal",
            "provincia": "Provincia",
            "encuestador": "Encuestador/a",
            "fase_actual": "Fase actual",
            "fecha_socializacion": "Fecha socialización",
            "fecha_diligenciamiento": "Fecha diligenciamiento",
            "dias_sd": "Días S→D",
            "estado_sd": "Estado S→D",
            "alerta_sd": "Alerta",
        }
    )
