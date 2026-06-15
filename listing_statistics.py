from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from rank_listings import add_ranking_columns

GRAYSCALE_MAP_STYLE = "carto-positron"
MIN_APARTMENT_PRICE_PER_SQM = 1_000_000
MAX_APARTMENT_PRICE_PER_SQM = 30_000_000
MIN_APARTMENT_SIZE_SQM = 12
MAX_APARTMENT_SIZE_SQM = 1_000
HEATMAP_COLOR_MIN_PRICE_PER_SQM = 1_000_000
HEATMAP_COLOR_MAX_PRICE_PER_SQM = 12_000_000


def mnt_millions(value: float) -> str:
    if pd.isna(value):
        return ""
    return f"{value / 1_000_000:.2f}M ₮"


def prepare_data(input_path: str | Path) -> pd.DataFrame:
    input_path = Path(input_path)
    if not input_path.exists():
        raise SystemExit(f"CSV not found: {input_path}")

    df = pd.read_csv(input_path, low_memory=False)
    df = add_ranking_columns(df)
    df["price_per_sqm"] = pd.to_numeric(df["price_per_sqm"], errors="coerce")
    df["price_mnt"] = pd.to_numeric(df["price_mnt"], errors="coerce")
    df["size_sqm"] = pd.to_numeric(df["size_sqm"], errors="coerce")
    df = df[(df["price_per_sqm"] > 0) & (df["price_mnt"] > 0) & (df["size_sqm"] > 0)].copy()
    return df


def apartment_quality_mask(df: pd.DataFrame) -> pd.Series:
    return (
        df["property_category"].eq("apartment")
        & df["price_per_sqm"].between(MIN_APARTMENT_PRICE_PER_SQM, MAX_APARTMENT_PRICE_PER_SQM, inclusive="both")
        & df["size_sqm"].between(MIN_APARTMENT_SIZE_SQM, MAX_APARTMENT_SIZE_SQM, inclusive="both")
    )


def region_stats(df: pd.DataFrame, group_col: str, min_listings: int = 5) -> pd.DataFrame:
    aggregations = {
        "listings": ("ad_id", "count"),
        "median_price_per_sqm": ("price_per_sqm", "median"),
        "mean_price_per_sqm": ("price_per_sqm", "mean"),
        "median_price_mnt": ("price_mnt", "median"),
        "median_size_sqm": ("size_sqm", "median"),
        "apartments": ("property_category", lambda s: int((s == "apartment").sum())),
        "three_room_listings": ("rooms_clean", lambda s: int((s == 3.0).sum())),
        "latitude": ("latitude", "median"),
        "longitude": ("longitude", "median"),
        "avg_distance_to_sukhbaatar_km": ("distance_to_sukhbaatar_km", "mean"),
    }
    if group_col != "district":
        aggregations["district"] = ("district", lambda s: s.mode().iloc[0] if not s.mode().empty else "")

    grouped = df.groupby(group_col, dropna=True).agg(**aggregations).reset_index().rename(columns={group_col: "region"})
    if "district" not in grouped.columns:
        grouped["district"] = grouped["region"]
    grouped = grouped[grouped["listings"] >= min_listings].copy()
    grouped = grouped.sort_values("median_price_per_sqm")
    grouped["median_price_per_sqm_m"] = grouped["median_price_per_sqm"].map(mnt_millions)
    grouped["median_price_mnt_m"] = grouped["median_price_mnt"].map(mnt_millions)
    return grouped


def room_stats(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("room_category", dropna=False)
        .agg(
            listings=("ad_id", "count"),
            median_price_per_sqm=("price_per_sqm", "median"),
            median_price_mnt=("price_mnt", "median"),
            median_size_sqm=("size_sqm", "median"),
            median_distance_to_sukhbaatar_km=("distance_to_sukhbaatar_km", "median"),
        )
        .reset_index()
        .sort_values("median_price_per_sqm")
    )


def property_type_stats(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("property_category", dropna=False)
        .agg(
            listings=("ad_id", "count"),
            median_price_per_sqm=("price_per_sqm", "median"),
            median_price_mnt=("price_mnt", "median"),
            median_size_sqm=("size_sqm", "median"),
            median_distance_to_sukhbaatar_km=("distance_to_sukhbaatar_km", "median"),
        )
        .reset_index()
        .sort_values("median_price_per_sqm")
    )


def create_price_map(region_df: pd.DataFrame, output_path: str | Path, title: str) -> None:
    map_df = region_df.dropna(subset=["latitude", "longitude", "median_price_per_sqm"]).copy()
    if map_df.empty:
        raise SystemExit("No mappable regions after filtering.")

    map_df["marker_size"] = map_df["listings"].clip(lower=5, upper=80)
    lon_min = float(map_df["longitude"].min())
    lon_max = float(map_df["longitude"].max())
    lat_min = float(map_df["latitude"].min())
    lat_max = float(map_df["latitude"].max())
    lon_pad = max(0.004, (lon_max - lon_min) * 0.08)
    lat_pad = max(0.004, (lat_max - lat_min) * 0.08)
    bounds = {
        "west": lon_min - lon_pad,
        "east": lon_max + lon_pad,
        "south": lat_min - lat_pad,
        "north": lat_max + lat_pad,
    }
    fig = px.scatter_mapbox(
        map_df,
        lat="latitude",
        lon="longitude",
        color="median_price_per_sqm",
        size="marker_size",
        size_max=28,
        color_continuous_scale="RdYlGn_r",
        hover_name="region",
        hover_data={
            "district": True,
            "listings": True,
            "median_price_per_sqm_m": True,
            "median_price_mnt_m": True,
            "median_size_sqm": ":.1f",
            "three_room_listings": True,
            "avg_distance_to_sukhbaatar_km": ":.2f",
            "latitude": False,
            "longitude": False,
            "marker_size": False,
            "median_price_per_sqm": False,
        },
        title=title,
    )
    fig.update_layout(
        mapbox_style=GRAYSCALE_MAP_STYLE,
        mapbox={"bounds": bounds},
        coloraxis_colorbar_title="Median ₮/sqm",
        margin={"r": 0, "t": 48, "l": 0, "b": 0},
        height=820,
    )
    fig.write_html(output_path, include_plotlyjs="cdn")


def create_price_heatmap(listing_df: pd.DataFrame, output_path: str | Path, title: str) -> None:
    heat_df = listing_df.dropna(subset=["latitude", "longitude", "price_per_sqm"]).copy()
    if heat_df.empty:
        raise SystemExit("No mappable listings after filtering.")
    heat_df["heatmap_color_price_per_sqm"] = heat_df["price_per_sqm"].clip(
        lower=HEATMAP_COLOR_MIN_PRICE_PER_SQM,
        upper=HEATMAP_COLOR_MAX_PRICE_PER_SQM,
    )

    hover_text = heat_df.apply(
        lambda row: (
            f"{row.get('title', '')}<br>"
            f"Location: {row.get('location', '')}<br>"
            f"Price/sqm: {mnt_millions(row['price_per_sqm'])}<br>"
            f"Map color: {mnt_millions(row['heatmap_color_price_per_sqm'])}"
            f"{' (capped)' if row['price_per_sqm'] > HEATMAP_COLOR_MAX_PRICE_PER_SQM else ''}<br>"
            f"Price: {mnt_millions(row['price_mnt'])}<br>"
            f"Size: {row['size_sqm']:.1f} sqm<br>"
            f"Rooms: {row.get('room_category', 'unknown')}<br>"
            f"Distance source: {row.get('distance_source', '')}"
        ),
        axis=1,
    )

    # Plotly density maps aggregate nearby z values, which makes dense areas look
    # more expensive than the actual listings. Use per-listing colored points so
    # the colorbar is bounded by real listing-level price/sqm values.
    fig = go.Figure(
        go.Scattermapbox(
            lat=heat_df["latitude"],
            lon=heat_df["longitude"],
            mode="markers",
            marker={
                "size": 9,
                "color": heat_df["heatmap_color_price_per_sqm"],
                "colorscale": "RdYlGn_r",
                "cmin": HEATMAP_COLOR_MIN_PRICE_PER_SQM,
                "cmax": HEATMAP_COLOR_MAX_PRICE_PER_SQM,
                "opacity": 0.72,
                "colorbar": {"title": "Listing ₮/sqm<br>(color capped)"},
            },
            hoverinfo="text",
            text=hover_text,
            name="Listings",
        )
    )
    fig.add_trace(
        go.Scattermapbox(
            lat=[47.918873],
            lon=[106.917701],
            mode="markers+text",
            marker={"size": 12, "color": "black"},
            text=["Sukhbaatar Square"],
            textposition="top right",
            hovertext=["Sukhbaatar Square"],
            hoverinfo="text",
        )
    )
    fig.update_layout(
        title=title,
        mapbox={
            "style": GRAYSCALE_MAP_STYLE,
            "center": {"lat": 47.918873, "lon": 106.917701},
            "zoom": 10.2,
        },
        margin={"r": 0, "t": 48, "l": 0, "b": 0},
        height=820,
    )
    fig.write_html(output_path, include_plotlyjs="cdn")


def print_top10(top_path: str | Path) -> None:
    top_path = Path(top_path)
    if not top_path.exists():
        print(f"Top ranking file not found: {top_path}")
        return

    df = pd.read_csv(top_path).head(10)
    cols = [
        "recommendation_rank",
        "title",
        "price_mnt",
        "price_per_sqm",
        "distance_to_sukhbaatar_km",
        "location",
        "size_sqm",
        "link",
    ]
    print("\nTop 10 3-room apartment matches:")
    print(df[cols].to_string(index=False))


def build_statistics(
    input_path: str | Path,
    output_prefix: str,
    map_property_category: str = "apartment",
    min_listings: int = 5,
) -> None:
    df = prepare_data(input_path)

    map_source = df[df["property_category"].eq(map_property_category)].copy()
    if map_source.empty:
        raise SystemExit(f"No rows for property category: {map_property_category}")

    if map_property_category == "apartment":
        quality_mask = apartment_quality_mask(map_source)
        outliers = map_source[~quality_mask].copy()
        map_source = map_source[quality_mask].copy()
    else:
        outliers = map_source.iloc[0:0].copy()

    subregion = region_stats(map_source, "sub_location", min_listings=min_listings)
    district = region_stats(map_source, "district", min_listings=1)
    rooms = room_stats(map_source)
    property_types = property_type_stats(df)

    subregion_path = Path(f"{output_prefix}_apartment_region_stats.csv")
    district_path = Path(f"{output_prefix}_apartment_district_stats.csv")
    rooms_path = Path(f"{output_prefix}_apartment_room_stats.csv")
    property_path = Path(f"{output_prefix}_property_type_stats.csv")
    outlier_path = Path(f"{output_prefix}_apartment_price_outliers.csv")
    capped_path = Path(f"{output_prefix}_apartment_heatmap_color_capped.csv")
    map_path = Path(f"{output_prefix}_apartment_price_per_sqm_map.html")
    heatmap_path = Path(f"{output_prefix}_apartment_price_per_sqm_heatmap.html")

    subregion.to_csv(subregion_path, index=False, encoding="utf-8-sig")
    district.to_csv(district_path, index=False, encoding="utf-8-sig")
    rooms.to_csv(rooms_path, index=False, encoding="utf-8-sig")
    property_types.to_csv(property_path, index=False, encoding="utf-8-sig")
    outlier_cols = [
        "ad_id",
        "title",
        "price_mnt",
        "price_per_sqm",
        "size_sqm",
        "size_sqm_raw",
        "size_sqm_source",
        "rooms_clean",
        "location",
        "property_category",
        "link",
    ]
    outliers[[col for col in outlier_cols if col in outliers.columns]].to_csv(
        outlier_path, index=False, encoding="utf-8-sig"
    )
    capped_rows = map_source[map_source["price_per_sqm"] > HEATMAP_COLOR_MAX_PRICE_PER_SQM].copy()
    capped_rows[[col for col in outlier_cols if col in capped_rows.columns]].to_csv(
        capped_path, index=False, encoding="utf-8-sig"
    )
    create_price_map(
        subregion,
        map_path,
        f"Ulaanbaatar apartment median price per sqm by region (min {min_listings} listings)",
    )
    create_price_heatmap(
        map_source,
        heatmap_path,
        "Ulaanbaatar apartment actual listing price per sqm (color capped at 12M ₮/sqm)",
    )

    print_top10("unegui_ub_50_ranked_3room_apartments.csv")
    print(
        f"\nApartment map/stat rows after quality filter: {len(map_source)} "
        f"(excluded {len(outliers)} outlier/suspicious rows; saved to {outlier_path})"
    )
    print(
        f"Heatmap color scale capped at {mnt_millions(HEATMAP_COLOR_MAX_PRICE_PER_SQM)}; "
        f"{len(capped_rows)} mapped high-end rows exceed that cap and are saved to {capped_path}."
    )

    print("\nLowest median apartment price/sqm regions:")
    print(
        subregion[
            ["region", "district", "listings", "median_price_per_sqm_m", "median_price_mnt_m", "median_size_sqm"]
        ]
        .head(10)
        .to_string(index=False)
    )

    print("\nHighest median apartment price/sqm regions:")
    print(
        subregion.tail(10)
        .sort_values("median_price_per_sqm", ascending=False)[
            ["region", "district", "listings", "median_price_per_sqm_m", "median_price_mnt_m", "median_size_sqm"]
        ]
        .to_string(index=False)
    )

    print("\nDistrict apartment stats:")
    print(
        district[
            ["region", "listings", "median_price_per_sqm_m", "median_price_mnt_m", "median_size_sqm"]
        ].to_string(index=False)
    )

    print(f"\nSaved map to {map_path}")
    print(f"Saved heatmap to {heatmap_path}")
    print(f"Saved region stats to {subregion_path}")
    print(f"Saved district stats to {district_path}")
    print(f"Saved room stats to {rooms_path}")
    print(f"Saved property-type stats to {property_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create listing statistics and a median price/sqm map.")
    parser.add_argument("--input", default="unegui_ub_50_pages_details.csv", help="Scraped details CSV.")
    parser.add_argument("--output-prefix", default="unegui_ub_50_stats", help="Output file prefix.")
    parser.add_argument("--min-listings", type=int, default=5, help="Minimum listings per mapped region.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    build_statistics(args.input, args.output_prefix, min_listings=args.min_listings)


if __name__ == "__main__":
    main()
