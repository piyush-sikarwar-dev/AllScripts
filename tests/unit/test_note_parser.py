"""Note parser (Visits tab Structured view). All note text here is invented."""

import logging

from app.services.note_parser import clean_text, original_text, parse_note, split_fragments

XML_NOTE = (
    "Sample patient reports stable sugars.\n\n"
    '<?xml version="1.0" encoding="ISO-8859-1"?><reasonsForVisit><hasRFV>true</hasRFV>'
    "<patientDemLine>Sample, Patient A 64 F</patientDemLine>"
    '<chiefComplaint><rfvItem kndgCode="0" kndgName="diabetes">'
    "<hpStatement>Sample patient reports stable sugars.</hpStatement>"
    '<kndgLimits low="1" high="2"/>'
    "<itemEnctInfo><lineId>7</lineId><hpLinkText>link</hpLinkText>"
    "<hpLinkTextDetail>detail</hpLinkTextDetail></itemEnctInfo>"
    "<lexiconNarrative>Narrative |......||......| text</lexiconNarrative>"
    "</rfvItem>"
    '<rfvItem kndgCode="1" kndgName="hypertension"><hpStatement>BP has been fine.</hpStatement>'
    "</rfvItem>"
    '<rfvItem kndgCode="2" kndgName="Diabetes"/></chiefComplaint>'
    '<sectionEnctInfo id="2" description="History of Present Illness">'
    "<attendingCaregiver>Dr Example</attendingCaregiver><datetimeStamp>2019</datetimeStamp>"
    "<isFromTemplate>0</isFromTemplate></sectionEnctInfo></reasonsForVisit>"
)


def titles(note):
    return [s.title for s in note.sections]


def test_example_note_with_xml():
    note = parse_note(XML_NOTE)
    assert note.parse_ok
    assert titles(note) == ["Chief complaint", "History of Present Illness"]
    assert note.sections[0].paragraphs == ["Diabetes, Hypertension"]  # de-duplicated, capitalised
    assert note.sections[1].paragraphs == [
        "Sample patient reports stable sugars.",
        "BP has been fine.",
    ]
    text = " ".join(p for s in note.sections for p in s.paragraphs)
    for metadata in ("Sample, Patient A 64 F", "link", "detail", "Dr Example", "2019", "true"):
        assert metadata not in text


def test_leading_text_kept_when_it_is_not_the_history():
    note = parse_note("Called in a refill.\n" + XML_NOTE.split("\n\n", 1)[1])
    assert titles(note)[-1] == "Note"
    assert note.sections[-1].paragraphs == ["Called in a refill."]


def test_lexicon_narrative_used_when_no_hp_statement():
    note = parse_note(
        '<?xml version="1.0"?><reasonsForVisit><chiefComplaint><rfvItem kndgName="cough">'
        "<lexiconNarrative>Dry |......||......| cough   for two  days</lexiconNarrative>"
        "</rfvItem></chiefComplaint></reasonsForVisit>"
    )
    assert note.sections[1].title == "History of present illness"
    assert note.sections[1].paragraphs == ["Dry cough for two days"]


def test_note_without_xml_is_one_note_section():
    note = parse_note("First paragraph.\n\nSecond   paragraph.\n")
    assert titles(note) == ["Note"]
    assert note.sections[0].paragraphs == ["First paragraph.", "Second paragraph."]
    assert parse_note("BP < 140 and pulse > 60").sections[0].paragraphs == [
        "BP < 140 and pulse > 60"
    ]


def test_broken_xml_falls_back_and_logs_only_the_encounter(caplog):
    caplog.set_level(logging.WARNING, logger="app.notes")
    note = parse_note(
        'Intro.<?xml version="1.0"?><reasonsForVisit><rfvItem kndgName="x">'
        "Text<b></reasonsForVisit>",
        encounter_id=4242,
    )
    assert not note.parse_ok
    assert titles(note) == ["Note"]
    assert "Intro." in note.sections[0].paragraphs[0] and "<" not in note.sections[0].paragraphs[0]
    assert "note_parse_fallback encounter=4242" in caplog.text
    assert "Intro" not in caplog.text  # never note text in logs


def test_xml_entities_and_dtds_are_refused():
    evil = (
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        "<reasonsForVisit><chiefComplaint><rfvItem kndgName='&x;'/></chiefComplaint>"
        "</reasonsForVisit>"
    )
    note = parse_note(evil)
    assert not note.parse_ok  # refused, shown as stripped text instead
    assert "passwd" not in " ".join(p for s in note.sections for p in s.paragraphs)


def test_multiple_xml_fragments():
    one = '<?xml version="1.0"?><reasonsForVisit><chiefComplaint><rfvItem kndgName="a"/>'
    one += "</chiefComplaint></reasonsForVisit>"
    two = one.replace('"a"', '"b"')
    note = parse_note(one + "\n" + two)
    assert note.parse_ok and note.sections[0].paragraphs == ["A, B"]
    assert [k for k, _ in split_fragments(one + "between" + two)] == ["xml", "text", "xml"]


def test_empty_note():
    assert parse_note("").sections == []
    assert parse_note(None).sections == []
    assert parse_note("   \n ").parse_ok


def test_clean_text_removes_separators_and_keeps_paragraphs():
    assert clean_text("a |......||......| b\n\n\n c  d") == ["a b", "c d"]


def test_original_text_pretty_prints_xml_and_keeps_text():
    out = original_text(XML_NOTE)
    assert out.startswith("Sample patient reports stable sugars.")
    assert "<reasonsForVisit>" in out and "\n  <chiefComplaint>" in out
    broken = 'x<?xml version="1.0"?><a><b></a>'
    assert original_text(broken) == broken  # unparseable: exactly as stored
