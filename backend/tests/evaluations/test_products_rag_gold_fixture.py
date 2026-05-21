import json
from pathlib import Path

from app.services.kb_parsers.csv import parse_csv_segments

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
GOLD_FIXTURE = BACKEND_ROOT / "tests" / "evaluations" / "fixtures" / "products_rag_gold.json"
PRODUCTS_CSV = PROJECT_ROOT / "test-data" / "products.csv"
ALLOWED_RELEVANCE_TYPES = {
    "same_active_ingredient",
    "same_brand_family",
    "same_product_category",
}


def test_products_rag_gold_fixture_references_existing_products() -> None:
    available_names = _available_product_names()
    entries = json.loads(GOLD_FIXTURE.read_text(encoding="utf-8"))

    assert entries
    for entry in entries:
        assert entry["query"].strip()
        assert entry["relevance_type"] in ALLOWED_RELEVANCE_TYPES
        assert entry["expected_name"] in available_names
        assert entry["expected_name"] in entry["relevant_names"]
        assert set(entry["relevant_names"]) <= available_names


def _available_product_names() -> set[str]:
    segments = parse_csv_segments(PRODUCTS_CSV.read_bytes(), title="products.csv")
    return {_name_from_chunk(segment.content) for segment in segments}


def _name_from_chunk(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("name: "):
            return line.removeprefix("name: ")
    return ""
