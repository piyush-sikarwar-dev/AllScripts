"""Appointments tab: the EMR schedule merged with practice-management appointments.

The patient's list comes from the cached repository function `appointments` (metadata only, a
few dozen rows for most patients); filtering, counts and paging happen here. Statuses and their
filter groups come from config/appointment_statuses.yaml. Nothing here logs comments.
"""

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

import yaml

from app.crosswalk import PatientRef
from app.formatting import date_us, sort_key, to_clinic_time
from app.lookups import CONFIG_DIR
from app.models.appointments import (
    AppointmentRow,
    AppointmentsPage,
    AppointmentsState,
    AppointmentStat,
    StatusChip,
)
from app.models.common import PAGE_SIZE, Pager
from app.repositories import source_repository
from app.services import call

GROUPS: list[tuple[str, str]] = [
    ("all", "All"),
    ("kept", "Kept"),
    ("cancelled", "Cancelled"),
    ("no_show", "No-show"),
    ("scheduled", "Scheduled"),
    ("other", "Other"),
]
GROUP_KEYS = frozenset(k for k, _ in GROUPS)


@lru_cache
def _statuses() -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / "appointment_statuses.yaml").read_text(encoding="utf-8"))


def status_of(appt: dict) -> tuple[str, str]:
    """(label, group). The PM status wins when the appointment was matched to PM."""
    cfg = _statuses()
    pm = (appt.get("pm_status") or "").strip().upper()
    if pm and pm in cfg["pm"]:
        entry = cfg["pm"][pm]
    elif appt.get("emr_status") in cfg["emr"]:
        entry = cfg["emr"][appt["emr_status"]]
    else:
        entry = cfg["default"]
    return entry["label"], entry["group"]


def parse_state(params: Mapping[str, str]) -> AppointmentsState:
    status = params.get("status", "all")
    year, page = params.get("year", ""), params.get("page", "")
    return AppointmentsState(
        status=status if status in GROUP_KEYS else "all",
        year=int(year) if year.isdigit() and 1990 <= int(year) <= 2100 else None,
        page=int(page) if page.isdigit() and 0 < int(page) <= 100_000 else 1,
    )


def _time(value: Any) -> str:
    if value is None:
        return "—"
    local = to_clinic_time(value) if value.tzinfo else value
    if local.hour == 0 and local.minute == 0:
        return "—"
    return f"{local.hour % 12 or 12}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


def _year(value: Any) -> int | None:
    if value is None:
        return None
    return (to_clinic_time(value) if value.tzinfo else value).year


def _details(appt: dict, group: str) -> str:
    parts = []
    if group == "cancelled" and appt.get("cancel_reason"):
        parts.append(appt["cancel_reason"])
    if appt.get("arrived"):
        parts.append(f"Arrived {appt['arrived']}")
    if appt.get("left"):
        parts.append(f"Left {appt['left']}")
    if appt.get("duration"):
        parts.append(f"{appt['duration']} min")
    return " · ".join(parts)


def appointment_row(appt: dict) -> AppointmentRow:
    label, group = status_of(appt)
    comment = (appt.get("comment") or "").strip()
    return AppointmentRow(
        date=date_us(appt["starts"]),
        time=_time(appt["starts"]),
        type=appt.get("type") or "—",
        provider=appt.get("provider") or "—",
        location=appt.get("location") or "—",
        status=group,
        status_label=label,
        details=_details(appt, group),
        comment=comment[:300] or None,
        sources=appt.get("sources") or ["EMR"],
    )


async def all_appointments(ref: PatientRef) -> list[dict]:
    rows = await call(source_repository().appointments, ref.emr_id, ref.ntier_id)
    return sorted(rows, key=lambda a: (sort_key(a["starts"]), a["id"]), reverse=True)


def build_page(appts: list[dict], state: AppointmentsState) -> AppointmentsPage:
    groups = [status_of(a)[1] for a in appts]
    in_year = [state.year is None or _year(a["starts"]) == state.year for a in appts]
    counts = dict.fromkeys(GROUP_KEYS, 0)
    for group, ok in zip(groups, in_year, strict=True):
        if ok:
            counts["all"] += 1
            counts[group] += 1
    chips = [StatusChip(key=k, label=label, count=counts[k], selected=state.status == k)
             for k, label in GROUPS if k in ("all", state.status) or counts[k]]  # fmt: skip
    rows = [a for a, g, ok in zip(appts, groups, in_year, strict=True)
            if ok and state.status in ("all", g)]  # fmt: skip
    pager = Pager(page=state.page, total=len(rows), page_size=PAGE_SIZE)
    if pager.page > pager.pages:
        pager = Pager(page=pager.pages, total=len(rows), page_size=PAGE_SIZE)
    kept = [a for a, g in zip(appts, groups, strict=True) if g == "kept"]
    total = len(appts)
    stats = [
        AppointmentStat(label="Appointments", value=f"{total:,}",
                        caption=f"Since {date_us(appts[-1]['starts'])}" if appts else ""),
        AppointmentStat(label="Kept", value=f"{len(kept):,}",
                        caption=f"Last {date_us(kept[0]['starts'])}" if kept else ""),
        AppointmentStat(label="Cancelled", value=f"{groups.count('cancelled'):,}"),
        AppointmentStat(label="No-shows", value=f"{groups.count('no_show'):,}"),
    ]  # fmt: skip
    years = sorted({y for a in appts if (y := _year(a["starts"]))}, reverse=True)
    noun = "appointment" if len(rows) == 1 else "appointments"
    where = f"Year {state.year}" if state.year else "All years"
    return AppointmentsPage(
        stats=stats,
        chips=chips,
        years=years,
        rows=[appointment_row(a) for a in rows[pager.offset : pager.offset + PAGE_SIZE]],
        pager=pager,
        context=f"{where} · {len(rows):,} {noun}",
    )


async def appointments_tab(ref: PatientRef, params: Mapping[str, str]) -> dict:
    state = parse_state(params)
    page = build_page(await all_appointments(ref), state)
    state = state.model_copy(update={"page": page.pager.page})
    return {"appts_state": state, "appts": page}
