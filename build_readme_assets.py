from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Iterable

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

try:
    import plotly.graph_objects as go
except Exception:  # pragma: no cover - optional dependency for local README asset generation
    go = None


ROOT = Path(__file__).resolve().parent
DEFAULT_REGION_CSV = ROOT / "unegui_ub_all_stats_apartment_region_stats.csv"
DEFAULT_TOP10_CSV = ROOT / "unegui_ub_all_3room_filtered_forecast_top10.csv"
DEFAULT_MAP_HTML = ROOT / "unegui_ub_all_stats_apartment_price_per_sqm_map.html"
DEFAULT_OUT_DIR = ROOT / "assets"


def clean_text(value: object, max_len: int | None = None) -> str:
    if value is None or pd.isna(value):
        return ""
    text = " ".join(str(value).replace("\r", " ").replace("\n", " ").split())
    if max_len and len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def safe_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def fmt_money(value: object) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return ""
    if abs(parsed) >= 1_000_000:
        return f"{parsed / 1_000_000:.2f}M MNT"
    return f"{parsed:,.0f} MNT"


def fmt_pct(value: object, digits: int = 1) -> str:
    parsed = safe_float(value)
    if parsed is None:
        return ""
    return f"{parsed * 100:.{digits}f}%"


def load_font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


FONT_TITLE = load_font(44)
FONT_SUB = load_font(24)
FONT_HEAD = load_font(28)
FONT_BODY = load_font(20)
FONT_SMALL = load_font(16)
FONT_TINY = load_font(14)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = clean_text(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if text_size(draw, candidate, font)[0] <= max_width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int = 6,
    max_lines: int | None = None,
) -> int:
    lines = wrap_text(draw, text, font, max_width)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".") + "..."
    current_y = y
    line_height = text_size(draw, "Ag", font)[1] + line_gap
    for line in lines:
        draw.text((x, current_y), line, font=font, fill=fill)
        current_y += line_height
    return current_y


def lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def blend_color(stops: list[tuple[float, tuple[int, int, int]]], value: float) -> tuple[int, int, int]:
    value = max(0.0, min(1.0, value))
    if value <= stops[0][0]:
        return stops[0][1]
    if value >= stops[-1][0]:
        return stops[-1][1]
    for (left_pos, left_rgb), (right_pos, right_rgb) in zip(stops, stops[1:]):
        if left_pos <= value <= right_pos:
            span = right_pos - left_pos or 1.0
            t = (value - left_pos) / span
            return (
                lerp(left_rgb[0], right_rgb[0], t),
                lerp(left_rgb[1], right_rgb[1], t),
                lerp(left_rgb[2], right_rgb[2], t),
            )
    return stops[-1][1]


MAP_STOPS = [
    (0.0, (30, 64, 175)),
    (0.25, (14, 165, 233)),
    (0.5, (16, 185, 129)),
    (0.75, (245, 158, 11)),
    (1.0, (239, 68, 68)),
]


def price_color(value: float, minimum: float, maximum: float) -> tuple[int, int, int]:
    if maximum <= minimum:
        return MAP_STOPS[-1][1]
    return blend_color(MAP_STOPS, (value - minimum) / (maximum - minimum))


def draw_panel_frame(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str = "#ffffff") -> None:
    draw.rounded_rectangle(box, radius=28, fill=fill, outline="#dbe2ea", width=2)


def split_plotly_newplot_args(html_text: str) -> list[str]:
    marker = "Plotly.newPlot("
    start = html_text.find(marker)
    if start == -1:
        raise ValueError("Could not find Plotly.newPlot call in HTML file.")

    segment = html_text[start + len(marker) :]
    args: list[str] = []
    current: list[str] = []
    depth = 0
    string_delim: str | None = None
    escape = False

    for ch in segment:
        if string_delim is not None:
            current.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == string_delim:
                string_delim = None
            continue

        if ch in ('"', "'"):
            string_delim = ch
            current.append(ch)
            continue
        if ch in "[{(":
            depth += 1
            current.append(ch)
            continue
        if ch in "]})":
            depth -= 1
            current.append(ch)
            if depth == 0 and ch == ")":
                break
            continue
        if ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
            continue
        current.append(ch)

    if current:
        args.append("".join(current).strip())

    return args


def render_actual_html_map_cover(
    html_path: Path,
    output_path: Path,
    chrome_path: str | None = None,
) -> None:
    if go is None:
        raise RuntimeError("plotly is not available")
    if not html_path.exists():
        raise FileNotFoundError(html_path)

    html_text = html_path.read_text(encoding="utf-8")
    args = split_plotly_newplot_args(html_text)
    if len(args) < 3:
        raise ValueError("Could not parse Plotly figure JSON from HTML.")

    data = json.loads(args[1])
    layout = json.loads(args[2].rstrip(")"))

    if chrome_path:
        chrome = Path(chrome_path)
        chrome_dir = chrome if chrome.is_dir() else chrome.parent
        os.environ["PATH"] = f"{chrome_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    fig = go.Figure(data=data, layout=layout)
    fig.write_image(str(output_path), width=1600, height=1000, scale=1)


def convex_hull(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique

    def cross(o: tuple[int, int], a: tuple[int, int], b: tuple[int, int]) -> int:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[int, int]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[int, int]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def draw_schematic_map_cover(region_df: pd.DataFrame, output_path: Path) -> None:
    df = region_df.dropna(subset=["latitude", "longitude", "median_price_per_sqm"]).copy()
    if df.empty:
        raise SystemExit("Region stats file has no usable coordinates.")

    width, height = 1600, 1000
    image = Image.new("RGB", (width, height), "#f7f9fc")
    draw = ImageDraw.Draw(image)

    draw.text((60, 42), "Unegui UB apartment price map", font=FONT_TITLE, fill="#111827")
    draw.text(
        (60, 96),
        "Median asking price per sqm by region, with sample size represented by point size",
        font=FONT_SUB,
        fill="#4b5563",
    )

    map_box = (50, 150, 1070, 930)
    legend_box = (1100, 150, 1550, 930)
    draw_panel_frame(draw, map_box)
    draw_panel_frame(draw, legend_box)

    lon_min = float(df["longitude"].min())
    lon_max = float(df["longitude"].max())
    lat_min = float(df["latitude"].min())
    lat_max = float(df["latitude"].max())
    lon_pad = max(0.012, (lon_max - lon_min) * 0.08)
    lat_pad = max(0.012, (lat_max - lat_min) * 0.08)
    lon_min -= lon_pad
    lon_max += lon_pad
    lat_min -= lat_pad
    lat_max += lat_pad

    left, top, right, bottom = map_box
    plot_left = left + 58
    plot_top = top + 42
    plot_right = right - 36
    plot_bottom = bottom - 86

    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = int(plot_top + (plot_bottom - plot_top) * frac)
        draw.line((plot_left, y, plot_right, y), fill="#e8edf3", width=1)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = int(plot_left + (plot_right - plot_left) * frac)
        draw.line((x, plot_top, x, plot_bottom), fill="#e8edf3", width=1)

    def transform(lon: float, lat: float) -> tuple[int, int]:
        x = plot_left + (lon - lon_min) / (lon_max - lon_min) * (plot_right - plot_left)
        y = plot_bottom - (lat - lat_min) / (lat_max - lat_min) * (plot_bottom - plot_top)
        return int(round(x)), int(round(y))

    point_pixels = [transform(float(row["longitude"]), float(row["latitude"])) for _, row in df.iterrows()]
    hull = convex_hull(point_pixels)

    if len(hull) >= 3:
        draw.polygon(hull, fill="#eef2f7", outline="#cbd5e1")
        draw.line(hull + [hull[0]], fill="#cbd5e1", width=2)

    draw.text((plot_left + 24, plot_top + 14), "Ulaanbaatar", font=FONT_HEAD, fill="#334155")
    draw.text((plot_left + 24, plot_top + 44), "schematic city underlay", font=FONT_SMALL, fill="#64748b")

    if len(hull) >= 4:
        ridge_color = "#d6dee8"
        for offset in (0.22, 0.44, 0.66):
            start = hull[int(len(hull) * offset) % len(hull)]
            end = hull[int(len(hull) * (offset + 0.27)) % len(hull)]
            draw.line((start[0], start[1], end[0], end[1]), fill=ridge_color, width=2)

    price_min = float(df["median_price_per_sqm"].min())
    price_max = float(df["median_price_per_sqm"].max())
    size_min = float(df["listings"].min())
    size_max = float(df["listings"].max())
    df = df.sort_values("median_price_per_sqm")
    for _, row in df.iterrows():
        x, y = transform(float(row["longitude"]), float(row["latitude"]))
        price = float(row["median_price_per_sqm"])
        count = float(row["listings"])
        radius = 10 + int(round((math.sqrt(count) - math.sqrt(size_min)) / (math.sqrt(size_max) - math.sqrt(size_min) or 1) * 14))
        fill = price_color(price, price_min, price_max)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline="white", width=3)

    square_lon = 106.917701
    square_lat = 47.918873
    sx, sy = transform(square_lon, square_lat)
    draw.ellipse((sx - 8, sy - 8, sx + 8, sy + 8), fill="#111827", outline="white", width=2)
    square_label = "Sukhbaatar Square"
    sq_w, sq_h = text_size(draw, square_label, FONT_TINY)
    sq_x = min(sx + 12, plot_right - sq_w - 4)
    sq_y = max(plot_top + 4, sy - sq_h - 8)
    draw.text((sq_x, sq_y), square_label, font=FONT_TINY, fill="#111827")

    draw.text((plot_left, bottom - 56), "Point size reflects listing count; color reflects median price per sqm", font=FONT_SMALL, fill="#4b5563")

    # Color bar
    bar_left = plot_right - 190
    bar_top = bottom - 58
    bar_width = 160
    bar_height = 16
    for i in range(bar_width):
        color = price_color(price_min + (price_max - price_min) * (i / max(1, bar_width - 1)), price_min, price_max)
        draw.line((bar_left + i, bar_top, bar_left + i, bar_top + bar_height), fill=color, width=1)
    draw.rectangle((bar_left, bar_top, bar_left + bar_width, bar_top + bar_height), outline="#1f2937", width=1)
    draw.text((bar_left, bar_top + 22), f"{fmt_money(price_min)}", font=FONT_TINY, fill="#374151")
    max_label = f"{fmt_money(price_max)}"
    max_w, _ = text_size(draw, max_label, FONT_TINY)
    draw.text((bar_left + bar_width - max_w, bar_top + 22), max_label, font=FONT_TINY, fill="#374151")

    draw.text((1118, 178), "Lowest median price regions", font=FONT_HEAD, fill="#111827")
    draw.text((1118, 510), "Highest median price regions", font=FONT_HEAD, fill="#111827")

    def write_ranked_rows(start_y: int, rows: pd.DataFrame) -> None:
        y = start_y
        for _, row in rows.iterrows():
            color = price_color(float(row["median_price_per_sqm"]), price_min, price_max)
            draw.rounded_rectangle((1118, y + 6, 1138, y + 26), radius=6, fill=color)
            label = clean_text(row["region"], 33)
            line = f"{label}"
            value = f"{fmt_money(row['median_price_per_sqm'])} / sqm   {int(row['listings'])} listings"
            y = draw_wrapped(draw, line, 1148, y, FONT_BODY, "#111827", 352, max_lines=1)
            y = draw_wrapped(draw, value, 1148, y + 2, FONT_SMALL, "#4b5563", 352, max_lines=1)
            y += 14

    write_ranked_rows(225, df.head(5))
    write_ranked_rows(557, df.tail(5).sort_values("median_price_per_sqm", ascending=False))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def draw_map_cover(region_df: pd.DataFrame, output_path: Path, map_html_path: Path, chrome_path: str | None = None) -> None:
    try:
        render_actual_html_map_cover(map_html_path, output_path, chrome_path=chrome_path)
        return
    except Exception as exc:
        print(f"Falling back to schematic README map cover: {exc}")

    draw_schematic_map_cover(region_df, output_path)


def draw_top10_cover(top10_df: pd.DataFrame, output_path: Path) -> None:
    df = top10_df.sort_values("forecast_rank").copy()
    if df.empty:
        raise SystemExit("Top 10 forecast file is empty.")

    width, height = 1600, 1000
    image = Image.new("RGB", (width, height), "#f7f9fc")
    draw = ImageDraw.Draw(image)

    draw.text((60, 42), "Top 10 forecast shortlist", font=FONT_TITLE, fill="#111827")
    draw.text(
        (60, 96),
        "3-room listings filtered to 300M-600M MNT and area above 70 sqm",
        font=FONT_SUB,
        fill="#4b5563",
    )

    panel_box = (50, 150, 1550, 930)
    draw_panel_frame(draw, panel_box)
    left, top, right, bottom = panel_box

    max_gain = float(df["expected_gain_pct"].max())
    min_gain = max(0.0, float(df["expected_gain_pct"].min()))
    chart_left = left + 510
    chart_right = right - 50
    chart_top = top + 58
    row_gap = 72
    bar_height = 18

    draw.text((left + 38, top + 18), "Listings", font=FONT_HEAD, fill="#111827")
    draw.text((chart_left, top + 18), "5-year upside", font=FONT_HEAD, fill="#111827")

    for index, (_, row) in enumerate(df.iterrows(), start=1):
        y = chart_top + (index - 1) * row_gap
        title = clean_text(row["title"], 44)
        location = clean_text(row.get("location"), 46)
        price = fmt_money(row.get("price_mnt"))
        size = f"{safe_float(row.get('size_sqm')):,.1f} sqm" if safe_float(row.get("size_sqm")) is not None else ""
        dist = f"{safe_float(row.get('distance_to_sukhbaatar_km')):,.2f} km" if safe_float(row.get("distance_to_sukhbaatar_km")) is not None else ""
        upside = fmt_pct(row.get("expected_gain_pct"))

        draw.rounded_rectangle((left + 34, y - 2, left + 476, y + 48), radius=16, fill="#ffffff", outline="#e5e7eb")
        draw.ellipse((left + 46, y + 10, left + 72, y + 36), fill="#111827")
        rank_text = str(int(row["forecast_rank"]))
        tw, th = text_size(draw, rank_text, FONT_TINY)
        draw.text((left + 59 - tw / 2, y + 23 - th / 2), rank_text, font=FONT_TINY, fill="#ffffff")
        draw_wrapped(draw, title, left + 88, y + 4, FONT_BODY, "#111827", 340, max_lines=1)
        draw.text((left + 88, y + 30), f"{location}  |  {price}  |  {size}  |  {dist}", font=FONT_SMALL, fill="#6b7280")

        track_y = y + 15
        draw.rounded_rectangle((chart_left, track_y, chart_right, track_y + bar_height), radius=8, fill="#e8edf3")
        gain = max(0.0, float(row["expected_gain_pct"]))
        fill_width = int(round((gain / max_gain) * (chart_right - chart_left))) if max_gain > 0 else 0
        fill_width = max(8, min(chart_right - chart_left, fill_width))
        bar_fill = (30, 64, 175) if index > 1 else (16, 185, 129)
        draw.rounded_rectangle((chart_left, track_y, chart_left + fill_width, track_y + bar_height), radius=8, fill=bar_fill)
        draw.text((chart_right + 14, y + 8), upside, font=FONT_BODY, fill="#111827")

    footer_y = 948
    draw.text((60, footer_y), "Ranking weights: forecast upside 45%, newness 20%, current price/sqm 15%, distance 20%", font=FONT_SMALL, fill="#4b5563")
    draw.text((60, footer_y + 24), "The shortlist is deduped and filtered for obvious location conflicts before ranking.", font=FONT_SMALL, fill="#4b5563")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def build_assets(region_csv: Path, top10_csv: Path, map_html_path: Path, out_dir: Path, chrome_path: str | None = None) -> tuple[Path, Path]:
    if not region_csv.exists():
        raise SystemExit(f"Region stats CSV not found: {region_csv}")
    if not top10_csv.exists():
        raise SystemExit(f"Top 10 CSV not found: {top10_csv}")

    region_df = pd.read_csv(region_csv)
    top10_df = pd.read_csv(top10_csv)

    map_path = out_dir / "ub_median_price_map.png"
    top10_path = out_dir / "ub_top10_forecast.png"
    draw_map_cover(region_df, map_path, map_html_path, chrome_path=chrome_path)
    draw_top10_cover(top10_df, top10_path)
    return map_path, top10_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build PNG figures for the repository README.")
    parser.add_argument("--region-csv", default=str(DEFAULT_REGION_CSV), help="Full-scrape region stats CSV.")
    parser.add_argument("--top10-csv", default=str(DEFAULT_TOP10_CSV), help="Top 10 forecast CSV.")
    parser.add_argument("--map-html", default=str(DEFAULT_MAP_HTML), help="HTML map output to snapshot for the README.")
    parser.add_argument("--chrome-path", default="", help="Optional path to a Chrome executable or its parent directory.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for the PNG assets.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    build_assets(
        Path(args.region_csv),
        Path(args.top10_csv),
        Path(args.map_html),
        Path(args.out_dir),
        chrome_path=args.chrome_path or None,
    )


if __name__ == "__main__":
    main()
