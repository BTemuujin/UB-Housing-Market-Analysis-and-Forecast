from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

from scraper import parse_area_sqm


SUKHBAATAR_SQUARE_LAT = 47.918873
SUKHBAATAR_SQUARE_LON = 106.917701


AREA_COORDS = {
    # Central / near central
    "Сүхбаатар, Хороо 1": (47.9188, 106.9196),
    "Сүхбаатар, Хороо 2": (47.9138, 106.9219),
    "Сүхбаатар, Хороо 3": (47.9147, 106.9099),
    "Сүхбаатар, Хороо 4": (47.9174, 106.9052),
    "Сүхбаатар, Хороо 5": (47.9251, 106.9134),
    "Сүхбаатар, Хороо 6": (47.9258, 106.9209),
    "Сүхбаатар, Хороо 7": (47.9305, 106.9194),
    "Сүхбаатар, Хороо 8": (47.9286, 106.9097),
    "Сүхбаатар, Хороо 9": (47.9342, 106.9115),
    "Сүхбаатар, Хороо 10": (47.9383, 106.9192),
    "Сүхбаатар, Хороо 11": (47.9451, 106.9274),
    "Сүхбаатар, Хороо 12": (47.9527, 106.9315),
    "Чингэлтэй, Хороо 1": (47.9208, 106.9101),
    "Чингэлтэй, Хороо 2": (47.9245, 106.9092),
    "Чингэлтэй, Хороо 3": (47.9287, 106.9068),
    "Чингэлтэй, Хороо 4": (47.9318, 106.9005),
    "Чингэлтэй, Хороо 5": (47.9355, 106.8994),
    "Баянгол, Хороо 1": (47.9113, 106.8990),
    "Баянгол, Хороо 2": (47.9136, 106.8905),
    "Баянгол, Хороо 3": (47.9164, 106.8849),
    "Баянгол, Хороо 4": (47.9182, 106.8788),
    "Төмөр зам": (47.9112, 106.8892),
    "3, 4 хороолол": (47.9187, 106.8697),
    "10-р хороолол": (47.9140, 106.8581),
    "13-р хороолол": (47.9126, 106.9362),
    "15-р хороолол": (47.9128, 106.9465),
    "19-р хороолол": (47.9027, 106.8847),
    "11-р хороолол": (47.9350, 106.9270),
    "100 айл": (47.9296, 106.9160),
    "Дөлгөөн нуур": (47.9297, 106.9082),
    "Их тойруу": (47.9245, 106.9170),
    "Бөхийн өргөө": (47.9146, 106.9330),
    "Метро Молл": (47.9165, 106.9165),
    "Хүүхдийн 100": (47.9142, 106.9122),
    "Америкын элчин сайдын яам": (47.9265, 106.9250),
    "Сүхбаатарын талбай": (SUKHBAATAR_SQUARE_LAT, SUKHBAATAR_SQUARE_LON),
    "Баянбүрд": (47.9295, 106.9075),
    "Сэлх": (48.0000, 106.9450),
    # Khan-Uul
    "Зайсан": (47.8870, 106.9157),
    "King Tower": (47.8972, 106.9210),
    "River Garden": (47.8905, 106.9382),
    "Хүннү": (47.8977, 106.8537),
    "Яармаг": (47.8868, 106.8079),
    "Нисэх": (47.8644, 106.7661),
    "Био комбинат": (47.8134, 106.7104),
    "Хан-Уул, Хороо 3": (47.9006, 106.8897),
    "Хан-Уул, Хороо 4": (47.8875, 106.8074),
    "Хан-Уул, Хороо 6": (47.8777, 106.7878),
    "Хан-Уул, Хороо 8": (47.8759, 106.7651),
    "Хан-Уул, Хороо 11": (47.8877, 106.9162),
    "Хан-Уул, Хороо 14": (47.8721, 106.7259),
    "Хан-Уул, Хороо 15": (47.9023, 106.8959),
    "Хан-Уул, Хороо 17": (47.8924, 106.8758),
    "Хан-Уул, Хороо 18": (47.8947, 106.8425),
    "Хан-Уул, Хороо 23": (47.8836, 106.8082),
    # Bayanzurkh
    "Амгалан": (47.9130, 107.0001),
    "Баянмонгол хороолол": (47.9045, 106.9495),
    "Зүүн 4 зам": (47.9148, 106.9320),
    "Сансар": (47.9225, 106.9445),
    "Натур худалдааны төв": (47.9043, 106.9325),
    "Их Засаг Их сургууль": (47.9230, 106.9600),
    "Улаанхуаран": (47.9185, 106.9800),
    "16-р хороолол": (47.9120, 106.9650),
    "Нохойтой хөшөө": (47.9180, 106.9860),
    "Чулуун овоо": (47.9135, 106.9990),
    "Халдвартын эмнэлэг": (47.9040, 106.9510),
    "Үндэсний цэцэрлэгт хүрээлэн": (47.9033, 106.9295),
    "Баянзүрх, Хороо 1": (47.9193, 106.9412),
    "Баянзүрх, Хороо 2": (47.9230, 106.9430),
    "Баянзүрх, Хороо 3": (47.9204, 106.9519),
    "Баянзүрх, Хороо 4": (47.9158, 106.9478),
    "Баянзүрх, Хороо 5": (47.9145, 106.9562),
    "Баянзүрх, Хороо 6": (47.9129, 106.9620),
    "Баянзүрх, Хороо 8": (47.9174, 106.9811),
    "Баянзүрх, Хороо 11": (47.9320, 106.9960),
    "Баянзүрх, Хороо 13": (47.9061, 106.9536),
    "Баянзүрх, Хороо 14": (47.9084, 106.9362),
    "Баянзүрх, Хороо 15": (47.9123, 106.9318),
    "Баянзүрх, Хороо 16": (47.9189, 106.9698),
    "Баянзүрх, Хороо 18": (47.9047, 106.9462),
    "Баянзүрх, Хороо 21": (47.9568, 106.9872),
    "Баянзүрх, Хороо 22": (47.9301, 106.9572),
    "Баянзүрх, Хороо 25": (47.9049, 106.9293),
    "Баянзүрх, Хороо 26": (47.9050, 106.9439),
    "Баянзүрх, Хороо 29": (47.9210, 106.9930),
    "Баянзүрх, Хороо 36": (47.9027, 106.9635),
    "Баянзүрх, Хороо 38": (47.9278, 106.9802),
    "Гачуурт": (47.9134, 107.1710),
    # Songinokhairkhan
    "21-р хороолол": (47.9220, 106.8025),
    "Сонгинохайрхан, Хороо 1": (47.9288, 106.8340),
    "Сонгинохайрхан, Хороо 18": (47.9149, 106.8170),
    "Сонгинохайрхан, Хороо 19": (47.9156, 106.8098),
    "Сонгинохайрхан, Хороо 20": (47.9034, 106.7947),
    "Сонгинохайрхан, Хороо 32": (47.8728, 106.6922),
}

DISTRICT_COORDS = {
    "Сүхбаатар": (47.9285, 106.9190),
    "Чингэлтэй": (47.9330, 106.9060),
    "Баянгол": (47.9140, 106.8760),
    "Баянзүрх": (47.9150, 106.9560),
    "Хан-Уул": (47.8890, 106.8660),
    "Сонгинохайрхан": (47.9130, 106.7900),
}

COORD_RE = re.compile(r"(?<!\d)(4[67]\.\d{4,})[^\d]+(10[56]\.\d{4,})(?!\d)")
WORD_RE = re.compile(r"[^\w\u0400-\u04ff]+", flags=re.UNICODE)

NON_APARTMENT_KEYWORDS = (
    "газар",
    "газрын",
    "газартай",
    "gazar",
    "gazap",
    "газap",
    "газaр",
    "хашаа",
    "хаус",
    "таун хаус",
    "зуслан",
    "лагерь",
    "аос",
    "агуулах",
    "обьект",
    "объект",
    "үйлчилгээ",
    "оффис",
    "offis",
    "office",
    "гараж",
    "граж",
    "зогсоол",
    "хостел",
    "зочид буудал",
    "үйлдвэр",
    "салон",
    "ресторан",
    "павильон",
    "тэц",
)
APARTMENT_KEYWORDS = (
    "орон сууц",
    "байр",
    "apartment",
    "апартмент",
    "хотхон",
    "mkv",
    "мкв",
    "m2",
    "м2",
    "м²",
)
TITLE_NON_APARTMENT_KEYWORDS = (
    "газар",
    "газрын",
    "газартай",
    "gazar",
    "gazap",
    "газap",
    "газaр",
    "хашаа",
    "хаус",
    "таун хаус",
    "зуслан",
    "лагерь",
    "аос",
    "агуулах",
    "обьект",
    "объект",
    "үйлчилгээ",
    "оффис",
    "offis",
    "office",
    "хостел",
    "зочид буудал",
    "үйлдвэр",
    "салон",
    "ресторан",
    "павильон",
    "тэц",
)
PARKING_KEYWORDS = ("гараж", "граж", "зогсоол")
LAND_KEYWORDS = ("газар", "газрын", "газартай", "gazar", "gazap", "газap", "газaр")
HOUSE_KEYWORDS = ("хаус", "аос", "хашаа", "зуслан", "лагерь")
COMMERCIAL_KEYWORDS = (
    "агуулах",
    "обьект",
    "объект",
    "үйлчилгээ",
    "үйлдвэр",
    "салон",
    "ресторан",
    "павильон",
    "тэц",
    "хостел",
    "зочид буудал",
    "оффис",
    "offis",
    "office",
)


def clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower()
    text = WORD_RE.sub(" ", text)
    return " ".join(text.split())


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def extract_coordinates(row: pd.Series) -> tuple[float | None, float | None, str]:
    for column in ("detail_description", "description", "Website"):
        text = clean_text(row.get(column))
        match = COORD_RE.search(text)
        if match:
            return float(match.group(1)), float(match.group(2)), f"exact:{column}"

    sub_location = clean_text(row.get("sub_location"))
    if sub_location in AREA_COORDS:
        lat, lon = AREA_COORDS[sub_location]
        return lat, lon, "area_lookup"

    location = clean_text(row.get("location"))
    if location in AREA_COORDS:
        lat, lon = AREA_COORDS[location]
        return lat, lon, "area_lookup"

    district = clean_text(row.get("district"))
    if district in DISTRICT_COORDS:
        lat, lon = DISTRICT_COORDS[district]
        return lat, lon, "district_centroid"

    return None, None, "unknown"


def clean_rooms(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        rooms = int(float(value))
    except (TypeError, ValueError):
        return None
    if 1 <= rooms <= 10:
        return float(rooms)
    return None


def room_category(value: Any) -> str:
    rooms = clean_rooms(value)
    if rooms is None:
        return "unknown"
    rooms_int = int(rooms)
    if rooms_int >= 5:
        return "5+ rooms"
    return f"{rooms_int} room" if rooms_int == 1 else f"{rooms_int} rooms"


def property_category(row: pd.Series) -> str:
    listing_type = normalize_text(row.get("Төрөл"))
    title_only = normalize_text(f"{row.get('title', '')} {row.get('detail_title', '')}")
    full_text = normalize_text(f"{title_only} {row.get('detail_description', '')} {row.get('description', '')}")

    if listing_type:
        if any(keyword in listing_type for keyword in HOUSE_KEYWORDS):
            return "house"
        if any(keyword in listing_type for keyword in LAND_KEYWORDS):
            return "land"
        if any(keyword in listing_type for keyword in ("гараж", "граж", "зогсоол")):
            return "parking"
        return "commercial_or_other"

    has_title_apartment_signal = any(keyword in title_only for keyword in APARTMENT_KEYWORDS)
    if any(keyword in title_only for keyword in PARKING_KEYWORDS) and not has_title_apartment_signal:
        return "parking"
    if any(keyword in title_only for keyword in TITLE_NON_APARTMENT_KEYWORDS):
        if any(keyword in title_only for keyword in LAND_KEYWORDS) and "орон сууц" not in title_only:
            return "land"
        if any(keyword in title_only for keyword in HOUSE_KEYWORDS):
            return "house"
        if any(keyword in title_only for keyword in COMMERCIAL_KEYWORDS):
            return "commercial_or_other"
        return "commercial_or_other"
    if has_title_apartment_signal:
        return "apartment"

    has_floor_fields = pd.notna(row.get("Барилгын давхар")) or pd.notna(row.get("Хэдэн давхарт"))
    if has_floor_fields:
        return "apartment"

    if any(keyword in full_text for keyword in NON_APARTMENT_KEYWORDS):
        if any(keyword in full_text for keyword in LAND_KEYWORDS) and "орон сууц" not in full_text:
            return "land"
        if any(keyword in full_text for keyword in HOUSE_KEYWORDS):
            return "house"
        if any(keyword in full_text for keyword in PARKING_KEYWORDS):
            return "parking"
        if any(keyword in full_text for keyword in COMMERCIAL_KEYWORDS):
            return "commercial_or_other"
        return "commercial_or_other"

    if any(keyword in full_text for keyword in APARTMENT_KEYWORDS):
        return "apartment"

    return "unknown"


def as_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def first_area_from_columns(row: pd.Series, columns: tuple[str, ...]) -> float | None:
    for column in columns:
        area = parse_area_sqm(row.get(column))
        if area is not None and area > 0:
            return float(area)
    return None


def minimum_apartment_area(rooms: float | None) -> float:
    if rooms is None:
        return 12.0
    if rooms <= 1:
        return 15.0
    if rooms == 2:
        return 25.0
    if rooms == 3:
        return 40.0
    if rooms == 4:
        return 50.0
    return 60.0


def choose_size_sqm(row: pd.Series) -> tuple[float | None, str]:
    current = as_float(row.get("size_sqm")) or as_float(row.get("area_sqm"))
    title_area = first_area_from_columns(row, ("title", "detail_title"))
    text_area = first_area_from_columns(row, ("title", "detail_title", "description", "detail_description"))
    explicit_area = first_area_from_columns(row, ("Талбай", "Хэмжээ", "Газрын хэмжээ"))
    fallback_area = title_area or text_area or explicit_area

    rooms = clean_rooms(row.get("rooms_clean", row.get("rooms")))
    category = clean_text(row.get("property_category"))
    min_apartment_area = minimum_apartment_area(rooms)

    if title_area is not None:
        if current is None:
            return title_area, "title_area"
        if category == "apartment" and (current < min_apartment_area or current > 1_000):
            return title_area, "title_area_corrected_implausible_apartment_area"
        if current <= 10 and title_area >= 20:
            return title_area, "title_area_corrected_tiny_area"
        if current > 0 and (title_area / current >= 5 or current / title_area >= 20):
            return title_area, "title_area_corrected_conflicting_area"

    if text_area is not None:
        if current is None:
            return text_area, "text_area"
        if category == "apartment" and (current < min_apartment_area or current > 1_000):
            return text_area, "text_area_corrected_implausible_apartment_area"
        if current <= 5 and text_area >= 20:
            return text_area, "text_area_corrected_tiny_area"
        if current > 10_000 and text_area <= 10_000:
            return text_area, "text_area_corrected_huge_area"

    if current is None:
        return fallback_area, "fallback_area" if fallback_area is not None else "missing_area"
    if category == "apartment" and (current < 12 or current > 1_000):
        return None, "invalid_apartment_area"
    if category in {"house", "land", "commercial_or_other"} and current <= 5 and fallback_area is None:
        return None, "invalid_non_apartment_area"
    return current, "existing_area"


def round_optional(value: Any, digits: int = 1) -> Any:
    if value is None or pd.isna(value):
        return pd.NA
    return round(float(value), digits)


def make_group_key(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    return df[columns].apply(lambda row: "|".join(clean_text(value) for value in row), axis=1)


def duplicate_report(df: pd.DataFrame) -> pd.DataFrame:
    strict_cols = ["title_norm", "location_norm", "size_round", "rooms_clean", "price_mnt"]
    loose_cols = ["location_norm", "size_round", "rooms_clean", "price_mnt"]

    strict = df[df[strict_cols].notna().all(axis=1)].copy()
    strict["duplicate_type"] = "strict_title_location_size_rooms_price"
    strict["duplicate_group_key"] = make_group_key(strict, strict_cols)
    strict = strict[strict.duplicated("duplicate_group_key", keep=False)]

    loose = df[df[loose_cols].notna().all(axis=1)].copy()
    loose["duplicate_type"] = "loose_location_size_rooms_price"
    loose["duplicate_group_key"] = make_group_key(loose, loose_cols)
    loose = loose[loose.duplicated("duplicate_group_key", keep=False)]

    report = pd.concat([strict, loose], ignore_index=True)
    if report.empty:
        return report

    keep_cols = [
        "duplicate_type",
        "duplicate_group_key",
        "ad_id",
        "title",
        "price_mnt",
        "price_per_sqm",
        "location",
        "size_sqm",
        "rooms_clean",
        "seller",
        "published_text",
        "link",
    ]
    report["duplicate_group_size"] = report.groupby(["duplicate_type", "duplicate_group_key"])["ad_id"].transform("count")
    keep_cols.insert(2, "duplicate_group_size")
    return report.sort_values(["duplicate_type", "duplicate_group_key", "published_text"])[keep_cols]


def add_ranking_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["title_norm"] = df.get("title", "").map(normalize_text)
    df["location_norm"] = df.get("location", "").map(normalize_text)
    df["rooms_clean"] = df.get("rooms", pd.Series(pd.NA, index=df.index)).map(clean_rooms)
    df["room_category"] = df["rooms_clean"].map(room_category)
    df["property_category"] = df.apply(property_category, axis=1)

    if "size_sqm" in df.columns:
        df["size_sqm_raw"] = df["size_sqm"]
    if "area_sqm" in df.columns:
        df["area_sqm_raw"] = df["area_sqm"]

    size_results = df.apply(choose_size_sqm, axis=1, result_type="expand")
    size_results.columns = ["size_sqm", "size_sqm_source"]
    df[["size_sqm", "size_sqm_source"]] = size_results
    df["area_sqm"] = df["size_sqm"]
    df["size_round"] = df["size_sqm"].map(lambda value: round_optional(value, 1))

    if "price_per_sqm" in df.columns:
        df["price_per_sqm_raw"] = df["price_per_sqm"]
    price = pd.to_numeric(df.get("price_mnt"), errors="coerce")
    size = pd.to_numeric(df.get("size_sqm"), errors="coerce")
    df["price_per_sqm"] = (price / size).where((price > 0) & (size > 0))

    coords = df.apply(extract_coordinates, axis=1, result_type="expand")
    coords.columns = ["latitude", "longitude", "distance_source"]
    df[["latitude", "longitude", "distance_source"]] = coords
    df["distance_to_sukhbaatar_km"] = df.apply(
        lambda row: haversine_km(
            SUKHBAATAR_SQUARE_LAT,
            SUKHBAATAR_SQUARE_LON,
            row["latitude"],
            row["longitude"],
        )
        if pd.notna(row["latitude"]) and pd.notna(row["longitude"])
        else pd.NA,
        axis=1,
    )

    df["is_3_rooms"] = df["rooms_clean"].eq(3.0)
    df["room_penalty"] = df["rooms_clean"].map(
        lambda value: 0.0
        if value == 3.0
        else 0.5
        if value in (2.0, 4.0)
        else 1.0
    )

    valid_price = pd.to_numeric(df["price_per_sqm"], errors="coerce")
    valid_distance = pd.to_numeric(df["distance_to_sukhbaatar_km"], errors="coerce")
    df["price_score"] = valid_price.rank(pct=True, method="average", na_option="bottom")
    df["distance_score"] = valid_distance.rank(pct=True, method="average", na_option="bottom")
    df["best_score"] = 0.50 * df["price_score"] + 0.30 * df["distance_score"] + 0.20 * df["room_penalty"]

    strict_cols = ["title_norm", "location_norm", "size_round", "rooms_clean", "price_mnt"]
    loose_cols = ["location_norm", "size_round", "rooms_clean", "price_mnt"]
    strict_valid = df[strict_cols].notna().all(axis=1) & df["title_norm"].ne("") & df["location_norm"].ne("")
    loose_valid = df[loose_cols].notna().all(axis=1) & df["location_norm"].ne("")

    df["strict_duplicate_group_size"] = 1
    df["loose_duplicate_group_size"] = 1
    if strict_valid.any():
        strict_key = make_group_key(df.loc[strict_valid], strict_cols)
        df.loc[strict_valid, "strict_duplicate_group_size"] = strict_key.map(strict_key.value_counts()).to_numpy()
    if loose_valid.any():
        loose_key = make_group_key(df.loc[loose_valid], loose_cols)
        df.loc[loose_valid, "loose_duplicate_group_size"] = loose_key.map(loose_key.value_counts()).to_numpy()

    df["possible_duplicate"] = (df["strict_duplicate_group_size"] > 1) | (df["loose_duplicate_group_size"] > 1)

    return df


def order_for_review(df: pd.DataFrame) -> pd.DataFrame:
    priority = [
        "recommendation_rank",
        "best_score",
        "is_3_rooms",
        "price_per_sqm",
        "distance_to_sukhbaatar_km",
        "distance_source",
        "room_category",
        "rooms_clean",
        "property_category",
        "possible_duplicate",
        "strict_duplicate_group_size",
        "loose_duplicate_group_size",
        "ad_id",
        "title",
        "price",
        "price_mnt",
        "location",
        "district",
        "sub_location",
        "size_sqm",
        "listing_date",
        "seller",
        "link",
    ]
    cols = [col for col in priority if col in df.columns]
    cols.extend(col for col in df.columns if col not in cols)
    return df[cols]


def rank_listings(input_path: str | Path, output_prefix: str = "ranked_listings") -> None:
    input_path = Path(input_path)
    if not input_path.exists():
        raise SystemExit(f"CSV not found: {input_path}")

    df = pd.read_csv(input_path)
    ranked = add_ranking_columns(df)
    duplicate_rows = duplicate_report(ranked)

    candidate_mask = (
        ranked["price_per_sqm"].notna()
        & ranked["distance_to_sukhbaatar_km"].notna()
        & ranked["rooms_clean"].notna()
    )
    candidates = ranked[candidate_mask].copy()
    candidates = candidates.sort_values(
        ["is_3_rooms", "best_score", "price_per_sqm", "distance_to_sukhbaatar_km"],
        ascending=[False, True, True, True],
    )
    candidates["recommendation_rank"] = range(1, len(candidates) + 1)
    candidates = order_for_review(candidates)

    deduped = candidates.sort_values(["best_score", "listing_date"], ascending=[True, False])
    deduped = deduped.drop_duplicates(
        subset=["title_norm", "location_norm", "size_round", "rooms_clean", "price_mnt"],
        keep="first",
    )
    deduped = deduped.sort_values(
        ["is_3_rooms", "best_score", "price_per_sqm", "distance_to_sukhbaatar_km"],
        ascending=[False, True, True, True],
    )
    deduped["recommendation_rank"] = range(1, len(deduped) + 1)
    deduped = order_for_review(deduped)

    ranked_path = Path(f"{output_prefix}_ranked_all.csv")
    deduped_path = Path(f"{output_prefix}_ranked_deduped.csv")
    apartment_path = Path(f"{output_prefix}_ranked_3room_apartments.csv")
    duplicates_path = Path(f"{output_prefix}_duplicates.csv")
    summary_path = Path(f"{output_prefix}_summary.csv")

    apartment_3room = deduped[(deduped["is_3_rooms"]) & (deduped["property_category"].eq("apartment"))].copy()
    apartment_3room = apartment_3room.sort_values(
        ["best_score", "price_per_sqm", "distance_to_sukhbaatar_km"],
        ascending=[True, True, True],
    )
    apartment_3room["recommendation_rank"] = range(1, len(apartment_3room) + 1)
    apartment_3room = order_for_review(apartment_3room)

    candidates.to_csv(ranked_path, index=False, encoding="utf-8-sig")
    deduped.to_csv(deduped_path, index=False, encoding="utf-8-sig")
    apartment_3room.to_csv(apartment_path, index=False, encoding="utf-8-sig")
    duplicate_rows.to_csv(duplicates_path, index=False, encoding="utf-8-sig")

    summary = pd.DataFrame(
        [
            ("input_rows", len(df)),
            ("rankable_rows", len(candidates)),
            ("rankable_deduped_rows", len(deduped)),
            ("duplicate_ad_id_rows", int(df.duplicated("ad_id").sum()) if "ad_id" in df.columns else 0),
            ("duplicate_link_rows", int(df.duplicated("link").sum()) if "link" in df.columns else 0),
            ("possible_duplicate_rows", int(ranked["possible_duplicate"].sum())),
            ("duplicate_report_rows", len(duplicate_rows)),
            ("three_room_rankable_rows", int(candidates["is_3_rooms"].sum())),
            ("three_room_apartment_rows", len(apartment_3room)),
        ],
        columns=["metric", "value"],
    )
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    print(f"Input rows: {len(df)}")
    print(f"Rankable rows: {len(candidates)}")
    print(f"Rankable deduped rows: {len(deduped)}")
    print(f"Possible duplicate rows: {int(ranked['possible_duplicate'].sum())}")
    print(f"Duplicate report rows: {len(duplicate_rows)}")
    print(f"3-room rankable rows: {int(candidates['is_3_rooms'].sum())}")
    print(f"3-room apartment rows: {len(apartment_3room)}")
    print(f"Saved ranked list to {ranked_path}")
    print(f"Saved deduped ranked list to {deduped_path}")
    print(f"Saved 3-room apartment ranked list to {apartment_path}")
    print(f"Saved duplicate report to {duplicates_path}")
    print(f"Saved summary to {summary_path}")

    preview_cols = [
        "recommendation_rank",
        "best_score",
        "price_per_sqm",
        "distance_to_sukhbaatar_km",
        "room_category",
        "title",
        "price_mnt",
        "location",
        "size_sqm",
        "link",
    ]
    print("\nTop 15 deduped matches:")
    print(deduped[preview_cols].head(15).to_string(index=False))
    print("\nTop 15 3-room apartment matches:")
    print(apartment_3room[preview_cols].head(15).to_string(index=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank Unegui listings by price/sqm, distance, and room count.")
    parser.add_argument("--input", default="unegui_ub_50_pages_details.csv", help="Scraped details CSV.")
    parser.add_argument("--output-prefix", default="unegui_ranked", help="Prefix for output CSV files.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rank_listings(args.input, args.output_prefix)


if __name__ == "__main__":
    main()
