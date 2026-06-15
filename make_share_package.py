from __future__ import annotations

import math
import shutil
import textwrap
import zipfile
from datetime import date
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "share_results_corrected"
ZIP_PATH = ROOT / "Unegui_UB_results_package_corrected.zip"

TOP10_REPORT_DIR = ROOT / "top10_listing_report_corrected"
TOP10_CSV = TOP10_REPORT_DIR / "top10_details.csv"
PHOTO_MANIFEST_CSV = TOP10_REPORT_DIR / "top10_photo_manifest.csv"
TOP10_HTML = TOP10_REPORT_DIR / "top10_listings_report.html"
TOP10_IMAGES = TOP10_REPORT_DIR / "images"

HEATMAP_HTML = ROOT / "unegui_ub_50_stats_apartment_price_per_sqm_heatmap.html"
MEDIAN_MAP_HTML = ROOT / "unegui_ub_50_stats_apartment_price_per_sqm_map.html"
REGION_STATS_CSV = ROOT / "unegui_ub_50_stats_apartment_region_stats.csv"
DISTRICT_STATS_CSV = ROOT / "unegui_ub_50_stats_apartment_district_stats.csv"
ROOM_STATS_CSV = ROOT / "unegui_ub_50_stats_apartment_room_stats.csv"
PROPERTY_STATS_CSV = ROOT / "unegui_ub_50_stats_property_type_stats.csv"
RANKED_CSV = ROOT / "unegui_ub_50_ranked_3room_apartments.csv"
OUTLIER_CSV = ROOT / "unegui_ub_50_stats_apartment_price_outliers.csv"
CAPPED_CSV = ROOT / "unegui_ub_50_stats_apartment_heatmap_color_capped.csv"


def fmt_money(value) -> str:
    if pd.isna(value):
        return ""
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M MNT"
    return f"{value:,.0f} MNT"


def fmt_num(value, decimals: int = 2) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):,.{decimals}f}"


def clean_text(value, max_len: int | None = None) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    if max_len and len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def find_font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT_REG = find_font(32)
FONT_MED = find_font(36)
FONT_BIG = find_font(54)
FONT_SMALL = find_font(24)
FONT_TINY = find_font(20)


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: str = "#1f2933",
    max_width: int = 1400,
    line_gap: int = 8,
    max_lines: int | None = None,
) -> int:
    words = clean_text(text).split()
    if not words:
        return xy[1]
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if width <= max_width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".") + "..."
    y = xy[1]
    line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + line_gap
    for line in lines:
        draw.text((xy[0], y), line, font=font, fill=fill)
        y += line_height
    return y


def new_page() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    page = Image.new("RGB", (1654, 2339), "white")
    draw = ImageDraw.Draw(page)
    return page, draw


def paste_photo(page: Image.Image, path: Path, box: tuple[int, int, int, int]) -> None:
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((box[2] - box[0], box[3] - box[1]))
            x = box[0] + ((box[2] - box[0]) - img.width) // 2
            y = box[1] + ((box[3] - box[1]) - img.height) // 2
            ImageDraw.Draw(page).rounded_rectangle(box, radius=12, outline="#d5d7da", width=2)
            page.paste(img, (x, y))
    except Exception:
        ImageDraw.Draw(page).rounded_rectangle(box, radius=12, outline="#d5d7da", width=2)
        ImageDraw.Draw(page).text((box[0] + 20, box[1] + 20), "Image unavailable", font=FONT_SMALL, fill="#9a3412")


def add_footer(draw: ImageDraw.ImageDraw, page_no: int) -> None:
    draw.line((80, 2260, 1574, 2260), fill="#e5e7eb", width=2)
    draw.text((80, 2280), "Unegui UB listing analysis package", font=FONT_TINY, fill="#6b7280")
    draw.text((1460, 2280), f"Page {page_no}", font=FONT_TINY, fill="#6b7280")


def make_pdf(top10: pd.DataFrame, photos: pd.DataFrame, region: pd.DataFrame, district: pd.DataFrame, pdf_path: Path) -> None:
    pages: list[Image.Image] = []

    page, draw = new_page()
    draw.text((80, 120), "Unegui UB Top 10 Apartment Results", font=FONT_BIG, fill="#111827")
    y = draw_wrapped(
        draw,
        "Shareable summary for the ranked 3-room apartment shortlist. Ranking favors low price per sqm, closeness to Sukhbaatar Square, and 3-room listings.",
        (80, 220),
        FONT_REG,
        max_width=1450,
        max_lines=4,
    )
    total_photos = len(photos[photos["error"].isna()])
    facts = [
        ("Listings in shortlist", str(len(top10))),
        ("Downloaded listing photos", str(total_photos)),
        ("Data source", "Unegui.mn UB city listing scrape"),
        ("Package date", date.today().isoformat()),
    ]
    y += 50
    for label, value in facts:
        draw.text((100, y), label, font=FONT_SMALL, fill="#4b5563")
        draw.text((520, y), value, font=FONT_SMALL, fill="#111827")
        y += 52
    y += 40
    draw.text((80, y), "Included files", font=FONT_MED, fill="#111827")
    y += 70
    for item in (
        "Unegui_UB_Top10_Report.pdf - readable PDF summary",
        "Unegui_UB_Interactive_Report.html - all top-10 photos and details",
        "maps/ - interactive price heatmap and regional median price map",
        "Unegui_UB_Listings.xlsx - spreadsheet with listings and statistics",
        "data/ - CSV copies for backup",
    ):
        y = draw_wrapped(draw, "- " + item, (110, y), FONT_SMALL, max_width=1300) + 10
    add_footer(draw, 1)
    pages.append(page)

    page, draw = new_page()
    draw.text((80, 90), "Top 10 Summary", font=FONT_BIG, fill="#111827")
    headers = ["#", "Title", "Price", "sqm", "MNT/sqm", "km", "Location"]
    xs = [80, 140, 620, 800, 930, 1120, 1240]
    y = 180
    for x, header in zip(xs, headers):
        draw.text((x, y), header, font=FONT_TINY, fill="#4b5563")
    draw.line((80, y + 34, 1570, y + 34), fill="#d1d5db", width=2)
    y += 56
    for _, row in top10.iterrows():
        draw.text((xs[0], y), str(int(row["rank"])), font=FONT_TINY, fill="#111827")
        draw_wrapped(draw, clean_text(row["title"], 58), (xs[1], y), FONT_TINY, max_width=450, max_lines=2)
        draw.text((xs[2], y), fmt_money(row["price_mnt"]), font=FONT_TINY, fill="#111827")
        draw.text((xs[3], y), fmt_num(row["size_sqm"], 1), font=FONT_TINY, fill="#111827")
        draw.text((xs[4], y), fmt_money(row["price_per_sqm"]), font=FONT_TINY, fill="#111827")
        draw.text((xs[5], y), fmt_num(row["distance_to_sukhbaatar_km"], 2), font=FONT_TINY, fill="#111827")
        draw_wrapped(draw, clean_text(row["location"], 45), (xs[6], y), FONT_TINY, max_width=320, max_lines=2)
        y += 120
    add_footer(draw, 2)
    pages.append(page)

    page, draw = new_page()
    draw.text((80, 90), "Regional Statistics", font=FONT_BIG, fill="#111827")
    y = 190
    draw.text((80, y), "Lowest median apartment price per sqm", font=FONT_MED, fill="#111827")
    y += 70
    for _, row in region.head(5).iterrows():
        draw.text((110, y), f"{clean_text(row['region'])}: {fmt_money(row['median_price_per_sqm'])} / sqm", font=FONT_SMALL, fill="#111827")
        y += 48
    y += 60
    draw.text((80, y), "Highest median apartment price per sqm", font=FONT_MED, fill="#111827")
    y += 70
    for _, row in region.tail(5).sort_values("median_price_per_sqm", ascending=False).iterrows():
        draw.text((110, y), f"{clean_text(row['region'])}: {fmt_money(row['median_price_per_sqm'])} / sqm", font=FONT_SMALL, fill="#111827")
        y += 48
    y += 80
    draw.text((80, y), "District medians", font=FONT_MED, fill="#111827")
    y += 70
    for _, row in district.sort_values("median_price_per_sqm").iterrows():
        label = row["district"] if "district" in row else row.iloc[0]
        draw.text((110, y), f"{clean_text(label)}: {fmt_money(row['median_price_per_sqm'])} / sqm", font=FONT_SMALL, fill="#111827")
        y += 48
    add_footer(draw, 3)
    pages.append(page)

    page_no = 4
    for _, row in top10.iterrows():
        page, draw = new_page()
        rank = int(row["rank"])
        draw.text((80, 80), f"#{rank}  {clean_text(row['title'], 55)}", font=FONT_MED, fill="#111827")
        y = 150
        core = [
            ("Price", fmt_money(row["price_mnt"])),
            ("Size", f"{fmt_num(row['size_sqm'], 1)} sqm"),
            ("Rooms", clean_text(row.get("room_category") or row.get("rooms"))),
            ("Price per sqm", fmt_money(row["price_per_sqm"])),
            ("Distance to Sukhbaatar Square", f"{fmt_num(row['distance_to_sukhbaatar_km'], 2)} km"),
            ("Location", clean_text(row["location"])),
            ("Listing date", clean_text(row.get("listing_date_iso") or row.get("listing_date"))),
            ("Seller", clean_text(row.get("seller"))),
        ]
        for label, value in core:
            draw.text((90, y), label, font=FONT_TINY, fill="#6b7280")
            y = draw_wrapped(draw, value, (420, y), FONT_TINY, max_width=1030, max_lines=2)
            y += 14

        listing_photos = photos[(photos["rank"] == rank) & (photos["error"].isna())].sort_values("image_index")
        photo_paths = [TOP10_REPORT_DIR / clean_text(p) for p in listing_photos["local_path"].head(4)]
        boxes = [(90, 720, 790, 1180), (865, 720, 1565, 1180), (90, 1210, 790, 1670), (865, 1210, 1565, 1670)]
        for photo_path, box in zip(photo_paths, boxes):
            paste_photo(page, photo_path, box)

        detail_y = 1730
        details = [
            ("Floor", row.get("Хэдэн давхарт")),
            ("Building floors", row.get("Барилгын давхар")),
            ("Year", row.get("Ашиглалтанд орсон он")),
            ("Balcony", row.get("Тагт")),
            ("Garage", row.get("Гараж")),
            ("Windows", row.get("Цонх")),
            ("Payment", row.get("Төлбөрийн нөхцөл")),
            ("Elevator", row.get("Цахилгаан шаттай эсэх")),
        ]
        for i, (label, value) in enumerate(details):
            x = 90 if i % 2 == 0 else 850
            if i % 2 == 0 and i:
                detail_y += 48
            draw.text((x, detail_y), f"{label}: {clean_text(value, 46)}", font=FONT_TINY, fill="#111827")
        detail_y += 90
        draw.text((90, detail_y), "Description", font=FONT_SMALL, fill="#111827")
        detail_y += 42
        draw_wrapped(draw, clean_text(row.get("detail_description"), 520), (90, detail_y), FONT_TINY, max_width=1450, max_lines=8)
        add_footer(draw, page_no)
        pages.append(page)
        page_no += 1

    pages[0].save(pdf_path, save_all=True, append_images=pages[1:], resolution=120)


def col_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def excel_value(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(float(value)):
            return value
        return None
    return str(value)


def make_sheet_xml(df: pd.DataFrame) -> str:
    rows = []
    columns = list(df.columns)
    header_cells = []
    for c, name in enumerate(columns):
        ref = f"{col_name(c)}1"
        header_cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(name))}</t></is></c>')
    rows.append(f'<row r="1">{"".join(header_cells)}</row>')
    for r_idx, (_, row) in enumerate(df.iterrows(), start=2):
        cells = []
        for c_idx, col in enumerate(columns):
            value = excel_value(row[col])
            if value is None:
                continue
            ref = f"{col_name(c_idx)}{r_idx}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    last_ref = f"{col_name(max(len(columns) - 1, 0))}{max(len(df) + 1, 1)}"
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="18" customWidth="1"/>' for i in range(len(columns)))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="A1:{last_ref}"/><cols>{cols}</cols><sheetData>{"".join(rows)}</sheetData>'
        '</worksheet>'
    )


def write_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    sheet_items = list(sheets.items())
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        overrides = [
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        ]
        for i, _ in enumerate(sheet_items, start=1):
            overrides.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' + "".join(overrides) + "</Types>")
        zf.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        workbook_sheets = []
        workbook_rels = []
        for i, (name, _) in enumerate(sheet_items, start=1):
            safe_name = escape(name[:31])
            workbook_sheets.append(f'<sheet name="{safe_name}" sheetId="{i}" r:id="rId{i}"/>')
            workbook_rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
        zf.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + "".join(workbook_sheets) + "</sheets></workbook>")
        zf.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(workbook_rels) + "</Relationships>")
        for i, (_, df) in enumerate(sheet_items, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", make_sheet_xml(df))


def copy_csv(src: Path, dest: Path) -> None:
    df = pd.read_csv(src)
    df.to_csv(dest, index=False, encoding="utf-8-sig")


def make_readme(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """\
            Unegui UB Results Package

            Open Unegui_UB_Top10_Report.pdf first for a simple readable summary.

            For the full photo/detail view, open Unegui_UB_Interactive_Report.html.
            The maps are in the maps folder:
            - Unegui_UB_Heatmap_Price_per_sqm.html
            - Unegui_UB_Median_Price_Map.html

            The spreadsheet is Unegui_UB_Listings.xlsx.
            CSV backup files are in the data folder.

            Notes:
            - Ranking favors lower price per sqm, shorter distance to Sukhbaatar Square, and 3-room listings.
            - The heatmap uses individual listing-level price per sqm values, not summed density values.
            - Suspicious apartment price/sqm outliers are listed in data/Apartment_Price_Outliers.csv.
            - High-end listings whose heatmap colors were capped are listed in data/Heatmap_Color_Capped_Listings.csv.
            - Original Unegui listing links are included in the report and spreadsheet.
            """
        ),
        encoding="utf-8",
    )


def zip_dir(source: Path, dest: Path) -> None:
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(source.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(source.parent))


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "maps").mkdir(exist_ok=True)
    (OUT_DIR / "data").mkdir(exist_ok=True)

    top10 = pd.read_csv(TOP10_CSV)
    photos = pd.read_csv(PHOTO_MANIFEST_CSV)
    region = pd.read_csv(REGION_STATS_CSV).sort_values("median_price_per_sqm")
    district = pd.read_csv(DISTRICT_STATS_CSV)
    room = pd.read_csv(ROOM_STATS_CSV)
    property_stats = pd.read_csv(PROPERTY_STATS_CSV)
    ranked = pd.read_csv(RANKED_CSV).head(100)
    outliers = pd.read_csv(OUTLIER_CSV)
    capped = pd.read_csv(CAPPED_CSV)

    shutil.copy2(TOP10_HTML, OUT_DIR / "Unegui_UB_Interactive_Report.html")
    shutil.copy2(HEATMAP_HTML, OUT_DIR / "maps" / "Unegui_UB_Heatmap_Price_per_sqm.html")
    shutil.copy2(MEDIAN_MAP_HTML, OUT_DIR / "maps" / "Unegui_UB_Median_Price_Map.html")
    shutil.copytree(TOP10_IMAGES, OUT_DIR / "images", dirs_exist_ok=True)

    copy_csv(TOP10_CSV, OUT_DIR / "data" / "Top10_Full_Details.csv")
    copy_csv(PHOTO_MANIFEST_CSV, OUT_DIR / "data" / "Top10_Photo_Manifest.csv")
    copy_csv(REGION_STATS_CSV, OUT_DIR / "data" / "Region_Stats.csv")
    copy_csv(DISTRICT_STATS_CSV, OUT_DIR / "data" / "District_Stats.csv")
    copy_csv(ROOM_STATS_CSV, OUT_DIR / "data" / "Room_Stats.csv")
    copy_csv(PROPERTY_STATS_CSV, OUT_DIR / "data" / "Property_Type_Stats.csv")
    copy_csv(OUTLIER_CSV, OUT_DIR / "data" / "Apartment_Price_Outliers.csv")
    copy_csv(CAPPED_CSV, OUT_DIR / "data" / "Heatmap_Color_Capped_Listings.csv")

    make_pdf(top10, photos, region, district, OUT_DIR / "Unegui_UB_Top10_Report.pdf")

    write_xlsx(
        OUT_DIR / "Unegui_UB_Listings.xlsx",
        {
            "Top 10 Full Details": top10,
            "Photo Manifest": photos,
            "Top Ranked 100": ranked,
            "Region Stats": region,
            "District Stats": district,
            "Room Stats": room,
            "Property Stats": property_stats,
            "Price Outliers": outliers,
            "Heatmap Color Capped": capped,
        },
    )
    make_readme(OUT_DIR / "README.txt")
    zip_dir(OUT_DIR, ZIP_PATH)

    print(f"Created {OUT_DIR}")
    print(f"Created {ZIP_PATH}")


if __name__ == "__main__":
    main()
