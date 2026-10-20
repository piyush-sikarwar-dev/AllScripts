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


def test_pharmacy_fills_view(client):
    r = client.get(f"/patients/{_key(WITH)}", params={"tab": "meds", "filter": "fills"})
    assert r.status_code == 200 and "Pharmacy fills" in r.text
    assert "Surescripts" in r.text and "last checked 05/01/2023" in r.text
    assert "METFORMIN HCL 500 MG TABLET" in r.text and "500 MG 500 MG" not in r.text
    assert "Qty 60 · 30-day supply" in r.text and "SAMPLE PHARMACY #12" in r.text
    assert "DOCTOR, SAMPLE" in r.text and "Showing 6 of 6" in r.text
    assert r.text.index("06/01/2022") < r.text.index("02/01/2022")  # newest fill first
    r = client.get(f"/patients/{_key(WITH)}/tab/meds", params={"filter": "fills"}, headers=HTMX)
    assert r.headers["HX-Push-Url"] == f"/patients/{_key(WITH)}?tab=meds&filter=fills"
    r = client.get(f"/patients/{_key(NOTHING)}", params={"tab": "meds", "filter": "fills"})
    assert "No pharmacy fill history from Surescripts." in r.text


def test_live_pharmacy_fills_merge_repeats(monkeypatch):
    from datetime import date

    from app.repositories import emr, live

    base = {"drug_name": "X 5 MG", "strength": "5 MG", "quantity": 30, "pharmacy": "P",
            "written_date": date(2020, 1, 1), "checked_at": None}  # fmt: skip
    rows = [
        {**base, "fill_id": 1, "last_fill_date": date(2020, 2, 1)},
        {**base, "fill_id": 2, "last_fill_date": date(2020, 3, 1)},
        {**base, "fill_id": 3, "last_fill_date": date(2020, 2, 1)},  # same fill, later request
    ]
    monkeypatch.setattr(emr, "pharmacy_fills", lambda emr_id: [dict(r) for r in rows])
    out = live.pharmacy_fills(1)
    assert [r["fill_id"] for r in out] == [2, 1]


def test_lab_orders_view(client):
    r = client.get(f"/patients/{_key(WITH)}", params={"tab": "labs", "view": "orders"})
    assert r.status_code == 200 and "Lab orders" in r.text
    assert "Not resulted (2)" in r.text and "Canceled (1)" in r.text and "All orders (4)" in r.text
    assert "Lipid panel" in r.text and "Vitamin D, 25-hydroxy" in r.text  # Ordered + Pending
    assert "Patient to return fasting" in r.text and "E11.9 Type 2 diabetes mellitus" in r.text
    assert "Hemoglobin A1c" not in r.text and "CBC with differential" not in r.text
    r = client.get(f"/patients/{_key(WITH)}/tab/labs", params={"view": "orders", "status": "all"},
                   headers=HTMX)  # fmt: skip
    assert "Hemoglobin A1c" in r.text and "TSH" in r.text
    assert "CBC with differential" not in r.text  # erroneous orders never shown
    assert r.headers["HX-Push-Url"] == f"/patients/{_key(WITH)}?tab=labs&view=orders&status=all"
    r = client.get(f"/patients/{_key(NOTHING)}", params={"tab": "labs", "view": "orders"})
    assert "No lab orders waiting for results." in r.text


@pytest.mark.anyio
async def test_pdf_context_lists_open_and_canceled_orders():
    ref = await resolve(_key(WITH))
    ctx = await gather(ref, ExportRequest(sections=["labs"]))
    tests = [o.test for o in ctx["lab_orders"]]
    assert sorted(tests) == ["Lipid panel", "TSH", "Vitamin D, 25-hydroxy"]


def test_overview_reminders_and_referrals(client):
    p = next(p for p in PATIENTS[:5] if p.ntier_id is not None)
    r = client.get(f"/patients/{_key(p)}")
    html = r.text
    assert "Clinical reminders" in html and "Repeat A1C" in html and "High priority" in html
    assert "Completed 01/20/2022 by Nurse, Example" in html
    assert "Entered by mistake" not in html  # erroneous reminders hidden
    assert html.index("Repeat A1C") < html.index("Annual physical")  # open first
    assert "Referrals received" in html and "Referrer, Sample" in html and "AUTH-123" in html
    assert "E11.9 Type 2 diabetes mellitus without complications" in html and "Closed" in html
    assert "Referred for diabetes management" in html


def test_overview_without_pm_has_no_referrals(client):
    p = next(p for p in PATIENTS[:5] if p.ntier_id is None)
    r = client.get(f"/patients/{_key(p)}")
    assert "No referrals received." in r.text


def test_release_log_lists_allscripts_requests(client):
    r = client.get("/release-log")
    assert r.status_code == 200 and "Release requests recorded in Allscripts" in r.text
    assert "Lab results, H&amp;P reports" in r.text and "Entire chart" in r.text
    assert "Example Law Office" in r.text and "In Progress" in r.text
    assert f'href="/patients/EMR:{PATIENTS[0].emr_id}"' in r.text
    r = client.get("/release-log", params={"from": "05/02/2014", "to": "05/02/2014"})
    assert "Entire chart" in r.text and "Example Law Office" not in r.text


@pytest.mark.anyio
async def test_pdf_context_has_reminders_and_referrals():
    p = next(p for p in PATIENTS[:5] if p.ntier_id is not None)
    ref = await resolve(_key(p))
    ctx = await gather(ref, ExportRequest(sections=["demographics"]))
    assert [r.subject for r in ctx["reminders"]] == ["Repeat A1C", "Annual physical"]
    assert ctx["referrals"][0].authorization == "AUTH-123"
