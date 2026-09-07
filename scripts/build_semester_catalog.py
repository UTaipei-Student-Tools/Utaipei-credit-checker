"""Build a read-only, allowlisted display catalog from the supplied crawler export."""
import hashlib
import json
import sys
from pathlib import Path


def build(source, output):
    source = Path(source)
    raw = (source / "courses_listed.json").read_bytes()
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    queries = {q["id"]: q["department_name"] for q in manifest["queries"]}
    fields = ("class_name", "course_code", "course_name_zh", "credits", "required_elective",
              "teaching_raw", "mixed_classes", "remarks", "campus")
    courses = []
    for row in json.loads(raw):
        if row["status"] != "listed":
            continue
        item = {key: row.get(key, "") for key in fields}
        item["departments"] = sorted({queries[q] for q in row["source_queries"] if q in queries})
        courses.append(item)
    payload = {"query": manifest["query"], "captured_at": manifest["started_at"],
               "source_sha256": hashlib.sha256(raw).hexdigest(), "courses": courses}
    Path(output).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {len(courses)} display rows; no login data or executable actions.")


if __name__ == "__main__":
    build(*sys.argv[1:])
