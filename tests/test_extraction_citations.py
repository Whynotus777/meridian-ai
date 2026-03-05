import json
from types import SimpleNamespace

import fitz

from core.extractor import CIMExtractor
from parsers.pdf_parser import PDFParser, ExtractedTable


class FakeLLMClient:
    def __init__(self, response_obj):
        self._response_text = json.dumps(response_obj)
        self.last_system = ""
        self.last_user = ""

    def complete(self, system: str, user: str, max_tokens: int = 4096, temperature: float = 0.0) -> str:
        self.last_system = system
        self.last_user = user
        return self._response_text


def _make_sample_pdf(path):
    doc = fitz.open()
    page = doc.new_page()
    text = (
        "Financial Highlights\n"
        "LTM Revenue: $120 million\n"
        "LTM EBITDA: $30 million\n"
        "Adjusted EBITDA: $34 million\n"
        "Gross Margin: 62%\n"
        "EBITDA Margin: 25%\n"
        "Top customer concentration: 18%\n"
        "Annual CapEx: $6 million\n"
    )
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def _citation(page: int, section: str, snippet: str):
    return {"page": page, "section": section, "snippet": snippet}


def _is_citation_obj(value):
    return (
        isinstance(value, dict)
        and isinstance(value.get("page"), int)
        and isinstance(value.get("section"), str)
        and isinstance(value.get("snippet"), str)
        and bool(value.get("snippet").strip())
    )


def test_with_citations_includes_additive_citation_fields(tmp_path):
    pdf_path = tmp_path / "sample_10k_like.pdf"
    _make_sample_pdf(str(pdf_path))

    parser = PDFParser(max_pages=5, extract_tables=False)
    parsed = parser.parse(str(pdf_path))

    parsed.tables.append(
        ExtractedTable(
            page_number=1,
            headers=["Metric", "LTM"],
            rows=[
                ["Revenue", "$120 million"],
                ["EBITDA", "$30 million"],
                ["Adjusted EBITDA", "$34 million"],
                ["CapEx", "$6 million"],
            ],
            context="Financial Highlights",
        )
    )

    fake_response = {
        "schema_version": "v2",
        "financials": {
            "revenue": {
                "ltm": 120000000,
                "cagr_3yr": 0.12,
                "ltm_citation": _citation(1, "Financial Highlights", "LTM Revenue: $120 million"),
                "cagr_3yr_citation": _citation(1, "Financial Highlights", "Revenue growth over prior periods is 12%"),
            },
            "ebitda": {
                "ltm": 30000000,
                "margin_ltm": 0.25,
                "adjusted_ebitda_ltm": 34000000,
                "ltm_citation": _citation(1, "Financial Highlights", "LTM EBITDA: $30 million"),
                "margin_ltm_citation": _citation(1, "Financial Highlights", "EBITDA Margin: 25%"),
                "adjusted_ebitda_ltm_citation": _citation(1, "Financial Highlights", "Adjusted EBITDA: $34 million"),
            },
            "gross_margin": 0.62,
            "gross_margin_citation": _citation(1, "Financial Highlights", "Gross Margin: 62%"),
            "capex": 6000000,
            "capex_citation": _citation(1, "Financial Highlights", "Annual CapEx: $6 million"),
        },
        "customers": {
            "top_customer_concentration": 0.18,
            "top_customer_concentration_citation": _citation(
                1, "Financial Highlights", "Top customer concentration: 18%"
            ),
        },
    }

    extractor = CIMExtractor.__new__(CIMExtractor)
    extractor.config = SimpleNamespace(max_tokens=4096, temperature=0.0)
    extractor.client = FakeLLMClient(fake_response)
    from prompts.extraction import PromptRegistry

    extractor.prompt_registry = PromptRegistry()

    result = extractor.extract(parsed, with_citations=True)

    assert "Table page: 1" in extractor.client.last_user
    assert "Table section heading: Financial Highlights" in extractor.client.last_user
    assert "ltm_citation" in extractor.client.last_user

    citations_to_check = [
        result["financials"]["revenue"].get("ltm_citation"),
        result["financials"]["ebitda"].get("ltm_citation"),
        result["financials"]["ebitda"].get("adjusted_ebitda_ltm_citation"),
        result["financials"]["revenue"].get("cagr_3yr_citation"),
        result["financials"].get("gross_margin_citation"),
        result["financials"]["ebitda"].get("margin_ltm_citation"),
        result["customers"].get("top_customer_concentration_citation"),
        result["financials"].get("capex_citation"),
    ]
    valid_count = sum(_is_citation_obj(c) for c in citations_to_check)
    assert valid_count >= 5
