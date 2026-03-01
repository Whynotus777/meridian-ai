#!/usr/bin/env python3
"""Meridian AI — CLI entry point.

Usage:
    python main.py analyze path/to/cim.pdf [--profile balanced|conservative|growth] [--output ./out.json]
    python main.py qa path/to/cim.pdf "What is the EBITDA margin?"
    python main.py parse path/to/cim.pdf  (just parse and show structure, no LLM)
    python main.py batch ./cims_dir/ [--profile balanced] [--output ./batch_output/]
    python main.py compare path/to/cim.pdf --va v1 --vb v2  (compare prompt versions)
"""

import sys
import os
import json
import argparse
import glob

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import PipelineConfig, ModelConfig
from core.pipeline import MeridianPipeline


def cmd_analyze(args):
    """Run full analysis pipeline."""
    config = PipelineConfig(verbose=True)
    pipeline = MeridianPipeline(config)

    print(f"\n{'='*60}")
    print(f"  MERIDIAN AI — CIM Analysis Pipeline")
    print(f"{'='*60}")
    print(f"  File: {args.file}")
    print(f"  Profile: {args.profile}")
    print(f"{'='*60}\n")

    result = pipeline.analyze(args.file, scoring_profile=args.profile)

    # Print summary
    co = result.extracted_data.get("company_overview", {})
    print(f"\n{'='*60}")
    print(f"  ANALYSIS COMPLETE: {co.get('company_name', 'Unknown')}")
    print(f"{'='*60}")
    print(f"  Industry: {co.get('industry', 'N/A')} / {co.get('sub_industry', 'N/A')}")

    fin = result.extracted_data.get("financials", {})
    print(f"  Revenue (LTM): {fin.get('revenue', {}).get('ltm', 'N/A')}")
    print(f"  EBITDA (LTM): {fin.get('ebitda', {}).get('ltm', 'N/A')}")

    if result.deal_score:
        ds = result.deal_score
        print(f"\n  Deal Score: {ds.total_score:.0%} (Grade: {ds.grade})")
        print(f"  Recommendation: {ds.recommendation}")
        for dim in ds.dimensions:
            bar = "█" * int(dim.score * 20) + "░" * (20 - int(dim.score * 20))
            print(f"    {dim.dimension:25s} {bar} {dim.score:.0%}")

    if result.risks:
        critical = [r for r in result.risks if r.severity == "Critical"]
        high = [r for r in result.risks if r.severity == "High"]
        if critical:
            print(f"\n  CRITICAL RISKS:")
            for r in critical:
                print(f"    • {r.title}: {r.description}")
        if high:
            print(f"\n  HIGH RISKS:")
            for r in high[:3]:
                print(f"    • {r.title}: {r.description}")

    if result.comps:
        print(f"\n  TOP COMPARABLES:")
        for c in result.comps[:5]:
            mult = ""
            if c.ev_ebitda:
                mult = f" ({c.ev_ebitda:.1f}x EV/EBITDA)"
            print(f"    • {c.name}{mult} — {c.rationale[:80]}")

    # Fund matching
    try:
        from scoring.fund_matcher import MatchingEngine
        engine = MatchingEngine()
        matches = engine.match(result.extracted_data, top_n=3)
        print(f"\n  TOP PE FUND MATCHES:")
        for i, m in enumerate(matches, 1):
            print(f"    #{i} {m.fund.name} — {m.total_score:.0%} match")
            if m.reasons:
                print(f"       {m.reasons[0]}")
    except Exception:
        pass

    # Export JSON
    output_path = (
        args.output
        or f"./output/{co.get('company_name', 'analysis').replace(' ', '_').lower()}_analysis.json"
    )
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    pipeline.export(result, output_path)
    print(f"\n  Full analysis exported to: {output_path}")

    # Save memo as markdown
    if result.memo:
        memo_path = output_path.replace(".json", "_memo.md")
        with open(memo_path, "w") as f:
            f.write(result.memo)
        print(f"  Investment memo saved to: {memo_path}")

    # Export Excel
    try:
        from output.excel_export import export_excel
        xlsx_path = output_path.replace(".json", ".xlsx")
        export_excel(result, xlsx_path)
        print(f"  Excel workbook saved to: {xlsx_path}")
    except Exception as e:
        print(f"  (Excel export skipped: {e})")

    # Export Word memo
    try:
        from output.memo_formatter import export_memo_docx
        docx_path = output_path.replace(".json", "_memo.docx")
        export_memo_docx(result.memo, result.extracted_data, result.risks, result.comps, docx_path)
        print(f"  Word memo saved to: {docx_path}")
    except Exception as e:
        print(f"  (Word export skipped: {e})")

    print(f"\n  Total time: {result.timing.get('total', 0):.1f}s")
    print(f"{'='*60}\n")


def cmd_qa(args):
    """Ask a question about a CIM."""
    config = PipelineConfig(verbose=False)
    pipeline = MeridianPipeline(config)

    print(f"\nQuestion: {args.question}")
    print(f"Document: {args.file}\n")

    answer = pipeline.ask(args.question, args.file)
    print(f"Answer:\n{answer}\n")


def cmd_parse(args):
    """Parse a document and show structure (no LLM calls)."""
    from parsers.pdf_parser import PDFParser
    from parsers.docx_parser import DOCXParser

    ext = os.path.splitext(args.file)[1].lower()
    if ext == ".pdf":
        parser = PDFParser()
    elif ext in (".docx", ".doc"):
        parser = DOCXParser()
    else:
        print(f"Unsupported: {ext}")
        return

    doc = parser.parse(args.file)
    print(f"\nDocument: {doc.filename}")
    print(f"   Pages: {doc.total_pages}")
    print(f"   Text length: {len(doc.raw_text):,} chars")
    print(f"   Tables found: {len(doc.tables)}")
    print(f"   Financial tables: {len(doc.get_financial_tables())}")

    if doc.tables:
        print(f"\n   Sample tables:")
        for t in doc.tables[:3]:
            print(f"   Page {t.page_number}: {t.headers[:4]} ({len(t.rows)} rows)")

    print(f"\n   First 500 chars:")
    print(f"   {doc.raw_text[:500]}")


def cmd_batch(args):
    """Batch-analyze all CIMs in a directory and produce a comparison Excel."""
    import time

    # Discover CIM files
    patterns = ["*.pdf", "*.docx", "*.doc"]
    cim_files = []
    for pat in patterns:
        cim_files.extend(glob.glob(os.path.join(args.directory, pat)))
    cim_files = sorted(set(cim_files))

    if not cim_files:
        print(f"No CIM files (PDF/DOCX) found in: {args.directory}")
        return

    print(f"\n{'='*60}")
    print(f"  MERIDIAN AI — Batch Analysis")
    print(f"{'='*60}")
    print(f"  Directory: {args.directory}")
    print(f"  Found {len(cim_files)} CIM file(s)")
    print(f"  Profile: {args.profile}")
    print(f"{'='*60}\n")

    config = PipelineConfig(verbose=False)  # Suppress per-file logs
    pipeline = MeridianPipeline(config)

    output_dir = args.output or os.path.join(args.directory, "meridian_batch_output")
    os.makedirs(output_dir, exist_ok=True)

    results_with_files = []  # List of (filename, AnalysisResult)
    errors = []

    for i, cim_file in enumerate(cim_files, 1):
        basename = os.path.basename(cim_file)
        print(f"[{i}/{len(cim_files)}] Analyzing: {basename}")
        t0 = time.time()
        try:
            result = pipeline.analyze(cim_file, scoring_profile=args.profile)
            elapsed = time.time() - t0

            # Save individual JSON
            stem = os.path.splitext(basename)[0]
            json_path = os.path.join(output_dir, f"{stem}_analysis.json")
            pipeline.export(result, json_path)

            # Save individual Excel
            try:
                from output.excel_export import export_excel
                xlsx_path = os.path.join(output_dir, f"{stem}.xlsx")
                export_excel(result, xlsx_path)
            except Exception:
                pass

            co = result.extracted_data.get("company_overview", {})
            ds = result.deal_score
            print(
                f"  Done in {elapsed:.1f}s — "
                f"{co.get('company_name','?')} | "
                f"Score: {ds.total_score:.0%} ({ds.grade}) | "
                f"{ds.recommendation}"
            )
            results_with_files.append((cim_file, result))

        except Exception as exc:
            print(f"  ERROR: {exc}")
            errors.append((cim_file, str(exc)))

    print(f"\n{'='*60}")
    print(f"  Batch complete: {len(results_with_files)} succeeded, {len(errors)} failed")

    # Build comparison Excel
    if results_with_files:
        try:
            from output.excel_export import export_batch_comparison
            comparison_path = os.path.join(output_dir, "batch_comparison.xlsx")
            export_batch_comparison(results_with_files, comparison_path)
            print(f"  Comparison Excel saved to: {comparison_path}")
        except Exception as e:
            print(f"  (Batch comparison Excel failed: {e})")

    if errors:
        print(f"\n  Failed files:")
        for f, err in errors:
            print(f"    • {os.path.basename(f)}: {err}")

    # Summary table to stdout
    print(f"\n  {'Company':<30} {'Score':>8} {'Grade':>6} {'Recommendation'}")
    print(f"  {'-'*80}")
    for _, result in results_with_files:
        co = result.extracted_data.get("company_overview", {})
        ds = result.deal_score
        name  = co.get("company_name", "Unknown")[:28]
        score = f"{ds.total_score:.0%}" if ds else "N/A"
        grade = ds.grade if ds else "N/A"
        rec   = (ds.recommendation or "")[:40] if ds else "N/A"
        print(f"  {name:<30} {score:>8} {grade:>6}  {rec}")

    print(f"\n  Output directory: {output_dir}")
    print(f"{'='*60}\n")


def cmd_compare(args):
    """Compare extraction accuracy between two prompt versions."""
    from config.settings import ModelConfig
    from prompts.extraction import compare_extractions, PromptRegistry

    print(f"\n{'='*60}")
    print(f"  MERIDIAN AI — Prompt Version Comparison")
    print(f"{'='*60}")
    print(f"  File:      {args.file}")
    print(f"  Version A: {args.va}")
    print(f"  Version B: {args.vb}")
    print(f"{'='*60}\n")

    # Validate versions
    registry = PromptRegistry()
    for v in (args.va, args.vb):
        try:
            pv = registry.get(v)
            print(f"  {v}: {pv.description}")
        except KeyError as e:
            print(f"  ERROR: {e}")
            return

    print(f"\n  Available versions: {', '.join(registry.list_versions())}\n")

    # Parse document
    from parsers.pdf_parser import PDFParser
    from parsers.docx_parser import DOCXParser

    ext = os.path.splitext(args.file)[1].lower()
    if ext == ".pdf":
        parser = PDFParser()
    elif ext in (".docx", ".doc"):
        parser = DOCXParser()
    else:
        print(f"Unsupported file type: {ext}")
        return

    doc = parser.parse(args.file)
    print(f"  Parsed: {doc.total_pages} pages, {len(doc.raw_text):,} chars")
    print(f"\n  Running extractions (this takes 30-60s)...\n")

    model_cfg = ModelConfig()
    from core.llm_client import LLMClient
    client = LLMClient(model_cfg)

    diff = compare_extractions(
        document_text=doc.raw_text,
        version_a=args.va,
        version_b=args.vb,
        client=client,
        model=model_cfg.model,
    )

    # Print summary
    print(diff["summary"])
    print(f"  Field differences ({diff['field_diff']['different_count']}):")
    for item in diff["field_diff"]["differences"][:20]:
        a_flag = "✓" if item["a_provided"] else "✗"
        b_flag = "✓" if item["b_provided"] else "✗"
        print(f"    {item['field']}")
        print(f"      {args.va} [{a_flag}]: {str(item['value_a'])[:60]}")
        print(f"      {args.vb} [{b_flag}]: {str(item['value_b'])[:60]}")

    # Save full diff
    output_path = args.output or f"./output/version_comparison_{args.va}_vs_{args.vb}.json"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        import dataclasses

        def _default(obj):
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
            return str(obj)

        json.dump(diff, f, indent=2, default=_default)
    print(f"\n  Full comparison saved to: {output_path}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Meridian AI — PE Deal Intelligence Engine"
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    # analyze
    p_analyze = sub.add_parser("analyze", help="Full CIM analysis")
    p_analyze.add_argument("file", help="Path to CIM (PDF or DOCX)")
    p_analyze.add_argument(
        "--profile",
        default="balanced",
        choices=["balanced", "conservative", "growth"],
        help="Scoring weight profile",
    )
    p_analyze.add_argument("--output", help="Output JSON path")

    # qa
    p_qa = sub.add_parser("qa", help="Ask questions about a CIM")
    p_qa.add_argument("file", help="Path to CIM")
    p_qa.add_argument("question", help="Your question")

    # parse
    p_parse = sub.add_parser("parse", help="Parse document only (no LLM)")
    p_parse.add_argument("file", help="Path to document")

    # batch
    p_batch = sub.add_parser("batch", help="Batch-analyze a directory of CIMs")
    p_batch.add_argument("directory", help="Directory containing PDF/DOCX CIM files")
    p_batch.add_argument(
        "--profile",
        default="balanced",
        choices=["balanced", "conservative", "growth"],
        help="Scoring weight profile (applied to all files)",
    )
    p_batch.add_argument("--output", help="Output directory (default: <directory>/meridian_batch_output/)")

    # compare
    p_compare = sub.add_parser("compare", help="Compare two prompt versions on a CIM")
    p_compare.add_argument("file", help="Path to CIM (PDF or DOCX)")
    p_compare.add_argument("--va", default="v1", help="First prompt version (default: v1)")
    p_compare.add_argument("--vb", default="v2", help="Second prompt version (default: v2)")
    p_compare.add_argument("--output", help="Output JSON path for full diff")

    args = parser.parse_args()

    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "qa":
        cmd_qa(args)
    elif args.command == "parse":
        cmd_parse(args)
    elif args.command == "batch":
        cmd_batch(args)
    elif args.command == "compare":
        cmd_compare(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
