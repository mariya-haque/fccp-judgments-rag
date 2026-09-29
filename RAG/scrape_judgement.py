import os
import json
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.fccp.gov.pk/judgments"
NUM_PAGES = 5                  
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "pdfs")
METADATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "judgments_metadata.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    # Pehle base page hit karo taake koi session/CSRF cookie set ho jaye
    session.get(BASE_URL, timeout=20)
    return session


def scrape_page(session: requests.Session, page_num: int):
    url = BASE_URL if page_num == 1 else f"{BASE_URL}?page={page_num}"
    resp = session.get(url, timeout=20, headers={"Referer": BASE_URL})
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        print(f"[warn] page {page_num}: koi table nahi mila")
        return []

    rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
    results = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 4:
            continue

        title = cols[0].get_text(strip=True)
        judge = cols[1].get_text(strip=True)
        date = cols[2].get_text(strip=True)
        link_tag = cols[3].find("a")
        download_url = link_tag.get("href") if link_tag else None

        if not title or not download_url:
            continue

        if download_url.startswith("/"):
            download_url = "https://www.fccp.gov.pk" + download_url

        results.append({
            "title": title,
            "judge": judge,
            "date": date,
            "download_url": download_url,
        })
    return results


def sanitize_filename(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in " ._-" else "_" for c in name)
    return keep.strip()[:150] or "judgment"


def download_pdf(item: dict, session: requests.Session):
    filename = sanitize_filename(f"{item['title']}_{item['date']}") + ".pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(filepath):
        print(f"[skip] already downloaded: {filename}")
        item["pdf_path"] = filepath
        return

    try:
        resp = session.get(
            item["download_url"], timeout=30,
            headers={"Referer": BASE_URL}
        )
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and not resp.content.startswith(b"%PDF"):
            print(f"[warn] shayad PDF nahi hai: {item['title']} (Content-Type: {content_type})")
            item["pdf_path"] = None
            return

        with open(filepath, "wb") as f:
            f.write(resp.content)
        item["pdf_path"] = filepath
        print(f"[ok] downloaded: {filename}")

    except requests.exceptions.RequestException as e:
        print(f"[error] failed to download {item['title']}: {e}")
        item["pdf_path"] = None


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session = get_session()

    all_items = []
    for page in range(1, NUM_PAGES + 1):
        print(f"\n--- Scraping page {page} ---")
        items = scrape_page(session, page)
        print(f"Found {len(items)} judgments on page {page} (raw rows before dedup)")
        all_items.extend(items)
        time.sleep(1)  

    seen = set()
    deduped = []
    for item in all_items:
        key = item["download_url"]
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    if len(deduped) != len(all_items):
        print(f"\n[dedup] {len(all_items) - len(deduped)} duplicate rows removed "
              f"({len(all_items)} -> {len(deduped)})")
    all_items = deduped

    print(f"\nTotal unique judgments found: {len(all_items)}")
    print("Downloading PDFs...")
    for item in all_items:
        download_pdf(item, session)

    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    downloaded = sum(1 for i in all_items if i.get("pdf_path"))
    print(f"\nDone. {downloaded}/{len(all_items)} PDFs downloaded successfully.")
    print(f"Metadata saved to {METADATA_FILE}")
    print(f"PDFs saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()