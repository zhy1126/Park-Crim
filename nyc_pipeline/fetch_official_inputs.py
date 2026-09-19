from __future__ import annotations

import json
import html as html_lib
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
PRESS_RAW = RAW / "press_releases"
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"
for path in (RAW, PRESS_RAW, DATA, ARTIFACTS):
    path.mkdir(parents=True, exist_ok=True)

BASE = "https://www.nycgovparks.org"
ARCHIVE = BASE + "/news/press-releases/?month={month:02d}&year={year}"
PARKS_GEOJSON = "https://data.cityofnewyork.us/resource/enfh-gkve.geojson?$limit=5000"
PARKS_METADATA = "https://data.cityofnewyork.us/api/views/enfh-gkve"

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (compatible; academic park-opening research; contact via NYC Open Data)",
        "Accept": "text/html,application/json",
    }
)

CANDIDATE_PATTERN = re.compile(
    r"\b(open(?:s|ed|ing)?|reopen(?:s|ed|ing)?|unveil(?:s|ed|ing)?|"
    r"debut(?:s|ed|ing)?|ribbon[- ]cutting|cuts? (?:the )?ribbon|dedicat(?:e|es|ed|ing)|"
    r"new park|new public space)\b",
    re.I,
)


def get(url: str, timeout: int = 45) -> requests.Response:
    response = SESSION.get(url, timeout=timeout)
    response.raise_for_status()
    return response


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def scrape_archive_page(year: int, month: int) -> list[dict[str, object]]:
    url = ARCHIVE.format(year=year, month=month)
    response = get(url)
    html_path = PRESS_RAW / f"archive_{year}_{month:02d}.html"
    html_path.write_text(response.text, encoding="utf-8")
    rows: list[dict[str, object]] = []
    pattern = re.compile(
        r'<div class="dp_dates_container">.*?'
        r'<div class="dp_dates_header">(.*?)</div>.*?'
        r'<a href="([^"]+)" class="dp_events">(.*?)</a>',
        re.I | re.S,
    )
    for header_html, href, title_html in pattern.findall(response.text):
        header_text = clean_text(html_lib.unescape(re.sub(r"<[^>]+>", " ", header_html)))
        try:
            release_date = datetime.strptime(f"{header_text} {year}", "%b %d %Y").date()
        except ValueError:
            continue
        text = clean_text(html_lib.unescape(re.sub(r"<[^>]+>", " ", title_html)))
        if not href or len(text) < 12:
            continue
        detail_url = urljoin(BASE, href)
        if "/pressrelease/" not in detail_url and "press_releases.php?id=" not in detail_url:
            continue
        rows.append(
            {
                "release_date": release_date.isoformat(),
                "title": text,
                "url": detail_url,
                "candidate_keyword": bool(CANDIDATE_PATTERN.search(text)),
            }
        )
    unique = {row["url"]: row for row in rows}
    return list(unique.values())


def fetch_candidate_details(index: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    candidates = index[index["candidate_keyword"]].copy()
    for position, row in enumerate(candidates.itertuples(index=False), start=1):
        response = get(row.url)
        id_match = re.search(r"[?&]id=(\d+)", row.url)
        slug = f"id_{id_match.group(1)}" if id_match else re.sub(
            r"[^A-Za-z0-9_-]+", "_", row.url.rstrip("/").split("/")[-1]
        )
        (PRESS_RAW / f"detail_{slug}.html").write_text(response.text, encoding="utf-8")
        soup = BeautifulSoup(response.text, "html.parser")
        main = soup.find("main") or soup.find(id="main") or soup.body or soup
        body_text = clean_text(main.get_text(" ", strip=True))
        rows.append(
            {
                "release_date": row.release_date,
                "title": row.title,
                "url": row.url,
                "body_text": body_text,
                "mentions_new_park": bool(re.search(r"\b(new park|new public park|new public space)\b", body_text, re.I)),
                "mentions_open_to_public": bool(re.search(r"\b(open(?:ed|s)? to the public|officially open|now open)\b", body_text, re.I)),
                "mentions_reopening": bool(re.search(r"\b(reopen(?:ed|s|ing)?|re-opening)\b", body_text, re.I)),
                "mentions_reconstruction": bool(re.search(r"\b(reconstruct(?:ed|ion)|renovat(?:ed|ion)|rehabilitat(?:ed|ion))\b", body_text, re.I)),
            }
        )
        if position % 25 == 0:
            time.sleep(0.2)
    return pd.DataFrame(rows)


def main() -> None:
    index_path = DATA / "nyc_press_release_index_2010_2019.csv"
    candidate_path = DATA / "nyc_press_release_opening_candidates.csv"
    if index_path.exists() and candidate_path.exists():
        index = pd.read_csv(index_path)
        candidates = pd.read_csv(candidate_path)
    else:
        archive_rows: list[dict[str, object]] = []
        for year in range(2010, 2020):
            for month in range(1, 13):
                archive_rows.extend(scrape_archive_page(year, month))
        index = pd.DataFrame(archive_rows).drop_duplicates("url").sort_values(["release_date", "title"])
        index.to_csv(index_path, index=False, encoding="utf-8-sig")

        candidates = fetch_candidate_details(index)
        candidates.to_csv(candidate_path, index=False, encoding="utf-8-sig")

    parks = get(PARKS_GEOJSON).json()
    (RAW / "nyc_parks_properties.geojson").write_text(json.dumps(parks), encoding="utf-8")
    metadata = get(PARKS_METADATA).json()
    (RAW / "nyc_parks_properties_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = {
        "archive_pages": 120,
        "release_records": int(len(index)),
        "keyword_candidates": int(len(candidates)),
        "park_features": int(len(parks.get("features", []))),
        "date_min": index["release_date"].min() if len(index) else None,
        "date_max": index["release_date"].max() if len(index) else None,
    }
    (ARTIFACTS / "official_fetch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
