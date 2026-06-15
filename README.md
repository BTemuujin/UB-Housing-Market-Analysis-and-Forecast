# Unegui UB Apartment Analysis

This repository scrapes public Unegui.mn apartment listings for Ulaanbaatar, normalizes the listing data, computes price and location statistics, builds a 5-year nominal MNT forecast, and exports a shareable top-10 shortlist with real listing photos and maps.

The project is built for reproducible analysis rather than one-off spreadsheets. The checked-in files are the scripts and documentation. Generated CSV, XLSX, HTML, ZIP, PDF, and download folders are intentionally excluded from version control.

## Snapshot

### Ulaanbaatar price map
![Ulaanbaatar median price map](assets/ub_median_price_map.png)

The cover map is exported from the real Plotly HTML map output and is fit to the data extent so it only shows the regions with listings.

### Forecast shortlist
![Forecast shortlist](assets/ub_top10_forecast.png)

## What This Project Does

1. Scrapes Unegui listing pages and, when requested, individual detail pages.
2. Parses price, room count, size, listing date, location, and listing links.
3. Computes apartment statistics by district, region, room count, and property type.
4. Builds a forecasting model using local Unegui medians plus official 1212 tables.
5. Ranks listings using forecast upside, newness, current price per sqm, and distance to Sukhbaatar Square.
6. Exports a shareable top-10 HTML report with actual listing photos, a map overview, and one map per listing.

## Repository Layout

- `scraper.py` - crawl Unegui listing pages, optionally fetch detail pages, and create basic analysis CSVs.
- `listing_statistics.py` - build region and district statistics plus the price-per-sqm heatmap and median map.
- `rank_listings.py` - clean, deduplicate, and rank listings by price/sqm, distance, and room count.
- `forecast_listings.py` - build the 5-year nominal MNT forecast and final ranked shortlist.
- `export_top10_details.py` - download listing photos and render the top-10 HTML report with maps and full details.
- `build_readme_assets.py` - build the PNG figures used on the README front page.
- `make_share_package.py` - legacy bundle builder for earlier shareable outputs.
- `Stats/` - local 1212 tables used by the forecast step. Not tracked in git.
- `share_results*/`, `top10_*report/`, and the generated CSV/XLSX/ZIP/PDF files - build outputs. Not tracked in git.

## Current Analysis Rules

The current full-scrape ranking workflow uses these filters:

- 3-room apartments only.
- Total asking price between 300,000,000 MNT and 600,000,000 MNT.
- Total area strictly greater than 70 sqm.
- Rows with obvious title/location district conflicts are excluded from ranking.
- Near-duplicate listings with the same location, size, room count, and very similar asking prices are collapsed to one representative.

Forecast assumptions:

- New means built in 2021 or later.
- Fair value per sqm is a 50/50 blend of local Unegui medians and official 1212 district averages.
- The forecast is a 5-year nominal MNT projection.

Current ranking weights:

- Forecast upside: 45%
- Building newness: 20%
- Current MNT per sqm: 15%
- Distance to Sukhbaatar Square: 20%

## Key Outputs

The current full-scrape workflow produces these main files:

- `unegui_ub_all_pages_details.csv` - raw full scrape of Unegui listing pages.
- `unegui_ub_all_stats_apartment_price_per_sqm_heatmap.html` - heatmap based on actual listing-level price per sqm values.
- `unegui_ub_all_stats_apartment_price_per_sqm_map.html` - median price-per-sqm map by region.
- `unegui_ub_all_3room_filtered_forecast_all.csv` - all rows with forecast fields and exclusion notes.
- `unegui_ub_all_3room_filtered_forecast_ranked_apartments.csv` - deduped ranked list.
- `unegui_ub_all_3room_filtered_forecast_top10.csv` - final top 10 shortlist.
- `Unegui_UB_all_3room_filtered_Forecast_Listings.xlsx` - shareable workbook.
- `top10_forecast_all_3room_filtered_report/top10_listings_report.html` - HTML report with photos, details, overview map, and one map per listing.
- `Unegui_UB_all_3room_filtered_forecast_results_package.zip` - bundled share package.

## Reproducible Workflow

### 1. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 2. Scrape all pages

Use `--all-pages` to discover pagination automatically. Add `--details` to fetch the listing detail pages, which is required for the richer analysis outputs.

```bash
python scraper.py --all-pages --details --workers 12 --output unegui_ub_all_pages_details.csv --analyze --analysis-prefix unegui_ub_all
```

### 3. Build statistics and maps

```bash
python listing_statistics.py --input unegui_ub_all_pages_details.csv --output-prefix unegui_ub_all_stats
```

This produces the region and district statistics, room counts, property-type breakdowns, the apartment price-per-sqm heatmap, and the median price-per-sqm map.

### 4. Build the forecast ranking

Place the required 1212 tables in `Stats/` first. The forecast step expects the annual HPI table and the district price table used by `forecast_listings.py`.

```bash
python forecast_listings.py --input unegui_ub_all_pages_details.csv --stats-dir Stats --output-prefix unegui_ub_all_3room_filtered
```

### 5. Export the top-10 report

```bash
python export_top10_details.py --input unegui_ub_all_3room_filtered_forecast_ranked_apartments.csv --output-dir top10_forecast_all_3room_filtered_report --top-n 10 --workers 8
```

The HTML report includes:

- actual listing photos downloaded from the listing page,
- the parsed listing details,
- one overview map of the top 10,
- one individual map for each listing,
- links back to the original Unegui pages.

### 6. Build the README figures

```bash
python build_readme_assets.py --map-html unegui_ub_all_stats_apartment_price_per_sqm_map.html
```

If Chrome is not already available to Kaleido in your environment, pass `--chrome-path /path/to/chrome` so the map cover is rendered from the HTML export instead of falling back to the schematic version.

This writes:

- `assets/ub_median_price_map.png`
- `assets/ub_top10_forecast.png`

## Data Notes

- `price_per_sqm` is always derived from the asking price and area of the listing.
- `asking_to_fair_pct` is `(asking price / estimated fair value) - 1`. Negative values mean the asking price is below the model estimate.
- The heatmap uses actual listing-level price-per-sqm values, not district medians.
- The median map uses median price per sqm by region or district.
- Some coordinates are inferred from area or district lookups when exact listing coordinates are not available.
- The forecast is a ranking tool, not a formal appraisal.

## Requirements

- Python 3.10 or newer.
- `pandas`
- `requests`
- `beautifulsoup4`
- `plotly`
- `kaleido`
- `Pillow`

Install them with:

```bash
python -m pip install -r requirements.txt
```

---

## Монгол хувилбар

Энэ репозитор нь Улаанбаатар дахь Unegui.mn-ийн орон сууцны заруудыг татаж, өгөгдлийг цэвэрлэн нэгтгэж, үнэ болон байршлын статистик тооцоолж, 5 жилийн нэрлэсэн MNT-ийн төсөөлөл гарган, бодит зураг болон газрын зурагтай топ-10 жагсаалт үүсгэнэ.

Энэ төсөл нь нэг удаагийн хүснэгтээс илүү дахин ажиллуулах боломжтой шинжилгээнд зориулагдсан. Репод зөвхөн скрипт болон баримт бичиг хадгална. Үүсгэсэн CSV, XLSX, HTML, ZIP, PDF болон татсан өгөгдлийн хавтаснуудыг git-д оруулахгүй.

## Хураангуй зураг

### Улаанбаатарын үнийн зураг
![Улаанбаатарын үнийн зураг](assets/ub_median_price_map.png)

Энэ зураг нь Plotly-оор үүсгэсэн бодит HTML map-ээс экспортлогдсон бөгөөд өгөгдөлтэй бүсүүдийг л харуулахаар fit хийсэн.

### Таамагласан эхний 10
![Таамагласан эхний 10](assets/ub_top10_forecast.png)

## Төсөл юу хийдэг вэ

1. Unegui.mn-ийн зарын хуудсуудыг scrape хийж, шаардлагатай үед дэлгэрэнгүй хуудсуудыг нь татна.
2. Үнэ, өрөөний тоо, талбай, зарын огноо, байршил, зарын холбоосыг parse хийнэ.
3. Дүүрэг, бүс, өрөөний тоо, үл хөдлөхийн төрлөөр статистик тооцоолно.
4. Орон нутгийн Unegui дундаж болон 1212.mn-ийн албан ёсны хүснэгтийг ашиглан forecast загвар байгуулна.
5. Ирээдүйн өсөлт, шинэ байдал, одоогийн ₮/м², Сүхбаатарын талбай хүртэлх зайгаар заруудыг эрэмбэлнэ.
6. Бодит зураг, ерөнхий газрын зураг, зар бүрийн тусдаа зурагтай хуваалцахад бэлэн топ-10 HTML report гаргана.

## Репозиторын бүтэц

- `scraper.py` - Unegui-ийн зарын хуудсуудыг crawl хийж, шаардлагатай бол дэлгэрэнгүй хуудсуудыг татан суурь CSV үүсгэнэ.
- `listing_statistics.py` - бүс, дүүргийн статистик, ₮/м² heatmap болон median map үүсгэнэ.
- `rank_listings.py` - заруудыг price/sqm, зай, өрөөний тоогоор цэвэрлэж, dedupe хийж, эрэмбэлнэ.
- `forecast_listings.py` - 5 жилийн нэрлэсэн MNT-ийн forecast болон эцсийн ranked shortlist үүсгэнэ.
- `export_top10_details.py` - зарын зургуудыг татаж, map болон бүрэн дэлгэрэнгүйтэй top-10 HTML report гаргана.
- `build_readme_assets.py` - README-ийн нүүрэнд ашиглах PNG зургуудыг үүсгэнэ.
- `make_share_package.py` - өмнөх shareable output-уудын legacy bundle builder.
- `Stats/` - forecast алхамд ашиглах орон нутгийн 1212 хүснэгтүүд. Git-д tracked биш.
- `share_results*/`, `top10_*report/`, мөн үүссэн CSV/XLSX/ZIP/PDF файлууд - build output. Git-д tracked биш.

## Одоогийн шүүлтүүрийн дүрэм

Full-scrape дээрх одоогийн ranking workflow дараах шүүлтүүрийг ашиглана:

- Зөвхөн 3 өрөөтэй орон сууц.
- Нийт үнэ 300,000,000 MNT-ээс 600,000,000 MNT-ийн хооронд.
- Нийт талбай 70 м²-ээс их.
- Гарчиг/байршлын дүүргийн илт зөрчилтэй мөрүүдийг ranking-аас хасна.
- Ижил байршил, ижил хэмжээ, ижил өрөөний тоо, маш ойролцоо үнэтэй near-duplicate заруудыг нэг төлөөлөгч мөр болгон нэгтгэнэ.

Forecast-ийн таамаглал:

- Шинэ гэдэг нь 2021 оноос хойш баригдсан гэсэн үг.
- Fair value per sqm нь Unegui-ийн local median болон 1212.mn-ийн дүүргийн дундажийн 50/50 холимог.
- Forecast нь 5 жилийн нэрлэсэн MNT-ийн төсөөлөл.

Одоогийн ranking weight:

- Ирээдүйн өсөлт: 45%
- Барилгын шинэ байдал: 20%
- Одоогийн MNT/м²: 15%
- Сүхбаатарын талбай хүртэлх зай: 20%

## Гол output-ууд

Full-scrape workflow дараах үндсэн файлуудыг үүсгэнэ:

- `unegui_ub_all_pages_details.csv` - Unegui listing pages-ийн raw full scrape.
- `unegui_ub_all_stats_apartment_price_per_sqm_heatmap.html` - listing түвшний бодит price per sqm утгад суурилсан heatmap.
- `unegui_ub_all_stats_apartment_price_per_sqm_map.html` - бүсээрх median price per sqm map.
- `unegui_ub_all_3room_filtered_forecast_all.csv` - forecast талбарууд болон хасалтын тайлбартай бүх мөр.
- `unegui_ub_all_3room_filtered_forecast_ranked_apartments.csv` - dedupe хийгдсэн ranked жагсаалт.
- `unegui_ub_all_3room_filtered_forecast_top10.csv` - эцсийн top 10 shortlist.
- `Unegui_UB_all_3room_filtered_Forecast_Listings.xlsx` - хуваалцахад бэлэн workbook.
- `top10_forecast_all_3room_filtered_report/top10_listings_report.html` - зураг, дэлгэрэнгүй, overview map, зар бүрийн map бүхий HTML report.
- `Unegui_UB_all_3room_filtered_forecast_results_package.zip` - багцласан share package.

## Дахин ажиллуулах workflow

### 1. Dependency суулгах

```bash
python -m pip install -r requirements.txt
```

### 2. Бүх хуудсыг scrape хийх

`--all-pages` нь pagination-ийг автоматаар олно. `--details` нь зарын дэлгэрэнгүй хуудсуудыг татна. Энэ нь баяжуулсан анализад шаардлагатай.

```bash
python scraper.py --all-pages --details --workers 12 --output unegui_ub_all_pages_details.csv --analyze --analysis-prefix unegui_ub_all
```

### 3. Статистик болон map үүсгэх

```bash
python listing_statistics.py --input unegui_ub_all_pages_details.csv --output-prefix unegui_ub_all_stats
```

Энэ алхам нь бүс, дүүргийн статистик, өрөөний тооны хуваарилалт, үл хөдлөхийн төрлийн breakdown, apartment price-per-sqm heatmap, мөн median price-per-sqm map үүсгэнэ.

### 4. Forecast ranking хийх

Шаардлагатай 1212 хүснэгтүүдийг эхлээд `Stats/` дотор байрлуулна. Forecast алхам нь жилийн HPI хүснэгт болон `forecast_listings.py` ашигладаг дүүргийн үнийн хүснэгтийг хүлээнэ.

```bash
python forecast_listings.py --input unegui_ub_all_pages_details.csv --stats-dir Stats --output-prefix unegui_ub_all_3room_filtered
```

### 5. Top-10 report экспортлох

```bash
python export_top10_details.py --input unegui_ub_all_3room_filtered_forecast_ranked_apartments.csv --output-dir top10_forecast_all_3room_filtered_report --top-n 10 --workers 8
```

HTML report-д дараах зүйлс орно:

- зарын хуудаснаас татсан бодит зураг,
- parse хийсэн зарын дэлгэрэнгүй,
- top 10-ийн нэг ерөнхий map,
- зар бүрийн нэг тусдаа map,
- анхны Unegui хуудсууд руу буцах холбоос.

### 6. README-ийн зургуудыг үүсгэх

```bash
python build_readme_assets.py --map-html unegui_ub_all_stats_apartment_price_per_sqm_map.html
```

Хэрэв таны орчинд Kaleido-д зориулсан Chrome бэлэн биш бол `--chrome-path /path/to/chrome` нэмнэ. Ингэснээр cover map нь HTML export-оос шууд render хийгдэнэ; эс бөгөөс schematic хувилбар руу fallback хийнэ.

Энэ алхам дараах файлуудыг бичнэ:

- `assets/ub_median_price_map.png`
- `assets/ub_top10_forecast.png`

## Өгөгдлийн тэмдэглэл

- `price_per_sqm` нь зарын нийт үнэ болон талбайгаас үргэлж тооцогдоно.
- `asking_to_fair_pct` нь `(asking price / estimated fair value) - 1`. Сөрөг утга нь зарын үнэ model-ийн estimate-ээс доогуур байгааг илтгэнэ.
- Heatmap нь дүүргийн median биш, listing түвшний бодит price-per-sqm утгыг ашиглана.
- Median map нь бүс эсвэл дүүрэг тус бүрийн median price per sqm-ийг ашиглана.
- Зарим координатыг exact listing coordinate байхгүй үед бүс эсвэл дүүргийн lookup-аар нөхөж тооцно.
- Forecast нь үнэлгээний хэрэгсэл болохоос албан ёсны appraisal биш.

## Шаардлагатай зүйлс

- Python 3.10 эсвэл түүнээс шинэ.
- `pandas`
- `requests`
- `beautifulsoup4`
- `plotly`
- `kaleido`
- `Pillow`

Суулгах команд:

```bash
python -m pip install -r requirements.txt
```
