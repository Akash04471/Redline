import io
import re
import pdfplumber
import docx
from pydantic import BaseModel

class ClauseCandidate(BaseModel):
    clause_index: int
    raw_text: str
    clause_category: str

def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extracts text from PDF or DOCX file bytes."""
    if filename.lower().endswith('.pdf'):
        text = ""
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    elif filename.lower().endswith('.docx'):
        doc = docx.Document(io.BytesIO(file_bytes))
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    else:
        raise ValueError(f"Unsupported file format: {filename}")

def _guess_category(text: str) -> str:
    """Simple keyword heuristic to guess the clause category."""
    text_lower = text.lower()
    if "indemnif" in text_lower or "hold harmless" in text_lower:
        return "Indemnification"
    if "liabilit" in text_lower or "damages" in text_lower:
        return "Limitation of Liability"
    if "terminat" in text_lower:
        return "Termination"
    if "intellectual property" in text_lower or "copyright" in text_lower or "patent" in text_lower:
        return "Intellectual Property"
    if "data processing" in text_lower or "privacy" in text_lower or "gdpr" in text_lower or "ccpa" in text_lower or "personal data" in text_lower:
        return "Data Processing"
    if "confidential" in text_lower or "non-disclosure" in text_lower:
        return "Confidentiality"
    return "General"

def split_into_clauses(full_text: str) -> list[ClauseCandidate]:
    """
    Heuristic splitter using numbered-heading patterns and paragraph breaks as fallback.
    Logs warnings for extremely short or long fragments.
    """
    # Normalize newlines
    full_text = full_text.replace('\r\n', '\n')
    
    # Regex for numbered headings or sections at the start of a line
    # Matches: "1. ", "1.1. ", "Section 3:", "ARTICLE IV", etc.
    header_pattern = re.compile(r'^(?:\d+\.(?:\d+\.)*\s+|Section\s+\d+:?\s*|ARTICLE\s+[IVXLCDM]+:?\s*)', re.MULTILINE | re.IGNORECASE)
    
    # Find all header matches to split the text
    matches = list(header_pattern.finditer(full_text))
    
    raw_blocks = []
    if not matches:
        # Fallback: split by paragraph breaks if no headers found
        raw_blocks = [b.strip() for b in re.split(r'\n\s*\n', full_text) if b.strip()]
    else:
        # Split by headers
        last_idx = 0
        for i, match in enumerate(matches):
            if i == 0:
                # Add text before the first header if any
                pre_text = full_text[0:match.start()].strip()
                if pre_text:
                    raw_blocks.append(pre_text)
            else:
                block = full_text[last_idx:match.start()].strip()
                if block:
                    raw_blocks.append(block)
            last_idx = match.start()
            
        # Add the last block
        last_block = full_text[last_idx:].strip()
        if last_block:
            raw_blocks.append(last_block)

    # Secondary fallback: if any raw_block is extremely long, split it by paragraph breaks
    refined_blocks = []
    for block in raw_blocks:
        if len(block.split()) > 500:
            sub_blocks = [b.strip() for b in re.split(r'\n\s*\n', block) if b.strip()]
            refined_blocks.extend(sub_blocks)
        else:
            refined_blocks.append(block)

    candidates = []
    idx = 1
    for block in refined_blocks:
        if not block:
            continue
            
        word_count = len(block.split())
        
        # Filter extremely short fragments (likely titles, headers, or OCR garbage)
        if word_count < 15:
            print(f"Warning: Clause {idx} too short ({word_count} words), skipping: {block[:30]}...")
            continue
            
        # Log warning for huge chunks but keep them
        if word_count > 500:
            print(f"Warning: Clause {idx} unusually long ({word_count} words). Might contain multiple clauses.")
            
        category = _guess_category(block)
        candidates.append(ClauseCandidate(
            clause_index=idx,
            raw_text=block,
            clause_category=category
        ))
        idx += 1
        
    return candidates
