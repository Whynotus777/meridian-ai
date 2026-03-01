# Meridian AI — PE Deal Intelligence Engine

> Working name. Replace before shipping.

## What It Does

Upload a CIM (Confidential Information Memorandum) PDF/DOCX → get back:
1. **Structured financial extraction** (revenue, EBITDA, margins, growth, customer concentration)
2. **Auto-generated investment memo** (IC-ready, with thesis, risks, key questions)
3. **Comparable company/transaction sets**
4. **Risk flags** (customer concentration, key-person, regulatory, financial inconsistencies)
5. **Deal score** (configurable weights per firm's criteria)
6. **Natural language Q&A** over the document

## Architecture

```
meridian-ai/
├── config/
│   ├── settings.py          # Global config, API keys, model selection
│   └── scoring_weights.py   # Configurable scoring weights per firm
├── core/
│   ├── __init__.py
│   ├── pipeline.py           # Main orchestrator: CIM → full analysis
│   ├── extractor.py          # LLM-powered structured data extraction
│   ├── memo_generator.py     # Investment memo drafting
│   ├── comp_builder.py       # Comparable company/transaction sets
│   ├── risk_analyzer.py      # Red flag detection
│   └── qa_engine.py          # Natural language Q&A over documents
├── parsers/
│   ├── __init__.py
│   ├── pdf_parser.py         # PDF → structured text + tables
│   ├── docx_parser.py        # DOCX → structured text + tables
│   └── table_extractor.py    # Financial table detection and extraction
├── scoring/
│   ├── __init__.py
│   ├── deal_scorer.py        # Multi-dimensional deal scoring
│   └── fund_matcher.py       # PE fund matching (from your D.E. Shaw work)
├── output/
│   ├── __init__.py
│   ├── excel_export.py       # Export financials to Excel
│   ├── memo_formatter.py     # Format memo as DOCX/PDF
│   └── json_export.py        # Structured JSON output
├── prompts/
│   ├── extraction.py         # Extraction prompt templates
│   ├── memo.py               # Memo generation prompts
│   ├── risk.py               # Risk analysis prompts
│   └── qa.py                 # Q&A prompt templates
├── data/
│   └── pe_fund_universe.json # PE fund database (from your case study)
├── tests/
│   └── test_pipeline.py      # End-to-end tests
├── main.py                   # CLI entry point
├── requirements.txt
└── README.md
```

## Phase Roadmap

- **Phase 1 (MVP)**: CIM analysis, memo gen, comp sets, risk flags, deal scoring
- **Phase 2**: Data room ingestion, contract analysis, diligence accelerator
- **Phase 3**: Portfolio monitoring, LP reporting, value creation tracking
- **Phase 4**: Deal sourcing, sector expansion, CRM integrations

## Quick Start

```bash
export ANTHROPIC_API_KEY="your-key"
python main.py analyze path/to/cim.pdf
python main.py qa path/to/cim.pdf "What is the customer retention rate?"
python main.py score path/to/cim.pdf --weights conservative
```
