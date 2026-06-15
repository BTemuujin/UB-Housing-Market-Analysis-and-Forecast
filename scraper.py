from __future__ import annotations

import argparse
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from bs4.element import Tag


BASE_URL = (
    "https://www.unegui.mn/l-hdlh/l-hdlh-zarna/"
    "?cities=30&cities=1&cities=29&cities=35&cities=34&cities=32"
)
SITE_ROOT = "https://www.unegui.mn"
DEFAULT_OUTPUT = "unegui_data.csv"
DEFAULT_WORKERS = 1
_THREAD_LOCAL = threading.local()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "mn,en-US;q=0.9,en;q=0.8",
    "Referer": "https://www.unegui.mn/",
}

BLOCK_MARKERS = (
    "Just a moment...",
    "Enable JavaScript and cookies to continue",
    "/cdn-cgi/challenge-platform/",
    "cf-mitigated",
)

PRICE_RE = re.compile(
    r"(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>тэрбум|сая|мянга)?\s*₮?",
    flags=re.IGNORECASE,
)
ROOMS_RE = re.compile(r"(?<!\d)(?P<rooms>\d{1,2})\s*(?:өрөө|oroo|room)\b", re.IGNORECASE)
DIMENSION_RE = re.compile(
    r"(?P<width>\d+(?:[.,]\d+)?)\s*[xх*×]\s*(?P<height>\d+(?:[.,]\d+)?)\s*"
    r"(?:мкв|м\.кв|м2|м²|m2|m²)\b",
    re.IGNORECASE,
)
SQM_RE = re.compile(
    r"(?P<area>\d+(?:[.,]\d+)?)\s*(?:мкв|м\.кв|м2|м²|m2|m²)\b",
    re.IGNORECASE,
)
HECTARE_RE = re.compile(r"(?P<area>\d+(?:[.,]\d+)?)\s*(?:га|hectare|hectares)\b", re.IGNORECASE)
ISO_DATETIME_RE = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})(?:\s+(?P<time>\d{1,2}:\d{2}))?")
RELATIVE_RE = re.compile(
    r"(?P<count>\d+)\s*(?P<unit>минут|цаг|өдөр|хоног|долоо\s*хоног)[^\d]*өмнө",
    re.IGNORECASE,
)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def normalize_number(value: str) -> float | None:
    value = clean_text(value)
    if not value:
        return None

    if "," in value and "." not in value:
        left, right = value.rsplit(",", 1)
        value = left + right if len(right) == 3 else left + "." + right
    else:
        value = value.replace(",", "")

    try:
        return float(value)
    except ValueError:
        return None


def parse_price_values(price_text: Any) -> list[int]:
    text = clean_text(price_text).lower()
    if not text:
        return []

    values: list[int] = []
    for match in PRICE_RE.finditer(text):
        number = normalize_number(match.group("number"))
        if number is None:
            continue

        unit = (match.group("unit") or "").lower()
        multiplier = 1
        if unit == "мянга":
            multiplier = 1_000
        elif unit == "сая":
            multiplier = 1_000_000
        elif unit == "тэрбум":
            multiplier = 1_000_000_000

        values.append(int(round(number * multiplier)))

    return values


def first_price_value(price_text: Any) -> int | None:
    values = parse_price_values(price_text)
    return values[0] if values else None


def max_price_value(price_text: Any) -> int | None:
    values = parse_price_values(price_text)
    return max(values) if values else None


def parse_rooms(*texts: Any) -> int | None:
    for text in texts:
        cleaned = clean_text(text)
        if re.fullmatch(r"\d{1,2}", cleaned):
            return int(cleaned)

        match = ROOMS_RE.search(cleaned)
        if match:
            return int(match.group("rooms"))
    return None


def parse_area_sqm(*texts: Any) -> float | None:
    for text in texts:
        cleaned = clean_text(text)
        dimension_match = DIMENSION_RE.search(cleaned)
        if dimension_match:
            width = normalize_number(dimension_match.group("width"))
            height = normalize_number(dimension_match.group("height"))
            if width is not None and height is not None:
                return width * height

        match = SQM_RE.search(cleaned)
        if match:
            return normalize_number(match.group("area"))

        match = HECTARE_RE.search(cleaned)
        if match:
            area = normalize_number(match.group("area"))
            return area * 10_000 if area is not None else None

    return None


def positive_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def first_area_from_row(row: pd.Series, columns: tuple[str, ...]) -> float | None:
    for column in columns:
        area = parse_area_sqm(row.get(column))
        if area is not None and area > 0:
            return float(area)
    return None


def minimum_area_for_rooms(rooms: float | None) -> float:
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


def choose_area_sqm(row: pd.Series) -> float | None:
    current = positive_float(row.get("area_sqm")) or positive_float(row.get("size_sqm"))
    title_area = first_area_from_row(row, ("title", "detail_title"))
    text_area = first_area_from_row(row, ("title", "detail_title", "description", "detail_description"))

    rooms = positive_float(row.get("rooms"))
    min_area = minimum_area_for_rooms(rooms)

    if title_area is not None:
        if current is None:
            return title_area
        if current < min_area or current > 1_000:
            return title_area
        if current <= 10 and title_area >= 20:
            return title_area
        if current > 0 and (title_area / current >= 5 or current / title_area >= 20):
            return title_area

    if text_area is not None:
        if current is None:
            return text_area
        if current < min_area or current > 10_000:
            return text_area
        if current <= 5 and text_area >= 20:
            return text_area

    return current


def parse_listing_datetime(value: Any, now: datetime | None = None) -> tuple[str | None, str | None]:
    text = clean_text(value)
    if not text:
        return None, None

    now = now or datetime.now()
    iso_match = ISO_DATETIME_RE.search(text)
    if iso_match:
        date_part = iso_match.group("date")
        time_part = iso_match.group("time")
        if time_part:
            parsed = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M")
            return parsed.date().isoformat(), parsed.isoformat(timespec="minutes")
        parsed_date = datetime.strptime(date_part, "%Y-%m-%d").date()
        return parsed_date.isoformat(), None

    date_base: datetime | None = None
    if "Өчигдөр" in text:
        date_base = now - timedelta(days=1)
    elif "Өнөөдөр" in text:
        date_base = now
    else:
        relative_match = RELATIVE_RE.search(text)
        if relative_match:
            count = int(relative_match.group("count"))
            unit = relative_match.group("unit").replace(" ", "").lower()
            if unit.startswith("минут"):
                date_base = now - timedelta(minutes=count)
            elif unit.startswith("цаг"):
                date_base = now - timedelta(hours=count)
            elif unit.startswith(("өдөр", "хоног")):
                date_base = now - timedelta(days=count)
            elif unit.startswith("долоохоног"):
                date_base = now - timedelta(weeks=count)

    if date_base is None:
        return None, None

    time_match = re.search(r"(?P<time>\d{1,2}:\d{2})", text)
    if time_match:
        hour, minute = [int(part) for part in time_match.group("time").split(":", 1)]
        date_base = date_base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return date_base.date().isoformat(), date_base.isoformat(timespec="minutes")

    return date_base.date().isoformat(), None


def split_location(location: Any) -> tuple[str | None, str | None]:
    cleaned = clean_text(location).replace("УБ —", "").strip(" ,-")
    if not cleaned:
        return None, None

    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if len(parts) == 1:
        return parts[0], None
    return parts[0], ", ".join(parts[1:])


def absolute_url(href: str | None, base_url: str = SITE_ROOT) -> str:
    if not href:
        return ""
    return urljoin(base_url, href)


def page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}page={page}"


def extract_ad_id(url: str) -> str | None:
    match = re.search(r"/adv/(\d+)", url)
    return match.group(1) if match else None


def select_text(node: Tag | BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        tag = node.select_one(selector)
        if tag:
            text = clean_text(tag.get_text(" ", strip=True))
            if text:
                return text
    return ""


def select_tag(node: Tag | BeautifulSoup, selectors: list[str]) -> Tag | None:
    for selector in selectors:
        tag = node.select_one(selector)
        if isinstance(tag, Tag):
            return tag
    return None


def select_attr(node: Tag | BeautifulSoup, selectors: list[str], attr: str) -> str:
    for selector in selectors:
        tag = node.select_one(selector)
        if tag and tag.has_attr(attr):
            value = clean_text(tag.get(attr))
            if value:
                return value
    return ""


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def get_thread_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = make_session()
        _THREAD_LOCAL.session = session
    return session


def is_blocked_response(response: requests.Response) -> bool:
    if response.headers.get("cf-mitigated") == "challenge":
        return True
    body_head = response.text[:10_000]
    return any(marker in body_head for marker in BLOCK_MARKERS)


def fetch_html(session: requests.Session, url: str, timeout: int = 20) -> str:
    response = session.get(url, timeout=timeout)
    if is_blocked_response(response):
        raise RuntimeError(
            "Unegui returned a Cloudflare challenge page instead of listing HTML. "
            "This script does not bypass bot checks; use it only where you have "
            "authorized access to the normal public HTML, or ask the site for an "
            "API/data export."
        )
    response.raise_for_status()
    return response.text


def fetch_url(url: str, min_delay: float = 0.0, max_delay: float = 0.0) -> str:
    sleep_between_requests(min_delay, max_delay)
    return fetch_html(get_thread_session(), url)


def discover_max_page(soup: BeautifulSoup) -> int | None:
    pages: set[int] = set()
    for link in soup.select('a[href*="page="]'):
        href = link.get("href")
        if not href:
            continue
        query = parse_qs(urlparse(href).query)
        for value in query.get("page", []):
            if value.isdigit():
                pages.add(int(value))

    for link in soup.select("a"):
        text = clean_text(link.get_text())
        if text.isdigit():
            pages.add(int(text))

    return max(pages) if pages else None


def has_listing_link(node: Tag) -> bool:
    return node.select_one('a[href*="/adv/"]') is not None


def find_listing_nodes(soup: BeautifulSoup) -> list[Tag]:
    selectors = [
        "div.advert.js-item-listing",
        "[data-id].js-item-listing",
        "div.advert",
        "div.list-announcement-block",
        "li.announcement-container",
        "div.announcement-block",
        "article.announcement-block",
        'div[class*="announcement-block"]',
    ]

    for selector in selectors:
        nodes = [node for node in soup.select(selector) if isinstance(node, Tag) and has_listing_link(node)]
        if nodes:
            return dedupe_nodes(nodes)

    nodes: list[Tag] = []
    for link in soup.select('a.announcement-block__title[href*="/adv/"], a[itemprop="name"][href*="/adv/"]'):
        parent: Tag | None = link if isinstance(link, Tag) else None
        for _ in range(6):
            if parent is None or parent.parent is None or not isinstance(parent.parent, Tag):
                break
            parent = parent.parent
            classes = " ".join(parent.get("class", []))
            if "announcement" in classes:
                nodes.append(parent)
                break
        else:
            if isinstance(link.parent, Tag):
                nodes.append(link.parent)

    return dedupe_nodes(nodes)


def dedupe_nodes(nodes: list[Tag]) -> list[Tag]:
    seen: set[int] = set()
    unique: list[Tag] = []
    for node in nodes:
        marker = id(node)
        if marker not in seen:
            seen.add(marker)
            unique.append(node)
    return unique


def parse_listing_node(node: Tag, source_url: str, page: int) -> dict[str, Any] | None:
    link_tag = select_tag(
        node,
        [
            'a.advert__content-title[href*="/adv/"]',
            'a.announcement-block__title[href*="/adv/"]',
            'a[itemprop="name"][href*="/adv/"]',
            'a[href*="/adv/"]',
        ],
    )
    if not isinstance(link_tag, Tag):
        return None

    link = absolute_url(link_tag.get("href"), source_url)
    title = clean_text(link_tag.get_text(" ", strip=True))

    meta_price = select_attr(node, ['meta[itemprop="price"]'], "content")
    price_text = meta_price or select_text(
        node,
        [
            ".advert__content-price",
            ".announcement-block__price",
            ".announcement-price",
            '[class*="price"]',
            '[itemprop="price"]',
        ],
    )

    date_text = select_text(
        node,
        [
            ".advert__content-date",
            ".announcement-block__date",
            ".announcement-date",
            '[class*="date"]',
            "time",
        ],
    )
    location = select_text(
        node,
        [
            ".advert__content-place",
            ".announcement-block__location",
            ".announcement-block__address",
            '[class*="location"]',
            '[class*="address"]',
        ],
    )
    description = select_text(
        node,
        [
            ".advert__content-description",
            ".announcement-block__description",
            '[class*="description"]',
        ],
    )
    seller = select_text(node, [".advert__header-name", '[class*="seller"]', '[class*="author"]'])
    badges = clean_text(" ".join(tag.get_text(" ", strip=True) for tag in node.select(".advert__body-sticker")))
    image_count = select_attr(node, [".js-active-index-swiper"], "data-count")

    if not title and not link:
        return None

    row: dict[str, Any] = {
        "ad_id": extract_ad_id(link) or clean_text(node.get("data-id")),
        "title": title,
        "price_text": price_text,
        "price_mnt": first_price_value(price_text),
        "price_mnt_max": max_price_value(price_text),
        "date_text": date_text,
        "location": location,
        "description": description,
        "seller": seller,
        "badges": badges,
        "image_count": int(image_count) if image_count.isdigit() else None,
        "link": link,
        "source_page": page,
        "source_url": source_url,
    }
    row["rooms"] = parse_rooms(title, description)
    row["area_sqm"] = parse_area_sqm(title, description)
    row["district"], row["sub_location"] = split_location(location)
    return row


def parse_listing_page(html: str, source_url: str, page: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for node in find_listing_nodes(soup):
        row = parse_listing_node(node, source_url, page)
        if row:
            rows.append(row)
    return rows


def parse_detail_page(html: str, url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text("\n", strip=True)

    detail: dict[str, Any] = {
        "detail_title": select_text(soup, ["h1", '[itemprop="name"]']),
        "detail_price_text": select_attr(soup, ['meta[itemprop="price"]'], "content")
        or select_text(soup, [".announcement-price__cost", ".announcement-price", '[class*="price"]']),
        "detail_description": select_text(
            soup,
            [
                '[itemprop="description"]',
                ".announcement-description",
                ".announcement__description",
                '[class*="description"]',
            ],
        ),
        "detail_url": url,
    }

    ad_id_match = re.search(r"Зарын дугаар:\s*(\d+)", page_text)
    if ad_id_match:
        detail["detail_ad_id"] = ad_id_match.group(1)

    published_match = re.search(r"Нийтэлсэн:\s*([^\n]+)", page_text)
    if published_match:
        detail["published_text"] = clean_text(published_match.group(1))

    for item in soup.select("li"):
        text = clean_text(item.get_text(" ", strip=True))
        if ":" not in text or len(text) > 160:
            continue
        key, value = [part.strip() for part in text.split(":", 1)]
        if key and value:
            detail[key] = value

    return detail


def sleep_between_requests(min_delay: float, max_delay: float) -> None:
    if max_delay <= 0 and min_delay <= 0:
        return
    if max_delay <= 0:
        max_delay = min_delay
    if min_delay > max_delay:
        min_delay, max_delay = max_delay, min_delay
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = normalize_columns(df.copy())

    if "price_mnt" not in df.columns:
        df["price_mnt"] = pd.NA
    if "price_mnt_max" not in df.columns:
        df["price_mnt_max"] = pd.NA

    for price_column in ("price_text", "detail_price_text"):
        if price_column in df.columns:
            df["price_mnt"] = df["price_mnt"].fillna(df[price_column].map(first_price_value))
            df["price_mnt_max"] = df["price_mnt_max"].fillna(df[price_column].map(max_price_value))

    for column in ("price_mnt", "price_mnt_max", "rooms", "area_sqm"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    text_columns = [
        column
        for column in (
            "title",
            "description",
            "detail_title",
            "detail_description",
            "Талбай",
            "Хэмжээ",
            "Газрын хэмжээ",
            "Өрөө",
            "Өрөөний тоо",
            "Хэдэн өрөө",
        )
        if column in df.columns
    ]
    if text_columns:
        combined_text = df[text_columns].fillna("").astype(str).agg(" ".join, axis=1)
    else:
        combined_text = pd.Series("", index=df.index)

    explicit_room_columns = [column for column in ("Өрөө", "Өрөөний тоо", "Хэдэн өрөө") if column in df.columns]
    explicit_rooms = pd.Series(pd.NA, index=df.index)
    for column in explicit_room_columns:
        explicit_rooms = explicit_rooms.fillna(df[column].map(parse_rooms))

    if "rooms" not in df.columns:
        df["rooms"] = pd.NA
    df["rooms"] = pd.to_numeric(df["rooms"], errors="coerce")
    if explicit_room_columns:
        explicit_rooms = pd.to_numeric(explicit_rooms, errors="coerce")
        df["rooms"] = df["rooms"].where(explicit_rooms.isna(), explicit_rooms)
    df["rooms"] = df["rooms"].fillna(combined_text.map(parse_rooms))

    explicit_area_columns = [column for column in ("Талбай", "Хэмжээ", "Газрын хэмжээ") if column in df.columns]
    explicit_area = pd.Series(pd.NA, index=df.index)
    for column in explicit_area_columns:
        explicit_area = explicit_area.fillna(df[column].map(parse_area_sqm))

    if "area_sqm" not in df.columns:
        df["area_sqm"] = pd.NA
    df["area_sqm"] = pd.to_numeric(df["area_sqm"], errors="coerce")
    if explicit_area_columns:
        explicit_area = pd.to_numeric(explicit_area, errors="coerce")
        df["area_sqm"] = df["area_sqm"].where(explicit_area.isna(), explicit_area)
    df["area_sqm"] = df["area_sqm"].fillna(combined_text.map(parse_area_sqm))
    df["area_sqm"] = df.apply(choose_area_sqm, axis=1)

    if "location" in df.columns:
        parsed_locations = df["location"].map(split_location)
        if "district" not in df.columns:
            df["district"] = parsed_locations.map(lambda value: value[0])
        else:
            df["district"] = df["district"].fillna(parsed_locations.map(lambda value: value[0]))
        if "sub_location" not in df.columns:
            df["sub_location"] = parsed_locations.map(lambda value: value[1])
        else:
            df["sub_location"] = df["sub_location"].fillna(parsed_locations.map(lambda value: value[1]))

    if "price_mnt" in df.columns and "area_sqm" in df.columns:
        price = pd.to_numeric(df["price_mnt"], errors="coerce")
        area = pd.to_numeric(df["area_sqm"], errors="coerce")
        df["price_per_sqm"] = (price / area).where((price > 0) & (area > 0))

    if "price" not in df.columns:
        df["price"] = ""
    for price_column in ("price_text", "detail_price_text"):
        if price_column in df.columns:
            df["price"] = df["price"].replace("", pd.NA).fillna(df[price_column])

    if "area_sqm" in df.columns:
        df["size_sqm"] = df["area_sqm"]
    elif "size_sqm" not in df.columns:
        df["size_sqm"] = pd.NA

    if "listing_date" not in df.columns:
        df["listing_date"] = ""
    for date_column in ("published_text", "date_text"):
        if date_column in df.columns:
            df["listing_date"] = df["listing_date"].replace("", pd.NA).fillna(df[date_column])

    parsed_dates = df["listing_date"].map(parse_listing_datetime)
    if "listing_date_iso" not in df.columns:
        df["listing_date_iso"] = parsed_dates.map(lambda value: value[0])
    else:
        df["listing_date_iso"] = df["listing_date_iso"].fillna(parsed_dates.map(lambda value: value[0]))
    if "listing_datetime_iso" not in df.columns:
        df["listing_datetime_iso"] = parsed_dates.map(lambda value: value[1])
    else:
        df["listing_datetime_iso"] = df["listing_datetime_iso"].fillna(parsed_dates.map(lambda value: value[1]))

    return df


def order_columns(df: pd.DataFrame) -> pd.DataFrame:
    priority_columns = [
        "ad_id",
        "title",
        "price",
        "price_mnt",
        "price_mnt_max",
        "location",
        "district",
        "sub_location",
        "size_sqm",
        "area_sqm",
        "rooms",
        "listing_date",
        "listing_date_iso",
        "listing_datetime_iso",
        "date_text",
        "published_text",
        "seller",
        "badges",
        "image_count",
        "price_per_sqm",
        "link",
        "source_page",
        "source_url",
    ]
    ordered = [column for column in priority_columns if column in df.columns]
    ordered.extend(column for column in df.columns if column not in ordered)
    return df[ordered]


def required_field_report(df: pd.DataFrame) -> pd.Series:
    required_columns = {
        "price": "price_mnt",
        "location": "location",
        "size": "size_sqm",
        "rooms": "rooms",
        "listing_date": "listing_date",
    }
    report: dict[str, str] = {}
    total = len(df)
    for label, column in required_columns.items():
        if column not in df.columns:
            report[label] = f"0/{total} (missing column {column})"
            continue
        present = df[column].notna()
        if df[column].dtype == object:
            present = present & df[column].astype(str).str.strip().ne("")
        count = int(present.sum())
        percent = (count / total * 100) if total else 0
        report[label] = f"{count}/{total} ({percent:.1f}%)"
    return pd.Series(report)


def print_required_field_report(df: pd.DataFrame) -> None:
    print("Required field coverage:")
    print(required_field_report(df).to_string())


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "Title": "title",
        "Price": "price_text",
        "Date_Location": "date_location",
        "Link": "link",
    }
    return df.rename(columns={key: value for key, value in rename_map.items() if key in df.columns})


def fetch_listing_page(
    base_url: str,
    page: int,
    min_delay: float = 0.0,
    max_delay: float = 0.0,
) -> tuple[int, str, list[dict[str, Any]], str | None, BeautifulSoup | None]:
    url = page_url(base_url, page)
    try:
        html = fetch_url(url, min_delay=min_delay, max_delay=max_delay)
        soup = BeautifulSoup(html, "html.parser")
        rows = parse_listing_page(html, url, page)
        for index, row in enumerate(rows):
            row["_source_index"] = index
        return page, url, rows, None, soup
    except (requests.RequestException, RuntimeError) as exc:
        return page, url, [], str(exc), None


def fetch_listing_detail(
    row: dict[str, Any],
    min_delay: float = 0.0,
    max_delay: float = 0.0,
) -> tuple[dict[str, Any], str | None]:
    link = row.get("link", "")
    if not link:
        return row, "missing detail link"

    try:
        detail_html = fetch_url(link, min_delay=min_delay, max_delay=max_delay)
        row.update(parse_detail_page(detail_html, link))
        return row, None
    except (requests.RequestException, RuntimeError) as exc:
        row["detail_error"] = str(exc)
        return row, str(exc)


def scrape_unegui(
    base_url: str = BASE_URL,
    max_pages: int | None = 3,
    output_path: str | Path = DEFAULT_OUTPUT,
    include_details: bool = False,
    min_delay: float = 0.0,
    max_delay: float = 0.0,
    workers: int = DEFAULT_WORKERS,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    seen_links: set[str] = set()
    workers = max(1, int(workers))
    target_pages = max_pages
    page_delay = 0.0 if workers > 1 else min_delay
    detail_delay = min_delay

    print(f"Using {workers} worker(s).")

    pages_to_fetch: list[int]
    if target_pages is None:
        print(f"Scraping page 1: {page_url(base_url, 1)}")
        page, url, page_rows, error, soup = fetch_listing_page(base_url, 1)
        if error:
            print(f"Request failed on page {page}: {error}")
            page_rows = []
            pages_to_fetch = []
        else:
            target_pages = discover_max_page(soup) if soup is not None else 1
            target_pages = target_pages or 1
            print(f"Discovered {target_pages} pages.")
            print(f"  page {page}: found {len(page_rows)} listings")
            for row in page_rows:
                link = row.get("link", "")
                if link in seen_links:
                    continue
                seen_links.add(link)
                rows.append(row)
            pages_to_fetch = list(range(2, target_pages + 1))
    else:
        pages_to_fetch = list(range(1, target_pages + 1))

    if pages_to_fetch:
        print(f"Scraping {len(pages_to_fetch)} listing page(s) with {workers} worker(s)...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(fetch_listing_page, base_url, page, page_delay, max_delay): page
                for page in pages_to_fetch
            }
            completed = 0
            for future in as_completed(futures):
                completed += 1
                page, url, page_rows, error, _soup = future.result()
                if error:
                    print(f"  page {page}: request failed: {error}")
                    continue
                if not page_rows:
                    print(f"  page {page}: no listings found")
                    continue
                for row in page_rows:
                    link = row.get("link", "")
                    if link in seen_links:
                        continue
                    seen_links.add(link)
                    rows.append(row)
                print(
                    f"  page {page}: found {len(page_rows)} listings "
                    f"({completed}/{len(pages_to_fetch)} pages done; {len(rows)} unique rows)"
                )

    rows.sort(key=lambda row: (row.get("source_page") or 0, row.get("_source_index") or 0))

    if include_details and rows:
        detail_total = sum(1 for row in rows if row.get("link"))
        print(f"Fetching {detail_total} detail page(s) with {workers} worker(s)...")
        detail_errors = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(fetch_listing_detail, row, detail_delay, max_delay): index
                for index, row in enumerate(rows)
                if row.get("link")
            }
            completed = 0
            for future in as_completed(futures):
                completed += 1
                _row, error = future.result()
                if error:
                    detail_errors += 1
                if completed == detail_total or completed % 50 == 0:
                    print(f"  details: {completed}/{detail_total} done; errors: {detail_errors}")

    for row in rows:
        row.pop("_source_index", None)

    df = order_columns(enrich_dataframe(pd.DataFrame(rows)))
    if not df.empty:
        output_path = Path(output_path)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"Saved {len(df)} rows to {output_path}")
        print_required_field_report(df)
    else:
        print("No data was extracted.")
    return df


def format_mnt(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} тэрбум ₮"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f} сая ₮"
    return f"{value:,.0f} ₮"


def analyze_csv(input_path: str | Path, output_prefix: str = "unegui_analysis") -> None:
    input_path = Path(input_path)
    if not input_path.exists():
        raise SystemExit(f"CSV not found: {input_path}")

    df = pd.read_csv(input_path)
    df = order_columns(enrich_dataframe(df))

    cleaned_path = Path(f"{output_prefix}_cleaned.csv")
    df.to_csv(cleaned_path, index=False, encoding="utf-8-sig")

    print(f"Rows: {len(df)}")
    print_required_field_report(df)
    if "price_mnt" in df.columns:
        price = pd.to_numeric(df["price_mnt"], errors="coerce")
        print(f"Rows with price: {price.notna().sum()}")
        print(f"Median price: {format_mnt(price.median())}")
        print(f"Mean price: {format_mnt(price.mean())}")

    if "district" in df.columns:
        summary = (
            df.groupby("district", dropna=True)
            .agg(
                listings=("title", "count") if "title" in df.columns else ("district", "count"),
                median_price_mnt=("price_mnt", "median") if "price_mnt" in df.columns else ("district", "count"),
                mean_price_mnt=("price_mnt", "mean") if "price_mnt" in df.columns else ("district", "count"),
                median_price_per_sqm=("price_per_sqm", "median")
                if "price_per_sqm" in df.columns
                else ("district", "count"),
            )
            .sort_values(["listings"], ascending=False)
        )
        summary_path = Path(f"{output_prefix}_by_district.csv")
        summary.to_csv(summary_path, encoding="utf-8-sig")
        print(f"Saved district summary to {summary_path}")
        print(summary.head(10).to_string())

    if "rooms" in df.columns:
        room_summary = (
            df.dropna(subset=["rooms"])
            .groupby("rooms")
            .agg(
                listings=("rooms", "count"),
                median_price_mnt=("price_mnt", "median") if "price_mnt" in df.columns else ("rooms", "count"),
                median_area_sqm=("area_sqm", "median") if "area_sqm" in df.columns else ("rooms", "count"),
            )
            .sort_index()
        )
        room_path = Path(f"{output_prefix}_by_rooms.csv")
        room_summary.to_csv(room_path, encoding="utf-8-sig")
        print(f"Saved room summary to {room_path}")

    print(f"Saved cleaned data to {cleaned_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape Unegui real-estate sale listings and create basic analysis CSVs."
    )
    parser.add_argument("--url", default=BASE_URL, help="Category URL to scrape.")
    parser.add_argument("--max-pages", type=int, default=3, help="Number of listing pages to scrape.")
    parser.add_argument(
        "--all-pages",
        action="store_true",
        help="Discover pagination from page 1 and scrape every listed page.",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="CSV path for scraped listings.")
    parser.add_argument(
        "--details",
        action="store_true",
        help="Also fetch each detail page. This is much slower and creates many requests.",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Concurrent request workers.")
    parser.add_argument("--min-delay", type=float, default=0.0, help="Minimum per-request delay.")
    parser.add_argument("--max-delay", type=float, default=0.0, help="Maximum per-request delay.")
    parser.add_argument("--analyze", action="store_true", help="Run analysis after scraping.")
    parser.add_argument("--analysis-only", help="Skip scraping and analyze an existing CSV.")
    parser.add_argument("--analysis-prefix", default="unegui_analysis", help="Prefix for analysis outputs.")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.analysis_only:
        analyze_csv(args.analysis_only, args.analysis_prefix)
        return

    max_pages = None if args.all_pages else args.max_pages
    scrape_unegui(
        base_url=args.url,
        max_pages=max_pages,
        output_path=args.output,
        include_details=args.details,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        workers=args.workers,
    )

    if args.analyze:
        analyze_csv(args.output, args.analysis_prefix)


if __name__ == "__main__":
    main()
