"""In-memory stand-in for the source repositories (used when USE_FAKE_DATA=true and in unit tests).

Function names and return shapes are the contract the real `app/repositories/` modules implement
from Phase 4 on: plain dicts / lists of dicts with raw values.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.documents.render import embedded_images, render_document
from tests.fakes.data import PATIENTS, PATIENTS_BY_ID, FakePatient


def totals() -> dict[str, int]:
    return {
        "patients": len(PATIENTS),
        "encounters": sum(len(p.visits) for p in PATIENTS),
        "lab_results": sum(len(p.labs) for p in PATIENTS),
        "scanned_documents": sum(1 for p in PATIENTS for d in p.documents if d["kind"] == "scan"),
    }


def _summary(p: FakePatient) -> dict:
    return {
        "emr_id": p.emr_id,
        "last_name": p.last_name,
        "first_name": p.first_name,
        "middle_initial": p.middle_initial,
        "dob": p.dob,
        "sex": p.sex,
        "chart_id": p.chart_id,
        "deceased": p.deceased,
        "ntier_id": p.ntier_id,
        "dmz_id": p.dmz_id,
    }


def search_patients(
    *,
    last_name: str | None,
    first_name: str | None,
    dob: date | None,
    chart_id: str | None,
    offset: int,
    limit: int,
) -> tuple[list[dict], int]:
    def matches(p: FakePatient) -> bool:
        return (
            (last_name is None or p.last_name.lower().startswith(last_name.lower()))
            and (first_name is None or p.first_name.lower().startswith(first_name.lower()))
            and (dob is None or p.dob == dob)
            and (chart_id is None or p.chart_id == chart_id)
        )

    found = sorted(
        (p for p in PATIENTS if matches(p)), key=lambda p: (p.last_name, p.first_name, p.emr_id)
    )
    return [_summary(p) for p in found[offset : offset + limit]], len(found)


def last_visits(emr_ids: list[int]) -> dict[int, object]:
    result = {}
    for emr_id in emr_ids:
        visits = PATIENTS_BY_ID[emr_id].visits
        if visits:
            result[emr_id] = max(v["start"] for v in visits)
    return result


def get_patient(emr_id: int) -> dict | None:
    p = PATIENTS_BY_ID.get(emr_id)
    if p is None:
        return None
    return _summary(p) | {
        "phone": p.phone,
        "address": p.address,
        "city": p.city,
        "state": p.state,
        "zip": p.zip,
        "pm_account": p.pm_account,
        "primary_insurance": p.primary_insurance,
        "has_photo": patient_photo(emr_id) is not None,
    }


def patient_names(emr_ids: list[int]) -> dict[int, str]:
    return {
        i: f"{PATIENTS_BY_ID[i].last_name}, {PATIENTS_BY_ID[i].first_name}"
        for i in emr_ids
        if i in PATIENTS_BY_ID
    }


def visits(emr_id: int, office_only: bool = False) -> list[dict]:
    rows = list(PATIENTS_BY_ID[emr_id].visits)
    return [v for v in rows if v["is_office_visit"]] if office_only else rows


def last_visit(emr_id: int) -> dict | None:
    visits = PATIENTS_BY_ID[emr_id].visits
    if not visits:
        return None
    v = max(visits, key=lambda v: v["start"])
    return {k: v[k] for k in ("start", "visit_type", "provider", "location")}


def visit(emr_id: int, contact_id: int) -> dict | None:
    return next((v for v in PATIENTS_BY_ID[emr_id].visits if v["contact_id"] == contact_id), None)


def visit_vitals(emr_id: int, contact_id: int) -> list[dict]:
    rows = [v for v in PATIENTS_BY_ID[emr_id].vitals if v["contact_id"] == contact_id]
    return sorted(rows, key=lambda v: (v["date"], v["id"]))


def notes(emr_id: int) -> list[dict]:
    return [n | {"kind": "document"} for n in PATIENTS_BY_ID[emr_id].notes]


def note_index(emr_id: int) -> list[dict]:
    """Notes tab index: the synthetic clinical notes + the older fake notes (as documents)."""
    p = PATIENTS_BY_ID[emr_id]
    rows = [{k: v for k, v in n.items() if k not in ("html", "text", "message_fields",
                                                     "attachment_name")}
            for n in p.clinical_notes]  # fmt: skip
    rows += [
        {"kind": "document", "id": n["id"], "date": n["date"], "title": n["title"],
         "who": n["author"], "app_source": None, "map_sources": [], "source": n["source"],
         "encounter_id": None}
        for n in p.notes
    ]  # fmt: skip
    return rows


def note(emr_id: int, kind: str, note_id: int) -> dict | None:
    p = PATIENTS_BY_ID[emr_id]
    synthetic = next(
        (n for n in p.clinical_notes if n["kind"] == kind and n["id"] == note_id), None
    )
    if synthetic is not None:
        html = (
            render_document(synthetic["html"].encode(), note_id) if synthetic.get("html") else None
        )
        return synthetic | {"html": html, "text": synthetic.get("text"), "author": synthetic["who"]}
    found = next((n for n in PATIENTS_BY_ID[emr_id].notes if n["id"] == note_id), None)
    if found is None or kind != "document":
        return None
    text = "Placeholder note text generated for interface review only."
    return found | {"kind": kind, "html": None, "text": text}


def history(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].history)


def medications(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].medications)


def labs(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].labs)


def vitals(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].vitals)


def documents(emr_id: int) -> list[dict]:
    return [
        d | {"kind": d["kind"] if d["kind"] in ("scan", "attachment") else "document"}
        for d in PATIENTS_BY_ID[emr_id].documents
    ]


def document_pages(emr_id: int, document_id: int) -> dict | None:
    d = next((d for d in PATIENTS_BY_ID[emr_id].documents if d["id"] == document_id), None)
    if d is None or d["kind"] != "scan":
        return None
    pages = [
        {
            "page_id": document_id * 100 + n,
            "location": f"\\\\amhs-db1\\hmscan\\fake\\{document_id}-{n}",
        }
        for n in range(1, d["pages"] + 1)
    ]
    return {
        "id": document_id,
        "date": d["date"],
        "type": d["type"],
        "title": d["title"],
        "pages": pages,
        "source": "EMR",
    }


# --- Visits tab (Option C): fake data has one contact per encounter -------------------------


def _fake_category(v: dict) -> str:
    return "office" if v["is_office_visit"] else "other"


def _fake_encounters(emr_id: int, category: str | None) -> list[dict]:
    rows = [
        v
        for v in PATIENTS_BY_ID[emr_id].visits
        if category is None or _fake_category(v) == category
    ]
    return sorted(rows, key=lambda v: (v["start"], v["encounter_id"]), reverse=True)


def _fake_summary(v: dict) -> dict:
    last, _, first = v["provider"].partition(", ")
    return {
        "encounter_id": v["encounter_id"],
        "date": v["start"],
        "visit_type": v["visit_type"],
        "category": _fake_category(v),
        "signed": v["signed"],
        "provider": v["provider"],
        "provider_short": f"{first[:1]}. {last}" if first else last,
        "location": v["location"],
        "source": "EMR",
    }


def visits_page(
    emr_id: int, category: str | None, year: int | None, q: str | None, page: int
) -> dict:
    rows = _fake_encounters(emr_id, category)
    if year is not None:
        rows = [v for v in rows if v["start"].year == year]
    if q:
        needle = q.lower()
        rows = [
            v
            for v in rows
            if needle in v["provider"].lower()
            or any(needle in t.lower() or needle in c.lower() for t, c in v["diagnoses"])
        ]
    start = (page - 1) * 25
    return {
        "total": len(rows),
        "rows": [
            _fake_summary(v) | {"diagnoses": [(c, t) for t, c in v["diagnoses"]]}
            for v in rows[start : start + 25]
        ],
    }


def visits_activity(emr_id: int, category: str | None) -> dict:
    rows = _fake_encounters(emr_id, category)
    years: dict[int, int] = {}
    providers: dict[str, list] = {}
    diagnoses: dict[tuple[str, str], list] = {}
    for v in rows:
        years[v["start"].year] = years.get(v["start"].year, 0) + 1
        providers.setdefault(v["provider"], []).append(v["start"])
        for title, code in v["diagnoses"]:
            diagnoses.setdefault((code, title), []).append(v["start"])
    top_p = max(providers.items(), key=lambda kv: (len(kv[1]), max(kv[1])), default=None)
    top_d = max(diagnoses.items(), key=lambda kv: (len(kv[1]), max(kv[1])), default=None)
    return {
        "years": years,
        "total": len(rows),
        "last_visit": rows[0]["start"] if rows else None,
        "top_provider": top_p[0] if top_p else None,
        "top_provider_count": len(top_p[1]) if top_p else 0,
        "top_diagnosis": top_d[0][1] if top_d else None,
        "top_diagnosis_code": top_d[0][0] if top_d else None,
        "top_diagnosis_count": len(top_d[1]) if top_d else 0,
    }


def encounter(emr_id: int, encounter_id: int) -> dict | None:
    v = next((v for v in PATIENTS_BY_ID[emr_id].visits if v["encounter_id"] == encounter_id), None)
    if v is None:
        return None
    readings = [r for r in PATIENTS_BY_ID[emr_id].vitals if r["contact_id"] == v["contact_id"]]
    return _fake_summary(v) | {
        "assessment": [(c, t) for t, c in v["diagnoses"]],
        "plan": list(v["plan"]),
        "addenda": list(v["addenda"]),
        "note_documents": [],
        "other_documents": [],
        "text_notes": [v["note_text"]] if v["note_text"] else [],
        "vitals": sorted(readings, key=lambda r: (r["date"], r["id"])),
    }


# --- Problems & allergies tab (Option B) ---------------------------------------------------------


def history_entries(emr_id: int) -> list[dict]:
    return [dict(e) for e in PATIENTS_BY_ID[emr_id].hx_entries]


def history_changes(emr_id: int, hx_id: int) -> list[dict]:
    return [dict(r) for r in PATIENTS_BY_ID[emr_id].hx_revisions.get(hx_id, [])]


def appointments(emr_id: int, ntier_id: int | None) -> list[dict]:
    return [dict(a) for a in PATIENTS_BY_ID[emr_id].appointments]


def portal_attachment(emr_id: int, portal_id: int) -> dict | None:
    from tests.fakes.data import FAKE_PDF

    for n in PATIENTS_BY_ID[emr_id].clinical_notes:
        if n["kind"] == "portal" and n["id"] == portal_id and n.get("attachment"):
            return {
                "content": FAKE_PDF,
                "attachment_name": n["attachment"],
                "attachment_type": ".pdf",
            }
    return None


def _fake_image(fmt: str) -> bytes:
    """A small 2-page TIFF or a 1-page JPEG, generated on request (no files in the repo)."""
    import io

    from PIL import Image

    pages = [Image.new("L", (120, 160), color=shade) for shade in (230, 200)]
    out = io.BytesIO()
    if fmt == "tif":
        pages[0].save(out, format="TIFF", save_all=True, append_images=pages[1:])
    else:
        pages[0].convert("RGB").save(out, format="JPEG")
    return out.getvalue()


def attachment_file(emr_id: int, attachment_id: int) -> dict | None:
    from tests.fakes.data import FAKE_PDF

    doc = next((d for d in PATIENTS_BY_ID[emr_id].documents
                if d["kind"] == "attachment" and d["id"] == attachment_id), None)  # fmt: skip
    if doc is None or doc["format"] == "rtf":
        return None
    content = FAKE_PDF if doc["format"] == "pdf" else _fake_image(doc["format"])
    return {"content": content, "file_format": doc["format"]}


def attachment_text(emr_id: int, attachment_id: int) -> str | None:
    doc = next((d for d in PATIENTS_BY_ID[emr_id].documents
                if d["kind"] == "attachment" and d["id"] == attachment_id), None)  # fmt: skip
    if doc is None or doc["format"] != "rtf":
        return None
    return "Dear Dr. Example, placeholder letter text generated for interface review only."


def document_image(emr_id: int, document_id: int, index: int) -> tuple[str, bytes] | None:
    for note in PATIENTS_BY_ID[emr_id].clinical_notes:
        if note["kind"] == "document" and note["id"] == document_id and note.get("html"):
            images = embedded_images(note["html"].encode())
            return images[index] if 0 <= index < len(images) else None
    return None


# A tiny valid JPEG (1x1 grey pixel), used as the photo of every second fake patient.
_FAKE_PHOTO = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912"
    "130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b080001"
    "000101011100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b51000020103"
    "03020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f024336272"
    "82090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475"
    "767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9"
    "cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda0008010100003f00fbd3ffd9"
)


def _index(emr_id: int) -> int:
    return next(i for i, p in enumerate(PATIENTS) if p.emr_id == emr_id)


def patient_details(emr_id: int, ntier_id: int | None) -> dict:
    p = PATIENTS_BY_ID[emr_id]
    i = _index(emr_id)
    if i % 6 == 5:  # some patients have nothing beyond the header
        return {
            "insurances": [],
            "pm_policies": [],
            "profile": {"marital_status": None, "has_photo": 0},
            "race": [],
            "ethnicity": [],
            "contacts": [],
            "care_team": [],
            "consents": [],
        }
    insurances = [
        {
            "policy_id": emr_id * 10 + n,
            "rank": rank,
            "carrier": carrier,
            "carrier_phone": "555-0100",
            "plan_type": plan_type,
            "group_number": f"G{emr_id}{n}",
            "plan_number": None,
            "member_id": f"M{emr_id}{n}",
            "effective_date": date(2015 + n, 1, 1),
            "termination_date": date(2018, 12, 31) if archived else None,
            "subscriber_last": p.last_name,
            "subscriber_first": p.first_name,
            "subscriber_middle": None,
            "subscriber_dob": p.dob,
            "relation_code": 1,
            "workers_comp": 0,
            "archived": archived,
        }
        for n, (rank, carrier, plan_type, archived) in enumerate(
            [
                (0, p.primary_insurance or "Sample Health Plan", 5, 0),
                (1, "Example Medicare", 1, 0),
                (0, "Old Sample Insurer", 3, 1),
            ]
        )
    ]
    pm = (
        [
            {
                "policy_id": emr_id,
                "coverage": "P",
                "relationship": " ",
                "carrier": "Sample PM Carrier",
                "carrier_phone": "555-0200",
                "plan_name": "Sample PPO",
                "group_name": "Example Employer",
                "group_number": "PMG1",
                "certificate_number": f"CERT{emr_id}",
                "effective_date": date(2016, 3, 1),
                "expiration_date": None,
                "copay": Decimal("25.0000"),
                "holder_last": p.last_name,
                "holder_first": p.first_name,
                "holder_middle": None,
                "holder_dob": p.dob,
            }
        ]
        if ntier_id is not None
        else []
    )
    profile = {
        "marital_status": 2,
        "guarantor_relation": 1,
        "guarantor_last": p.last_name,
        "guarantor_first": p.first_name,
        "guarantor_middle": None,
        "guarantor_suffix": None,
        "guarantor_dob": p.dob,
        "guarantor_address": p.address,
        "guarantor_city": p.city,
        "guarantor_state": p.state,
        "guarantor_zip": p.zip,
        "guarantor_phone": p.phone,
        "has_photo": 1 if i % 2 == 0 else 0,
    }
    contacts = [
        {
            "contact_id": 1,
            "rank": 1,
            "last_name": "Contact",
            "first_name": "Sample",
            "middle_name": None,
            "relationship": "Spouse",
            "emergency": 1,
            "proxy": 1,
            "address": "1 Example St",
            "city": "Sampletown",
            "state": "NY",
            "zip": "00000",
            "phone": "555-0300",
            "mobile": "555-0301",
            "email": None,
        }
    ]
    care_team = [
        {
            "role_code": 1,
            "added_at": datetime(2016, 1, 4, tzinfo=UTC),
            "provider_last": "Doctor",
            "provider_first": "Sample",
            "provider_title": "MD",
        },
        {
            "role_code": 3,
            "added_at": datetime(2019, 6, 1, tzinfo=UTC),
            "provider_last": "Specialist",
            "provider_first": "Example",
            "provider_title": "DO",
        },
    ]
    consents = [
        {
            "consent_id": 1,
            "consent_code": 1,
            "answer_code": 3,
            "expires": None,
            "recorded_at": datetime(2016, 1, 4, tzinfo=UTC),
        },
        {
            "consent_id": 2,
            "consent_code": 14,
            "answer_code": 1,
            "expires": date(2030, 1, 1),
            "recorded_at": datetime(2020, 2, 2, tzinfo=UTC),
        },
    ]
    return {
        "insurances": insurances,
        "pm_policies": pm,
        "profile": profile,
        "race": [5],
        "ethnicity": [2],
        "contacts": contacts,
        "care_team": care_team,
        "consents": consents,
    }


def patient_photo(emr_id: int) -> bytes | None:
    return _FAKE_PHOTO if _index(emr_id) % 2 == 0 and _index(emr_id) % 6 != 5 else None


_FILLS = [
    ("METFORMIN HCL 500 MG TABLET", "500 MG", 60, 30, "TAKE 1 TABLET BY MOUTH TWICE DAILY", "2"),
    ("LISINOPRIL 10 MG TABLET", "10 MG", 30, 30, None, "5"),
    ("AMOXICILLIN 500 MG CAPSULE", "500 MG", 30, 10, "TAKE 1 CAPSULE THREE TIMES DAILY", None),
]


def pharmacy_fills(emr_id: int) -> list[dict]:
    i = _index(emr_id)
    if i % 6 == 5:
        return []
    rows = []
    for n, (drug, strength, qty, days, sig, refills) in enumerate(_FILLS):
        for k in range(2):  # two fills of each prescription
            rows.append(
                {
                    "fill_id": emr_id * 100 + n * 10 + k,
                    "checked_at": datetime(2023, 5, 1, 14, 0, tzinfo=UTC),
                    "drug_name": drug,
                    "strength": strength,
                    "quantity": qty,
                    "quantity_unit": "   ",
                    "days_supply": days,
                    "sig": sig,
                    "refills": refills,
                    "substitutions": 0,
                    "written_date": date(2022, 1 + n, 5),
                    "last_fill_date": date(2022, 2 + n + k * 2, 1),
                    "prescriber": "DOCTOR, SAMPLE" if n != 1 else None,
                    "pharmacy": "SAMPLE PHARMACY #12",
                }
            )
    rows.sort(key=lambda r: (r["last_fill_date"], r["written_date"]), reverse=True)
    return rows


# (test, status code: 1 Ordered, 3 Final, 5 Pending, 6 Canceled, 7 Erroneous, comment)
_LAB_ORDERS = [
    ("Lipid panel", 1, "Patient to return fasting"),
    ("Hemoglobin A1c", 3, None),
    ("Vitamin D, 25-hydroxy", 5, None),
    ("TSH", 6, "Canceled by provider"),
    ("CBC with differential", 7, None),
]


def lab_orders(emr_id: int) -> list[dict]:
    if _index(emr_id) % 6 == 5:
        return []
    rows = [
        {
            "order_id": emr_id * 10 + n,
            "ordered_at": datetime(2021, 1 + n, 10, 15, 0, tzinfo=UTC),
            "test": test,
            "catalog_name": None,
            "status_code": status,
            "reported_at": datetime(2021, 1 + n, 12, tzinfo=UTC) if status == 3 else None,
            "comment": comment,
            "in_house": 0,
            "provider_last": "Doctor",
            "provider_first": "Sample",
            "provider_title": "MD",
            "diagnosis": "Type 2 diabetes mellitus" if n < 2 else None,
            "diagnosis_code": "E11.9" if n < 2 else None,
        }
        for n, (test, status, comment) in enumerate(_LAB_ORDERS)
    ]
    rows.sort(key=lambda r: r["ordered_at"], reverse=True)
    return rows
