import json
from pathlib import Path

import pytest

from aiaqyn.cli import FixtureProvider
from aiaqyn.document import read_document
from aiaqyn.pipeline import Pipeline
from aiaqyn.report import summarize, write_reports
from aiaqyn.schema import Evidence, WitnessModel
from aiaqyn.solver import solve_witness

ROOT = Path(__file__).resolve().parent.parent


def fixture():
    return json.loads((ROOT / "examples/mini.fixture.json").read_text())


def model():
    return WitnessModel.model_validate(fixture()["formalizations"]["models"][0])


def test_witness_and_counterfactual_repair():
    m = model()
    result = solve_witness(m)
    assert result["status"] == "divergence"
    assert result["inputs"]["price"] >= 10000
    assert result["left_output"] == 0 and result["right_output"] == 1000
    m.right.output.offset = 0
    assert solve_witness(m)["status"] == "no_divergence"


def test_unreachable_guard_is_not_evidence():
    m = model()
    m.variables[0].maximum = 9999
    assert solve_witness(m)["status"] == "unreachable"


def test_unknown_variable_rejected():
    m = model()
    m.left.output.variable = "invented"
    with pytest.raises(ValueError, match="Unknown variable"):
        solve_witness(m)


def test_citation_grounding():
    doc = read_document(ROOT / "examples/mini.md")
    doc.verify(Evidence(line_start=2, line_end=2, quote="доставка стоит 0 тенге"))
    with pytest.raises(ValueError):
        doc.verify(Evidence(line_start=3, line_end=3, quote="доставка стоит 0 тенге"))
    with pytest.raises(ValueError):
        doc.verify(Evidence(line_start=2, line_end=999, quote="доставка"))


def test_fixture_cannot_be_applied_to_another_document():
    with pytest.raises(ValueError, match="different document"):
        FixtureProvider(ROOT / "examples/mini.fixture.json", "wrong")


def test_end_to_end_and_html_injection(tmp_path):
    doc = read_document(ROOT / "examples/mini.md")
    provider = FixtureProvider(ROOT / "examples/mini.fixture.json", doc.sha256)
    data = Pipeline(provider, lambda _: None).run(doc)
    assert summarize(data)["supported"] == 1
    data["metadata"] = dict(
        document="mini",
        date="test",
        model="fixture",
        version="test",
        mode="TEST",
        provider="fixture",
        sha256=doc.sha256,
        calls=0,
    )
    data["source"] = dict(lines=["</script><script>alert(1)</script>"], pages=[None])
    write_reports(tmp_path / "report.md", data)
    content = (tmp_path / "report.html").read_text()
    assert "</script><script>alert(1)</script>" not in content
    assert "\\u003c/script" in content
    assert (tmp_path / "report.json").exists()


def test_missing_assessment_stops_pipeline():
    doc = read_document(ROOT / "examples/mini.md")
    provider = FixtureProvider(ROOT / "examples/mini.fixture.json", doc.sha256)
    provider.fixture["audit"]["assessments"].pop()
    with pytest.raises(ValueError, match="assessment"):
        Pipeline(provider, lambda _: None).run(doc)


def test_reviewer_must_cover_findings():
    doc = read_document(ROOT / "examples/mini.md")
    provider = FixtureProvider(ROOT / "examples/mini.fixture.json", doc.sha256)
    provider.fixture["review"]["decisions"] = []
    with pytest.raises(ValueError, match="Reviewer"):
        Pipeline(provider, lambda _: None).run(doc)


def test_blank_pdf_fails_explicitly(tmp_path):
    from pypdf import PdfWriter

    p = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(p)
    with pytest.raises(ValueError, match="OCR"):
        read_document(p)


def test_duplicate_model_is_rejected():
    doc = read_document(ROOT / "examples/mini.md")
    provider = FixtureProvider(ROOT / "examples/mini.fixture.json", doc.sha256)
    provider.fixture["formalizations"]["models"] *= 2
    with pytest.raises(ValueError, match="Duplicate witness"):
        Pipeline(provider, lambda _: None).run(doc)
