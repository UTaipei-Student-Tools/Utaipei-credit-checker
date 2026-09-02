from __future__ import annotations

import json
from pathlib import Path

import typer

from app.core.audit import audit_all
from app.models import AuditRequest, EarthBioDomain
from app.parsers.selection import parse_selection_html_with_diagnostics
from app.parsers.transcript import parse_transcript_pdf_with_diagnostics
from app.scraper.utaipei import scrape_readonly_sync

app = typer.Typer(help="UTaipei credit audit CLI")


@app.command()
def audit(
    transcript: Path | None = typer.Option(None, help="歷年成績單 PDF"),
    selection_html: Path | None = typer.Option(None, help="選課結果 HTML"),
    admission_year: int = typer.Option(114, help="目前只支援 114"),
    earth_bio_domain: EarthBioDomain = typer.Option(EarthBioDomain.EARTH_ENVIRONMENT),
    include_chem_double_major: bool = False,
    include_cs_double_major: bool = False,
    include_cs_minor: bool = False,
):
    courses = []
    diagnostics = []
    if transcript:
        parsed = parse_transcript_pdf_with_diagnostics(transcript)
        courses.extend(parsed.courses)
        diagnostics.append(parsed.diagnostic)
    if selection_html:
        parsed = parse_selection_html_with_diagnostics(selection_html.read_text(encoding="utf-8"))
        courses.extend(parsed.courses)
        diagnostics.append(parsed.diagnostic)
    if not courses:
        raise typer.BadParameter("沒有可供審核的課程資料。")
    if any(item.quality == "failed" for item in diagnostics):
        raise typer.BadParameter("至少一項輸入解析失敗，已停止審核。")
    request = AuditRequest(
        admission_year=admission_year,
        earth_bio_domain=earth_bio_domain,
        include_chem_double_major=include_chem_double_major,
        include_cs_double_major=include_cs_double_major,
        include_cs_minor=include_cs_minor,
    )
    output = {
        "diagnostics": [item.model_dump(mode="json", exclude={"unparsed_samples"}) for item in diagnostics],
        "results": [result.model_dump(mode="json", exclude={"requirements": {"__all__": {"matched_courses": {"__all__": {"raw"}}}}, "in_progress": {"__all__": {"raw"}}, "needs_review": {"__all__": {"raw"}}, "excluded": {"__all__": {"raw"}}}) for result in audit_all(courses, request)],
    }
    typer.echo(json.dumps(output, ensure_ascii=False, indent=2))


@app.command()
def fetch(
    username: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True),
):
    result = scrape_readonly_sync(username, password)
    typer.echo(
        json.dumps(
            {
                "transcript_courses": [course.model_dump(mode="json", exclude={"raw"}) for course in result.transcript_courses],
                "selection_courses": [course.model_dump(mode="json", exclude={"raw"}) for course in result.selection_courses],
                "diagnostics": [item.model_dump(mode="json", exclude={"unparsed_samples"}) for item in result.diagnostics],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
