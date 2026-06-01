from __future__ import annotations

import typer

app = typer.Typer(help="Ingestion CLI for the veille tech index.")


@app.command()
def news(topics: list[str] = typer.Option(..., "--topic", "-t", help="Topic to query.")) -> None:
    raise NotImplementedError


@app.command()
def scrape(urls: list[str] = typer.Option(..., "--url", "-u", help="URL to scrape.")) -> None:
    raise NotImplementedError


if __name__ == "__main__":
    app()
