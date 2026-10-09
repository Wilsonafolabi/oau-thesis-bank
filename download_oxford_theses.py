
import argparse
import csv
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://ora.ox.ac.uk"
OAI = f"{BASE}/oai2"
OUT = Path("oxford_theses")
PDF_DIR = OUT / "pdfs"
CSV_FILE = OUT / "theses.csv"

# Conservative delays. Follow any stricter limits supplied by ORA.
OAI_DELAY = 1.5
PAGE_DELAY = 3.0
MAX_PDF_MB = 300

NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "OxfordThesisResearchDownloader/1.0 "
        "(academic research; contact ORA before bulk downloading)"
    )
})


def request(url, params=None, stream=False):
    """Make a polite request; stop rather than bypass access restrictions."""
    response = session.get(
        url, params=params, timeout=(15, 90),
        stream=stream, allow_redirects=True
    )

    if response.status_code in (401, 403, 429):
        response.close()
        raise RuntimeError(
            f"Access restricted or rate limited: HTTP "
            f"{response.status_code}. Stopping."
        )

    if response.status_code >= 500:
        response.close()
        raise RuntimeError(
            f"ORA server error: HTTP {response.status_code}. Stopping."
        )

    response.raise_for_status()
    return response


def find_thesis_set():
    """Discover the official thesis set rather than guessing its identifier."""
    response = request(OAI, {"verb": "ListSets"})
    root = ET.fromstring(response.content)

    for item in root.findall(".//oai:set", NS):
        name = item.findtext("oai:setName", default="", namespaces=NS)
        spec = item.findtext("oai:setSpec", default="", namespaces=NS)

        if "thesis" in (name + " " + spec).lower():
            print(f"Using thesis set: {spec} ({name})")
            return spec

    raise RuntimeError(
        "No thesis set found in OAI-PMH ListSets. "
        "Check ORA's current API documentation."
    )


def iter_thesis_records(set_spec):
    """Harvest public metadata via OAI-PMH, including pagination."""
    params = {
        "verb": "ListRecords",
        "metadataPrefix": "oai_dc",
        "set": set_spec,
    }

    while True:
        time.sleep(OAI_DELAY)
        response = request(OAI, params)
        root = ET.fromstring(response.content)

        error = root.find("oai:error", NS)
        if error is not None:
            raise RuntimeError(
                f"OAI-PMH error: {error.attrib.get('code')} "
                f"{error.text or ''}"
            )

        for record in root.findall(".//oai:record", NS):
            header = record.find("oai:header", NS)
            if header is None or header.attrib.get("status") == "deleted":
                continue

            identifier = header.findtext(
                "oai:identifier", default="", namespaces=NS
            )
            metadata = record.find("oai:metadata", NS)

            if not identifier or metadata is None:
                continue

            dc = metadata.find("dc:dc", NS)
            if dc is None:
                dc = next(iter(metadata), None)
            if dc is None:
                continue

            titles = [
                x.text.strip() for x in dc.findall("dc:title", NS)
                if x.text and x.text.strip()
            ]
            creators = [
                x.text.strip() for x in dc.findall("dc:creator", NS)
                if x.text and x.text.strip()
            ]
            dates = [
                x.text.strip() for x in dc.findall("dc:date", NS)
                if x.text and x.text.strip()
            ]
            subjects = [
                x.text.strip() for x in dc.findall("dc:subject", NS)
                if x.text and x.text.strip()
            ]
            descriptions = [
                x.text.strip() for x in dc.findall("dc:description", NS)
                if x.text and x.text.strip()
            ]
            identifiers = [
                x.text.strip() for x in dc.findall("dc:identifier", NS)
                if x.text and x.text.strip()
            ]

            # Prefer a public ORA record URL, not an arbitrary external URL.
            record_url = next(
                (
                    x for x in identifiers
                    if urlparse(x).hostname == "ora.ox.ac.uk"
                    and "/objects/" in urlparse(x).path
                ),
                ""
            )

            if not record_url:
                # OAI identifiers can often be mapped to an ORA UUID.
                match = re.search(
                    r"uuid:([0-9a-fA-F-]{36})", identifier
                )
                if match:
                    record_url = (
                        f"{BASE}/objects/uuid%3A{match.group(1)}"
                    )

            yield {
                "oai_id": identifier,
                "title": titles[0] if titles else "",
                "author": "; ".join(creators),
                "date": "; ".join(dates),
                "subjects": "; ".join(subjects),
                "abstract": " ".join(descriptions),
                "record_url": record_url,
                "identifiers": "; ".join(identifiers),
            }

        token = root.findtext(
            ".//oai:resumptionToken", default="", namespaces=NS
        )

        if not token.strip():
            break

        # OAI-PMH requires the token to be sent by itself.
        params = {"verb": "ListRecords", "resumptionToken": token.strip()}


def find_public_pdf_links(record_url, page_html):
    """Identify likely public PDF links on a record page."""
    soup = BeautifulSoup(page_html, "html.parser")
    candidates = []

    for a in soup.find_all("a", href=True):
        href = urljoin(record_url, a["href"])
        text = a.get_text(" ", strip=True).lower()
        path = urlparse(href).path.lower()

        if urlparse(href).scheme != "https":
            continue

        # Do not follow links to unrelated websites.
        if urlparse(href).hostname != "ora.ox.ac.uk":
            continue

        looks_like_pdf = (
            path.endswith(".pdf")
            or ".pdf?" in href.lower()
            or "download" in text
            or "full text" in text
            or "pdf" == text.strip()
        )

        if looks_like_pdf and href not in candidates:
            candidates.append(href)

    return candidates


def safe_filename(title, identifier):
    slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title or "thesis")
    slug = re.sub(r"\s+", " ", slug).strip(" ._")
    slug = slug[:100] or "thesis"
    digest = hashlib.sha256(identifier.encode()).hexdigest()[:12]
    return f"{slug}_{digest}.pdf"


def download_pdf(url, destination):
    """Save only responses whose content actually looks like a PDF."""
    temp = destination.with_suffix(".part")
    total = 0

    try:
        with request(url, stream=True) as response:
            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if "text/html" in content_type:
                return False, "HTML response, not a PDF"

            with temp.open("wb") as f:
                first_chunk = True

                for chunk in response.iter_content(1024 * 128):
                    if not chunk:
                        continue

                    if first_chunk:
                        first_chunk = False
                        if not chunk.startswith(b"%PDF-"):
                            return False, "Response is not a PDF"

                    total += len(chunk)

                    if total > MAX_PDF_MB * 1024 * 1024:
                        return False, "PDF exceeds configured size limit"

                    f.write(chunk)

        if total == 0:
            return False, "Empty file"

        temp.replace(destination)
        return True, "Downloaded"

    finally:
        if temp.exists():
            temp.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=10000)
    parser.add_argument(
        "--metadata-only", action="store_true",
        help="Harvest metadata without visiting record pages or downloading PDFs"
    )
    parser.add_argument(
        "--i-have-ora-approval", action="store_true",
        help="Confirm that ORA has authorised the planned bulk retrieval"
    )
    args = parser.parse_args()

    if args.target < 1:
        raise SystemExit("--target must be positive")

    if not args.metadata_only and not args.i_have_ora_approval:
        raise SystemExit(
            "For bulk PDF retrieval, contact ORA first. After approval, "
            "rerun with --i-have-ora-approval. "
            "Use --metadata-only to harvest metadata without PDF downloads."
        )

    OUT.mkdir(exist_ok=True)
    PDF_DIR.mkdir(exist_ok=True)

    fields = [
        "oai_id", "title", "author", "date", "subjects", "abstract",
        "record_url", "identifiers", "pdf_url", "status", "local_path"
    ]

    # Resume from the existing index.
    rows = {}
    if CSV_FILE.exists():
        with CSV_FILE.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                rows[row.get("oai_id", "")] = row

    downloaded = sum(
        1 for r in rows.values()
        if r.get("status") == "downloaded"
        and r.get("local_path")
        and Path(r["local_path"]).is_file()
    )

    print(f"Existing valid PDFs: {downloaded}/{args.target}")
    set_spec = find_thesis_set()

    def save_index():
        with CSV_FILE.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows.values())

    seen = set(rows)
    scanned = 0

    try:
        for record in iter_thesis_records(set_spec):
            oid = record["oai_id"]
            if oid in seen:
                continue
            seen.add(oid)
            scanned += 1

            row = {field: "" for field in fields}
            row.update(record)
            row["status"] = "metadata_only" if args.metadata_only else "pending"
            rows[oid] = row

            if args.metadata_only:
                if scanned % 100 == 0:
                    save_index()
                    print(f"Metadata records processed: {scanned}")
                continue

            if downloaded >= args.target:
                break

            if not record["record_url"]:
                row["status"] = "no_public_record_url"
                continue

            time.sleep(PAGE_DELAY)
            page = request(record["record_url"])
            links = find_public_pdf_links(record["record_url"], page.text)

            if not links:
                row["status"] = "no_obvious_public_pdf_link"
                continue

            saved = False
            last_reason = ""

            for link in links:
                # Resume if this record's PDF already exists.
                destination = PDF_DIR / safe_filename(
                    record["title"], oid
                )

                if destination.exists() and destination.stat().st_size > 0:
                    row["pdf_url"] = link
                    row["local_path"] = str(destination)
                    row["status"] = "downloaded"
                    saved = True
                    break

                try:
                    ok, reason = download_pdf(link, destination)
                    if ok:
                        row["pdf_url"] = link
                        row["local_path"] = str(destination)
                        row["status"] = "downloaded"
                        downloaded += 1
                        saved = True
                        print(f"[{downloaded}/{args.target}] {record['title']}")
                        break
                    last_reason = reason

                except requests.RequestException as exc:
                    last_reason = str(exc)
                    break

            if not saved:
                row["status"] = "skipped: " + (last_reason or "PDF unavailable")

            # Checkpoint regularly so a stopped run can be resumed.
            if scanned % 10 == 0 or downloaded >= args.target:
                save_index()
                print(
                    f"Scanned: {scanned} | PDFs: {downloaded}/{args.target}"
                )

        save_index()

    except KeyboardInterrupt:
        print("\nStopped by user; saving progress.")
        save_index()

    except Exception:
        save_index()
        raise

    print("\nFinished.")
    print(f"Valid PDFs: {downloaded}")
    print(f"Index: {CSV_FILE.resolve()}")
    print(f"PDF folder: {PDF_DIR.resolve()}")


if __name__ == "__main__":
    main()