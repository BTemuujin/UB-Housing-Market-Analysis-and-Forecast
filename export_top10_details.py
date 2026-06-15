from __future__ import annotations

import argparse
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scraper import HEADERS, fetch_html, make_session, parse_detail_page


DEFAULT_INPUT = "unegui_ub_50_ranked_3room_apartments.csv"
DEFAULT_OUTPUT_DIR = "top10_listing_report"


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def safe_name(value: object, fallback: str = "listing") -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^\w\u0400-\u04ff-]+", "_", text, flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:90] or fallback


def mnt(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return clean_text(value)
    if pd.isna(number):
        return ""
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:,.2f}M ₮"
    return f"{number:,.0f} ₮"


def number(value: object, digits: int = 2) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return clean_text(value)
    if pd.isna(parsed):
        return ""
    return f"{parsed:,.{digits}f}"


def safe_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def listing_photo_urls(soup: BeautifulSoup) -> list[str]:
    urls: list[str] = []
    for img in soup.select("img.announcement__images-item"):
        src = img.get("data-full") or img.get("data-src") or img.get("src")
        if src and "media/cache" in src:
            urls.append(src)

    if not urls:
        for img in soup.select("section.list-announcement img[itemprop='image'], meta[property='og:image']"):
            src = img.get("data-full") or img.get("data-src") or img.get("src") or img.get("content")
            if src and "media/cache" in src:
                urls.append(src)

    unique: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def download_image(image_url: str, output_path: Path, referer: str) -> tuple[str, str, str]:
    headers = dict(HEADERS)
    headers["Referer"] = referer
    try:
        response = requests.get(image_url, headers=headers, timeout=30)
        response.raise_for_status()
        output_path.write_bytes(response.content)
        return image_url, str(output_path), ""
    except requests.RequestException as exc:
        return image_url, "", str(exc)


def detail_fields_from_row(row: pd.Series, parsed_detail: dict[str, object]) -> dict[str, object]:
    preferred_columns = [
        "forecast_rank",
        "forecast_ranking_score",
        "forecast_applicable",
        "expected_gain_pct",
        "expected_gain_mnt",
        "forecast_5yr_value_mnt",
        "forecast_5yr_price_per_sqm_mnt",
        "estimated_fair_value_mnt",
        "fair_price_per_sqm_mnt",
        "asking_to_fair_pct",
        "annual_growth_rate",
        "building_age_class",
        "built_year",
        "recommendation_rank",
        "best_score",
        "price_per_sqm",
        "distance_to_sukhbaatar_km",
        "distance_source",
        "room_category",
        "rooms_clean",
        "property_category",
        "possible_duplicate",
        "ad_id",
        "title",
        "price",
        "price_mnt",
        "location",
        "district",
        "sub_location",
        "latitude",
        "longitude",
        "size_sqm",
        "area_sqm",
        "rooms",
        "listing_date",
        "listing_date_iso",
        "published_text",
        "seller",
        "badges",
        "image_count",
        "price_per_sqm",
        "link",
        "Шал",
        "Тагт",
        "Ашиглалтанд орсон он",
        "Гараж",
        "Цонх",
        "Барилгын давхар",
        "Хаалга",
        "Талбай",
        "Хэдэн давхарт",
        "Төлбөрийн нөхцөл",
        "Цонхны тоо",
        "Барилгын явц",
        "Цахилгаан шаттай эсэх",
        "Төрөл",
        "Зориулалт",
        "Website",
        "detail_description",
    ]

    fields: dict[str, object] = {}
    for column in preferred_columns:
        if column in row.index and clean_text(row[column]):
            fields[column] = row[column]

    for key, value in parsed_detail.items():
        if clean_text(value) and key not in fields:
            fields[key] = value

    return fields


def render_field_value(key: str, value: object) -> str:
    if key in {
        "price_mnt",
        "price_mnt_max",
        "detail_price_text",
        "expected_gain_mnt",
        "forecast_5yr_value_mnt",
        "forecast_5yr_price_per_sqm_mnt",
        "estimated_fair_value_mnt",
        "fair_price_per_sqm_mnt",
    }:
        return html.escape(mnt(value))
    if key in {"price_per_sqm"}:
        return html.escape(f"{mnt(value)} / sqm")
    if key in {"expected_gain_pct", "asking_to_fair_pct", "annual_growth_rate"}:
        try:
            return html.escape(f"{float(value):.1%}")
        except (TypeError, ValueError):
            return html.escape(clean_text(value))
    if key in {"distance_to_sukhbaatar_km"}:
        return html.escape(f"{number(value)} km")
    if key in {"best_score", "forecast_ranking_score"}:
        return html.escape(number(value, 4))
    if key == "link":
        url = clean_text(value)
        return f'<a href="{html.escape(url)}" target="_blank" rel="noreferrer">{html.escape(url)}</a>'
    return html.escape(clean_text(value))


def map_point(listing: dict[str, object]) -> dict[str, object] | None:
    fields = listing["fields"]
    lat = safe_float(fields.get("latitude"))
    lon = safe_float(fields.get("longitude"))
    if lat is None or lon is None:
        return None
    return {
        "rank": listing["rank"],
        "title": clean_text(fields.get("title") or fields.get("detail_title") or f"Listing {listing['rank']}"),
        "location": clean_text(fields.get("location")),
        "price": mnt(fields.get("price_mnt")),
        "price_per_sqm": f"{mnt(fields.get('price_per_sqm'))} / sqm",
        "distance_km": number(fields.get("distance_to_sukhbaatar_km")),
        "lat": lat,
        "lon": lon,
    }


def render_overview_map(listings: list[dict[str, object]]) -> str:
    points = [point for listing in listings if (point := map_point(listing))]
    if not points:
        return ""
    return """
    <section class="overview">
      <h2>Top 10 Map</h2>
      <div id="overview-map" class="overview-map"></div>
    </section>
    """


def render_listing_map(listing: dict[str, object]) -> str:
    point = map_point(listing)
    if point is None:
        return ""
    return f"""
      <div class="map-block">
        <h3>Map Location</h3>
        <div id="listing-map-{listing['rank']}" class="listing-map"></div>
      </div>
    """


def render_listing_card(listing: dict[str, object]) -> str:
    fields = listing["fields"]
    images = listing["images"]
    title = clean_text(fields.get("title") or fields.get("detail_title") or f"Listing {listing['rank']}")
    rows = "\n".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{render_field_value(str(key), value)}</td></tr>"
        for key, value in fields.items()
    )
    gallery = "\n".join(
        f"""
        <figure>
          <a href="{html.escape(image['local_path'])}" target="_blank">
            <img src="{html.escape(image['local_path'])}" alt="{html.escape(title)} photo {image['index']}">
          </a>
          <figcaption>Photo {image['index']}</figcaption>
        </figure>
        """
        for image in images
        if image.get("local_path")
    )
    failed = [image for image in images if image.get("error")]
    failed_html = ""
    if failed:
        failed_html = "<p class='warning'>Some images failed to download. See the photo manifest CSV.</p>"

    return f"""
    <section class="listing">
      <header>
        <div class="rank">#{listing['rank']}</div>
        <div>
          <h2>{html.escape(title)}</h2>
          <p class="meta">{html.escape(clean_text(fields.get('location')))} · {render_field_value('price_mnt', fields.get('price_mnt'))} · {render_field_value('price_per_sqm', fields.get('price_per_sqm'))}</p>
        </div>
      </header>
      {render_listing_map(listing)}
      <div class="gallery">{gallery}</div>
      {failed_html}
      <details open>
        <summary>All details</summary>
        <table>{rows}</table>
      </details>
    </section>
    """


def render_report(listings: list[dict[str, object]], output_path: Path) -> None:
    points = [point for listing in listings if (point := map_point(listing))]
    map_json = json.dumps(points, ensure_ascii=False)
    cards = "\n".join(render_listing_card(listing) for listing in listings)
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Top 10 Unegui Listings</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f5f5f5; color: #191919; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 20px; font-size: 28px; }}
    .listing {{ background: white; border: 1px solid #ddd; border-radius: 8px; margin: 0 0 24px; padding: 18px; }}
    header {{ display: flex; gap: 14px; align-items: flex-start; margin-bottom: 14px; }}
    .rank {{ background: #111; color: white; border-radius: 999px; width: 44px; height: 44px; display: grid; place-items: center; font-weight: 700; flex: 0 0 auto; }}
    h2 {{ margin: 0 0 6px; font-size: 21px; }}
    .meta {{ margin: 0; color: #555; }}
    .gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; margin: 12px 0 16px; }}
    .overview {{ background: white; border: 1px solid #ddd; border-radius: 8px; margin: 0 0 24px; padding: 18px; }}
    .overview h2 {{ margin: 0 0 12px; font-size: 22px; }}
    .overview-map {{ width: 100%; height: 560px; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; }}
    .map-block {{ margin: 12px 0 16px; }}
    .map-block h3 {{ margin: 0 0 8px; font-size: 16px; }}
    .listing-map {{ width: 100%; height: 300px; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; }}
    figure {{ margin: 0; border: 1px solid #e0e0e0; border-radius: 6px; overflow: hidden; background: #fafafa; }}
    img {{ width: 100%; height: 170px; object-fit: cover; display: block; }}
    figcaption {{ padding: 6px 8px; font-size: 12px; color: #555; }}
    summary {{ cursor: pointer; font-weight: 700; margin-bottom: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-top: 1px solid #e8e8e8; padding: 7px 8px; text-align: left; vertical-align: top; }}
    th {{ width: 235px; color: #444; background: #fafafa; }}
    a {{ color: #0645ad; word-break: break-all; }}
    .warning {{ color: #9a4b00; }}
  </style>
</head>
<body>
  <main>
    <h1>Top 10 Unegui Listings With Photos And Details</h1>
    {render_overview_map(listings)}
    {cards}
  </main>
  <script>
    const mapPoints = {map_json};
    const square = {{ rank: 0, title: "Sukhbaatar Square", lat: 47.918873, lon: 106.917701 }};
    const config = {{ responsive: true, displayModeBar: false }};

    function hoverText(point) {{
      return [
        "#" + point.rank + " " + point.title,
        point.location,
        "Price: " + point.price,
        "Price/sqm: " + point.price_per_sqm,
        "Distance: " + point.distance_km + " km"
      ].join("<br>");
    }}

    function renderOverview() {{
      const element = document.getElementById("overview-map");
      if (!element || !mapPoints.length || !window.Plotly) return;
      const trace = {{
        type: "scattermapbox",
        mode: "markers+text",
        lat: mapPoints.map(point => point.lat),
        lon: mapPoints.map(point => point.lon),
        text: mapPoints.map(point => "#" + point.rank),
        textposition: "top center",
        hovertext: mapPoints.map(hoverText),
        hoverinfo: "text",
        marker: {{ size: 14, color: "#dc2626", opacity: 0.9 }}
      }};
      const squareTrace = {{
        type: "scattermapbox",
        mode: "markers+text",
        lat: [square.lat],
        lon: [square.lon],
        text: ["Sukhbaatar Square"],
        textposition: "bottom right",
        hovertext: ["Sukhbaatar Square"],
        hoverinfo: "text",
        marker: {{ size: 12, color: "#111111" }}
      }};
      Plotly.newPlot(element, [trace, squareTrace], {{
        mapbox: {{
          style: "carto-positron",
          center: {{ lat: 47.918873, lon: 106.917701 }},
          zoom: 11.2
        }},
        margin: {{ l: 0, r: 0, t: 0, b: 0 }},
        showlegend: false
      }}, config);
    }}

    function renderListingMaps() {{
      if (!window.Plotly) return;
      mapPoints.forEach(point => {{
        const element = document.getElementById("listing-map-" + point.rank);
        if (!element) return;
        const trace = {{
          type: "scattermapbox",
          mode: "markers+text",
          lat: [point.lat],
          lon: [point.lon],
          text: ["#" + point.rank],
          textposition: "top center",
          hovertext: [hoverText(point)],
          hoverinfo: "text",
          marker: {{ size: 16, color: "#dc2626", opacity: 0.95 }}
        }};
        const squareTrace = {{
          type: "scattermapbox",
          mode: "markers+text",
          lat: [square.lat],
          lon: [square.lon],
          text: ["Sukhbaatar Square"],
          textposition: "bottom right",
          hovertext: ["Sukhbaatar Square"],
          hoverinfo: "text",
          marker: {{ size: 10, color: "#111111" }}
        }};
        const lineTrace = {{
          type: "scattermapbox",
          mode: "lines",
          lat: [square.lat, point.lat],
          lon: [square.lon, point.lon],
          hoverinfo: "skip",
          line: {{ color: "#666666", width: 1 }}
        }};
        Plotly.newPlot(element, [lineTrace, trace, squareTrace], {{
          mapbox: {{
            style: "carto-positron",
            center: {{ lat: (point.lat + square.lat) / 2, lon: (point.lon + square.lon) / 2 }},
            zoom: point.distance_km && Number(point.distance_km) > 2.5 ? 11.0 : 12.2
          }},
          margin: {{ l: 0, r: 0, t: 0, b: 0 }},
          showlegend: false
        }}, config);
      }});
    }}

    window.addEventListener("load", () => {{
      renderOverview();
      renderListingMaps();
    }});
  </script>
</body>
</html>
"""
    output_path.write_text(html_doc, encoding="utf-8")


def export_top_listings(input_path: str, output_dir: str, top_n: int, workers: int) -> None:
    input_path_obj = Path(input_path)
    if not input_path_obj.exists():
        raise SystemExit(f"Input CSV not found: {input_path}")

    output_root = Path(output_dir)
    image_root = output_root / "images"
    image_root.mkdir(parents=True, exist_ok=True)

    ranked = pd.read_csv(input_path_obj).head(top_n)
    session = make_session()

    listings: list[dict[str, object]] = []
    detail_rows: list[dict[str, object]] = []
    image_rows: list[dict[str, object]] = []

    for _, row in ranked.iterrows():
        rank_column = "forecast_rank" if "forecast_rank" in row.index else "recommendation_rank"
        rank = int(row[rank_column])
        ad_id = clean_text(row.get("ad_id")) or str(rank)
        link = clean_text(row.get("link"))
        listing_dir = image_root / f"{rank:02d}_{ad_id}_{safe_name(row.get('title'))}"
        listing_dir.mkdir(parents=True, exist_ok=True)

        print(f"Fetching listing #{rank}: {link}")
        html_text = fetch_html(session, link)
        soup = BeautifulSoup(html_text, "html.parser")
        parsed_detail = parse_detail_page(html_text, link)
        photo_urls = listing_photo_urls(soup)

        fields = detail_fields_from_row(row, parsed_detail)
        fields["downloaded_photo_count"] = len(photo_urls)

        images: list[dict[str, object]] = []
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {}
            for index, photo_url in enumerate(photo_urls, start=1):
                extension = Path(urlparse(photo_url).path).suffix or ".webp"
                image_path = listing_dir / f"photo_{index:02d}{extension}"
                futures[executor.submit(download_image, photo_url, image_path, link)] = (index, photo_url, image_path)

            for future in as_completed(futures):
                index, photo_url, image_path = futures[future]
                remote_url, local_path, error = future.result()
                local_rel = Path(local_path).relative_to(output_root).as_posix() if local_path else ""
                image_record = {
                    "rank": rank,
                    "ad_id": ad_id,
                    "title": clean_text(row.get("title")),
                    "image_index": index,
                    "remote_url": remote_url,
                    "local_path": local_rel,
                    "error": error,
                }
                image_rows.append(image_record)
                images.append({"index": index, "remote_url": remote_url, "local_path": local_rel, "error": error})

        images.sort(key=lambda item: item["index"])
        listings.append({"rank": rank, "fields": fields, "images": images})
        detail_rows.append({"rank": rank, **fields})
        print(f"  photos: {len([image for image in images if image.get('local_path')])}/{len(images)} downloaded")

    details_path = output_root / "top10_details.csv"
    manifest_path = output_root / "top10_photo_manifest.csv"
    report_path = output_root / "top10_listings_report.html"

    pd.DataFrame(detail_rows).to_csv(details_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(image_rows).sort_values(["rank", "image_index"]).to_csv(
        manifest_path,
        index=False,
        encoding="utf-8-sig",
    )
    render_report(listings, report_path)

    print(f"Saved HTML report to {report_path}")
    print(f"Saved details CSV to {details_path}")
    print(f"Saved photo manifest to {manifest_path}")
    print(f"Saved images under {image_root}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export top ranked Unegui listings with actual photos and all details.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Ranked listings CSV.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--top-n", type=int, default=10, help="Number of top listings to export.")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent image downloads per listing.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    export_top_listings(args.input, args.output_dir, args.top_n, args.workers)


if __name__ == "__main__":
    main()
