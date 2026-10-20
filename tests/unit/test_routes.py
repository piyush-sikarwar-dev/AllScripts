"""Route smoke tests on fake data: every page and tab renders; unknown things are 404."""

import re
from pathlib import Path

import pytest

from app.services.tabs import TAB_NAMES
from tests.fakes.data import PATIENTS

FIRST = f"EMR:{PATIENTS[0].emr_id}"
EMPTY_PATIENT = f"EMR:{PATIENTS[29].emr_id}"  # no clinical data at all
HTMX = {"HX-Request": "true"}


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_redirects_to_patients(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/patients"


def test_login_page(anon_client):
    r = anon_client.get("/login")
    assert r.status_code == 200
    assert "Sign in" in r.text
    assert "Sessions end after 15 minutes of inactivity." in r.text


def test_dashboard(client):
    r = client.get("/patients")
    assert r.status_code == 200
    for text in (
        "Patients",
        "Encounters",
        "Lab results",
        "Scanned documents",
        "All patients",
        "sorted by last name",
        "Page 1 of 2",
    ):
        assert text in r.text
    assert "Demo, Patient C" in r.text


def test_patient_rows_partial_search(client):
    r = client.get("/patients/rows", params={"q": "Sample"}, headers=HTMX)
    assert r.status_code == 200
    assert "Search results" in r.text
    assert "Sample, Patient A" in r.text
    assert "Example, Patient B" not in r.text
    assert r.headers["HX-Push-Url"] == "/patients?q=Sample"


def test_search_last_first_forms(client):
    for q in ("Sample, Patient G", "Sample Patient G"):
        r = client.get("/patients/rows", params={"q": q}, headers=HTMX)
        assert "Sample, Patient G" in r.text
        assert "Sample, Patient A<" not in r.text


def test_search_no_match_empty_state(client):
    r = client.get("/patients/rows", params={"q": "Zzz"}, headers=HTMX)
    assert "No patients match your search." in r.text


def test_search_bad_dob_shows_inline_error(client):
    r = client.get("/patients", params={"dob": "31/31/1999"})
    assert r.status_code == 200
    assert "Enter the date of birth as MM/DD/YYYY." in r.text
    assert 'aria-invalid="true"' in r.text
    # HTMX path updates the error slot out-of-band.
    r = client.get("/patients/rows", params={"dob": "nope"}, headers=HTMX)
    assert 'hx-swap-oob="true">Enter the date of birth as MM/DD/YYYY.' in r.text


def test_dashboard_page_two(client):
    r = client.get("/patients", params={"page": 2})
    assert r.status_code == 200
    assert "Page 2 of 2" in r.text


@pytest.mark.parametrize("tab", sorted(TAB_NAMES))
def test_chart_every_tab_full_page(client, tab):
    r = client.get(f"/patients/{FIRST}", params={"tab": tab})
    assert r.status_code == 200
    assert "Back to patients" in r.text
    assert 'aria-selected="true"' in r.text
    assert f'id="tab-{tab}" class="tab tab--active"' in r.text


@pytest.mark.parametrize("tab", sorted(TAB_NAMES))
def test_chart_every_tab_partial(client, tab):
    r = client.get(f"/patients/{FIRST}/tab/{tab}", headers=HTMX)
    assert r.status_code == 200
    assert 'id="chart-tabs"' in r.text
    assert "<html" not in r.text
    assert r.headers["HX-Push-Url"].startswith(f"/patients/{FIRST}?tab={tab}")


@pytest.mark.parametrize("tab", sorted(TAB_NAMES))
def test_empty_patient_every_tab(client, tab):
    r = client.get(f"/patients/{EMPTY_PATIENT}", params={"tab": tab})
    assert r.status_code == 200
    assert 'class="empty' in r.text


def test_visit_detail_partial(client):
    visit = next(v for v in PATIENTS[0].visits if v["is_office_visit"])
    r = client.get(f"/patients/{FIRST}/visits/{visit['encounter_id']}", headers=HTMX)
    assert r.status_code == 200
    assert "Assessment" in r.text and "data-focus-on-load" in r.text
    assert f"visit={visit['encounter_id']}" in r.headers["HX-Push-Url"]


def test_visit_deep_link(client):
    visit = PATIENTS[0].visits[0]
    r = client.get(
        f"/patients/{FIRST}",
        params={"tab": "visits", "type": "all", "visit": visit["encounter_id"]},
    )
    assert r.status_code == 200
    assert "visit-row--selected" in r.text


def test_visit_of_other_patient_is_404(client):
    other = PATIENTS[1].visits[0]["encounter_id"]
    r = client.get(f"/patients/{FIRST}/visits/{other}", headers=HTMX)
    assert r.status_code == 404


def test_documents_banner_when_scan_root_unset(client):
    with_scans = next(p for p in PATIENTS if any(d["kind"] == "scan" for d in p.documents))
    r = client.get(f"/patients/EMR:{with_scans.emr_id}", params={"tab": "docs"})
    assert "Scanned page images are not connected yet" in r.text
    assert 'role="note"' in r.text
    no_scans = next(
        p for p in PATIENTS if p.documents and not any(d["kind"] == "scan" for d in p.documents)
    )
    r = client.get(f"/patients/EMR:{no_scans.emr_id}", params={"tab": "docs"})
    assert "Scanned page images are not connected yet" not in r.text  # nothing to wait for


def test_labs_trend_and_bad_date(client):
    r = client.get(f"/patients/{FIRST}", params={"tab": "labs", "view": "trend"})
    assert r.status_code == 200 and "Lab trend" in r.text
    r = client.get(f"/patients/{FIRST}", params={"tab": "labs", "from": "13/45/2020"})
    assert "Enter the date as MM/DD/YYYY." in r.text


def test_pre2010_source_row_present(client):
    r = client.get(f"/patients/{FIRST}", params={"tab": "meds", "filter": "all"})
    assert "badge--legacy" in r.text


@pytest.mark.parametrize(
    "path",
    [
        "/patients/EMR:999999",
        "/patients/DMZ:1",
        "/patients/notakey",
        "/patients/EMR:0",
        f"/patients/{FIRST}/tab/unknown",
        "/patients/EMR:999999/tab/overview",
        "/no/such/page",
    ],
)
def test_not_found(client, path):
    r = client.get(path)
    assert r.status_code == 404
    assert "Traceback" not in r.text


def test_unknown_tab_query_is_404(client):
    assert client.get(f"/patients/{FIRST}", params={"tab": "secrets"}).status_code == 404


def test_htmx_404_is_a_fragment(client):
    r = client.get("/patients/EMR:999999/tab/overview", headers=HTMX)
    assert r.status_code == 404
    assert "<html" not in r.text


def test_release_log(client):
    r = client.get("/release-log")
    assert r.status_code == 200
    assert "No records have been released yet." in r.text


def test_no_inline_styles_or_handlers_in_templates():
    """CSP: no style= / on*= attributes and no inline <style> or <script> bodies."""
    root = Path(__file__).resolve().parents[2] / "app" / "templates"
    bad = re.compile(r"""\sstyle\s*=|\son[a-z]+\s*=|<style|<script(?![^>]*\bsrc=)""", re.I)
    offenders = [str(p) for p in root.rglob("*.html") if bad.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_no_cdn_references():
    root = Path(__file__).resolve().parents[2] / "app"
    pattern = re.compile(r"https?://(?!www\.w3\.org)", re.I)
    files = [*root.rglob("*.html"), *root.rglob("*.css"), root / "static" / "js" / "app.js"]
    assert [str(p) for p in files if pattern.search(p.read_text(encoding="utf-8"))] == []


def test_static_assets_are_versioned_so_updates_reach_the_browser(client):
    html = client.get("/patients").text
    css = re.search(r'href="(/static/css/app\.css\?v=[0-9a-f]{12})"', html)
    assert css and re.search(r'src="/static/js/app\.js\?v=[0-9a-f]{12}"', html)
    r = client.get(css.group(1))
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert client.get("/static/css/app.css").headers["cache-control"] == "no-cache"
