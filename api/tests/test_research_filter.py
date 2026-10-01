from app.services.research import assess_candidate, load_allowlist


def test_pdf_filter_keeps_free_journal_pdfs_and_drops_the_rest():
    allowlist = load_allowlist()
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    assert (
        assess_candidate(
            "https://www.bmj.com/content/open/sleep-restriction.pdf",
            "application/pdf",
            pdf,
            allowlist,
        )
        is None
    )
    assert (
        assess_candidate("https://sci-hub.se/10.1136/bmj.fake", "application/pdf", pdf, allowlist)
        == "blocked_host"
    )
    assert (
        assess_candidate(
            "https://www.bmj.com/content/368/bmj.m104",
            "text/html",
            b"<!doctype html><title>abstract</title>",
            allowlist,
        )
        == "not_a_pdf"
    )
    assert (
        assess_candidate("https://random-blog.example/paper.pdf", "application/pdf", pdf, allowlist)
        == "journal_not_allowed"
    )
