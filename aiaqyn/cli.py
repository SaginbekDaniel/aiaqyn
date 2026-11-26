import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from . import __version__
from .document import read_document
from .pipeline import Pipeline
from .provider import Provider
from .report import write_reports
from .schema import Audit, Formalizations, Inventory, Review


class FixtureProvider:
    """Explicit deterministic test double. Never described as a real model run."""

    def __init__(self, path, sha256):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if fixture["document_sha256"] != sha256:
            raise ValueError("Fixture is bound to a different document")
        self.fixture = fixture
        self.calls = 0

    def generate(self, prompt, schema):
        keys = {Inventory: "inventory", Audit: "audit", Review: "review", Formalizations: "formalizations"}
        return schema.model_validate(self.fixture[keys[schema]])


def version():
    try:
        root = Path(__file__).resolve().parent.parent
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=root, stderr=subprocess.DEVNULL, text=True
        ).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
        return f"{__version__}+{sha}" + (".dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return __version__ + "+unversioned"


def main():
    load_dotenv(Path.cwd() / ".env")
    parser = argparse.ArgumentParser(description="AI AQYN — проверяемое ревью требований")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, help="Output .md; also writes .json and .html")
    parser.add_argument(
        "--provider", choices=["gemini", "ollama"], default=os.getenv("AQYN_PROVIDER", "gemini")
    )
    parser.add_argument("--model", default=os.getenv("AQYN_MODEL", ""))
    parser.add_argument(
        "--fixture", type=Path, help="TEST ONLY: explicit recorded fixture, not LLM execution"
    )
    args = parser.parse_args()
    try:
        if args.output.suffix.lower() != ".md":
            raise ValueError("Output path must end in .md")
        targets = [args.output.with_suffix(s).resolve() for s in [".md", ".json", ".html"]]
        if args.input.resolve() in targets or (args.fixture and args.fixture.resolve() in targets):
            raise ValueError("Output would overwrite input")
        doc = read_document(args.input)
        provider = (
            FixtureProvider(args.fixture, doc.sha256) if args.fixture else Provider(args.provider, args.model)
        )
        data = Pipeline(provider, lambda msg: print(msg, file=sys.stderr)).run(doc)
        data["metadata"] = {
            "document": doc.name,
            "sha256": doc.sha256,
            "date": datetime.now(ZoneInfo("Asia/Almaty")).isoformat(),
            "version": version(),
            "provider": "fixture" if args.fixture else args.provider,
            "model": "TEST FIXTURE — NO LLM" if args.fixture else args.model,
            "mode": "ДЕМОНСТРАЦИЯ / НЕ ДЛЯ СДАЧИ" if args.fixture else "ЖИВОЙ ПРОГОН LLM",
            "calls": provider.calls,
            "pipeline_sha256": hashlib.sha256(
                Path(__file__).with_name("pipeline.py").read_bytes()
            ).hexdigest(),
        }
        data["source"] = {"lines": doc.lines, "pages": doc.pages}
        write_reports(args.output, data)
        print(
            f"Reports: {args.output}, {args.output.with_suffix('.json')}, {args.output.with_suffix('.html')}"
        )
    except (ValueError, OSError) as exc:
        print(f"Analysis stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
