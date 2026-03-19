"""
YOU DO NOT NEED TO RUN THIS SCRIPT UNLESS THE GRAPHQL API HAS CHANGED

Introspect the Reports GraphQL API and update the local schema file.

1. Under the launch menu select "⚠️🐍 Python: Update Schema"
2. Commit the changes to the schema file at `pyreports/graphql/rs-reports.schema.graphql`

"""

from pathlib import Path

import questionary
import requests
from graphql import build_client_schema, get_introspection_query, print_schema

API_URLS = {
    "staging": "https://api.reports.riverscapes.net/staging",
    "production": "https://api.reports.riverscapes.net",
}

SCHEMA_PATH = Path(__file__).parent.parent / "pyreports" / "graphql" / "rs-reports.schema.graphql"


def main():
    stage = questionary.select(
        "Which API stage to introspect?",
        choices=list(API_URLS.keys()),
        default="staging",
    ).ask()
    if not stage:
        return

    url = API_URLS[stage]
    print(f"Introspecting {stage} API at {url} ...")

    response = requests.post(
        url,
        json={"query": get_introspection_query()},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()

    if "errors" in result:
        raise SystemExit(f"Introspection failed: {result['errors']}")

    schema = build_client_schema(result["data"])
    sdl = print_schema(schema)

    SCHEMA_PATH.write_text(sdl + "\n", encoding="utf-8")
    print(f"Schema written to {SCHEMA_PATH}")


if __name__ == "__main__":
    main()
