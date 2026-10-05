from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Callable, Iterable
import re
import unicodedata

import numpy as np
import pandas as pd


EXCLUDED_COMPANY_ID = "99999999999"


COLUMN_ALIASES: dict[str, list[str]] = {
    "order": ["Nro. orden", "Nro orden", "orden", "numero de orden"],
    "company_id": ["Identificador Empresa", "Identificador de empresa", "id_empresa"],
    "ruc": ["RUC", "numero ruc", "número ruc"],
    "legal_name": ["Razón social", "Razon social", "razon_social"],
    "zone_initial": ["COORD. Z", "COORD Z", "coordinacion zonal"],
    "zone_final": ["CZ_FINAL", "CZ FINAL", "coordinacion zonal final"],
    "grid_date": ["fecha_malla", "fecha malla"],
    "other_zone": ["INF. OTRA ZONAL", "INF OTRA ZONAL", "informa en otra zonal"],
    "socialized": ["SOCIALIZACIÓN", "SOCIALIZACION"],
    "diligenced": ["DILIGENCIADA", "DILIGENCIAMIENTO"],
    "lifted": ["LEVANTADA"],
    "lift_date": ["FCH_LEVANTAMIENTO", "FCH LEVANTAMIENTO"],
    "field_week": ["COB_CAMP", "COB CAMP"],
    "lift_channel": ["LEVANT_P/A", "LEVANT P/A", "LEVANT PA"],
    "collection_mode": ["MODO_LEVANTAMIENTO", "MODO LEVANTAMIENTO"],
    "effective_field": ["EFECT_CAMPO", "EFECT CAMPO"],
    "critic": ["CRÍTICO", "CRITICO"],
    "criticized": ["CRITICADA"],
    "crit_date": ["FCH_CRÍTICA", "FCH CRITICA"],
    "crit_week": ["COB/CRIT", "COB CRIT"],
    "sessions": ["NUM_SESIONES", "NUM SESIONES"],
    "lift_result": ["LEVAN_SN", "LEVAN SN"],
    "effective_crit": ["EFECT_CRIT", "EFECT CRIT"],
    "novelty": ["DESGLO_EFECT", "DESGLO EFECT"],
    "interviewer": ["ENCUESTADOR", "encuestador/a"],
    "reviewer": ["REVISOR"],
    "reviewed": ["REVISADA"],
    "review_date": ["FCH_REVISIÓN", "FCH REVISION"],
    "street_main": ["DIR_1", "DIR 1"],
    "change_size": ["C_TAM", "C TAM"],
    "new_size": ["N_TAM", "N TAM"],
    "sample_size": ["TAMAÑO", "TAMANO"],
    "update_company": ["C_DAT_EMP", "C DAT EMP"],
    "new_establishments": ["N_EST", "N EST"],
    "sample_establishments": ["N° ESTAB", "N ESTAB", "NUM ESTAB"],
    "new_phone_1": ["N_TELÉF_1", "N_TELEF_1", "N TELEF 1"],
    "sample_phone_1": ["TELF. 1", "TELF 1", "TELEFONO 1"],
    "new_phone_2": ["N_TELÉF_2", "N_TELEF_2", "N TELEF 2"],
    "sample_phone_2": ["TELF. 2", "TELF 2", "TELEFONO 2"],
    "new_email": ["N_EMAIL", "N EMAIL"],
    "sample_email": ["Email", "correo electronico"],
    "new_web": ["N_WEB", "N WEB"],
    "sample_web": ["WEB", "pagina web"],
    "contact_phone": ["N_TELÉF_1_INF", "N_TELEF_1_INF", "N TELEF 1 INF"],
    "contact_name": ["N_CONT_1_INF", "N CONT 1 INF"],
    "location_reference": ["REF_1", "REF 1"],
    "manager_phone": ["N_TEL_GER", "N TEL GER"],
    "manager_name": ["NOM_GERENTE", "NOM GERENTE"],
    "manager_email": ["N_EMAIL_GER", "N EMAIL GER"],
}


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _rewind(source: object) -> None:
    if hasattr(source, "seek"):
        source.seek(0)


def load_quality_source(
    source: str | Path | bytes | BinaryIO,
    filename: str | None = None,
) -> pd.DataFrame:
    """Lee todas las variables del Directorio sin persistir el archivo cargado."""
    if isinstance(source, bytes):
        source = BytesIO(source)
    suffix = Path(filename or str(source)).suffix.lower()
    if suffix in {".csv", ".txt"}:
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "utf-16", "latin-1"):
            try:
                _rewind(source)
                return pd.read_csv(source, sep="\t", encoding=encoding, low_memory=False)
            except UnicodeDecodeError as exc:
                last_error = exc
        raise ValueError("No fue posible identificar la codificación del archivo TXT.") from last_error
    _rewind(source)
    return pd.read_excel(source, sheet_name=0)


def load_week_calendar(path: str | Path) -> pd.DataFrame:
    calendar = pd.read_excel(path, sheet_name=0)
    normalized = {normalize_name(column): column for column in calendar.columns}
    date_col = normalized.get("fecha")
    week_col = normalized.get("semana")
    if date_col is None or week_col is None:
        raise ValueError(f"{Path(path).name} debe contener las columnas Fecha y semana.")
    result = pd.DataFrame({
        "date": pd.to_datetime(calendar[date_col], errors="coerce", dayfirst=True).dt.normalize(),
        "week": pd.to_numeric(calendar[week_col], errors="coerce"),
    }).dropna(subset=["date", "week"])
    result["week"] = result["week"].astype(int)
    return result.drop_duplicates("date", keep="last").reset_index(drop=True)


def _resolve_columns(columns: Iterable[object]) -> dict[str, str]:
    normalized = {normalize_name(column): str(column) for column in columns}
    resolved: dict[str, str] = {}
    for key, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            match = normalized.get(normalize_name(alias))
            if match is not None:
                resolved[key] = match
                break
    return resolved


def _identifier(series: pd.Series, default: str = "Sin dato") -> pd.Series:
    def clean(value: object) -> str:
        if pd.isna(value):
            return default
        if isinstance(value, (int, np.integer)):
            return str(int(value))
        if isinstance(value, (float, np.floating)) and float(value).is_integer():
            return str(int(value))
        value = re.sub(r"\.0$", "", str(value).strip())
        return value or default
    return series.map(clean).astype("string")


def _text(series: pd.Series, default: str = "") -> pd.Series:
    values = series.astype("string").str.strip()
    return values.mask(values.isna(), default)


def _blank(series: pd.Series) -> pd.Series:
    values = _text(series).str.upper()
    return values.isin(["", "NA", "N/A", "NAN", "NONE", "<NA>"])


def _number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _date(series: pd.Series) -> pd.Series:
    values = series.copy()
    text = values.astype("string").str.strip()
    iso_mask = text.str.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T].*)?", na=False)
    parsed = pd.to_datetime(values.where(~iso_mask), errors="coerce", dayfirst=True)
    if iso_mask.any():
        parsed.loc[iso_mask] = pd.to_datetime(
            text.loc[iso_mask].str.slice(0, 10), format="%Y-%m-%d", errors="coerce"
        )
    return parsed.dt.normalize()


def _norm_text(series: pd.Series) -> pd.Series:
    return _text(series).map(normalize_name)


def _word_count(series: pd.Series) -> pd.Series:
    return _text(series).str.split().str.len().fillna(0)


def _phone(series: pd.Series) -> pd.Series:
    return _identifier(series, default="").str.replace(r"\s+", "", regex=True)


def _display_value(value: object) -> str:
    if pd.isna(value):
        return "(vacío)"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    text = str(value).strip()
    return text if text and text.upper() not in {"NA", "N/A", "NAN", "<NA>"} else "(vacío)"


def evaluate_quality_validations(
    raw: pd.DataFrame,
    field_calendar: pd.DataFrame,
    critique_calendar: pd.DataFrame,
    allowed_cases: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Ejecuta las reglas que pueden calcularse únicamente con el Directorio."""
    data = raw.copy()
    resolved = _resolve_columns(data.columns)

    def series(key: str) -> pd.Series:
        return data[resolved[key]]

    row_number = _number(series("order")) if "order" in resolved else pd.Series(np.arange(1, len(data) + 1), index=data.index)
    fallback = pd.Series(np.arange(1, len(data) + 1), index=data.index)
    row_number = row_number.where(row_number.notna(), fallback).round().astype(int)
    width = max(4, len(str(int(row_number.max()))) if len(row_number) else 4)
    data["__case"] = "Caso " + row_number.astype(str).str.zfill(width)
    data["__company_id"] = _identifier(series("company_id")) if "company_id" in resolved else "Sin dato"
    data["__ruc"] = _identifier(series("ruc")) if "ruc" in resolved else "Sin dato"
    data["__legal_name"] = _text(series("legal_name"), "Sin dato") if "legal_name" in resolved else "Sin dato"
    initial_zone = _text(series("zone_initial"), "Sin dato") if "zone_initial" in resolved else pd.Series("Sin dato", index=data.index)
    final_zone = _text(series("zone_final"), "Sin dato") if "zone_final" in resolved else initial_zone
    data["__zone"] = final_zone.mask(final_zone.eq("Sin dato") | final_zone.eq(""), initial_zone)

    special_mask = data["__company_id"].eq(EXCLUDED_COMPANY_ID)
    excluded_special = int(special_mask.sum())
    data = data.loc[~special_mask].copy()
    if allowed_cases is not None:
        allowed = set(map(str, allowed_cases))
        data = data.loc[data["__case"].isin(allowed)].copy()

    resolved = _resolve_columns(data.columns)

    def s(key: str) -> pd.Series:
        return data[resolved[key]]

    summary_rows: list[dict[str, object]] = []
    detail_rows: list[dict[str, object]] = []

    def register(
        code: str,
        description: str,
        category: str,
        required: list[str],
        eligible_fn: Callable[[], pd.Series],
        issue_fn: Callable[[], pd.Series],
        fields: list[str],
        expected: str,
    ) -> None:
        missing = [key for key in required if key not in resolved]
        if missing:
            summary_rows.append({
                "Código": code,
                "Categoría": category,
                "Validación": description,
                "Estado": "No evaluada",
                "Empresas evaluadas": 0,
                "Casos": 0,
                "% con incidencia": np.nan,
                "Variables faltantes": ", ".join(missing),
            })
            return
        eligible = eligible_fn().reindex(data.index, fill_value=False).fillna(False).astype(bool)
        issue = issue_fn().reindex(data.index, fill_value=False).fillna(False).astype(bool) & eligible
        evaluated = int(eligible.sum())
        cases = int(issue.sum())
        summary_rows.append({
            "Código": code,
            "Categoría": category,
            "Validación": description,
            "Estado": "Ejecutada",
            "Empresas evaluadas": evaluated,
            "Casos": cases,
            "% con incidencia": cases / evaluated if evaluated else np.nan,
            "Variables faltantes": "",
        })
        display_fields = [resolved[key] for key in fields if key in resolved]
        for index in data.index[issue]:
            values = " | ".join(
                f"{column}={_display_value(data.at[index, column])}" for column in display_fields
            )
            detail_rows.append({
                "Caso": data.at[index, "__case"],
                "Identificador empresa": data.at[index, "__company_id"],
                "RUC": data.at[index, "__ruc"],
                "Razón social": data.at[index, "__legal_name"],
                "Coordinación Zonal": data.at[index, "__zone"],
                "Código": code,
                "Categoría": category,
                "Validación": description,
                "Campos revisados": ", ".join(display_fields),
                "Valores encontrados": values,
                "Criterio esperado": expected,
            })

    one = lambda key: _number(s(key)).eq(1)
    two = lambda key: _number(s(key)).eq(2)
    all_rows = lambda: pd.Series(True, index=data.index)

    zone_codes = {"litoral": 2, "ac campo": 3, "sur": 4, "centro": 5}

    def expected_other_zone() -> pd.Series:
        initial = _norm_text(s("zone_initial"))
        final = _norm_text(s("zone_final"))
        expected = final.map(zone_codes)
        return expected.where(initial.ne(final), 1)

    register(
        "1", "Correspondencia de la empresa que informa en otra zonal", "Flujo operativo",
        ["diligenced", "other_zone", "zone_initial", "zone_final"],
        lambda: one("diligenced"),
        lambda: _number(s("other_zone")).ne(expected_other_zone()) | expected_other_zone().isna(),
        ["other_zone", "zone_initial", "zone_final"],
        "Código 1 si permanece en su zonal; códigos 2 a 5 según la zonal final cuando es transferida.",
    )
    register(
        "2", "Una encuesta levantada debe estar diligenciada", "Flujo operativo",
        ["lifted", "diligenced"], lambda: one("lifted"), lambda: ~one("diligenced"),
        ["lifted", "diligenced"], "DILIGENCIADA = 1 cuando LEVANTADA = 1.",
    )
    register(
        "3", "Una encuesta criticada debe estar levantada y diligenciada", "Flujo operativo",
        ["criticized", "lifted", "diligenced"], lambda: one("criticized"),
        lambda: ~(one("lifted") & one("diligenced")),
        ["criticized", "lifted", "diligenced"], "LEVANTADA = 1 y DILIGENCIADA = 1.",
    )
    register(
        "4", "Campos operativos obligatorios de una encuesta levantada", "Completitud",
        ["lifted", "field_week", "lift_date", "lift_channel", "collection_mode", "effective_field"],
        lambda: one("lifted"),
        lambda: _blank(s("field_week")) | _date(s("lift_date")).isna() | _blank(s("lift_channel")) | _blank(s("collection_mode")) | _blank(s("effective_field")),
        ["field_week", "lift_date", "lift_channel", "collection_mode", "effective_field"],
        "Todos los campos de levantamiento deben estar completos.",
    )
    register(
        "5", "Campos operativos obligatorios de una encuesta criticada", "Completitud",
        ["criticized", "critic", "crit_week", "crit_date", "sessions", "lift_result", "effective_crit", "novelty"],
        lambda: one("criticized"),
        lambda: _blank(s("critic")) | _blank(s("crit_week")) | _date(s("crit_date")).isna() | _blank(s("sessions")) | _blank(s("lift_result")) | _blank(s("effective_crit")) | _blank(s("novelty")),
        ["critic", "crit_week", "crit_date", "sessions", "lift_result", "effective_crit", "novelty"],
        "Todos los campos de crítica deben estar completos.",
    )

    field_map = field_calendar.set_index("date")["week"]
    crit_map = critique_calendar.set_index("date")["week"]

    register(
        "8", "La semana de campo debe coincidir con la fecha de levantamiento", "Cobertura y fechas",
        ["lift_date", "field_week"], lambda: _date(s("lift_date")).notna(),
        lambda: _number(s("field_week")).ne(_date(s("lift_date")).map(field_map)) | _date(s("lift_date")).map(field_map).isna(),
        ["lift_date", "field_week"], "La semana debe corresponder al calendario oficial de CAMPO.",
    )
    register(
        "9", "La semana de crítica debe coincidir con la fecha de crítica", "Cobertura y fechas",
        ["crit_date", "crit_week"], lambda: _date(s("crit_date")).notna(),
        lambda: _number(s("crit_week")).ne(_date(s("crit_date")).map(crit_map)) | _date(s("crit_date")).map(crit_map).isna(),
        ["crit_date", "crit_week"], "La semana debe corresponder al calendario oficial de CRÍTICA.",
    )
    register(
        "12", "El nombre del crítico debe contener dos nombres y dos apellidos", "Personal operativo",
        ["criticized", "critic"], lambda: one("criticized"),
        lambda: _blank(s("critic")) | _word_count(s("critic")).lt(4),
        ["critic"], "Nombre con al menos cuatro componentes.",
    )
    register(
        "13", "El nombre del encuestador debe contener dos nombres y dos apellidos", "Personal operativo",
        ["lifted", "interviewer"], lambda: one("lifted"),
        lambda: _blank(s("interviewer")) | _word_count(s("interviewer")).lt(4),
        ["interviewer"], "Nombre con al menos cuatro componentes.",
    )

    effective_novelties = {
        normalize_name(value) for value in [
            "Cambio de rama de actividad", "Cambio de sector económico", "Cambio de razón social",
            "Cambio de RUC", "Actualización de ubicación geográfica/zonificación",
            "Empresas que producen para terceros", "Fusionadas", "Absorbidas", "Desintegración", "Escisión",
        ]
    }
    non_effective_novelties = {
        normalize_name(value) for value in [
            "No Ubicadas", "Rechazos", "Liquidadas",
            "Sin características - Ingresos y número de personal afiliado",
            "Sin características - Ingresos y/o número de personal ocupado",
            "Sin características - Sector no investigado",
            "Sin características - Rama de actividad no investigada",
            "Sin características - Sin Contabilidad en el año de referencia", "Inactivas",
        ]
    }

    def novelty_issue() -> pd.Series:
        effect = _number(s("effective_crit"))
        novelty = _norm_text(s("novelty"))
        return effect.isna() | ((effect.eq(1)) & ~novelty.isin(effective_novelties)) | ((effect.eq(2)) & ~novelty.isin(non_effective_novelties)) | (~effect.isin([1, 2]))

    register(
        "14", "La efectividad debe corresponder con el esquema de novedades", "Novedades",
        ["criticized", "effective_crit", "novelty"], lambda: one("criticized"), novelty_issue,
        ["effective_crit", "novelty"], "EFECT_CRIT y DESGLO_EFECT deben corresponder a la misma clasificación.",
    )
    register(
        "17", "La calle principal no debe contener otros componentes de la dirección", "Información de empresa",
        ["criticized", "street_main"], lambda: one("criticized") & ~_blank(s("street_main")),
        lambda: _norm_text(s("street_main")).str.contains(
            r"interseccion|kilometro|urbanizacion|nombre edificio|numero|numero de piso|referencia ubicacion|barrio|numero de oficina|ciudadela",
            regex=True, na=False,
        ),
        ["street_main"], "DIR_1 debe contener únicamente la calle principal.",
    )
    register(
        "18", "Un cambio a micro o pequeña empresa debe ser no efectivo", "Tamaño y efectividad",
        ["criticized", "change_size", "new_size", "effective_crit"],
        lambda: one("criticized") & one("change_size") & _norm_text(s("new_size")).isin(["micro empresa", "pequena empresa"]),
        lambda: ~two("effective_crit"),
        ["change_size", "new_size", "effective_crit"], "EFECT_CRIT = 2.",
    )
    register(
        "20", "El nuevo tamaño debe diferir del tamaño de la muestra", "Tamaño y efectividad",
        ["criticized", "change_size", "new_size", "sample_size"],
        lambda: one("criticized") & one("change_size"),
        lambda: _norm_text(s("new_size")).eq(_norm_text(s("sample_size"))),
        ["new_size", "sample_size"], "El tamaño nuevo debe ser distinto al tamaño de la muestra.",
    )

    comparisons = [
        ("22-A", "número de establecimientos", "new_establishments", "sample_establishments"),
        ("22-B", "teléfono 1", "new_phone_1", "sample_phone_1"),
        ("22-C", "teléfono 2", "new_phone_2", "sample_phone_2"),
        ("22-D", "correo electrónico", "new_email", "sample_email"),
        ("22-E", "página web", "new_web", "sample_web"),
    ]
    for code, label, new_key, old_key in comparisons:
        register(
            code, f"La actualización debe reflejar un cambio real en {label}", "Actualización de datos",
            ["criticized", "update_company", new_key, old_key],
            lambda new_key=new_key: one("criticized") & one("update_company") & ~_blank(s(new_key)),
            lambda new_key=new_key, old_key=old_key: _norm_text(s(new_key)).eq(_norm_text(s(old_key))),
            [new_key, old_key], f"El nuevo {label} debe diferir del registrado en la muestra.",
        )

    def phone_length_issue(key: str, minimum: int = 7, maximum: int = 10) -> pd.Series:
        length = _phone(s(key)).str.len()
        return ~length.between(minimum, maximum)

    def repeated_phone_issue(key: str) -> pd.Series:
        return _phone(s(key)).str.contains(r"0{5,}|9{5,}", regex=True, na=False)

    def mobile_length_issue(key: str) -> pd.Series:
        phone = _phone(s(key))
        return phone.str.startswith("09", na=False) & phone.str.len().ne(10)

    for code, key, label in [
        ("23", "new_phone_1", "teléfono 1"), ("24", "new_phone_2", "teléfono 2"),
    ]:
        register(code, f"El {label} debe tener entre 7 y 10 caracteres", "Información de contacto",
                 ["criticized", key], lambda key=key: one("criticized") & ~_blank(s(key)),
                 lambda key=key: phone_length_issue(key), [key], "Longitud entre 7 y 10 caracteres.")
    for code, key, label in [
        ("25", "new_phone_1", "teléfono 1"), ("26", "new_phone_2", "teléfono 2"),
    ]:
        register(code, f"El {label} no debe contener secuencias inválidas", "Información de contacto",
                 ["criticized", key], lambda key=key: one("criticized") & ~_blank(s(key)),
                 lambda key=key: repeated_phone_issue(key), [key], "No debe contener cinco o más ceros o nueves consecutivos.")
    for code, key, label in [
        ("27", "new_phone_1", "teléfono 1"), ("28", "new_phone_2", "teléfono 2"),
    ]:
        register(code, f"El {label} celular debe tener 10 caracteres", "Información de contacto",
                 ["criticized", key], lambda key=key: one("criticized") & ~_blank(s(key)) & _phone(s(key)).str.startswith("09", na=False),
                 lambda key=key: mobile_length_issue(key), [key], "Un celular que inicia en 09 debe tener 10 caracteres.")

    register(
        "31", "La página web actualizada no puede ser un correo electrónico", "Información de contacto",
        ["criticized", "new_web"], lambda: one("criticized") & ~_blank(s("new_web")),
        lambda: _text(s("new_web")).str.contains("@", regex=False, na=False),
        ["new_web"], "La página web no debe contener @.",
    )
    register(
        "32", "El correo electrónico actualizado debe contener @", "Información de contacto",
        ["criticized", "new_email"], lambda: one("criticized") & ~_blank(s("new_email")),
        lambda: ~_text(s("new_email")).str.contains("@", regex=False, na=False),
        ["new_email"], "Estructura mínima usuario@dominio.",
    )
    register(
        "33", "El teléfono del contacto debe tener entre 7 y 10 caracteres", "Información del informante",
        ["criticized", "contact_phone"], lambda: one("criticized") & ~_blank(s("contact_phone")),
        lambda: phone_length_issue("contact_phone"), ["contact_phone"], "Longitud entre 7 y 10 caracteres.",
    )
    register(
        "34", "El teléfono del contacto no debe contener secuencias inválidas", "Información del informante",
        ["criticized", "contact_phone"], lambda: one("criticized") & ~_blank(s("contact_phone")),
        lambda: repeated_phone_issue("contact_phone"), ["contact_phone"], "No debe contener cinco o más ceros o nueves consecutivos.",
    )
    register(
        "35", "El celular del contacto debe tener 10 caracteres", "Información del informante",
        ["criticized", "contact_phone"], lambda: one("criticized") & ~_blank(s("contact_phone")) & _phone(s("contact_phone")).str.startswith("09", na=False),
        lambda: mobile_length_issue("contact_phone"), ["contact_phone"], "Un celular que inicia en 09 debe tener 10 caracteres.",
    )

    def person_name_issue(key: str) -> pd.Series:
        value = _text(s(key))
        count = _word_count(s(key))
        has_title = value.str.contains(".", regex=False, na=False)
        return (has_title & count.lt(3)) | (~has_title & count.lt(2))

    register(
        "36", "El nombre del contacto debe contener al menos un nombre y un apellido", "Información del informante",
        ["criticized", "contact_name"], lambda: one("criticized") & ~_blank(s("contact_name")),
        lambda: person_name_issue("contact_name"), ["contact_name"], "Dos componentes como mínimo; tres si incluye un título abreviado.",
    )
    register(
        "37", "El nombre del contacto no puede contener un correo electrónico", "Información del informante",
        ["criticized", "contact_name"], lambda: one("criticized") & ~_blank(s("contact_name")),
        lambda: _text(s("contact_name")).str.contains("@", regex=False, na=False),
        ["contact_name"], "El nombre no debe contener @.",
    )
    register(
        "39", "La referencia de ubicación no puede contener únicamente números", "Información de empresa",
        ["criticized", "location_reference"], lambda: one("criticized") & ~_blank(s("location_reference")),
        lambda: _text(s("location_reference")).str.fullmatch(r"[0-9]+", na=False),
        ["location_reference"], "La referencia debe incluir una descripción textual.",
    )

    manager_eligible = lambda: one("criticized") & one("effective_crit") & ~_blank(s("manager_phone"))
    register(
        "40", "El teléfono del gerente debe tener entre 7 y 10 caracteres", "Información del gerente",
        ["criticized", "effective_crit", "manager_phone"], manager_eligible,
        lambda: phone_length_issue("manager_phone"), ["manager_phone"], "Longitud entre 7 y 10 caracteres.",
    )
    register(
        "41", "El teléfono del gerente no debe contener secuencias inválidas", "Información del gerente",
        ["criticized", "effective_crit", "manager_phone"], manager_eligible,
        lambda: repeated_phone_issue("manager_phone"), ["manager_phone"], "No debe contener cinco o más ceros o nueves consecutivos.",
    )
    register(
        "42", "El celular del gerente debe tener 10 caracteres", "Información del gerente",
        ["criticized", "effective_crit", "manager_phone"],
        lambda: manager_eligible() & _phone(s("manager_phone")).str.startswith("09", na=False),
        lambda: mobile_length_issue("manager_phone"), ["manager_phone"], "Un celular que inicia en 09 debe tener 10 caracteres.",
    )
    register(
        "43", "El nombre del gerente debe contener al menos un nombre y un apellido", "Información del gerente",
        ["criticized", "effective_crit", "manager_name"],
        lambda: one("criticized") & one("effective_crit") & ~_blank(s("manager_name")),
        lambda: person_name_issue("manager_name"), ["manager_name"], "Dos componentes como mínimo; tres si incluye un título abreviado.",
    )
    register(
        "44", "El nombre del gerente no puede contener un correo electrónico", "Información del gerente",
        ["criticized", "effective_crit", "manager_name"],
        lambda: one("criticized") & one("effective_crit") & ~_blank(s("manager_name")),
        lambda: _text(s("manager_name")).str.contains("@", regex=False, na=False),
        ["manager_name"], "El nombre no debe contener @.",
    )
    register(
        "45", "El correo electrónico del gerente debe contener @", "Información del gerente",
        ["criticized", "effective_crit", "manager_email"],
        lambda: one("criticized") & one("effective_crit") & ~_blank(s("manager_email")),
        lambda: ~_text(s("manager_email")).str.contains("@", regex=False, na=False),
        ["manager_email"], "Estructura mínima usuario@dominio.",
    )
    register(
        "46", "Una encuesta revisada debe estar criticada, levantada y diligenciada", "Flujo operativo",
        ["reviewed", "criticized", "lifted", "diligenced"], lambda: one("reviewed"),
        lambda: ~(one("criticized") & one("lifted") & one("diligenced")),
        ["reviewed", "criticized", "lifted", "diligenced"],
        "CRITICADA = 1, LEVANTADA = 1 y DILIGENCIADA = 1.",
    )
    register(
        "47", "Una encuesta revisada debe registrar revisor y fecha", "Completitud",
        ["reviewed", "reviewer", "review_date"], lambda: one("reviewed"),
        lambda: _blank(s("reviewer")) | _date(s("review_date")).isna(),
        ["reviewer", "review_date"], "Nombre del revisor y fecha de revisión completos.",
    )
    register(
        "48", "El nombre del revisor debe contener dos nombres y dos apellidos", "Personal operativo",
        ["reviewed", "reviewer"], lambda: one("reviewed"),
        lambda: _blank(s("reviewer")) | _word_count(s("reviewer")).lt(4),
        ["reviewer"], "Nombre con al menos cuatro componentes.",
    )
    register(
        "49", "Una encuesta diligenciada debe estar socializada", "Flujo operativo",
        ["diligenced", "socialized"], lambda: one("diligenced"), lambda: ~one("socialized"),
        ["diligenced", "socialized"], "SOCIALIZACIÓN = 1 cuando DILIGENCIADA = 1.",
    )

    for code, validation, missing_sources in [
        ("16", "Cambio de ubicación frente a la información declarada en Sección A", "Seccion_A"),
        ("21", "Nuevo tamaño frente al tamaño calculado con ingresos o personal", "Cap_1 / Cap_5"),
    ]:
        summary_rows.append({
            "Código": code,
            "Categoría": "Fuente externa",
            "Validación": validation,
            "Estado": "Excluida por fuente sensible",
            "Empresas evaluadas": 0,
            "Casos": 0,
            "% con incidencia": np.nan,
            "Variables faltantes": missing_sources,
        })

    summary = pd.DataFrame(summary_rows)
    details = pd.DataFrame(detail_rows, columns=[
        "Caso", "Identificador empresa", "RUC", "Razón social", "Coordinación Zonal",
        "Código", "Categoría", "Validación", "Campos revisados", "Valores encontrados", "Criterio esperado",
    ])
    controls = {
        "companies_evaluated": int(len(data)),
        "companies_with_issues": int(details["Caso"].nunique()) if not details.empty else 0,
        "issues": int(len(details)),
        "rules_executed": int(summary["Estado"].eq("Ejecutada").sum()),
        "rules_not_evaluated": int(summary["Estado"].eq("No evaluada").sum()),
        "rules_excluded": int(summary["Estado"].eq("Excluida por fuente sensible").sum()),
        "excluded_special_id": excluded_special,
    }
    return summary, details, controls
