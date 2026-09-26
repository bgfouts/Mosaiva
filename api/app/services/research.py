import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import ResearchItem
from app.services.records import load_hypotheses, load_interventions
from app.settings import ALLOWLIST_PATH, PAPERS_DIR, get_settings

BLOCKED_HOST_MARKERS = (
    "sci-hub",
    "scihub",
    "libgen",
    "annas-archive",
    "z-lib",
    "booksc.org",
)

DOMAIN_JOURNALS = {
    "nejm.org": "New England Journal of Medicine",
    "thelancet.com": "The Lancet",
    "jamanetwork.com": "JAMA",
    "bmj.com": "BMJ",
    "nature.com": "Nature",
    "science.org": "Science",
    "ncbi.nlm.nih.gov": "PubMed Central",
    "europepmc.org": "Europe PMC",
    "cochranelibrary.com": "Cochrane Library",
    "cochrane.org": "Cochrane Library",
    "acpjournals.org": "Annals of Internal Medicine",
    "journals.plos.org": "PLOS",
    "biomedcentral.com": "BMC",
}

MAX_PDF_BYTES = 15 * 1024 * 1024
EXCERPT_CHARS = 6000


def load_allowlist() -> dict:
    return json.loads(ALLOWLIST_PATH.read_text())


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def host_is_blocked(url: str) -> bool:
    host = _host(url)
    return any(marker in host for marker in BLOCKED_HOST_MARKERS)


def host_is_allowed(url: str, allowlist: dict | None = None) -> bool:
    host = _host(url)
    domains = (allowlist or load_allowlist()).get("domains", [])
    for domain in domains:
        domain = domain.lower()
        if host == domain or host.endswith("." + domain):
            return True
    return False


def is_pdf_payload(content_type: str, body: bytes) -> bool:
    if body.startswith(b"%PDF"):
        return True
    return "application/pdf" in (content_type or "").lower()


def assess_candidate(url: str, content_type: str, body: bytes, allowlist: dict | None = None) -> str | None:
    """Return a rejection reason, or None when the candidate may be kept."""
    if host_is_blocked(url):
        return "blocked_host"
    if not host_is_allowed(url, allowlist):
        return "journal_not_allowed"
    if not is_pdf_payload(content_type, body):
        return "not_a_pdf"
    return None


def journal_for(url: str, explicit: str = "") -> str:
    if explicit.strip():
        return explicit.strip()
    host = _host(url)
    for domain, name in DOMAIN_JOURNALS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return ""


def extract_pdf_text(path: Path, limit: int = EXCERPT_CHARS) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages[:8]:
        parts.append(page.extract_text() or "")
        if sum(len(part) for part in parts) >= limit:
            break
    return "\n".join(parts).strip()[:limit]


def _download(url: str) -> tuple[str, bytes]:
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": "MosaivaLocal/0.1 (personal research reader)"})
        response.raise_for_status()
        body = response.content[: MAX_PDF_BYTES + 1]
        if len(response.content) > MAX_PDF_BYTES:
            raise ValueError("PDF is larger than 15 MB.")
        return response.headers.get("content-type", ""), body


def _relevance_note(query: str, title: str, journal: str, excerpt: str) -> str:
    settings = get_settings()
    if not settings.openai_api_key or not excerpt:
        return "Saved from a freely available journal PDF. A relevance note needs an OpenAI API key and extractable text."
    from app.services.llm import OpenAIReasoner

    try:
        result = OpenAIReasoner().complete_json(
            "Write a relevance_note of two or three sentences about how the excerpt relates to the patient query. "
            "Use only the excerpt. Do not invent doses, protocols, or citations that are not in the excerpt.",
            {"query": query, "title": title, "journal": journal, "excerpt": excerpt[:4000]},
        )
        note = str(result.get("relevance_note") or "").strip()
        return note or "The model did not return a relevance note."
    except Exception:
        return "The PDF was saved, but the relevance note could not be generated."


def _store_pdf(db: Session, *, title: str, journal: str, year: int | None, url: str, body: bytes, query: str, hypothesis_ids: list[int], intervention_ids: list[int]) -> ResearchItem:
    existing = db.scalar(
        select(ResearchItem)
        .options(selectinload(ResearchItem.hypotheses), selectinload(ResearchItem.interventions))
        .where(ResearchItem.pdf_url == url)
    )
    if existing:
        known_hypotheses = {row.id for row in existing.hypotheses}
        known_interventions = {row.id for row in existing.interventions}
        extra_hypotheses = [row for row in load_hypotheses(db, hypothesis_ids) if row.id not in known_hypotheses]
        extra_interventions = [
            row for row in load_interventions(db, intervention_ids) if row.id not in known_interventions
        ]
        if extra_hypotheses or extra_interventions:
            existing.hypotheses.extend(extra_hypotheses)
            existing.interventions.extend(extra_interventions)
            db.commit()
            db.refresh(existing)
        return existing
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.pdf"
    path = PAPERS_DIR / filename
    path.write_bytes(body)
    excerpt = ""
    try:
        excerpt = extract_pdf_text(path)
    except Exception:
        excerpt = ""
    item = ResearchItem(
        title=title[:500] or journal or "Untitled paper",
        journal=journal[:200],
        year=year,
        pdf_url=url,
        local_path=str(path),
        excerpt=excerpt,
        query=query,
        relevance_note=_relevance_note(query, title, journal, excerpt),
    )
    item.hypotheses = load_hypotheses(db, hypothesis_ids)
    item.interventions = load_interventions(db, intervention_ids)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _resolve_fixture(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    from app.settings import ROOT

    return ROOT / path


def _web_hits(query: str, limit: int) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("The web search library is not installed.") from exc
    try:
        results = DDGS().text(f"{query} open access pdf", max_results=limit)
    except Exception as exc:
        raise RuntimeError(f"Web search failed: {exc}") from exc
    hits = []
    for row in results or []:
        url = row.get("href") or row.get("url") or ""
        if not url:
            continue
        hits.append({"title": row.get("title") or "", "url": url, "journal": "", "year": None})
    return hits


def search_and_store(
    db: Session,
    query: str,
    hypothesis_ids: list[int] | None = None,
    intervention_ids: list[int] | None = None,
    limit: int = 8,
    keep: int = 3,
) -> dict:
    hypothesis_ids = hypothesis_ids or []
    intervention_ids = intervention_ids or []
    load_hypotheses(db, hypothesis_ids)
    load_interventions(db, intervention_ids)
    fixture_path = get_settings().mosaiva_research_fixture.strip()
    if fixture_path:
        payload = json.loads(_resolve_fixture(fixture_path).read_text())
        hits = list(payload.get("hits") or [])
        base = _resolve_fixture(fixture_path).parent
    else:
        hits = _web_hits(query, limit)
        base = None

    kept: list[ResearchItem] = []
    skipped = 0
    allowlist = load_allowlist()
    for hit in hits:
        if len(kept) >= keep:
            break
        url = str(hit.get("url") or "")
        try:
            if base is not None and hit.get("pdf_file"):
                body = (base / str(hit["pdf_file"])).read_bytes()
                content_type = "application/pdf"
            else:
                content_type, body = _download(url)
        except Exception:
            skipped += 1
            continue
        reason = assess_candidate(url, content_type, body, allowlist)
        if reason:
            skipped += 1
            continue
        journal = journal_for(url, str(hit.get("journal") or ""))
        year = hit.get("year")
        item = _store_pdf(
            db,
            title=str(hit.get("title") or journal or "Journal PDF"),
            journal=journal,
            year=int(year) if isinstance(year, int) else None,
            url=url,
            body=body,
            query=query,
            hypothesis_ids=hypothesis_ids,
            intervention_ids=intervention_ids,
        )
        kept.append(item)
    message = ""
    if not kept:
        message = "No freely available PDFs from reputable journals matched."
    return {"items": kept, "considered": len(hits), "kept": len(kept), "skipped": skipped, "message": message}
