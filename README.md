# Meridian AI — PE Deal Intelligence Platform

## What It Does
90-second CIM/10-K to IC memo pipeline. Upload a document, get: extracted financials with confidence scores, investment committee memo, risk analysis, deal scoring, fund matching, and Excel/Word export.

## Architecture
- **app.py** — Streamlit UI (pipeline dashboard, 6 analysis tabs, portfolio view, comparison view)
- **core/pipeline.py** — Orchestration, parallel memo+risks+comps generation
- **core/extractor.py** — Document parsing + LLM extraction with context windowing
- **prompts/extraction.py** — Extraction prompt (v1) with analyst reasoning principles + memo generation prompt
- **parsers/pdf_parser.py** — PDF/DOCX/HTM parser using PyMuPDF
- **scoring/deal_scorer.py** — 5-dimension scoring (Market, Financial Quality, Growth, Management, Risk)
- **scoring/fund_matcher.py** — PE fund matching with sector penalty scoring
- **output/excel_export.py** — Excel export with financials, risk register, comp set, fund matches

## Key Design Decisions
- **v1 extraction + programmatic citations** (not v2 single-call) — better quality
- **Analyst reasoning principles** in extraction prompt: derivation, normalization, completeness, inference, confidence scoring, schema additions
- **Canonical memo format** enforced via prompt (title/date/prepared_by/sections array)
- **Critic validation** for derived fields (math reconciliation within 5%)
- **Aggressive extraction + strict validation** philosophy

## Current Status (March 2026)
### Working Well
- Financial extraction: 90%+ accuracy across CIMs and 10-Ks
- Revenue, EBITDA (stated/derived/normalized), margins, CapEx, FCF, debt, cash
- Revenue segments, revenue history with YoY growth
- IC memo generation with 8 standard sections
- Automated risk flags + sector-specific risk profiles
- Deal scoring with letter grades
- Pipeline dashboard, comparison view, portfolio view
- Excel + Word export
- Currency detection (USD/CAD)
- EBITDA variant recognition (Normalized, Adjusted, Pro Forma)

### Known Issues
- Fund matching returns irrelevant results for non-tech sectors (software PE bias in fund database)
- Revenue segments missed when data is qualitative or in charts (not tables)
- Memo format occasionally deviates from canonical schema despite prompt enforcement
- Comp set requires API integration (PitchBook/Capital IQ) for financial multiples
- Scoring weights may need per-sector tuning

### Tested Documents
| Document | Type | Industry | Revenue | Result |
|---|---|---|---|---|
| Instructure 10-K | SEC Filing | EdTech/SaaS | $258M | Full extraction ✅ |
| ACEP CIM | Sell-side CIM | Gaming | $430M | Full extraction ✅ |
| Acme Surfing CIM | Broker CIM | Consumer/Retail | $30M | Partial (6-page sample) ✅ |
| PTL Group CIM | Receivership CIM | Industrial | C$15M | Forecast-only handled ✅ |
| SolarWinds 10-K | SEC Filing | Enterprise SW | $938M | Full extraction ✅ |
| Cvent 10-K | SEC Filing | Event Tech | $188M | Full extraction ✅ |

## Setup
```bash
cd meridian-ai
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GOOGLE_API_KEY=your_gemini_key
streamlit run app.py
```

## Environment Variables
- `GOOGLE_API_KEY` — Gemini API key (required for extraction + memo generation)
- `ANTHROPIC_API_KEY` — Optional, for future Claude integration

## For Contributing Agents
Priority areas for improvement:
1. **Fund matcher** — scoring/fund_matcher.py — needs real PE fund database with sector coverage
2. **Extraction prompt** — prompts/extraction.py — handles most formats but edge cases remain
3. **Scoring engine** — scoring/deal_scorer.py — weights need sector-specific tuning
4. **Comp set** — needs API integration for peer financial multiples
5. **UI polish** — app.py — Streamlit limitations; consider migration to Next.js for production
