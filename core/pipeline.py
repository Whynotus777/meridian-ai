"""Main pipeline orchestrator.

This is the core engine: CIM document → full investment analysis.
Coordinates all modules in sequence.
"""

import os
import json
import time
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass

from config.settings import PipelineConfig, ModelConfig
from config.scoring_weights import ScoringWeights, PROFILES
from parsers.pdf_parser import PDFParser, ParsedDocument
from parsers.docx_parser import DOCXParser
from core.extractor import CIMExtractor
from core.memo_generator import MemoGenerator
from core.risk_analyzer import RiskAnalyzer, RiskFlag
from core.comp_builder import CompBuilder, Comparable
from core.qa_engine import QAEngine
from scoring.deal_scorer import DealScorer, DealScore
from output.json_export import export_full_analysis


@dataclass
class AnalysisResult:
    """Complete analysis output from the pipeline."""
    document: ParsedDocument
    extracted_data: Dict[str, Any]
    memo: str
    risks: List[RiskFlag]
    comps: List[Comparable]
    deal_score: DealScore
    timing: Dict[str, float]


class MeridianPipeline:
    """Main pipeline: CIM → full investment analysis.

    Usage:
        pipeline = MeridianPipeline()
        result = pipeline.analyze("path/to/cim.pdf")
        pipeline.export(result, "output/analysis.json")
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()

        # Initialize components
        self.extractor = CIMExtractor(self.config.model)
        self.memo_gen = MemoGenerator(self.config.model)
        self.risk_analyzer = RiskAnalyzer(self.config.model)
        self.comp_builder = CompBuilder(self.config.model)
        self.qa_engine = QAEngine(self.config.model)
        self.deal_scorer = DealScorer()

    def analyze(
        self,
        filepath: str,
        scoring_profile: str = "balanced",
    ) -> AnalysisResult:
        """Run the full analysis pipeline on a CIM document.

        Args:
            filepath: Path to PDF or DOCX CIM file.
            scoring_profile: "balanced", "conservative", or "growth".

        Returns:
            AnalysisResult with all outputs.
        """
        timing = {}

        # Step 1: Parse document
        self._log("Step 1/6: Parsing document...")
        t0 = time.time()
        document = self._parse_document(filepath)
        timing["parse"] = time.time() - t0
        self._log(
            f"  Parsed {document.total_pages} pages, "
            f"{len(document.tables)} tables, "
            f"{len(document.raw_text):,} chars"
        )

        # Step 2: Extract structured data
        self._log("Step 2/6: Extracting structured data...")
        t0 = time.time()
        extracted_data = self.extractor.extract(document)
        timing["extract"] = time.time() - t0
        company_name = extracted_data.get("company_overview", {}).get(
            "company_name", "Unknown"
        )
        self._log(f"  Extracted profile for: {company_name}")

        # Step 3: Generate memo
        memo = ""
        if self.config.enable_memo_generation:
            self._log("Step 3/6: Generating investment memo...")
            t0 = time.time()
            memo = self.memo_gen.generate(extracted_data)
            timing["memo"] = time.time() - t0
            self._log(f"  Memo: {len(memo):,} chars")

        # Step 4: Risk analysis
        risks = []
        if self.config.enable_risk_analysis:
            self._log("Step 4/6: Analyzing risks...")
            t0 = time.time()
            risks = self.risk_analyzer.analyze(extracted_data)
            timing["risk"] = time.time() - t0
            critical = len([r for r in risks if r.severity == "Critical"])
            high = len([r for r in risks if r.severity == "High"])
            self._log(
                f"  {len(risks)} risks identified "
                f"({critical} critical, {high} high)"
            )

        # Step 5: Comp builder
        comps = []
        if self.config.enable_comp_builder:
            self._log("Step 5/6: Building comparable sets...")
            t0 = time.time()
            comps = self.comp_builder.build(extracted_data)
            timing["comps"] = time.time() - t0
            self._log(f"  {len(comps)} comparables identified")

        # Step 6: Deal scoring
        deal_score = None
        if self.config.enable_deal_scoring:
            self._log("Step 6/6: Scoring deal...")
            t0 = time.time()
            weights = PROFILES.get(scoring_profile)
            self.deal_scorer = DealScorer(weights)
            deal_score = self.deal_scorer.score(extracted_data)
            timing["score"] = time.time() - t0
            self._log(
                f"  Score: {deal_score.total_score:.0%} "
                f"(Grade: {deal_score.grade}) — "
                f"{deal_score.recommendation}"
            )

        total_time = sum(timing.values())
        timing["total"] = total_time
        self._log(f"\nPipeline complete in {total_time:.1f}s")

        return AnalysisResult(
            document=document,
            extracted_data=extracted_data,
            memo=memo,
            risks=risks,
            comps=comps,
            deal_score=deal_score,
            timing=timing,
        )

    def ask(
        self,
        question: str,
        filepath: str,
        extracted_data: Optional[Dict] = None,
    ) -> str:
        """Ask a question about a CIM document.

        Args:
            question: Natural language question.
            filepath: Path to the CIM file.
            extracted_data: Optional pre-extracted data (saves re-extraction).
        """
        document = self._parse_document(filepath)
        return self.qa_engine.ask(question, document, extracted_data)

    def export(self, result: AnalysisResult, output_path: str) -> str:
        """Export analysis results to JSON."""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        return export_full_analysis(
            extracted_data=result.extracted_data,
            memo=result.memo,
            risks=result.risks,
            comps=result.comps,
            deal_score=result.deal_score,
            output_path=output_path,
        )

    def _parse_document(self, filepath: str) -> ParsedDocument:
        """Route to the correct parser based on file extension."""
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".pdf":
            parser = PDFParser(
                max_pages=self.config.parser.max_pages,
                extract_tables=self.config.parser.table_extraction,
            )
        elif ext in (".docx", ".doc"):
            parser = DOCXParser()
        else:
            raise ValueError(f"Unsupported file type: {ext}. Use PDF or DOCX.")
        return parser.parse(filepath)

    def _log(self, msg: str):
        if self.config.verbose:
            print(msg)
