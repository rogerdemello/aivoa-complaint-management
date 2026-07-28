"""Seed historical complaints so duplicate detection has something to find.

    .venv/Scripts/python.exe scripts/seed_complaints.py

CMP-2026-0002 is deliberately the same product and batch as the Apollo
amoxicillin demo, and CMP-2026-0005 is the same product on a different batch -
so the demo shows the model distinguishing a true duplicate from a trend.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.compat import configure_event_loop  # noqa: E402
from app.db.models import Complaint  # noqa: E402
from app.db.session import dispose_engine, get_session_factory  # noqa: E402
from app.graph.state import make_field  # noqa: E402

configure_event_loop()

SEEDS = [
    {
        "reference_no": "CMP-2026-0002",
        "product_name": "Amoxicillin Capsules",
        "batch_lot_number": "BMX240602",
        "complaint_type": "Discoloration",
        "description": (
            "Retail pharmacy reported pink to light brown discolouration on capsule "
            "bodies from batch BMX240602. Two strips also showed softening of the "
            "capsule shell suggesting moisture ingress."
        ),
        "customer_name": "MedPlus Pharmacy, Bengaluru",
        "complaint_source": "Email",
    },
    {
        "reference_no": "CMP-2026-0003",
        "product_name": "Metformin Hydrochloride API",
        "batch_lot_number": "MFH25K",
        "complaint_type": "Foreign Matter",
        "description": (
            "Formulator reported dark particulate matter adhering to the inner liner "
            "of one HDPE drum. Liner seal found partially torn on receipt."
        ),
        "customer_name": "Zenith Pharma Works",
        "complaint_source": "Customer Letter",
    },
    {
        "reference_no": "CMP-2026-0004",
        "product_name": "Pantoprazole Gastro-resistant Tablets",
        "batch_lot_number": "PNT25J094",
        "complaint_type": "Labeling Error",
        "description": (
            "Expiry date printed on the outer carton did not match the expiry printed "
            "on the blister foil. Batch numbers matched."
        ),
        "customer_name": "Cipla Distribution, Hyderabad",
        "complaint_source": "Phone",
    },
    {
        "reference_no": "CMP-2026-0005",
        "product_name": "Amoxicillin Capsules",
        "batch_lot_number": "BMX240515",
        "complaint_type": "Packaging Defect",
        "description": (
            "Blister foil found punctured in three strips on receipt at the "
            "distribution centre. No discolouration of the capsules observed."
        ),
        "customer_name": "Apollo Pharmacy, Chennai",
        "complaint_source": "Email",
    },
    {
        "reference_no": "CMP-2026-0006",
        "product_name": "Ibuprofen Tablets",
        "batch_lot_number": "IBU26A221",
        "complaint_type": "Damaged Goods",
        "description": (
            "Consignment arrived with 40 crushed tablets across six strips, "
            "attributed to transit damage. Outer carton visibly deformed."
        ),
        "customer_name": "Wellness Forever, Pune",
        "complaint_source": "Distributor",
    },
]


async def main() -> None:
    factory = get_session_factory()
    created = 0

    async with factory() as session:
        for seed in SEEDS:
            exists = await session.scalar(
                select(Complaint).where(Complaint.reference_no == seed["reference_no"])
            )
            if exists:
                print(f"  {seed['reference_no']} already present, skipping")
                continue

            session.add(
                Complaint(
                    id=uuid.uuid4(),
                    reference_no=seed["reference_no"],
                    session_id="seed",
                    status="closed",
                    product_name=seed["product_name"],
                    batch_lot_number=seed["batch_lot_number"],
                    complaint_type=seed["complaint_type"],
                    description=seed["description"],
                    fields={
                        "product_name": make_field(seed["product_name"], confidence=1.0),
                        "batch_lot_number": make_field(seed["batch_lot_number"], confidence=1.0),
                        "complaint_type": make_field(seed["complaint_type"], confidence=1.0),
                        "customer_name": make_field(seed["customer_name"], confidence=1.0),
                        "complaint_source": make_field(seed["complaint_source"], confidence=1.0),
                        "detailed_complaint_description": make_field(
                            seed["description"], confidence=1.0
                        ),
                    },
                )
            )
            created += 1
            print(f"  {seed['reference_no']} seeded")

        await session.commit()

    await dispose_engine()
    print(f"\n{created} complaint(s) seeded.")


if __name__ == "__main__":
    asyncio.run(main())
