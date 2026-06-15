# Unegui UB Housing Market Analysis and Forecast

This project scrapes public Unegui.mn apartment listings for Ulaanbaatar, cleans the listing data, maps price patterns, and ranks 3-room apartment listings using a 5-year nominal MNT forecast.

The repository is meant to hold reproducible code and documentation. Raw scrapes, generated CSV/XLSX/HTML/ZIP/PDF files, downloaded photos, and user-provided 1212.mn (Official Statistics Info) tables are intentionally excluded from git.

## Snapshot

### Ulaanbaatar Price Map
![Ulaanbaatar median price map](assets/ub_median_price_map.png)

### Forecast Shortlist
![Forecast shortlist](assets/ub_top10_forecast.png)

## What It Does

1. Scrapes listing pages and optional detail pages from Unegui.mn (free public listings website).
2. Extracts price, location, size, room count, listing date, links, and detail fields.
3. Cleans suspicious values, computes price per sqm, and estimates distance to Sukhbaatar Square.
4. Builds maps and statistics by region, district, room count, and property type.
5. Forecasts fair value using a 50/50 blend of Unegui area medians and official 1212.mn district averages.
6. Ranks filtered 3-room listings and exports a shareable top-10 HTML report with listing photos and maps.

## Current Ranking Scope

Hard filters:

- 3-room apartments only.
- Asking price from 300,000,000 MNT to 600,000,000 MNT.
- Area greater than 70 sqm.
- Obvious title/location district conflicts are excluded.
- Near-duplicates are collapsed by location, size, room count, and similar asking price.

Forecast assumptions:

- Nominal MNT, 5-year projection.
- `new` means built in 2021 or later.
- Fair value per sqm is 50% Unegui area median and 50% official 1212.mn district average.
- Forecast output is for ranking and screening, not a formal appraisal.

Ranking weights:

- Forecast upside: 45%
- Building newness: 20%
- Current MNT per sqm: 15%
- Distance to Sukhbaatar Square: 20%

## Reproduce The Analysis

Install dependencies:

```bash
pip install -r requirements.txt
```

Scrape all listing pages and detail pages:

```bash
python scraper.py --all-pages --details --workers N --output unegui_ub_all_pages_details.csv --analyze --analysis-prefix unegui_ub_all
```

Build statistics and maps:

```bash
python listing_statistics.py --input unegui_ub_all_pages_details.csv --output-prefix unegui_ub_all_stats
```

Build the 3-room forecast ranking. Place the required 1212.mn source tables in `Stats/` before this step:

```bash
python forecast_listings.py --input unegui_ub_all_pages_details.csv --stats-dir Stats --output-prefix unegui_ub_all_3room_filtered
```

Export the top-10 report:

```bash
python export_top10_details.py --input unegui_ub_all_3room_filtered_forecast_ranked_apartments.csv --output-dir top10_forecast_all_3room_filtered_report --top-n 10 --workers 8
```

Refresh the README figures:

```bash
python build_readme_assets.py --map-html unegui_ub_all_stats_apartment_price_per_sqm_map.html
```

## Main Outputs

- `unegui_ub_all_pages_details.csv` - full scraped listing dataset.
- `unegui_ub_all_stats_apartment_price_per_sqm_heatmap.html` - listing-level price/sqm heatmap.
- `unegui_ub_all_stats_apartment_price_per_sqm_map.html` - median price/sqm map by region.
- `unegui_ub_all_3room_filtered_forecast_all.csv` - forecast fields with exclusion notes.
- `unegui_ub_all_3room_filtered_forecast_ranked_apartments.csv` - deduped ranked listings.
- `unegui_ub_all_3room_filtered_forecast_top10.csv` - final top-10 shortlist.
- `top10_forecast_all_3room_filtered_report/top10_listings_report.html` - shareable report with photos, details, overview map, and one map per listing.
- `Unegui_UB_all_3room_filtered_Forecast_Listings.xlsx` and `Unegui_UB_all_3room_filtered_forecast_results_package.zip` - shareable workbook and package.

## Repository Layout

- `scraper.py` - scraper and basic analysis entry point.
- `listing_statistics.py` - statistics tables, median price map, and heatmap.
- `rank_listings.py` - cleaning, geocoding helpers, distance features, duplicate handling, and ranking utilities.
- `forecast_listings.py` - 5-year forecast model and final shortlist ranking.
- `export_top10_details.py` - listing photo download and HTML report export.
- `build_readme_assets.py` - PNG figures for this README.
- `make_share_package.py` - legacy package builder kept for older result bundles.
- `assets/` - tracked README images only.
- `Stats/` - user-provided 1212.mn source tables, ignored by git.

## Data Notes

- `price_per_sqm` is derived from listing asking price and area.
- `asking_to_fair_pct = (asking price / estimated fair value) - 1`; negative values indicate asking price below model-estimated fair value.
- The heatmap uses actual listing-level price/sqm values.
- The median map uses region or district median price/sqm.
- Some coordinates are inferred from area or district lookups when exact listing coordinates are unavailable.
- Generated data and reports are ignored so the public repo stays lightweight.

## Requirements

- Python 3.10+
- `pandas`
- `requests`
- `beautifulsoup4`
- `plotly`
- `kaleido`
- `Pillow`

## License

MIT License. See `LICENSE`.

## Монгол Товч Танилцуулга (AI orchuulga)

Энэ төсөл нь Unegui.mn дээрх Улаанбаатар хотын орон сууцны заруудыг татаж, үнэ, талбай, өрөөний тоо, байршил, зарын огноо зэрэг мэдээллийг цэвэрлэн нэгтгэнэ. Дараа нь бүсийн үнийн зураг, статистик, 5 жилийн нэрлэсэн MNT таамаглал, мөн 3 өрөө байрны топ-10 богино жагсаалт үүсгэнэ.

GitHub репод зөвхөн код, README, шаардлагатай зурагнууд хадгалагдана. Том хэмжээтэй татсан өгөгдөл, CSV/XLSX/HTML/ZIP/PDF гаралтын файлууд, татсан зураг, 1212.mn-ийн эх хүснэгтүүд git-д орохгүй.

## Монгол: Одоогийн Шүүлтүүр Ба Жин

Шүүлтүүр:

- Зөвхөн 3 өрөө орон сууц.
- Нийт үнэ 300 саяас 600 сая MNT.
- Талбай 70 м²-ээс их.
- Байршил/дүүргийн илт зөрчилтэй заруудыг хасна.
- Давхардсан эсвэл маш төстэй заруудыг нэгтгэнэ.

Таамаглал:

- 5 жилийн нэрлэсэн MNT төсөөлөл.
- 2021 оноос хойш баригдсан бол `new` гэж үзнэ.
- Fair value per sqm = 50% Unegui бүсийн медиан + 50% 1212.mn дүүргийн дундаж.
- Энэ нь албан ёсны үнэлгээ биш, харин эрэмбэлэх болон анхан шатны шүүлт хийх хэрэгсэл.

Эрэмбэлэх жин:

- Ирээдүйн өсөлт: 45%
- Барилгын шинэ байдал: 20%
- Одоогийн MNT/м²: 15%
- Сүхбаатарын талбай хүртэлх зай: 20%

## Монгол: Ажиллуулах Дараалал

Шаардлагатай сангуудыг суулгах:

```bash
pip install -r requirements.txt
```

Бүх зар болон дэлгэрэнгүй хуудсуудыг татах:

```bash
python scraper.py --all-pages --details --workers N --output unegui_ub_all_pages_details.csv --analyze --analysis-prefix unegui_ub_all
```

Статистик болон газрын зураг үүсгэх:

```bash
python listing_statistics.py --input unegui_ub_all_pages_details.csv --output-prefix unegui_ub_all_stats
```

Таамаглал дээр суурилсан эрэмбэлэлт хийх:

```bash
python forecast_listings.py --input unegui_ub_all_pages_details.csv --stats-dir Stats --output-prefix unegui_ub_all_3room_filtered
```

Топ-10 HTML тайлан гаргах:

```bash
python export_top10_details.py --input unegui_ub_all_3room_filtered_forecast_ranked_apartments.csv --output-dir top10_forecast_all_3room_filtered_report --top-n 10 --workers 8
```

README-ийн зургуудыг шинэчлэх:

```bash
python build_readme_assets.py --map-html unegui_ub_all_stats_apartment_price_per_sqm_map.html
```

## Монгол: Өгөгдлийн Тэмдэглэл

- `price_per_sqm` нь зарын нийт үнэ болон талбайгаас тооцогдоно.
- `asking_to_fair_pct` сөрөг байвал зарын үнэ загварын тооцоолсон fair value-ээс доогуур гэсэн үг.
- Heatmap зураг нь зар бүрийн бодит price/sqm утгыг ашиглана.
- Median map нь бүс эсвэл дүүргийн median price/sqm-ийг ашиглана.
- Зарим координатыг нарийвчилсан координат байхгүй үед бүс/дүүргийн lookup-аар нөхөж тооцно.
