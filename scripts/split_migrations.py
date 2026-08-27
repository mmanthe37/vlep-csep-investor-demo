"""
Split Combined epipheno schema sql.sql into 9 migration files.

Reads the combined SQL file and writes individual SQL files under migrations/up/.
"""

import re
from pathlib import Path

# Paths
COMBINED_SQL_PATH = Path("/Users/michaelmanthejr/Library/Mobile Documents/com~apple~CloudDocs/ReOrganization Master mar 26/Epilepsy Phenotype Project/Finalized Epilepsy Project Files/EpiPheno VLEP web platform/Combined epipheno schema sql.sql")
MIGRATIONS_DIR = Path("/Users/michaelmanthejr/Library/Mobile Documents/com~apple~CloudDocs/ReOrganization Master mar 26/Epilepsy Phenotype Project/Finalized Epilepsy Project Files/vlep_pipeline/migrations/up")

def main():
    if not COMBINED_SQL_PATH.exists():
        print(f"Error: Combined SQL file not found at {COMBINED_SQL_PATH}")
        return

    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

    with open(COMBINED_SQL_PATH, encoding="utf-8") as f:
        content = f.read()

    # Split by '-- FILE: ' comments
    files = re.split(r"^-- FILE:\s+", content, flags=re.MULTILINE)

    for file_chunk in files:
        if not file_chunk.strip():
            continue

        # Extract filename and content
        lines = file_chunk.split("\n", 1)
        filename = lines[0].strip()
        file_content = lines[1] if len(lines) > 1 else ""

        if not filename.endswith(".sql"):
            print(f"Skipping block with invalid filename: {filename}")
            continue

        dest_path = MIGRATIONS_DIR / filename
        with open(dest_path, "w", encoding="utf-8") as out:
            out.write(file_content)

        print(f"Wrote: {dest_path}")

if __name__ == "__main__":
    main()
