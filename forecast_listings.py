from __future__ import annotations

import argparse
import math
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import pandas as pd

from rank_listings import add_ranking_columns, clean_text, make_group_key, normalize_text


NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
ANALYSIS_YEAR = 2026
DEFAULT_NEW_CUTOFF_YEAR = 2021
DEFAULT_ROOMS_FILTER = 3
DEFAULT_INPUT = "unegui_ub_all_pages_details.csv"
DEFAULT_OUTPUT_PREFIX = "unegui_ub_all_3room_filtered"
DEFAULT_MIN_PRICE_MNT = 300_000_000
DEFAULT_MAX_PRICE_MNT = 600_000_000
DEFAULT_MIN_SIZE_SQM = 70.0
NEAR_DUPLICATE_PRICE_TOLERANCE = 0.03
FORECAST_YEARS = 5
MIN_REFERENCE_GROUP_SIZE = 5
MIN_DISTRICT_REFERENCE_SIZE = 10
MIN_APARTMENT_PRICE_PER_SQM = 1_000_000
MAX_APARTMENT_PRICE_PER_SQM = 30_000_000
MIN_APARTMENT_SIZE_SQM = 12
MAX_APARTMENT_SIZE_SQM = 1_000

DISTRICT_TEXT_SIGNALS = {
    "Баянгол": ("баянгол", "бгд"),
    "Баянзүрх": ("баянзүрх", "бзд"),
    "Сонгинохайрхан": ("сонгинохайрхан", "схд"),
    "Сүхбаатар": ("сүхбаатар", "сбд"),
    "Хан-Уул": ("хан уул", "хануул", "худ"),
    "Чингэлтэй": ("чингэлтэй", "чд"),
}


@dataclass(frozen=True)
class OfficialPrice:
    price_per_sqm_mnt: float
    latest_month: str
    source: str


@dataclass(frozen=True)
class GrowthRate:
    annual_rate: float
    raw_annual_rate: float
    source: str


def mnt_millions(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{float(value) / 1_000_000:.2f}M"


def safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text == "..":
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return 0
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - ord("A") + 1
    return number - 1


def read_xlsx_first_sheet(path: str | Path) -> list[list[str]]:
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{NS}si"):
                shared.append("".join(text.text or "" for text in item.iter(f"{NS}t")))

        sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row_node in sheet_root.findall(f"{NS}sheetData/{NS}row"):
            row_values: list[str] = []
            for cell in row_node.findall(f"{NS}c"):
                idx = column_index(cell.attrib.get("r", "A1"))
                while len(row_values) <= idx:
                    row_values.append("")

                value_node = cell.find(f"{NS}v")
                value = "" if value_node is None else value_node.text or ""
                if cell.attrib.get("t") == "s" and value:
                    value = shared[int(value)]
                row_values[idx] = value
            rows.append(row_values)
    return rows


def find_stats_file(stats_dir: str | Path, code: str) -> Path:
    stats_path = Path(stats_dir)
    matches = sorted(stats_path.glob(f"{code}_*.xlsx"))
    if not matches:
        raise SystemExit(f"Could not find {code}_*.xlsx in {stats_path}")
    return matches[-1]


def parse_annual_hpi_changes(path: str | Path) -> dict[str, GrowthRate]:
    rows = read_xlsx_first_sheet(path)
    if len(rows) < 5:
        raise SystemExit(f"Unexpected 1212 annual HPI table layout: {path}")

    latest_month = rows[1][1]
    label_map = {
        "Нийт орон сууцны үнийн өөрчлөлт": "unknown",
        "Шинэ орон сууцны үнийн өөрчлөлт": "new",
        "Хуучин орон сууцны үнийн өөрчлөлт": "old",
    }
    result: dict[str, GrowthRate] = {}
    for row in rows:
        label = row[0] if row else ""
        age_class = label_map.get(label)
        if not age_class:
            continue
        value = safe_float(row[1] if len(row) > 1 else None)
        if value is None:
            continue
        result[age_class] = GrowthRate(
            annual_rate=value / 100,
            raw_annual_rate=value / 100,
            source=f"DT_NSO_0300_00V1:{label}:{latest_month}",
        )
    return result


def previous_year_month(month: str) -> str:
    year, month_num = month.split("-", 1)
    return f"{int(year) - 1}-{month_num}"


def parse_district_prices(path: str | Path) -> tuple[dict[tuple[str, str], OfficialPrice], dict[tuple[str, str], GrowthRate]]:
    rows = read_xlsx_first_sheet(path)
    if len(rows) < 16:
        raise SystemExit(f"Unexpected 1212 district price table layout: {path}")

    months = rows[1][2:]
    latest_month = months[0]
    official_prices: dict[tuple[str, str], OfficialPrice] = {}
    district_growth: dict[tuple[str, str], GrowthRate] = {}
    current_age_class: str | None = None

    for row in rows[2:16]:
        if len(row) < 3:
            continue
        label = row[0].strip() if row[0] else ""
        if "Шинэ" in label:
            current_age_class = "new"
        elif "Хуучин" in label:
            current_age_class = "old"
        if current_age_class is None:
            continue

        district = row[1].strip() if len(row) > 1 else ""
        if not district:
            continue

        values_by_month: dict[str, float] = {}
        for month, value in zip(months, row[2:]):
            parsed = safe_float(value)
            if parsed is not None:
                values_by_month[month] = parsed * 1_000_000

        latest_value = values_by_month.get(latest_month)
        if latest_value is not None:
            official_prices[(current_age_class, district)] = OfficialPrice(
                price_per_sqm_mnt=latest_value,
                latest_month=latest_month,
                source=f"DT_NSO_0300_00V4:{current_age_class}:{district}:{latest_month}",
            )

        prior_month = previous_year_month(latest_month)
        prior_value = values_by_month.get(prior_month)
        if latest_value is not None and prior_value and prior_value > 0:
            rate = latest_value / prior_value - 1
            district_growth[(current_age_class, district)] = GrowthRate(
                annual_rate=rate,
                raw_annual_rate=rate,
                source=f"DT_NSO_0300_00V4:{current_age_class}:{district}:{latest_month}_vs_{prior_month}",
            )

    return official_prices, district_growth


def parse_built_year(value: Any) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"(19\d{2}|20\d{2})", text)
    if not match:
        return None
    year = int(match.group(1))
    if 1900 <= year <= ANALYSIS_YEAR + 3:
        return year
    return None


def text_district_signals(row: pd.Series) -> str:
    text = normalize_text(
        " ".join(
            clean_text(row.get(column))
            for column in ("title", "detail_title", "detail_description", "description")
        )
    )
    tokens = set(text.split())
    detected: list[str] = []
    for district, signals in DISTRICT_TEXT_SIGNALS.items():
        for signal in signals:
            if " " in signal:
                if signal in text:
                    detected.append(district)
                    break
            elif signal in tokens:
                detected.append(district)
                break
    return ";".join(sorted(set(detected)))


def has_location_conflict(row: pd.Series) -> bool:
    listed_district = clean_text(row.get("district"))
    signals = [part for part in clean_text(row.get("text_district_signals")).split(";") if part]
    if not listed_district or not signals:
        return False
    return listed_district not in signals


def building_age_class(built_year: int | None, building_stage: Any, new_cutoff_year: int) -> str:
    stage = clean_text(building_stage).lower()
    if built_year is not None:
        return "new" if built_year >= new_cutoff_year else "old"
    if "ороогүй" in stage:
        return "new"
    return "unknown"


def building_newness_score(built_year: int | None, age_class: str) -> float:
    if built_year is None:
        return 0.4 if age_class == "unknown" else 0.8
    age = max(0, ANALYSIS_YEAR - built_year)
    if age <= 5:
        return 1.0
    return max(0.0, 1.0 - (age / 30.0))


def listing_age_days(value: Any, reference_date: date) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = date.fromisoformat(text[:10])
    except ValueError:
        return None
    return float((reference_date - parsed).days)


def apartment_quality_mask(df: pd.DataFrame) -> pd.Series:
    price_per_sqm = pd.to_numeric(df["price_per_sqm"], errors="coerce")
    size_sqm = pd.to_numeric(df["size_sqm"], errors="coerce")
    return (
        df["property_category"].eq("apartment")
        & price_per_sqm.between(MIN_APARTMENT_PRICE_PER_SQM, MAX_APARTMENT_PRICE_PER_SQM, inclusive="both")
        & size_sqm.between(MIN_APARTMENT_SIZE_SQM, MAX_APARTMENT_SIZE_SQM, inclusive="both")
    )


def make_lookup_key(*parts: Any) -> tuple[str, ...]:
    return tuple(clean_text(part) for part in parts)


def grouped_medians(reference: pd.DataFrame, group_cols: list[str]) -> dict[tuple[str, ...], tuple[float, int]]:
    grouped = (
        reference.dropna(subset=["price_per_sqm"])
        .groupby(group_cols, dropna=False)
        .agg(median_price_per_sqm=("price_per_sqm", "median"), sample_size=("price_per_sqm", "count"))
        .reset_index()
    )
    result: dict[tuple[str, ...], tuple[float, int]] = {}
    for _, row in grouped.iterrows():
        key = make_lookup_key(*(row[col] for col in group_cols))
        result[key] = (float(row["median_price_per_sqm"]), int(row["sample_size"]))
    return result


def local_reference_medians(reference: pd.DataFrame) -> dict[str, dict[tuple[str, ...], tuple[float, int]]]:
    return {
        "sub_location_age": grouped_medians(reference, ["sub_location", "building_age_class"]),
        "sub_location": grouped_medians(reference, ["sub_location"]),
        "district_age": grouped_medians(reference, ["district", "building_age_class"]),
        "district": grouped_medians(reference, ["district"]),
        "age": grouped_medians(reference, ["building_age_class"]),
        "all": {("all",): (float(reference["price_per_sqm"].median()), int(reference["price_per_sqm"].count()))},
    }


def pick_local_median(
    row: pd.Series,
    lookups: dict[str, dict[tuple[str, ...], tuple[float, int]]],
) -> tuple[float | None, str, int | None]:
    candidates = [
        ("sub_location_age", make_lookup_key(row.get("sub_location"), row.get("building_age_class")), MIN_REFERENCE_GROUP_SIZE),
        ("sub_location", make_lookup_key(row.get("sub_location")), MIN_REFERENCE_GROUP_SIZE),
        ("district_age", make_lookup_key(row.get("district"), row.get("building_age_class")), MIN_DISTRICT_REFERENCE_SIZE),
        ("district", make_lookup_key(row.get("district")), MIN_DISTRICT_REFERENCE_SIZE),
        ("age", make_lookup_key(row.get("building_age_class")), MIN_DISTRICT_REFERENCE_SIZE),
        ("all", ("all",), 1),
    ]
    for source, key, minimum in candidates:
        found = lookups[source].get(key)
        if found is None:
            continue
        median, sample_size = found
        if sample_size >= minimum and not pd.isna(median):
            return median, f"local_unegui_{source}", sample_size
    return None, "missing", None


def pick_official_price(
    row: pd.Series,
    official_prices: dict[tuple[str, str], OfficialPrice],
) -> tuple[float | None, str]:
    district = clean_text(row.get("district"))
    age_class = clean_text(row.get("building_age_class"))
    age_keys = [age_class] if age_class in {"new", "old"} else ["new", "old"]
    districts = [district, "Дундаж"] if district else ["Дундаж"]

    values: list[OfficialPrice] = []
    for current_district in districts:
        for current_age in age_keys:
            found = official_prices.get((current_age, current_district))
            if found is not None:
                values.append(found)
        if values:
            break

    if not values:
        return None, "missing"
    if len(values) == 1:
        found = values[0]
        return found.price_per_sqm_mnt, found.source
    average = sum(item.price_per_sqm_mnt for item in values) / len(values)
    source = "average:" + "+".join(item.source for item in values)
    return average, source


def pick_growth_rate(
    row: pd.Series,
    base_growth: dict[str, GrowthRate],
    district_growth: dict[tuple[str, str], GrowthRate],
    min_growth: float,
    max_growth: float,
) -> GrowthRate:
    district = clean_text(row.get("district"))
    age_class = clean_text(row.get("building_age_class"))
    base_key = age_class if age_class in {"new", "old"} else "unknown"
    base = base_growth.get(base_key) or base_growth.get("unknown")
    if base is None:
        base = GrowthRate(annual_rate=0.10, raw_annual_rate=0.10, source="fallback:10pct")

    district_rate = district_growth.get((age_class, district)) if age_class in {"new", "old"} else None
    if district_rate is None:
        raw_rate = base.annual_rate
        source = base.source
    else:
        raw_rate = 0.5 * base.annual_rate + 0.5 * district_rate.annual_rate
        source = f"50pct({base.source})+50pct({district_rate.source})"

    clipped = min(max(raw_rate, min_growth), max_growth)
    if clipped != raw_rate:
        source = f"{source}; clipped_to_{min_growth:.1%}_{max_growth:.1%}"
    return GrowthRate(annual_rate=clipped, raw_annual_rate=raw_rate, source=source)


def blended_fair_price(
    local_median: float | None,
    official_price: float | None,
    local_weight: float,
) -> tuple[float | None, str]:
    if local_median is None and official_price is None:
        return None, "missing"
    if local_median is None:
        return official_price, "official_only"
    if official_price is None:
        return local_median, "local_only"
    official_weight = 1.0 - local_weight
    return local_weight * local_median + official_weight * official_price, f"{local_weight:.0%}_local_{official_weight:.0%}_official"


def pct_rank_high_good(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rank(pct=True, method="average", na_option="bottom")


def pct_rank_low_good(series: pd.Series) -> pd.Series:
    return 1.0 - pd.to_numeric(series, errors="coerce").rank(pct=True, method="average", na_option="bottom")


def drop_near_duplicates(df: pd.DataFrame, price_tolerance: float = NEAR_DUPLICATE_PRICE_TOLERANCE) -> tuple[pd.DataFrame, int]:
    kept_indices: list[Any] = []
    seen_prices: dict[tuple[str, str, str], list[float]] = {}

    for index, row in df.iterrows():
        location = clean_text(row.get("location_norm"))
        size = clean_text(row.get("size_round"))
        rooms = clean_text(row.get("rooms_clean"))
        price = safe_float(row.get("price_mnt"))
        if not location or not size or not rooms or price is None:
            kept_indices.append(index)
            continue

        key = (location, size, rooms)
        existing_prices = seen_prices.setdefault(key, [])
        if any(abs(price - existing) / max(price, existing) <= price_tolerance for existing in existing_prices):
            continue

        existing_prices.append(price)
        kept_indices.append(index)

    return df.loc[kept_indices].copy(), len(df) - len(kept_indices)


def order_output_columns(df: pd.DataFrame) -> pd.DataFrame:
    priority = [
        "forecast_rank",
        "forecast_ranking_score",
        "forecast_applicable",
        "forecast_upside_score",
        "building_newness_score",
        "current_price_per_sqm_score",
        "distance_score_forecast",
        "expected_gain_pct",
        "expected_gain_mnt",
        "forecast_5yr_value_mnt",
        "forecast_5yr_price_per_sqm_mnt",
        "estimated_fair_value_mnt",
        "fair_price_per_sqm_mnt",
        "asking_to_fair_pct",
        "annual_growth_rate",
        "annual_growth_rate_raw",
        "building_age_class",
        "built_year",
        "new_cutoff_year",
        "listing_age_days",
        "local_median_price_per_sqm_mnt",
        "local_median_source",
        "local_median_sample_size",
        "official_price_per_sqm_mnt",
        "official_price_source",
        "fair_value_source",
        "growth_rate_source",
        "forecast_note",
        "location_conflict",
        "text_district_signals",
        "possible_duplicate",
        "ad_id",
        "title",
        "price_mnt",
        "price_per_sqm",
        "location",
        "district",
        "sub_location",
        "size_sqm",
        "rooms_clean",
        "room_category",
        "property_category",
        "distance_to_sukhbaatar_km",
        "listing_date",
        "listing_date_iso",
        "seller",
        "link",
    ]
    columns = [column for column in priority if column in df.columns]
    columns.extend(column for column in df.columns if column not in columns)
    return df[columns]


def build_forecast(
    input_path: str | Path,
    output_prefix: str,
    stats_dir: str | Path,
    local_weight: float,
    forecast_weight: float,
    newness_weight: float,
    price_weight: float,
    distance_weight: float,
    new_cutoff_year: int,
    rooms_filter: int | None,
    min_price_mnt: float | None,
    max_price_mnt: float | None,
    min_size_sqm: float | None,
    min_growth: float,
    max_growth: float,
) -> None:
    input_path = Path(input_path)
    if not input_path.exists():
        raise SystemExit(f"CSV not found: {input_path}")

    total_weight = forecast_weight + newness_weight + price_weight + distance_weight
    if total_weight <= 0:
        raise SystemExit("Ranking weights must sum to a positive number.")
    forecast_weight, newness_weight, price_weight, distance_weight = [
        weight / total_weight for weight in (forecast_weight, newness_weight, price_weight, distance_weight)
    ]

    annual_hpi_path = find_stats_file(stats_dir, "DT_NSO_0300_00V1")
    district_price_path = find_stats_file(stats_dir, "DT_NSO_0300_00V4")
    base_growth = parse_annual_hpi_changes(annual_hpi_path)
    official_prices, district_growth = parse_district_prices(district_price_path)

    raw = pd.read_csv(input_path, low_memory=False)
    df = add_ranking_columns(raw)
    df["price_mnt"] = pd.to_numeric(df["price_mnt"], errors="coerce")
    df["price_per_sqm"] = pd.to_numeric(df["price_per_sqm"], errors="coerce")
    df["size_sqm"] = pd.to_numeric(df["size_sqm"], errors="coerce")
    df["built_year"] = df.get("Ашиглалтанд орсон он", pd.Series(pd.NA, index=df.index)).map(parse_built_year)
    df["text_district_signals"] = df.apply(text_district_signals, axis=1)
    df["location_conflict"] = df.apply(has_location_conflict, axis=1)
    df["new_cutoff_year"] = new_cutoff_year
    df["building_age_class"] = df.apply(
        lambda row: building_age_class(row["built_year"], row.get("Барилгын явц"), new_cutoff_year),
        axis=1,
    )
    df["building_newness_score"] = df.apply(
        lambda row: building_newness_score(row["built_year"], row["building_age_class"]),
        axis=1,
    )

    reference_date = pd.to_datetime(df["listing_date_iso"], errors="coerce").max()
    if pd.isna(reference_date):
        reference_day = date(ANALYSIS_YEAR, 1, 1)
    else:
        reference_day = reference_date.date()
    df["listing_age_days"] = df.get("listing_date_iso", pd.Series(pd.NA, index=df.index)).map(
        lambda value: listing_age_days(value, reference_day)
    )

    quality_mask = apartment_quality_mask(df)
    if rooms_filter is None:
        rooms_filter_mask = pd.Series(True, index=df.index)
        room_filter_label = "all rooms"
    else:
        rooms_filter_mask = df["rooms_clean"].eq(float(rooms_filter))
        room_filter_label = f"{rooms_filter} rooms"

    reference = df[quality_mask].copy()
    if reference.empty:
        raise SystemExit("No usable apartment reference rows after quality filtering.")
    local_reference = df[quality_mask & rooms_filter_mask].copy()
    if local_reference.empty:
        raise SystemExit(f"No usable apartment reference rows for room filter: {room_filter_label}")
    lookups = local_reference_medians(local_reference)

    local_results = df.apply(lambda row: pick_local_median(row, lookups), axis=1, result_type="expand")
    local_results.columns = ["local_median_price_per_sqm_mnt", "local_median_source", "local_median_sample_size"]
    df[local_results.columns] = local_results

    official_results = df.apply(lambda row: pick_official_price(row, official_prices), axis=1, result_type="expand")
    official_results.columns = ["official_price_per_sqm_mnt", "official_price_source"]
    df[official_results.columns] = official_results

    fair_results = df.apply(
        lambda row: blended_fair_price(
            safe_float(row["local_median_price_per_sqm_mnt"]),
            safe_float(row["official_price_per_sqm_mnt"]),
            local_weight,
        ),
        axis=1,
        result_type="expand",
    )
    fair_results.columns = ["fair_price_per_sqm_mnt", "fair_value_source"]
    df[fair_results.columns] = fair_results

    growth_results = df.apply(
        lambda row: pick_growth_rate(row, base_growth, district_growth, min_growth, max_growth),
        axis=1,
    )
    df["annual_growth_rate"] = growth_results.map(lambda item: item.annual_rate)
    df["annual_growth_rate_raw"] = growth_results.map(lambda item: item.raw_annual_rate)
    df["growth_rate_source"] = growth_results.map(lambda item: item.source)

    df["estimated_fair_value_mnt"] = df["fair_price_per_sqm_mnt"] * df["size_sqm"]
    df["forecast_5yr_price_per_sqm_mnt"] = df["fair_price_per_sqm_mnt"] * (1.0 + df["annual_growth_rate"]) ** FORECAST_YEARS
    df["forecast_5yr_value_mnt"] = df["forecast_5yr_price_per_sqm_mnt"] * df["size_sqm"]
    df["asking_to_fair_pct"] = df["price_mnt"] / df["estimated_fair_value_mnt"] - 1.0
    df["expected_gain_mnt"] = df["forecast_5yr_value_mnt"] - df["price_mnt"]
    df["expected_gain_pct"] = df["forecast_5yr_value_mnt"] / df["price_mnt"] - 1.0

    min_price_mask = pd.Series(True, index=df.index)
    max_price_mask = pd.Series(True, index=df.index)
    min_size_mask = pd.Series(True, index=df.index)
    if min_price_mnt is not None:
        min_price_mask = df["price_mnt"].ge(min_price_mnt)
    if max_price_mnt is not None:
        max_price_mask = df["price_mnt"].le(max_price_mnt)
    if min_size_sqm is not None:
        min_size_mask = df["size_sqm"].gt(min_size_sqm)

    filter_parts: list[str] = [room_filter_label]
    if min_price_mnt is not None:
        filter_parts.append(f"price >= {min_price_mnt:,.0f} MNT")
    if max_price_mnt is not None:
        filter_parts.append(f"price <= {max_price_mnt:,.0f} MNT")
    if min_size_sqm is not None:
        filter_parts.append(f"size > {min_size_sqm:g} sqm")
    selection_filter_label = "; ".join(filter_parts)

    df["forecast_applicable"] = (
        quality_mask
        & rooms_filter_mask
        & min_price_mask
        & max_price_mask
        & min_size_mask
        & df["price_mnt"].gt(0)
        & df["fair_price_per_sqm_mnt"].gt(0)
        & df["forecast_5yr_value_mnt"].gt(0)
        & df["distance_to_sukhbaatar_km"].notna()
        & ~df["location_conflict"]
    )
    df["forecast_note"] = "apartment_forecast"
    df.loc[~df["property_category"].eq("apartment"), "forecast_note"] = "not_apartment_official_hpi_not_applied"
    df.loc[df["property_category"].eq("apartment") & ~quality_mask, "forecast_note"] = "apartment_excluded_by_quality_filter"
    if rooms_filter is not None:
        df.loc[
            df["property_category"].eq("apartment") & quality_mask & ~rooms_filter_mask,
            "forecast_note",
        ] = f"excluded_room_filter_not_{rooms_filter}_rooms"
    if min_price_mnt is not None:
        df.loc[
            df["property_category"].eq("apartment") & quality_mask & rooms_filter_mask & ~min_price_mask,
            "forecast_note",
        ] = f"excluded_price_below_{int(min_price_mnt)}"
    if max_price_mnt is not None:
        df.loc[
            df["property_category"].eq("apartment") & quality_mask & rooms_filter_mask & min_price_mask & ~max_price_mask,
            "forecast_note",
        ] = f"excluded_price_above_{int(max_price_mnt)}"
    if min_size_sqm is not None:
        df.loc[
            df["property_category"].eq("apartment")
            & quality_mask
            & rooms_filter_mask
            & min_price_mask
            & max_price_mask
            & ~min_size_mask,
            "forecast_note",
        ] = f"excluded_size_not_above_{min_size_sqm:g}_sqm"
    df.loc[df["property_category"].eq("apartment") & df["location_conflict"], "forecast_note"] = "excluded_location_conflict_title_vs_listing_location"
    df.loc[df["forecast_applicable"] & df["building_age_class"].eq("unknown"), "forecast_note"] = "apartment_forecast_unknown_build_year"

    candidates = df[df["forecast_applicable"]].copy()
    candidates["forecast_upside_score"] = pct_rank_high_good(candidates["expected_gain_pct"])
    candidates["current_price_per_sqm_score"] = pct_rank_low_good(candidates["price_per_sqm"])
    candidates["distance_score_forecast"] = pct_rank_low_good(candidates["distance_to_sukhbaatar_km"])
    candidates["forecast_ranking_score"] = (
        forecast_weight * candidates["forecast_upside_score"]
        + newness_weight * candidates["building_newness_score"]
        + price_weight * candidates["current_price_per_sqm_score"]
        + distance_weight * candidates["distance_score_forecast"]
    )
    candidates = candidates.sort_values(
        ["forecast_ranking_score", "expected_gain_pct", "price_per_sqm", "distance_to_sukhbaatar_km"],
        ascending=[False, False, True, True],
    )

    strict_cols = ["title_norm", "location_norm", "size_round", "rooms_clean", "price_mnt"]
    dedupe_sort_cols = [
        "forecast_ranking_score",
        "expected_gain_pct",
        "listing_date_iso",
        "ad_id",
    ]
    deduped = candidates.sort_values(dedupe_sort_cols, ascending=[False, False, False, False]).copy()
    strict_valid = deduped[strict_cols].notna().all(axis=1) & deduped["title_norm"].ne("") & deduped["location_norm"].ne("")
    deduped["_forecast_dedupe_key"] = pd.NA
    if strict_valid.any():
        deduped.loc[strict_valid, "_forecast_dedupe_key"] = make_group_key(deduped.loc[strict_valid], strict_cols)
        deduped = deduped.drop_duplicates("_forecast_dedupe_key", keep="first")
    deduped = deduped.drop(columns=["_forecast_dedupe_key"])
    deduped, near_duplicate_rows_removed = drop_near_duplicates(deduped)
    deduped = deduped.sort_values(
        ["forecast_ranking_score", "expected_gain_pct", "price_per_sqm", "distance_to_sukhbaatar_km"],
        ascending=[False, False, True, True],
    )
    deduped["forecast_rank"] = range(1, len(deduped) + 1)

    all_output = df.copy()
    all_output["forecast_rank"] = pd.NA
    all_output["forecast_ranking_score"] = pd.NA
    all_output["forecast_upside_score"] = pd.NA
    all_output["current_price_per_sqm_score"] = pd.NA
    all_output["distance_score_forecast"] = pd.NA
    score_cols = [
        "forecast_rank",
        "forecast_ranking_score",
        "forecast_upside_score",
        "current_price_per_sqm_score",
        "distance_score_forecast",
    ]
    all_output.loc[deduped.index, score_cols] = deduped[score_cols]

    prefix = Path(output_prefix)
    all_path = Path(f"{prefix}_forecast_all.csv")
    ranked_path = Path(f"{prefix}_forecast_ranked_apartments.csv")
    top10_path = Path(f"{prefix}_forecast_top10.csv")
    summary_path = Path(f"{prefix}_forecast_summary.csv")
    methodology_path = Path(f"{prefix}_forecast_methodology.txt")

    order_output_columns(all_output).to_csv(all_path, index=False, encoding="utf-8-sig")
    order_output_columns(deduped).to_csv(ranked_path, index=False, encoding="utf-8-sig")
    order_output_columns(deduped.head(10)).to_csv(top10_path, index=False, encoding="utf-8-sig")

    summary_rows = [
        ("input_rows", len(raw)),
        ("apartment_reference_rows_after_quality_filter", len(reference)),
        ("local_reference_rows_after_room_filter", len(local_reference)),
        ("room_filter", room_filter_label),
        ("selection_filter", selection_filter_label),
        ("min_price_mnt", "" if min_price_mnt is None else f"{min_price_mnt:.0f}"),
        ("max_price_mnt", "" if max_price_mnt is None else f"{max_price_mnt:.0f}"),
        ("min_size_sqm_exclusive", "" if min_size_sqm is None else f"{min_size_sqm:g}"),
        ("forecast_applicable_rows", int(df["forecast_applicable"].sum())),
        ("location_conflict_rows_total", int(df["location_conflict"].sum())),
        (
            "apartment_location_conflict_rows_excluded",
            int((df["property_category"].eq("apartment") & df["location_conflict"]).sum()),
        ),
        ("near_duplicate_rows_removed_from_ranked", near_duplicate_rows_removed),
        ("forecast_ranked_deduped_rows", len(deduped)),
        ("new_cutoff_year", new_cutoff_year),
        ("forecast_years", FORECAST_YEARS),
        ("fair_value_blend", f"{local_weight:.0%} local Unegui median + {1 - local_weight:.0%} official 1212 district average"),
        ("ranking_weights", f"forecast={forecast_weight:.0%}; newness={newness_weight:.0%}; price_per_sqm={price_weight:.0%}; distance={distance_weight:.0%}"),
        ("official_annual_hpi_source", str(annual_hpi_path)),
        ("official_district_price_source", str(district_price_path)),
        ("base_growth_total", f"{base_growth.get('unknown').annual_rate:.2%}" if base_growth.get("unknown") else ""),
        ("base_growth_new", f"{base_growth.get('new').annual_rate:.2%}" if base_growth.get("new") else ""),
        ("base_growth_old", f"{base_growth.get('old').annual_rate:.2%}" if base_growth.get("old") else ""),
    ]
    if not deduped.empty:
        top = deduped.iloc[0]
        summary_rows.extend(
            [
                ("top_ad_id", top.get("ad_id", "")),
                ("top_title", top.get("title", "")),
                ("top_expected_gain_pct", f"{top.get('expected_gain_pct', 0):.2%}"),
                ("top_forecast_5yr_value_mnt", f"{top.get('forecast_5yr_value_mnt', 0):.0f}"),
            ]
        )
    pd.DataFrame(summary_rows, columns=["metric", "value"]).to_csv(summary_path, index=False, encoding="utf-8-sig")

    methodology = [
        "Unegui UB 5-year nominal MNT forecast methodology",
        "",
        f"Input listings: {input_path}",
        f"Official annual HPI table: {annual_hpi_path}",
        f"Official district price table: {district_price_path}",
        f"Room filter for ranking and local medians: {room_filter_label}.",
        f"Selection filter for ranking: {selection_filter_label}.",
        f"New building rule: built year >= {new_cutoff_year} is treated as new.",
        f"Fair value per sqm: {local_weight:.0%} local Unegui median + {1 - local_weight:.0%} official 1212 district average when both are available.",
        "Local median fallback order within the room-filtered apartment reference: sub-location+new/old, sub-location, district+new/old, district, new/old, all UB.",
        "Growth rate: 50% latest 1212 annual HPI change for new/old apartments + 50% latest district same-month YoY where available.",
        f"Growth clipping for base scenario: {min_growth:.1%} to {max_growth:.1%}.",
        "Forecast value: fair value is projected 5 years forward, then compared with current asking price.",
        "Forecast ranking score uses forecast upside %, building newness, current price/sqm, and distance to Sukhbaatar Square.",
        "Rows with obvious title/description district conflicts are kept in the all-output file but excluded from ranking.",
        "Non-apartment listings are kept in the all-output file, but are not ranked because the official HPI inputs are apartment-specific.",
    ]
    methodology_path.write_text("\n".join(methodology) + "\n", encoding="utf-8")

    top_cols = [
        "forecast_rank",
        "title",
        "price_mnt",
        "price_per_sqm",
        "fair_price_per_sqm_mnt",
        "forecast_5yr_value_mnt",
        "expected_gain_pct",
        "building_age_class",
        "built_year",
        "distance_to_sukhbaatar_km",
        "location",
        "link",
    ]
    print(f"Input rows: {len(raw)}")
    print(f"Apartment reference rows after quality filter: {len(reference)}")
    print(f"Local reference rows after room filter ({room_filter_label}): {len(local_reference)}")
    print(f"Selection filter: {selection_filter_label}")
    print(f"Forecast applicable apartment rows after selection filters: {int(df['forecast_applicable'].sum())}")
    print(f"Forecast ranked deduped rows: {len(deduped)}")
    print("\nTop 10 forecast-ranked apartments:")
    display = deduped.head(10)[[column for column in top_cols if column in deduped.columns]].copy()
    for column in ["price_mnt", "price_per_sqm", "fair_price_per_sqm_mnt", "forecast_5yr_value_mnt"]:
        if column in display.columns:
            display[column] = display[column].map(mnt_millions)
    if "expected_gain_pct" in display.columns:
        display["expected_gain_pct"] = display["expected_gain_pct"].map(lambda value: f"{value:.1%}" if pd.notna(value) else "")
    if "distance_to_sukhbaatar_km" in display.columns:
        display["distance_to_sukhbaatar_km"] = display["distance_to_sukhbaatar_km"].map(lambda value: f"{value:.2f}" if pd.notna(value) else "")
    print(display.to_string(index=False))
    print(f"\nSaved all forecasts to {all_path}")
    print(f"Saved ranked apartment forecasts to {ranked_path}")
    print(f"Saved top 10 forecast-ranked apartments to {top10_path}")
    print(f"Saved forecast summary to {summary_path}")
    print(f"Saved methodology to {methodology_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forecast UB apartment listings using local Unegui medians and 1212 statistics.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Scraped details CSV.")
    parser.add_argument("--stats-dir", default="Stats", help="Folder containing downloaded 1212 XLSX tables.")
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX, help="Output file prefix.")
    parser.add_argument("--local-weight", type=float, default=0.50, help="Fair-value weight for local Unegui medians.")
    parser.add_argument("--forecast-weight", type=float, default=0.45, help="Ranking weight for forecast upside.")
    parser.add_argument("--newness-weight", type=float, default=0.20, help="Ranking weight for building newness.")
    parser.add_argument("--price-weight", type=float, default=0.15, help="Ranking weight for current price per sqm.")
    parser.add_argument("--distance-weight", type=float, default=0.20, help="Ranking weight for Sukhbaatar Square distance.")
    parser.add_argument("--new-cutoff-year", type=int, default=DEFAULT_NEW_CUTOFF_YEAR, help="Built year treated as new or newer.")
    parser.add_argument(
        "--rooms-filter",
        type=int,
        default=DEFAULT_ROOMS_FILTER,
        help="Only rank this room count. Use 0 to rank all room counts.",
    )
    parser.add_argument(
        "--min-price-mnt",
        type=float,
        default=DEFAULT_MIN_PRICE_MNT,
        help="Minimum total price in MNT for ranked listings. Use 0 to disable.",
    )
    parser.add_argument(
        "--max-price-mnt",
        type=float,
        default=DEFAULT_MAX_PRICE_MNT,
        help="Maximum total price in MNT for ranked listings. Use 0 to disable.",
    )
    parser.add_argument(
        "--min-size-sqm",
        type=float,
        default=DEFAULT_MIN_SIZE_SQM,
        help="Exclusive minimum total area in sqm for ranked listings. Use 0 to disable.",
    )
    parser.add_argument("--min-growth", type=float, default=0.00, help="Minimum annual growth rate for base scenario.")
    parser.add_argument("--max-growth", type=float, default=0.20, help="Maximum annual growth rate for base scenario.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    build_forecast(
        input_path=args.input,
        output_prefix=args.output_prefix,
        stats_dir=args.stats_dir,
        local_weight=args.local_weight,
        forecast_weight=args.forecast_weight,
        newness_weight=args.newness_weight,
        price_weight=args.price_weight,
        distance_weight=args.distance_weight,
        new_cutoff_year=args.new_cutoff_year,
        rooms_filter=args.rooms_filter if args.rooms_filter > 0 else None,
        min_price_mnt=args.min_price_mnt if args.min_price_mnt > 0 else None,
        max_price_mnt=args.max_price_mnt if args.max_price_mnt > 0 else None,
        min_size_sqm=args.min_size_sqm if args.min_size_sqm > 0 else None,
        min_growth=args.min_growth,
        max_growth=args.max_growth,
    )


if __name__ == "__main__":
    main()
