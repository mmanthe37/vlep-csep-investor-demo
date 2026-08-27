import json
import os
import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.openapi.utils import get_openapi
from vlep.api.main import app

def generate_openapi():
    """Extract OpenAPI spec from FastAPI app and save it."""
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )

    # Ensure docs directory exists
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)

    openapi_path = docs_dir / "openapi.json"
    with open(openapi_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)

    print(f"OpenAPI specification saved to {openapi_path}")

    # Also create a simple index.html for Swagger UI
    index_path = docs_dir / "index.html"
    index_html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>VLEP Pipeline API</title>
  <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
  <style>
    html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
    *, *:before, *:after { box-sizing: inherit; }
    body { margin: 0; background: #fafafa; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
  <script>
    window.onload = function() {
      window.ui = SwaggerUIBundle({
        url: "./openapi.json",
        dom_id: '#swagger-ui',
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ],
        layout: "StandaloneLayout"
      });
    };
  </script>
</body>
</html>
"""
    with open(index_path, "w") as f:
        f.write(index_html)
    print(f"Swagger UI index saved to {index_path}")


if __name__ == "__main__":
    generate_openapi()
