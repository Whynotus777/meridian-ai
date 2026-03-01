"""Natural language Q&A engine over CIM documents.

Allows analysts to ask questions like:
- "What is the customer retention rate?"
- "How does margin compare year over year?"
- "What are the key growth drivers?"
"""

import json
from typing import Dict, Any, Optional

from config.settings import ModelConfig
from core.llm_client import LLMClient, strip_fences
from parsers.pdf_parser import ParsedDocument
from prompts.extraction import SYSTEM_PROMPT, QA_PROMPT


class QAEngine:
    """Q&A interface over CIM documents."""

    def __init__(self, config: Optional[ModelConfig] = None):
        self.config = config or ModelConfig()
        self.client = LLMClient(self.config)

    def ask(
        self,
        question: str,
        document: ParsedDocument,
        extracted_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Ask a question about the CIM.

        Args:
            question: Natural language question.
            document: The parsed CIM document.
            extracted_data: Optional pre-extracted structured data.

        Returns:
            Answer string.
        """
        # Build context
        doc_text = document.raw_text[:60000]  # Cap for token budget
        extracted_str = ""
        if extracted_data:
            extracted_str = json.dumps(extracted_data, indent=2, default=str)[:20000]

        prompt = QA_PROMPT.format(
            document_text=doc_text,
            extracted_data=extracted_str or "Not available",
            question=question,
        )

        return strip_fences(self.client.complete(
            system=SYSTEM_PROMPT,
            user=prompt,
            max_tokens=1000,
            temperature=0.0,
        ))

    def batch_ask(
        self,
        questions: list[str],
        document: ParsedDocument,
        extracted_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Ask multiple questions, return dict of question → answer."""
        return {q: self.ask(q, document, extracted_data) for q in questions}
