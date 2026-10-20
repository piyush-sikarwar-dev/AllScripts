"""Ntier_0010060 (PM) read-only queries — one function per .sql file."""

from typing import Any

from app.db.source import Source
from app.repositories.base import run_query

PM_ACCOUNT = "ntier/pm_account.sql"


def pm_account(ntier_id: int) -> dict[str, Any] | None:
    rows = run_query(Source.NTIER, PM_ACCOUNT, {"ntier_id": ntier_id})
    return rows[0] if rows else None


APPOINTMENTS = "ntier/appointments.sql"


def appointments(ntier_id: int) -> list[dict[str, Any]]:
    return run_query(Source.NTIER, APPOINTMENTS, {"ntier_id": ntier_id})


PATIENT_POLICIES = "ntier/patient_policies.sql"


def patient_policies(ntier_id: int) -> list[dict[str, Any]]:
    return run_query(Source.NTIER, PATIENT_POLICIES, {"ntier_id": ntier_id})


INCOMING_REFERRALS = "ntier/incoming_referrals.sql"
INCOMING_REFERRAL_DIAGNOSES = "ntier/incoming_referral_diagnoses.sql"


def incoming_referrals(ntier_id: int) -> list[dict[str, Any]]:
    return run_query(Source.NTIER, INCOMING_REFERRALS, {"ntier_id": ntier_id})


def incoming_referral_diagnoses(ntier_id: int) -> list[dict[str, Any]]:
    return run_query(Source.NTIER, INCOMING_REFERRAL_DIAGNOSES, {"ntier_id": ntier_id})
