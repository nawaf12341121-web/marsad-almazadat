#!/usr/bin/env python3
"""
Preview-only collector for Abdullah Fouad Auctions.
It reads public listing/detail pages and writes a reviewable JSON file.
It NEVER connects to Supabase and NEVER publishes or inserts auctions.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

LIST_URL = "https://abdullafouadauction.com/%D8%A7%D9%84%D9%85%D8%B2%D8%A7%D8%AF%D8%A7%D8%AA/"
SOURCE_NAME = "عبدالله فؤاد للمزادات"
HEADERS = {
    "User-Agent": "MarsadAlmazadatPreviewBot/0.1 (contact: site owner)",
    "Accept-Language": "ar,en;q=0.8",
}


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return BeautifulSoup(response.text, "html.parser")


def collect_detail_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = urljoin(base_url, anchor.get("href", "").strip())
        parsed = urlparse(href)
        if parsed.netloc.lower() != "abdullafouadauction.com":
            continue
        # Detail pages on this source use Arabic auction slugs.
        if "/المزاد-" not in parsed.path and "/auction/" not in parsed.path.lower():
            continue
        href = parsed._replace(query="", fragment="").geturl()
        if href not in seen:
            seen.add(href)
            found.append(href)
    return found


def extract_auction(session: requests.Session, url: str) -> dict:
    soup = get_soup(session, url)
    h1 = soup.find("h1")
    title = clean(h1.get_text(" ", strip=True) if h1 else "")
    if not title:
        title = clean((soup.find("meta", property="og:title") or {}).get("content", ""))

    description_tag = soup.find("meta", attrs={"name": "description"})
    description = clean(description_tag.get("content", "") if description_tag else "")

    text = clean(soup.get_text(" ", strip=True))
    location = ""
    location_match = re.search(r"الموقع\s*[:：]?\s*(.{5,180}?)(?:\s+(?:نوع المزاد|أيام المزاد|نص الإعلان|كيف تشارك))", text)
    if location_match:
        location = clean(location_match.group(1))

    published = ""
    published_match = re.search(r"تاريخ النشر\s*[:：]?\s*(.{3,50}?)(?:\s+(?:تفاصيل المزاد|نوع المزاد))", text)
    if published_match:
        published = clean(published_match.group(1))

    return {
        "source_name": SOURCE_NAME,
        "title": title,
        "auction_url": url,
        "source_url": LIST_URL,
        "description": description,
        "location_candidate": location,
        "published_date_candidate": published,
        "review_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview public Abdullah Fouad auction listings; no database writes.")
    parser.add_argument("--output", default="abdullah_fouad_preview.json", help="JSON output path")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between detail-page requests")
    args = parser.parse_args()

    session = requests.Session()
    try:
        listing_soup = get_soup(session, LIST_URL)
        links = collect_detail_links(listing_soup, LIST_URL)
        if not links:
            print("No auction detail links found. The source page structure may have changed.", file=sys.stderr)
            return 2

        auctions = []
        for index, link in enumerate(links):
            if index:
                time.sleep(max(0.5, args.delay))
            try:
                item = extract_auction(session, link)
                if item["title"]:
                    auctions.append(item)
            except requests.RequestException as exc:
                print(f"Skipped {link}: {exc}", file=sys.stderr)

        result = {
            "collector": "abdullah_fouad_preview",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "preview_only",
            "database_write": False,
            "source_listing_url": LIST_URL,
            "items_found": len(auctions),
            "auctions": auctions,
        }
        with open(args.output, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)

        print(f"Preview complete: {len(auctions)} auction(s) saved to {args.output}")
        print("No data was sent to Supabase or published on Marsad Almazadat.")
        for item in auctions:
            print(f"- {item['title']} | {item['auction_url']}")
        return 0
    except requests.RequestException as exc:
        print(f"Could not read source website: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
