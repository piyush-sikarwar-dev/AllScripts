"""Patient details on the Overview, in the header (photo) and in the PDF: insurance (EMR + PM),
race / ethnicity / marital status, emergency contacts and proxy, guarantor, care team, consents."""

import io

import pytest
from pypdf import PdfReader

from app.crosswalk import resolve
from app.services.export import ExportRequest, gather
from app.services.patient_details import patient_details
from tests.conftest import page_csrf
from tests.fakes.data import PATIENTS
from tests.unit.test_export import needs_pdf

HTMX = {"HX-Request": "true"}
WITH = PATIENTS[0]  # index 0: details + photo
NOTHING = PATIENTS[5]  # index 5: nothing beyond the header
NO_PHOTO = PATIENTS[1]


def _key(p) -> str:
    return f"EMR:{p.emr_id}"


def test_overview_shows_all_patient_details(client):
    r = client.get(f"/patients/{_key(WITH)}")
    assert r.status_code == 200
    html = r.text
    for text in ("Insurance", "Example Medicare", "Medicare", "BCBS", f"M{WITH.emr_id}0",
                 "Demographics", "White", "Not Hispanic or Latino", "Married",
                 "Emergency contacts &amp; proxy", "Contact, Sample", "Health-care proxy",
                 "Guarantor", "Self", "Care team", "Doctor, Sample, MD", "Primary care physician",
                 "Referral / consult", "Consents", "HIPAA", "HIE authorization / consent",
                 "expires 01/01/2030"):  # fmt: skip
        assert text in html, text
    assert "Old Sample Insurer" not in html and "Show archived (1)" in html


def test_archived_policies_toggle(client):
    r = client.get(f"/patients/{_key(WITH)}/tab/overview", params={"archived": "1"}, headers=HTMX)
    assert r.status_code == 200 and "Old Sample Insurer" in r.text
    assert "Hide archived (1)" in r.text and "badge--voided" in r.text
    assert r.headers["HX-Push-Url"] == f"/patients/{_key(WITH)}?tab=overview&archived=1"


def test_pm_policies_and_source_badges(client):
    p = next(p for p in PATIENTS[:5] if p.ntier_id is not None)
    r = client.get(f"/patients/{_key(p)}")
    assert "Sample PM Carrier" in r.text and "CERT" in r.text and "Copay $25.00" in r.text
    assert 'badge--pm">PM' in r.text and 'badge--emr">EMR' in r.text


def test_overview_empty_details(client):
    r = client.get(f"/patients/{_key(NOTHING)}")
    empty = ("No insurance policies on file.", "No emergency contacts on file.",
             "No guarantor on file.", "No assigned providers.", "No consents on file.")  # fmt: skip
    for text in empty:
        assert text in r.text, text


def test_header_photo_and_photo_route(client):
    r = client.get(f"/patients/{_key(WITH)}")
    assert f'src="/patients/{_key(WITH)}/photo"' in r.text and "avatar--photo" in r.text
    img = client.get(f"/patients/{_key(WITH)}/photo")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert img.content.startswith(b"\xff\xd8\xff")
    r = client.get(f"/patients/{_key(NO_PHOTO)}")
    assert "avatar--photo" not in r.text
    assert client.get(f"/patients/{_key(NO_PHOTO)}/photo").status_code == 404


@pytest.mark.anyio
async def test_pdf_context_includes_archived_policies():
    ref = await resolve(_key(WITH))
    req = ExportRequest(sections=["demographics"], date_from=None, date_to=None,
                        recipient="Example Law Office", purpose="Legal")  # fmt: skip
    ctx = await gather(ref, req)
    carriers = [p.carrier for p in ctx["details"].insurances]
    assert "Old Sample Insurer" in carriers  # a release includes every policy, marked archived
    assert any(p.archived for p in ctx["details"].insurances)
    details = await patient_details(ref)
    assert "Old Sample Insurer" not in [p.carrier for p in details.insurances]


@needs_pdf
def test_pdf_demographics_section(client):
    data = {"csrf_token": page_csrf(client), "sections": ["demographics"],
            "recipient": "Example Law Office", "purpose": "Legal"}  # fmt: skip
    r = client.post(f"/patients/{_key(WITH)}/export", data=data)
    assert r.status_code == 200, r.text[:300]
    pages = PdfReader(io.BytesIO(r.content)).pages
    text = " ".join(" ".join(p.extract_text().split()) for p in pages)  # table cells wrap
    for heading in ("Insurance", "Emergency contacts", "Guarantor", "Care team", "Consents"):
        assert heading in text, heading
    assert "Old Sample" in text and "(archived)" in text and "Not Hispanic or Latino" in text
