
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

BASE = "https://ora.ox.ac.uk"
OAI = f"{BASE}/oai2"
UUID = "b279b3f0-a041-4c60-bf4d-f48a36a45733"

s = requests.Session()
s.headers["User-Agent"] = (
    "AcademicResearchDiagnostic/1.0 (testing public repository access)"
)

def inspect_response(label, response):
    print(f"\n--- {label} ---")
    print("HTTP:", response.status_code)
    print("Final URL:", response.url)
    print("Content-Type:", response.headers.get("Content-Type", ""))
    return response

# 1. Inspect a single public record page.
try:
    r = s.get(
        f"{BASE}/objects/uuid:{UUID}",
        timeout=30,
        allow_redirects=True,
    )
    inspect_response("RECORD PAGE", r)

    if r.ok and "html" in r.headers.get("Content-Type", "").lower():
        soup = BeautifulSoup(r.text, "html.parser")
        print("Page title:", soup.title.get_text(" ", strip=True) if soup.title else "None")

        print("\nPossible file links:")
        found = 0
        for a in soup.find_all("a", href=True):
            href = a["href"]
            label = a.get_text(" ", strip=True)
            combined = (href + " " + label).lower()

            if any(word in combined for word in (
                "pdf", "download", "file", "bitstream",
                "attachment", "full text", "content"
            )):
                print(label[:100], "=>", href)
                found += 1
                if found >= 30:
                    break

        print("Candidate links shown:", found)

        print("\nFile-related metadata:")
        for tag in soup.find_all("meta"):
            name = (tag.get("name") or tag.get("property") or "").lower()
            content = tag.get("content", "")
            if any(word in name for word in ("file", "pdf", "download")):
                print(name, "=>", content[:300])

except requests.RequestException as e:
    print("\nRecord request failed:", repr(e))

# 2. Inspect the repository's richer metadata format.
try:
    r = s.get(
        OAI,
        params={
            "verb": "GetRecord",
            "metadataPrefix": "uketd_dc",
            "identifier": f"oai:ora.ox.ac.uk:{UUID}",
        },
        timeout=30,
    )
    inspect_response("OAI EXTENDED METADATA", r)

    if r.ok:
        root = ET.fromstring(r.content)
        print("XML root:", root.tag)

        # Print file-related fields without dumping the entire record.
        count = 0
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1].lower()
            value = (elem.text or "").strip()

            if value and any(word in tag for word in (
                "file", "format", "identifier", "access",
                "rights", "location", "url", "type"
            )):
                print(f"{tag}: {value[:400]}")
                count += 1
                if count >= 60:
                    break

        if count == 0:
            print(r.text[:2500])

except (requests.RequestException, ET.ParseError) as e:
    print("\nExtended metadata request failed:", repr(e))

print("\nDiagnostic complete. No PDFs were downloaded.")