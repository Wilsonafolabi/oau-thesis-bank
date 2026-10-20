
from pathlib import Path
import requests

BASE = "https://ora.ox.ac.uk"
RECORD_UUID = "b279b3f0-a041-4c60-bf4d-f48a36a45733"
FILE_ID = "dht24wk23v"

record_url = f"{BASE}/objects/uuid:{RECORD_UUID}"
pdf_url = f"{record_url}/files/{FILE_ID}"

output_dir = Path("oxford_theses") / "pdfs"
output_dir.mkdir(parents=True, exist_ok=True)
output_file = output_dir / "ora_single_test.pdf"

session = requests.Session()
session.headers.update({
    "User-Agent": "AcademicResearchDownloader/1.0 (single-file access test)",
    "Referer": record_url,
})

try:
    print("Testing one publicly linked thesis file...")
    response = session.get(
        pdf_url,
        timeout=60,
        allow_redirects=True,
        stream=True,
    )

    print("HTTP status:", response.status_code)
    print("Final URL:", response.url)
    print("Content-Type:", response.headers.get("Content-Type"))
    print("Content-Length:", response.headers.get("Content-Length", "unknown"))

    response.raise_for_status()

    # Read enough bytes to verify that this really is a PDF.
    first_chunk = next(response.iter_content(chunk_size=8192), b"")

    if not first_chunk.startswith(b"%PDF-"):
        print("\nThis response is not a directly served PDF.")
        print("First bytes:", repr(first_chunk[:300]))
        print("No file was saved.")
    else:
        with output_file.open("wb") as f:
            f.write(first_chunk)
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

        print("\nSUCCESS: A valid PDF header was detected.")
        print("Saved to:", output_file.resolve())
        print("File size:", output_file.stat().st_size, "bytes")

except requests.RequestException as exc:
    print("\nDownload test failed:", repr(exc))

finally:
    response.close() if "response" in locals() else None