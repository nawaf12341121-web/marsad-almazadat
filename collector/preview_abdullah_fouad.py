#!/usr/bin/env python3
"""
Preview-only collector for Abdullah Fouad Auctions.
Crawls all discoverable listing pages and extracts auction detail links.
It NEVER connects to Supabase and NEVER publishes or inserts auctions.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin, unquote, parse_qs

import requests
from bs4 import BeautifulSoup

LIST_URL = "https://abdullafouadauction.com/%D8%A7%D9%84%D9%85%D8%B2%D8%A7%D8%AF%D8%A7%D8%AA/"
ALLOWED_HOST = "abdullafouadauction.com"
SOURCE_NAME = "عبدالله فؤاد للمزادات"
HEADERS = {
    "User-Agent": "MarsadAlmazadatPreviewBot/0.2 (preview-only; respectful crawling)",
    "Accept-Language": "ar,en;q=0.8",
}


def clean(value: str | None) -> str:
    return re.sub(r"\\s+", " ", value or "").strip()


def canonical(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return BeautifulSoup(response.text, "html.parser")


def is_listing_page(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.netloc.lower() == ALLOWED_HOST
        and unquote(parsed.path).rstrip("/") == "/المزادات"
    )


def discover_listing_pages(soup: BeautifulSoup, current_url: str) -> list[str]:
    pages: list[str] = []
    for anchor in soup.select("a[href]"):
        candidate = canonical(urljoin(current_url, anchor.get("href", "").strip()))
        if not is_listing_page(candidate):
            continue
        query = parse_qs(urlparse(candidate).query)
        if "pg" in query:
            pages.append(candidate)
    return pages


def collect_detail_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    # Auction titles are rendered as linked headings in the listing cards.
    candidates = soup.select("h2 a[href], h3 a[href], h4 a[href]")
    for anchor in candidates:
        href = canonical(urljoin(base_url, anchor.get("href", "").strip()))
        parsed = urlparse(href)
        if parsed.netloc.lower() != ALLOWED_HOST or is_listing_page(href):
            continue
        if not parsed.path.strip("/"):
            continue
        if href not in seen:
            seen.add(href)
            found.append(href)

    # Fallback for a source layout change: retain same-domain non-listing links
    # whose visible text looks like a real auction title.
    if not found:
        for anchor in soup.select("a[href]"):
            href = canonical(urljoin(base_url, anchor.get("href", "").strip()))
            parsed = urlparse(href)
            label = clean(anchor.get_text(" ", strip=True))
            if (
                parsed.netloc.lower() == ALLOWED_HOST
                and not is_listing_page(href)
                and parsed.path.strip("/")
                and len(label) >= 8
                and label not in {"الرئيسية", "الخدمات", "من نحن", "اتصل بنا", "كيفية المزايدة"}
            ):
                if href not in seen:
                    seen.add(href)
                    found.append(href)
    return found


def crawl_listing_pages(session: requests.Session, max_pages: int, delay: float) -> tuple[list[str], list[str]]:
    queue = [LIST_URL]
    visited: list[str] = []
    auction_links: list[str] = []
    seen_auctions: set[str] = set()

    while queue and len(visited) < max_pages:
        page_url = queue.pop(0)
        if page_url in visited:
            continue
        soup = get_soup(session, page_url)
        visited.append(page_url)

        for link in collect_detail_links(soup, page_url):
            if link not in seen_auctions:
                seen_auctions.add(link)
                auction_links.append(link)

        for next_page in discover_listing_pages(soup, page_url):
            if next_page not in visited and next_page not in queue:
                queue.append(next_page)

        if queue:
            time.sleep(max(0.5, delay))

    return visited, auction_links


def extract_auction(session: requests.Session, url: str) -> dict:
    soup = get_soup(session, url)
    h1 = soup.find("h1")
    title = clean(h1.get_text(" ", strip=True) if h1 else "")
    if not title:
        meta_title = soup.find("meta", property="og:title")
        title = clean(meta_title.get("content", "") if meta_title else "")

    description_tag = soup.find("meta", attrs={"name": "description"})
    description = clean(description_tag.get("content", "") if description_tag else "")

    text = clean(soup.get_text(" ", strip=True))
    location = ""
    location_match = re.search(r"الموقع\\s*[:：]?\\s*(.{5,180}?)(?:\\s+(?:نوع المزاد|أيام المزاد|نص الإعلان|كيف تشارك))", text)
    if location_match:
        location = clean(location_match.group(1))

    published = ""
    published_match = re.search(r"تاريخ النشر\\s*[:：]?\\s*(.{3,50}?)(?:\\s+(?:تفاصيل المزاد|نوع المزاد))", text)
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
    parser = argparse.ArgumentParser(description="Preview public Abdullah Fouad auctions across listing pages; no database writes.")
    parser.add_argument("--output", default="abdullah_fouad_preview.json", help="JSON output path")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between page requests")
    parser.add_argument("--max-pages", type=int, default=30, help="Safety limit for listing pagination")
    args = parser.parse_args()

    session = requests.Session()
    try:
        listing_pages, links = crawl_listing_pages(session, max(1, args.max_pages), args.delay)
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
            "listing_pages_visited": listing_pages,
            "listing_page_count": len(listing_pages),
            "items_found": len(auctions),
            "auctions": auctions,
        }
        with open(args.output, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)

        print(f"Preview complete: {len(auctions)} auction(s) from {len(listing_pages)} listing page(s) saved to {args.output}")
        print("No data was sent to Supabase or published on Marsad Almazadat.")
        for item in auctions:
            print(f"- {item['title']} | {item['auction_url']}")
        return 0
    except requests.RequestException as exc:
        print(f"Could not read source website: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
