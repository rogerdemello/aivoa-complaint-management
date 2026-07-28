"""The sparse-patch contract.

The demo requires that "sorry, the batch number is BMX240602 and the affected
quantity is 48 capsules" updates two fields and leaves the rest of the record
alone. These tests pin that behaviour down without touching an LLM.
"""

from __future__ import annotations

from app.graph.nodes.extraction import merge_complaint, validation_branch
from app.graph.state import Source, make_field, new_state


def _seeded_record() -> dict:
    """A complaint already on file, as the Log tool would have left it."""
    return {
        "customer_name": make_field("Apollo Pharmacy", confidence=0.95, turn_id=1),
        "product_name": make_field("Amoxicillin Capsules", confidence=0.95, turn_id=1),
        "product_strength_grade": make_field("500 mg", confidence=0.9, turn_id=1),
        "complaint_type": make_field("Discoloration", confidence=0.85, turn_id=1),
        "detailed_complaint_description": make_field(
            "Discolored capsules observed in the received stock.", turn_id=1
        ),
        "initial_severity": make_field("Major", confidence=0.6, turn_id=1),
    }


def test_edit_preserves_untouched_fields():
    """The headline requirement: a correction must not erase the record."""
    state = new_state("s1", turn_id=2)
    state["complaint"] = _seeded_record()
    state["source"] = Source.EDIT.value
    state["raw_extraction"] = {
        "fields": {
            "batch_lot_number": {
                "value": "BMX240602",
                "confidence": 0.99,
                "evidence": "the batch number is BMX240602",
            },
            "quantity_affected": {"value": "48", "confidence": 0.95},
            "quantity_unit": {"value": "capsules", "confidence": 0.95},
        }
    }

    result = merge_complaint(state)
    merged = result["complaint"]

    # New values landed.
    assert merged["batch_lot_number"]["value"] == "BMX240602"
    assert merged["quantity_affected"]["value"] == "48"
    assert merged["quantity_unit"]["value"] == "capsules"

    # Everything from turn 1 survived, byte for byte.
    for field, original in _seeded_record().items():
        assert merged[field]["value"] == original["value"], f"{field} was clobbered"

    # And exactly three changes were recorded for the audit trail.
    assert {d["field"] for d in result["diffs"]} == {
        "batch_lot_number", "quantity_affected", "quantity_unit"
    }


def test_null_values_never_clear_existing_fields():
    """A null means "not mentioned", never "blank it out"."""
    state = new_state("s1", turn_id=2)
    state["complaint"] = _seeded_record()
    state["raw_extraction"] = {
        "fields": {
            "customer_name": {"value": None},
            "product_name": {"value": "N/A"},   # validator coerces to None
            "batch_lot_number": {"value": "BMX240602"},
        }
    }

    merged = merge_complaint(state)["complaint"]

    assert merged["customer_name"]["value"] == "Apollo Pharmacy"
    assert merged["product_name"]["value"] == "Amoxicillin Capsules"
    assert merged["batch_lot_number"]["value"] == "BMX240602"


def test_unchanged_value_produces_no_audit_row():
    """Re-stating a value is not a change and must not pollute the audit trail."""
    state = new_state("s1", turn_id=3)
    state["complaint"] = _seeded_record()
    state["raw_extraction"] = {
        "fields": {"product_name": {"value": "Amoxicillin Capsules", "confidence": 0.9}}
    }

    assert merge_complaint(state)["diffs"] == []


def test_hallucinated_field_names_are_dropped():
    state = new_state("s1", turn_id=2)
    state["complaint"] = {}
    state["raw_extraction"] = {
        "fields": {
            "product_name": {"value": "Metformin Hydrochloride API"},
            "warehouse_temperature": {"value": "25C"},  # not a form field
        }
    }

    merged = merge_complaint(state)["complaint"]
    assert "product_name" in merged
    assert "warehouse_temperature" not in merged


def test_diff_carries_evidence_and_previous_value():
    """The audit trail needs old -> new plus the text that justified it."""
    state = new_state("s1", turn_id=2)
    state["complaint"] = {"batch_lot_number": make_field("WRONG-001", turn_id=1)}
    state["source"] = Source.EDIT.value
    state["raw_extraction"] = {
        "fields": {
            "batch_lot_number": {
                "value": "CHG260712A",
                "confidence": 0.98,
                "evidence": "the batch number is CHG260712A",
            }
        }
    }

    diff = merge_complaint(state)["diffs"][0]
    assert diff["old_value"] == "WRONG-001"
    assert diff["new_value"] == "CHG260712A"
    assert diff["evidence"] == "the batch number is CHG260712A"
    assert diff["source"] == Source.EDIT.value


def test_malformed_extraction_leaves_record_intact():
    """After the repair loop gives up, the existing record must survive."""
    state = new_state("s1", turn_id=2)
    state["complaint"] = _seeded_record()
    state["raw_extraction"] = {"fields": "this is not a mapping"}

    result = merge_complaint(state)
    assert result["diffs"] == []
    assert "complaint" not in result  # record left untouched


class TestRepairLoop:
    def test_valid_extraction_proceeds_to_merge(self):
        state = new_state("s1")
        state["raw_extraction"] = {"fields": {}}
        state["validation_error"] = None
        assert validation_branch(state) == "merge_complaint"

    def test_failure_retries_the_correct_extractor(self):
        state = new_state("s1")
        state["raw_extraction"] = {"fields": {}}
        state["validation_error"] = "boom"
        state["repair_attempts"] = 1

        state["source"] = Source.EDIT.value
        assert validation_branch(state) == "extract_patch"

        state["source"] = Source.PROMPT.value
        assert validation_branch(state) == "extract_complaint"

    def test_gives_up_after_max_attempts(self):
        state = new_state("s1")
        state["raw_extraction"] = {"fields": {}}
        state["validation_error"] = "boom"
        state["repair_attempts"] = 2
        assert validation_branch(state) == "merge_complaint"
