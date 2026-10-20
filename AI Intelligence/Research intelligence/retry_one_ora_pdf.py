
from pathlib import Path
import requests
from pypdf import PdfReader

BASE = "https://ora.ox.ac.uk"
UUID = "b279b3f0-a041-4c60-bf4d-f48a36a45733"
FILE_ID = "dht24wk23v"

record_url = f"{BASE}/objects/uuid:{UUID}"
file_url = f"{record_url}/files/{FILE_ID}"

output = Path("oxford_theses/pdfs/ora_single_test.pdf")
output.parent.mkdir(parents=True, exist_ok=True)

session = requests.Session()
session.headers.update({
    "User-Agent": "AcademicResearchDownloader/1.0 (single-file retry)",
    "Referer": record_url,
})

try:
    print("Requesting the file again...")
    with session.get(
        file_url,
        timeout=(20, 180),
        allow_redirects=True,
    ) as response:
        print("HTTP:", response.status_code)
        print("Final URL:", response.url)
        print("Content-Type:", response.headers.get("Content-Type"))
        print("Content-Length:", response.headers.get("Content-Length"))
        print("Content-Range:", response.headers.get("Content-Range"))

        response.raise_for_status()

        content = response.content

        if not content.startswith(b"%PDF-"):
            raise ValueError(
                "The server response does not begin with a PDF signature."
            )

        # Save the full response before checking PDF integrity.
        output.write_bytes(content)

    print("Bytes received:", output.stat().st_size)

    reader = PdfReader(str(output), strict=False)
    print("Pages:", len(reader.pages))
    print("Metadata:", reader.metadata)

    if reader.pages:
        print(
            "First-page text:",
            (reader.pages[0].extract_text() or "")[:500]
        )

    print("\nPDF opened successfully.")

except Exception as exc:
    print("\nDownload or validation failed:", repr(exc))
    print("Inspect the HTTP headers above before retrying again.")