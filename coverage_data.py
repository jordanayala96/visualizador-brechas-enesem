from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Iterable
import re
import unicodedata

import numpy as np
import pandas as pd


EXCLUDED_COMPANY_ID = "99999999999"
ZONE_ORDER = ["LITORAL", "AC CAMPO", "SUR", "CENTRO"]
CHAPTER_COLUMNS = [
    "A", "B", "C", "1", "1.1", "2", "2.2 - 2.4", "2.5", "3", "4",
    "5.1 - 5.2", "5.3 - 5.9", "6", "7", "8", "9", "10.1 - 10.2",
    "10.3", "11", "12", "13", "I",
]


DIRECTORY_ALIASES: dict[str, list[str]] = {
    "company_id": ["Identificador Empresa", "Identificador de empresa", "id_empresa"],
    "zone_initial": ["COORD. Z", "COORD Z", "Coordinación Zonal", "Coordinacion Zonal"],
    "zone_final": ["CZ_FINAL", "CZ FINAL", "Coordinación Zonal Final"],
    "socialized": ["SOCIALIZACIÓN", "SOCIALIZACION"],
    "diligenced": ["DILIGENCIADA", "DILIGENCIAMIENTO"],
    "lifted": ["LEVANTADA"],
    "criticized": ["CRITICADA"],
    "effective_field": ["EFECT_CAMPO", "EFECT CAMPO"],
    "effective_crit": ["EFECT_CRIT", "EFECT CRIT"],
    "novelty": ["DESGLO_EFECT", "DESGLO EFECT"],
    "week_field": ["COB_CAMP", "COB CAMP", "COB/CAMP", "COB. CAMP"],
    "week_crit": ["COB/CRIT", "COB_CRIT", "COB CRIT", "COB. CRIT"],
    "socialization_date": ["FCH_SOCIALIZACIÓN", "FCH_SOCIALIZACION", "FECHA SOCIALIZACION"],
    "lift_date": ["FCH_LEVANTAMIENTO", "FECHA LEVANTAMIENTO"],
    "crit_date": ["FCH_CRÍTICA", "FCH_CRITICA", "FECHA CRITICA"],
}

PROGRESS_ALIASES: dict[str, list[str]] = {
    "company_id": ["Identificador Empresa", "Identificador de empresa", "id_empresa"],
}


@dataclass
class ReportData:
    directory: pd.DataFrame
    progress: pd.DataFrame
    planning: pd.DataFrame
    zones: list[str]
    selected_week: int
    cutoff: pd.Timestamp
    operation_start: pd.Timestamp
    socialization: pd.DataFrame
    transfers: pd.DataFrame
    field_coverage: pd.DataFrame
    field_indicators: pd.DataFrame
    field_chart: pd.DataFrame
    critique_coverage: pd.DataFrame
    critique_indicators: pd.DataFrame
    critique_chart: pd.DataFrame
    progress_status: pd.DataFrame
    progress_bands: pd.DataFrame
    novelties: pd.DataFrame
    warnings: list[str]
    controls: dict[str, int | str]


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def normalize_identifier(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    return re.sub(r"\.0$", "", str(value).strip())


def normalize_zone(value: object) -> str:
    if pd.isna(value):
        return "SIN DATO"
    key = normalize_name(value)
    mapping = {
        "litoral": "LITORAL",
        "ac campo": "AC CAMPO",
        "administracion central": "AC CAMPO",
        "administracion central campo": "AC CAMPO",
        "sur": "SUR",
        "centro": "CENTRO",
    }
    if not key:
        return "SIN DATO"
    return mapping.get(key, str(value).strip().upper())


def resolve_columns(columns: Iterable[object], aliases: dict[str, list[str]]) -> dict[str, str]:
    normalized = {normalize_name(column): str(column) for column in columns}
    resolved: dict[str, str] = {}
    for canonical, options in aliases.items():
        for option in options:
            if normalize_name(option) in normalized:
                resolved[canonical] = normalized[normalize_name(option)]
                break
    return resolved


def _read_frame(
    source: str | Path | bytes | BinaryIO,
    filename: str | None = None,
    sheet_name: str | int = 0,
) -> pd.DataFrame:
    if isinstance(source, bytes):
        source = BytesIO(source)
    suffix = Path(filename or str(source)).suffix.lower()
    if suffix in {".csv", ".txt", ".tsv"}:
        separator = "," if suffix == ".csv" else "\t"
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "utf-16", "latin-1"):
            try:
                if hasattr(source, "seek"):
                    source.seek(0)
                return pd.read_csv(source, sep=separator, encoding=encoding, low_memory=False)
            except UnicodeDecodeError as exc:
                last_error = exc
        raise ValueError("No fue posible identificar la codificación del archivo.") from last_error
    if hasattr(source, "seek"):
        source.seek(0)
    return pd.read_excel(source, sheet_name=sheet_name)


def _series(frame: pd.DataFrame, resolved: dict[str, str], key: str) -> pd.Series:
    column = resolved.get(key)
    if column is None:
        return pd.Series(pd.NA, index=frame.index, dtype="object")
    return frame[column]


def _numeric_flag(series: pd.Series, accepted: tuple[int, ...] = (1,)) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").isin(accepted)


def _week_number(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    missing = numeric.isna()
    if missing.any():
        extracted = series.astype("string").str.extract(r"(?i)(\d+)")[0]
        numeric = numeric.where(~missing, pd.to_numeric(extracted, errors="coerce"))
    return numeric


def load_coverage_directory(
    source: str | Path | bytes | BinaryIO,
    filename: str | None = None,
) -> tuple[pd.DataFrame, list[str], dict[str, int | str]]:
    raw = _read_frame(source, filename=filename)
    resolved = resolve_columns(raw.columns, DIRECTORY_ALIASES)
    required = [
        "company_id", "zone_initial", "zone_final", "socialized", "diligenced",
        "lifted", "criticized", "effective_field", "effective_crit", "novelty",
    ]
    missing = [key for key in required if key not in resolved]
    if missing:
        labels = ", ".join(missing)
        raise ValueError(f"El Directorio no contiene las variables obligatorias: {labels}.")

    out = pd.DataFrame(index=raw.index)
    out["company_id"] = _series(raw, resolved, "company_id").map(normalize_identifier)
    out["zone_initial"] = _series(raw, resolved, "zone_initial").map(normalize_zone)
    out["zone_final"] = _series(raw, resolved, "zone_final").map(normalize_zone)
    out["socialized"] = _numeric_flag(_series(raw, resolved, "socialized"))
    out["diligenced"] = _numeric_flag(_series(raw, resolved, "diligenced"))
    out["lifted"] = _numeric_flag(_series(raw, resolved, "lifted"))
    out["criticized"] = _numeric_flag(_series(raw, resolved, "criticized"))
    out["effective_field"] = _numeric_flag(_series(raw, resolved, "effective_field"))
    out["effective_crit_code"] = pd.to_numeric(
        _series(raw, resolved, "effective_crit"), errors="coerce"
    )
    out["novelty"] = _series(raw, resolved, "novelty").astype("string").str.strip()
    out["week_field"] = _week_number(_series(raw, resolved, "week_field"))
    out["week_crit"] = _week_number(_series(raw, resolved, "week_crit"))
    out["date_socialization"] = pd.to_datetime(
        _series(raw, resolved, "socialization_date"), errors="coerce", dayfirst=True
    )
    out["date_lift"] = pd.to_datetime(
        _series(raw, resolved, "lift_date"), errors="coerce", dayfirst=True
    )
    out["date_crit"] = pd.to_datetime(
        _series(raw, resolved, "crit_date"), errors="coerce", dayfirst=True
    )

    excluded = int(out["company_id"].eq(EXCLUDED_COMPANY_ID).sum())
    blank_ids = int(out["company_id"].eq("").sum())
    out = out.loc[~out["company_id"].eq(EXCLUDED_COMPANY_ID)].copy()
    duplicate_rows = int(out.loc[out["company_id"].ne(""), "company_id"].duplicated(keep=False).sum())
    out["_row"] = np.arange(len(out))
    with_id = out.loc[out["company_id"].ne("")].drop_duplicates("company_id", keep="last")
    without_id = out.loc[out["company_id"].eq("")]
    out = pd.concat([with_id, without_id], ignore_index=True).sort_values("_row").drop(columns="_row")
    out["case_key"] = out["company_id"].where(
        out["company_id"].ne(""),
        "__ROW_" + pd.Series(np.arange(len(out)), index=out.index).astype(str),
    )

    warnings: list[str] = []
    if excluded:
        warnings.append(
            f"Se excluyeron {excluded:,} registros con Identificador Empresa {EXCLUDED_COMPANY_ID}."
        )
    if blank_ids:
        warnings.append(f"El Directorio contiene {blank_ids:,} registros sin identificador de empresa.")
    if duplicate_rows:
        warnings.append(
            f"Se detectaron {duplicate_rows:,} filas pertenecientes a identificadores duplicados. "
            "Para los cálculos se conservó el último registro de cada empresa."
        )
    unknown = sorted(
        set(out["zone_final"].dropna().unique()) - set(ZONE_ORDER) - {"SIN DATO"}
    )
    if unknown:
        warnings.append("Coordinaciones no homologadas: " + ", ".join(unknown) + ".")

    controls: dict[str, int | str] = {
        "rows_loaded": int(len(raw)),
        "companies_used": int(len(out)),
        "excluded_special_id": excluded,
        "blank_ids": blank_ids,
        "duplicate_rows": duplicate_rows,
    }
    return out.reset_index(drop=True), warnings, controls


def load_progress(
    source: str | Path | bytes | BinaryIO,
    filename: str | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    raw = _read_frame(source, filename=filename, sheet_name=0)
    resolved = resolve_columns(raw.columns, PROGRESS_ALIASES)
    if "company_id" not in resolved:
        raise ValueError("El Reporte de avance no contiene la variable Identificador Empresa.")
    missing_chapters = [column for column in CHAPTER_COLUMNS if column not in raw.columns]
    if missing_chapters:
        raise ValueError(
            "El Reporte de avance no contiene los capítulos obligatorios: "
            + ", ".join(missing_chapters)
            + "."
        )
    out = pd.DataFrame(index=raw.index)
    out["company_id"] = raw[resolved["company_id"]].map(normalize_identifier)
    values = raw[CHAPTER_COLUMNS].astype("string").apply(lambda col: col.str.strip().str.upper())
    out["chapters_v"] = values.eq("V").sum(axis=1)
    out["chapters_g"] = values.eq("G").sum(axis=1)
    out["chapters_complete"] = out["chapters_v"] + out["chapters_g"]
    out["progress"] = out["chapters_complete"] / len(CHAPTER_COLUMNS)
    duplicate_rows = int(out.loc[out["company_id"].ne(""), "company_id"].duplicated(keep=False).sum())
    warnings: list[str] = []
    if duplicate_rows:
        warnings.append(
            f"El Reporte de avance contiene {duplicate_rows:,} filas de identificadores duplicados. "
            "Se conservó el último registro."
        )
    out = out.loc[out["company_id"].ne("")].drop_duplicates("company_id", keep="last")
    return out.reset_index(drop=True), warnings


def load_planning(path: str | Path) -> tuple[pd.DataFrame, list[str]]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo fijo de planificación: {path}.")
    rows: list[pd.DataFrame] = []
    warnings: list[str] = []
    for phase, sheet in (("Campo", "Campo"), ("Crítica", "Critica")):
        raw = pd.read_excel(path, sheet_name=sheet)
        first = raw.columns[0]
        frame = raw.copy()
        frame["week"] = frame[first].astype(str).str.extract(r"(?i)sem\s*(\d+)")[0]
        frame["week"] = pd.to_numeric(frame["week"], errors="coerce")
        frame = frame.loc[frame["week"].notna()].copy()
        value_columns = [column for column in frame.columns if column not in {first, "week"}]
        long = frame.melt(
            id_vars="week",
            value_vars=value_columns,
            var_name="zone",
            value_name="planned_increment",
        )
        long["zone"] = long["zone"].map(normalize_zone)
        long["planned_increment"] = pd.to_numeric(long["planned_increment"], errors="coerce").fillna(0)
        long["week"] = long["week"].astype(int)
        long["phase"] = phase
        long = long.sort_values(["zone", "week"])
        long["planned_cumulative"] = long.groupby("zone")["planned_increment"].cumsum()
        rows.append(long)
    planning = pd.concat(rows, ignore_index=True)
    return planning, warnings


def infer_operation_start(directory: pd.DataFrame) -> pd.Timestamp:
    candidates: list[pd.Timestamp] = []
    for column in ("date_socialization", "date_lift", "date_crit"):
        if column in directory and directory[column].notna().any():
            candidates.append(pd.Timestamp(directory[column].min()))
    if not candidates:
        return pd.Timestamp.today().normalize() - pd.to_timedelta(pd.Timestamp.today().weekday(), unit="D")
    earliest = min(candidates).normalize()
    return earliest - pd.to_timedelta(earliest.weekday(), unit="D")


def _week_from_date(series: pd.Series, operation_start: pd.Timestamp) -> pd.Series:
    days = (pd.to_datetime(series, errors="coerce").dt.normalize() - operation_start).dt.days
    week = np.floor(days / 7) + 1
    return pd.Series(week, index=series.index).where(days.ge(0))


def apply_effective_weeks(
    directory: pd.DataFrame,
    operation_start: pd.Timestamp,
) -> tuple[pd.DataFrame, list[str]]:
    out = directory.copy()
    warnings: list[str] = []
    out["week_field_effective"] = out["week_field"]
    out["week_crit_effective"] = out["week_crit"]
    if not out["week_field"].notna().any():
        out["week_field_effective"] = _week_from_date(out["date_lift"], operation_start)
        warnings.append(
            "No se encontró COB_CAMP. Para esta ejecución se derivó la semana de campo "
            "a partir de FCH_LEVANTAMIENTO."
        )
    if not out["week_crit"].notna().any():
        out["week_crit_effective"] = _week_from_date(out["date_crit"], operation_start)
        warnings.append(
            "No se encontró COB/CRIT. Para esta ejecución se derivó la semana de crítica "
            "a partir de FCH_CRÍTICA."
        )
    return out, warnings


def _zones(directory: pd.DataFrame, planning: pd.DataFrame) -> list[str]:
    present = set(directory["zone_initial"]) | set(directory["zone_final"]) | set(planning["zone"])
    result = [zone for zone in ZONE_ORDER if zone in present]
    result.extend(sorted(present - set(result) - {"SIN DATO"}))
    return result


def _count_by_zone(directory: pd.DataFrame, zone_column: str, mask: pd.Series | None = None) -> pd.Series:
    frame = directory if mask is None else directory.loc[mask]
    return frame.groupby(zone_column, dropna=False).size()


def _with_national(table: pd.DataFrame, count_columns: list[str]) -> pd.DataFrame:
    national: dict[str, object] = {"Coordinación Zonal": "NACIONAL"}
    for column in count_columns:
        national[column] = int(pd.to_numeric(table[column], errors="coerce").fillna(0).sum())
    return pd.concat([pd.DataFrame([national]), table], ignore_index=True)


def socialization_summary(
    directory: pd.DataFrame,
    zones: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mismatch = directory["zone_initial"].ne(directory["zone_final"])
    original = _count_by_zone(directory, "zone_initial")
    sent = _count_by_zone(directory, "zone_initial", mismatch)
    received = _count_by_zone(directory, "zone_final", mismatch)
    current = _count_by_zone(directory, "zone_final")
    socialized = _count_by_zone(directory, "zone_final", directory["socialized"])
    diligenced = _count_by_zone(directory, "zone_final", directory["diligenced"])

    rows: list[dict[str, object]] = []
    for zone in zones:
        sample = int(current.get(zone, 0))
        rows.append({
            "Coordinación Zonal": zone,
            "Muestra original": int(original.get(zone, 0)),
            "Enviadas": int(sent.get(zone, 0)),
            "Recibidas": int(received.get(zone, 0)),
            "Muestra actual": sample,
            "Socializadas": int(socialized.get(zone, 0)),
            "Diligenciadas": int(diligenced.get(zone, 0)),
            "Por socializar": max(sample - int(socialized.get(zone, 0)), 0),
        })
    table = pd.DataFrame(rows)
    count_columns = [column for column in table.columns if column != "Coordinación Zonal"]
    table = _with_national(table, count_columns)
    national_sample = float(table.loc[0, "Muestra actual"])
    table["% muestra"] = table["Muestra actual"] / national_sample if national_sample else np.nan
    table["% socialización"] = table["Socializadas"] / table["Muestra actual"].replace(0, np.nan)
    table["% diligenciamiento"] = table["Diligenciadas"] / table["Muestra actual"].replace(0, np.nan)
    ordered = [
        "Coordinación Zonal", "Muestra original", "Enviadas", "Recibidas",
        "Muestra actual", "% muestra", "Socializadas", "% socialización",
        "Diligenciadas", "% diligenciamiento", "Por socializar",
    ]
    table = table[ordered]

    transfers = pd.crosstab(
        directory.loc[mismatch, "zone_initial"],
        directory.loc[mismatch, "zone_final"],
    ).reindex(index=zones, columns=zones, fill_value=0)
    transfers["Total enviadas"] = transfers.sum(axis=1)
    total = transfers.sum(axis=0).to_frame().T
    total.index = ["Total recibidas"]
    transfers = pd.concat([transfers, total]).reset_index().rename(columns={"index": "Origen / destino"})
    return table, transfers


def phase_summary(
    directory: pd.DataFrame,
    planning: pd.DataFrame,
    zones: list[str],
    selected_week: int,
    phase: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if phase == "Campo":
        week_column = "week_field_effective"
        executed_flag = directory["lifted"]
        effective_flag = directory["effective_field"]
        executed_label = "Ejecutadas"
        effective_label = "Efectivas"
    else:
        week_column = "week_crit_effective"
        executed_flag = directory["criticized"]
        effective_flag = directory["effective_crit_code"].eq(1)
        executed_label = "Criticadas"
        effective_label = "Efectivas criticadas"

    valid_week = directory[week_column].between(1, selected_week, inclusive="both")
    executed_mask = executed_flag & valid_week
    effective_mask = effective_flag & valid_week
    original = _count_by_zone(directory, "zone_initial")
    current = _count_by_zone(directory, "zone_final")
    executed = _count_by_zone(directory, "zone_final", executed_mask)
    effective = _count_by_zone(directory, "zone_final", effective_mask)
    phase_plan = planning.loc[
        planning["phase"].eq(phase) & planning["week"].le(selected_week)
    ]
    planned = phase_plan.groupby("zone")["planned_increment"].sum()

    rows: list[dict[str, object]] = []
    for zone in zones:
        rows.append({
            "Coordinación Zonal": zone,
            "Muestra": int(original.get(zone, 0)),
            "Muestra actual": int(current.get(zone, 0)),
            "Planificadas": int(round(float(planned.get(zone, 0)))),
            executed_label: int(executed.get(zone, 0)),
            effective_label: int(effective.get(zone, 0)),
        })
    coverage = pd.DataFrame(rows)
    count_columns = [column for column in coverage.columns if column != "Coordinación Zonal"]
    coverage = _with_national(coverage, count_columns)
    for column in ("Planificadas", executed_label, effective_label):
        denominator = float(coverage.loc[0, column])
        coverage[f"% {column.lower()}"] = coverage[column] / denominator if denominator else np.nan

    indicators = coverage[["Coordinación Zonal"]].copy()
    indicators[f"{executed_label}/Muestra"] = (
        coverage[executed_label] / coverage["Muestra actual"].replace(0, np.nan)
    )
    indicators[f"{effective_label}/Muestra"] = (
        coverage[effective_label] / coverage["Muestra actual"].replace(0, np.nan)
    )
    indicators[f"{executed_label}/Planificadas"] = (
        coverage[executed_label] / coverage["Planificadas"].replace(0, np.nan)
    )
    indicators[f"{effective_label}/{executed_label}"] = (
        coverage[effective_label] / coverage[executed_label].replace(0, np.nan)
    )

    max_week = int(planning.loc[planning["phase"].eq(phase), "week"].max())
    weeks = pd.DataFrame({"Semana": range(1, max_week + 1)})
    plan_national = (
        planning.loc[planning["phase"].eq(phase)]
        .groupby("week")["planned_increment"]
        .sum()
        .reindex(range(1, max_week + 1), fill_value=0)
        .cumsum()
    )
    executed_weekly = (
        directory.loc[executed_flag & directory[week_column].between(1, max_week), week_column]
        .round()
        .astype("Int64")
        .value_counts()
        .reindex(range(1, max_week + 1), fill_value=0)
        .sort_index()
        .cumsum()
    )
    chart = weeks.copy()
    chart["Planificado acumulado"] = plan_national.to_numpy()
    chart[executed_label + " acumuladas"] = executed_weekly.to_numpy(dtype=float)
    chart.loc[chart["Semana"].gt(selected_week), executed_label + " acumuladas"] = np.nan
    current_national = int(coverage.loc[0, "Muestra actual"])
    chart["Muestra pendiente según planificación"] = current_national - chart["Planificado acumulado"]
    return coverage, indicators, chart


def progress_summaries(
    directory: pd.DataFrame,
    progress: pd.DataFrame,
    zones: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    merged = directory.merge(progress, on="company_id", how="left", validate="many_to_one")
    has_progress = merged["progress"].notna()
    merged["fill_status"] = np.select(
        [
            merged["lifted"],
            ~has_progress,
            has_progress & merged["progress"].eq(0),
            has_progress & merged["progress"].gt(0),
        ],
        ["Levantada", "Sin registro de avance", "No iniciada", "En proceso"],
        default="No iniciada",
    )
    statuses = ["Levantada", "En proceso", "No iniciada", "Sin registro de avance"]
    status_rows: list[dict[str, object]] = []
    for zone in zones:
        row: dict[str, object] = {"Coordinación Zonal": zone}
        zone_data = merged.loc[merged["zone_final"].eq(zone)]
        for status in statuses:
            row[status] = int(zone_data["fill_status"].eq(status).sum())
        row["Nacional"] = int(len(zone_data))
        status_rows.append(row)
    status_table = pd.DataFrame(status_rows)
    national = {"Coordinación Zonal": "NACIONAL"}
    for status in statuses:
        national[status] = int(status_table[status].sum())
    national["Nacional"] = int(status_table["Nacional"].sum())
    status_table = pd.concat([pd.DataFrame([national]), status_table], ignore_index=True)

    in_process = merged.loc[merged["fill_status"].eq("En proceso")].copy()
    in_process["progress_band"] = pd.cut(
        in_process["progress"],
        bins=[0, 0.5, 0.75, 1.0],
        labels=["Hasta 50%", "Entre 51% y 75%", "Entre 76% y 100%"],
        include_lowest=False,
        right=True,
    )
    bands = ["Hasta 50%", "Entre 51% y 75%", "Entre 76% y 100%"]
    band_rows: list[dict[str, object]] = []
    for zone in zones:
        row = {"Coordinación Zonal": zone}
        zone_data = in_process.loc[in_process["zone_final"].eq(zone)]
        for band in bands:
            row[band] = int(zone_data["progress_band"].astype("string").eq(band).sum())
        row["Nacional"] = int(len(zone_data))
        band_rows.append(row)
    band_table = pd.DataFrame(band_rows)
    national_band = {"Coordinación Zonal": "NACIONAL"}
    for band in bands:
        national_band[band] = int(band_table[band].sum())
    national_band["Nacional"] = int(band_table["Nacional"].sum())
    band_table = pd.concat([pd.DataFrame([national_band]), band_table], ignore_index=True)
    missing = int((~has_progress).sum())
    return status_table, band_table, missing


def _normalize_novelty(value: object) -> str:
    if pd.isna(value):
        return ""
    text = re.sub(r"\s+", " ", str(value).strip())
    key = normalize_name(text)
    if "sin caracteristicas" in key and ("ingresos" in key or "personal ocupado" in key):
        return "Sin características - Ingresos y/o número de personal ocupado"
    return text


def novelty_summary(
    directory: pd.DataFrame,
    zones: list[str],
    selected_week: int,
) -> pd.DataFrame:
    frame = directory.copy()
    frame["novelty_clean"] = frame["novelty"].map(_normalize_novelty)
    through_week = frame["week_field_effective"].between(1, selected_week, inclusive="both")
    has_novelty = frame["novelty_clean"].ne("")
    without_novelty = frame["novelty_clean"].map(normalize_name).eq("efectiva sin novedad")
    effective = through_week & frame["effective_crit_code"].eq(1) & has_novelty & ~without_novelty
    non_effective = through_week & frame["effective_crit_code"].eq(2) & has_novelty

    sections: list[pd.DataFrame] = []
    for section, mask in (("Efectivas con novedad", effective), ("No efectivas", non_effective)):
        part = frame.loc[mask, ["case_key", "zone_final", "novelty_clean"]].copy()
        if part.empty:
            continue
        pivot = part.pivot_table(
            index="novelty_clean",
            columns="zone_final",
            values="case_key",
            aggfunc=pd.Series.nunique,
            fill_value=0,
        ).reindex(columns=zones, fill_value=0)
        pivot["NACIONAL"] = pivot.sum(axis=1)
        pivot = pivot.reset_index().rename(columns={"novelty_clean": "Novedad"})
        pivot.insert(0, "Sección", section)
        sections.append(pivot)
    if not sections:
        return pd.DataFrame(columns=["Sección", "Novedad", *zones, "NACIONAL"])
    return pd.concat(sections, ignore_index=True)


def build_report_data(
    directory_source: str | Path | bytes | BinaryIO,
    directory_filename: str,
    progress_source: str | Path | bytes | BinaryIO,
    progress_filename: str,
    planning_path: str | Path,
    selected_week: int,
    cutoff: object,
    operation_start: object | None = None,
) -> ReportData:
    directory, warnings, controls = load_coverage_directory(
        directory_source, filename=directory_filename
    )
    progress, progress_warnings = load_progress(progress_source, filename=progress_filename)
    planning, planning_warnings = load_planning(planning_path)
    warnings.extend(progress_warnings)
    warnings.extend(planning_warnings)
    start = pd.Timestamp(operation_start).normalize() if operation_start else infer_operation_start(directory)
    directory, week_warnings = apply_effective_weeks(directory, start)
    warnings.extend(week_warnings)
    max_week = int(planning["week"].max())
    if selected_week < 1 or selected_week > max_week:
        raise ValueError(f"La semana debe estar entre 1 y {max_week}.")

    zones = _zones(directory, planning)
    socialization, transfers = socialization_summary(directory, zones)
    field_coverage, field_indicators, field_chart = phase_summary(
        directory, planning, zones, selected_week, "Campo"
    )
    critique_coverage, critique_indicators, critique_chart = phase_summary(
        directory, planning, zones, selected_week, "Crítica"
    )
    progress_status, progress_bands, missing_progress = progress_summaries(
        directory, progress, zones
    )
    if missing_progress:
        warnings.append(
            f"{missing_progress:,} empresas del Directorio no tienen correspondencia en el Reporte de avance."
        )
    novelties = novelty_summary(directory, zones, selected_week)

    mismatch_sample = 0
    plan_totals = planning.loc[
        planning["week"].eq(planning["week"].max())
    ].groupby(["phase", "zone"])["planned_cumulative"].max()
    current_counts = directory.groupby("zone_final").size()
    for zone in zones:
        planned_total = float(plan_totals.get(("Campo", zone), 0))
        mismatch_sample += int(round(planned_total - float(current_counts.get(zone, 0))))
    if any(
        int(round(float(plan_totals.get(("Campo", zone), 0)))) != int(current_counts.get(zone, 0))
        for zone in zones
    ):
        warnings.append(
            "La planificación total no coincide con la muestra actual en una o más coordinaciones. "
            "El reporte conserva ambos valores y no redistribuye diferencias automáticamente."
        )

    controls.update({
        "progress_rows": int(len(progress)),
        "selected_week": int(selected_week),
        "planning_max_week": max_week,
        "missing_progress": missing_progress,
        "sample_plan_net_difference": mismatch_sample,
    })
    return ReportData(
        directory=directory,
        progress=progress,
        planning=planning,
        zones=zones,
        selected_week=int(selected_week),
        cutoff=pd.Timestamp(cutoff).normalize(),
        operation_start=start,
        socialization=socialization,
        transfers=transfers,
        field_coverage=field_coverage,
        field_indicators=field_indicators,
        field_chart=field_chart,
        critique_coverage=critique_coverage,
        critique_indicators=critique_indicators,
        critique_chart=critique_chart,
        progress_status=progress_status,
        progress_bands=progress_bands,
        novelties=novelties,
        warnings=warnings,
        controls=controls,
    )
