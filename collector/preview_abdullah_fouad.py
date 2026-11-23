#!/usr/bin/env python3
"""Preview-only collector for Abdullah Fouad Auctions. No database writes."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from urllib.parse import urlparse, urljoin, unquote, parse_qs

import requests
from bs4 import BeautifulSoup

LIST_URL = "https://abdullafouadauction.com/%D8%A7%D9%84%D9%85%D8%B2%D8%A7%D8%AF%D8%A7%D8%AA/"
ALLOWED_HOSTS = {"abdullafouadauction.com", "www.abdullafouadauction.com"}
SOURCE_NAME = "عبدالله فؤاد للمزادات"
HEADERS = {
    "User-Agent": "MarsadAlmazadatPreviewBot/0.3 (preview-only; respectful crawling)",
    "Accept-Language": "ar,en;q=0.8",
}
MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4,
    "مايو": 5, "يونيو": 6, "يوليو": 7, "أغسطس": 8, "اغسطس": 8,
    "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" \t\r\n:：")


def canonical(url: str) -> str:
    p = urlparse(url)
    return p._replace(fragment="").geturl()


def get_soup(session: requests.Session, url: str) -> BeautifulSoup:
    response = session.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return BeautifulSoup(response.text, "html.parser")


def is_allowed(url: str) -> bool:
    return urlparse(url).netloc.lower() in ALLOWED_HOSTS


def is_listing_page(url: str) -> bool:
    p = urlparse(url)
    return is_allowed(url) and unquote(p.path).rstrip("/") == "/المزادات"


def discover_listing_pages(soup: BeautifulSoup, current_url: str) -> list[str]:
    pages = []
    for a in soup.select("a[href]"):
        candidate = canonical(urljoin(current_url, a.get("href", "").strip()))
        if is_listing_page(candidate) and "pg" in parse_qs(urlparse(candidate).query):
            pages.append(candidate)
    return list(dict.fromkeys(pages))


def collect_detail_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    found = []
    selectors = "h1 a[href], h2 a[href], h3 a[href], h4 a[href]"
    for a in soup.select(selectors):
        href = canonical(urljoin(base_url, a.get("href", "").strip()))
        if is_allowed(href) and not is_listing_page(href) and urlparse(href).path.strip("/"):
            found.append(href)
    if not found:
        for a in soup.select("a[href]"):
            href = canonical(urljoin(base_url, a.get("href", "").strip()))
            label = clean(a.get_text(" ", strip=True))
            if (is_allowed(href) and not is_listing_page(href)
                    and urlparse(href).path.strip("/") and len(label) >= 12
                    and not any(x in label for x in ("واتساب", "تسجيل", "الرئيسية", "اتصل"))):
                found.append(href)
    return list(dict.fromkeys(found))


def crawl_listing_pages(session: requests.Session, max_pages: int, delay: float):
    queue = [LIST_URL]
    visited, auction_links, errors = [], [], []
    seen = set()
    while queue and len(visited) < max_pages:
        page_url = queue.pop(0)
        if page_url in visited:
            continue
        try:
            soup = get_soup(session, page_url)
            visited.append(page_url)
            for link in collect_detail_links(soup, page_url):
                if link not in seen:
                    seen.add(link)
                    auction_links.append(link)
            for nxt in discover_listing_pages(soup, page_url):
                if nxt not in visited and nxt not in queue:
                    queue.append(nxt)
        except requests.RequestException as exc:
            errors.append({"stage": "listing", "url": page_url, "error": str(exc)})
        if queue:
            time.sleep(max(0.5, delay))
    return visited, auction_links, errors


def normalize_digits(text: str) -> str:
    return text.translate(ARABIC_DIGITS)


def parse_date_candidates(text: str) -> list[str]:
    """Return ISO dates explicitly found; never treat publication/inspection dates as auction dates."""
    t = normalize_digits(text)
    found = []
    # e.g. 22 إلى 26 نوفمبر 2026 / 1 نوفمبر 2026
    for m in re.finditer(r"(?<!\d)(\d{1,2})(?:\s*(?:إلى|الى|[-–])\s*(\d{1,2}))?\s+(" +
                         "|".join(MONTHS) + r")\s*(\d{4})", t):
        d1 = int(m.group(1))
        d2 = int(m.group(2)) if m.group(2) else d1
        month = MONTHS[m.group(3)]
        year = int(m.group(4))
        for day in (d1, d2):
            try:
                iso = date(year, month, day).isoformat()
                if iso not in found:
                    found.append(iso)
            except ValueError:
                pass
    return found


def labelled_value(text: str, labels: list[str], stop_labels: list[str]) -> str:
    # Label/value pairs are flattened by BeautifulSoup; stop at the next known label.
    label_pattern = "|".join(re.escape(x) for x in labels)
    stop_pattern = "|".join(re.escape(x) for x in stop_labels)
    m = re.search(r"(?:^|\s)(?:" + label_pattern + r")\s*[:：]?\s*(.{2,220}?)(?=\s+(?:" +
                  stop_pattern + r")\s*[:：]?|$)", text)
    return clean(m.group(1)) if m else ""


def status_from_text(text: str, end_date: str | None) -> str:
    head = text[:500]
    if "انتهى هذا المزاد" in text or re.search(r"\bمنتهي\b", head):
        return "ended"
    if "مباشر الآن" in head or "القائمة الآن" in head:
        return "active"
    if "قادم" in head or "القادمة" in head:
        return "upcoming"
    if end_date:
        try:
            end = date.fromisoformat(end_date)
            today = datetime.now(timezone.utc).date()
            if end < today:
                return "ended"
            return "active" if end == today else "upcoming"
        except ValueError:
            pass
    return "needs_review"


def extract_auction(session: requests.Session, url: str) -> dict:
    soup = get_soup(session, url)
    h1 = soup.find("h1")
    page_heading = clean(h1.get_text(" ", strip=True) if h1 else "")
    if not page_heading:
        meta = soup.find("meta", property="og:title")
        page_heading = clean(meta.get("content", "") if meta else "")

    text = clean(soup.get_text(" ", strip=True))
    description_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = clean(description_tag.get("content", "") if description_tag else "")

    # Source pages often use the asset owner as H1. Keep it separate from the generated descriptive title.
    owner = ""
    owner_match = re.search(r"(?:لـ\s*/?|لبيع الفائض عن الحاجة لـ\s*/?)\s*(.{5,120}?)(?:[.،,؛]|$)", text)
    if owner_match:
        owner = clean(owner_match.group(1))
    if not owner and page_heading and any(x in page_heading for x in ("شركة", "مؤسسة", "الهيئة", "المؤسسة")):
        owner = page_heading

    auction_type = ""
    type_match = re.search(r"نوع المزاد\s*[:：]?\s*(مزاد علني|ظرف مغلق|منافسة بيع بالظرف المختوم)", text)
    if type_match:
        auction_type = clean(type_match.group(1))

    inspection = labelled_value(text, ["المعاينة", "تاريخ المعاينة", "أيام المعاينة"],
                                ["أوقات المعاينة", "آخر موعد للمظاريف", "الموقع", "نوع المزاد", "تاريخ النشر", "أيام المزاد"])
    deadline = labelled_value(text, ["آخر موعد للمظاريف", "آخر موعد للتقديم", "موعد تقديم العروض"],
                              ["الموقع", "نوع المزاد", "تاريخ النشر", "نص الإعلان", "أوقات المعاينة"])
    auction_period = labelled_value(text, ["أيام المزاد", "تاريخ المزاد"],
                                    ["الموقع", "نوع المزاد", "تاريخ النشر", "نص الإعلان", "المعاينة", "أوقات المعاينة"])
    location = labelled_value(text, ["الموقع", "موقع المزاد", "موقع المعاينة"],
                              ["نوع المزاد", "أيام المزاد", "تاريخ المزاد", "المعاينة", "أوقات المعاينة", "نص الإعلان"])
    if not location:
        # Try the ad body only, bounded by the next known field.
        location = labelled_value(text, ["📍موقع المزاد", "📍موقع المعاينة"],
                                  ["المعروض للبيع", "المعاينة", "أوقات المعاينة", "الدفع", "لمزيد من المعلومات"])

    end_candidates = parse_date_candidates(deadline) or parse_date_candidates(auction_period)
    start_candidates = parse_date_candidates(auction_period)
    deadline_date = end_candidates[-1] if end_candidates else ""
    auction_start = start_candidates[0] if start_candidates else ""
    auction_end = start_candidates[-1] if start_candidates else deadline_date
    status = status_from_text(text, deadline_date or auction_end or None)

    # Build a useful title from the sale method and asset summary; don't publish the owner's name as the auction title.
    asset_summary = meta_description
    if not asset_summary:
        asset_summary = labelled_value(text, ["المعروض للبيع", "المعروض للبيع :"],
                                       ["الدفع", "لمزيد من المعلومات", "كيف تشارك"])
    title_parts = [auction_type or "مزاد", asset_summary[:110] if asset_summary else ""]
    title = " – ".join(x for x in title_parts if x)
    if not asset_summary and page_heading and page_heading != owner:
        title = page_heading
    if not title:
        title = page_heading

    review_reasons = []
    if not title or title == owner:
        review_reasons.append("auction_title_unclear")
    if not location:
        review_reasons.append("location_missing")
    if not (deadline_date or auction_end):
        review_reasons.append("auction_deadline_or_end_date_missing")
    if not auction_type:
        review_reasons.append("auction_type_missing")
    if status == "needs_review":
        review_reasons.append("status_unclear")

    return {
        "source_name": SOURCE_NAME,
        "title": title,
        "page_heading": page_heading,
        "asset_owner": owner,
        "auction_type": auction_type,
        "auction_url": url,
        "source_url": LIST_URL,
        "description": asset_summary or meta_description,
        "location": location,
        "inspection_period": inspection,
        "auction_period": auction_period,
        "submission_deadline": deadline,
        "published_date": labelled_value(text, ["تاريخ النشر"], ["تفاصيل المزاد", "نوع المزاد", "المعاينة"]),
        "auction_start_date": auction_start or None,
        "auction_end_date": auction_end or None,
        "submission_deadline_date": deadline_date or None,
        "status": status,
        "review_required": bool(review_reasons),
        "review_reasons": review_reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview public Abdullah Fouad auctions; no database writes.")
    parser.add_argument("--output", default="abdullah_fouad_preview.json")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--max-pages", type=int, default=30)
    args = parser.parse_args()

    session = requests.Session()
    listing_pages, links, errors = crawl_listing_pages(session, max(1, args.max_pages), args.delay)
    auctions, detail_errors = [], []
    for i, link in enumerate(links):
        if i:
            time.sleep(max(0.5, args.delay))
        try:
            auctions.append(extract_auction(session, link))
        except requests.RequestException as exc:
            detail_errors.append({"stage": "detail", "url": link, "error": str(exc)})

    counts = {k: sum(1 for a in auctions if a["status"] == k)
              for k in ("upcoming", "active", "ended", "needs_review")}
    result = {
        "collector": "abdullah_fouad_preview",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "preview_only",
        "database_write": False,
        "listing_pages_visited": listing_pages,
        "listing_page_count": len(listing_pages),
        "unique_detail_links_found": len(links),
        "details_extracted": len(auctions),
        "detail_error_count": len(detail_errors),
        "listing_error_count": len(errors),
        "status_counts": counts,
        "errors": errors + detail_errors,
        "items_found": len(auctions),
        "auctions": auctions,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: result[k] for k in (
        "listing_page_count", "unique_detail_links_found", "details_extracted",
        "detail_error_count", "listing_error_count", "status_counts", "database_write"
    )}, ensure_ascii=False))
    print(f"Preview saved to {args.output}; no Supabase connection or publishing.")
    return 0 if listing_pages and links else 2


if __name__ == "__main__":
    raise SystemExit(main())
