"""Print the cleaned text of one document, or only the lines that contain given words.

Usage: python3 scripts/show_doc.py DOC_ID [word ...]
"""

import json
import sys
from pathlib import Path

DOCUMENTS = Path(__file__).resolve().parents[1] / "data" / "processed" / "documents.jsonl"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python3 scripts/show_doc.py DOC_ID [word ...]")
        return 1
    doc_id, words = sys.argv[1], [word.lower() for word in sys.argv[2:]]
    with DOCUMENTS.open(encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)
            if record["id"] != doc_id:
                continue
            print(f"{doc_id} | {record['title']} | updated {record.get('last_updated_date')}")
            for page in record["pages"]:
                for number, text in enumerate(page["text"].splitlines(), start=1):
                    if not words or any(word in text.lower() for word in words):
                        print(f"{number:4}: {text}")
            return 0
    print("no such document")
    return 1


if __name__ == "__main__":
    sys.exit(main())
