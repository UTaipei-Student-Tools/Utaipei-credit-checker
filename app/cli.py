from __future__ import annotations

import json
from pathlib import Path

import typer

from app.core.audit import audit_all
from app.models import AuditRequest
from app.parsers.selection import parse_selection_html
from app.parsers.transcript import parse_transcript_pdf
from app.scraper.utaipei import scrape_readonly_sync

app = typer.Typer(help="UTaipei credit audit CLI")


@app.command()
def audit(
    transcript: Path | None = typer.Option(None, help="歷年成績單 PDF"),
    selection_html: Path | None = typer.Option(None, help="選課結果 HTML"),
    earth_bio_domain: str = typer.Option("earth_environment", help="earth_environment or life_science"),
    include_chem_double_major: bool = True,
    include_cs_double_major: bool = True,
    include_cs_minor: bool = False,
):
    courses = []
    if transcript:
        courses.extend(parse_transcript_pdf(transcript))
    if selection_html:
        courses.extend(parse_selection_html(selection_html.read_text(encoding="utf-8")))
    request = AuditRequest(
        earth_bio_domain=earth_bio_domain,
        include_chem_double_major=include_chem_double_major,
        include_cs_double_major=include_cs_double_major,
        include_cs_minor=include_cs_minor,
    )
    typer.echo(json.dumps([result.model_dump() for result in audit_all(courses, request)], ensure_ascii=False, indent=2))


@app.command()
def fetch(
    username: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True),
):
    result = scrape_readonly_sync(username, password)
    typer.echo(json.dumps({
        "transcript_courses": [course.model_dump() for course in result.transcript_courses],
        "selection_courses": [course.model_dump() for course in result.selection_courses],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
