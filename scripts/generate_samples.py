"""Generate realistic pharmaceutical complaint documents for the demo.

    python scripts/generate_samples.py

Writes to `samples/`:
  metformin_api_complaint.pdf  - API complaint from a formulator (Document tool)
  apollo_amoxicillin.eml       - FDF complaint email (Document tool)
  cipla_packaging_defect.txt   - plain-text complaint (format coverage)

The values here are deliberately consistent with the demo script in the README:
the PDF carries batch MFH26C and 25 kg in 1 drum, so the follow-up correction
to CHG260712A / 50 kg in 2 HDPE drums produces a visible, verifiable diff in
the form and the audit trail.
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors

OUT = Path(__file__).resolve().parents[1] / "samples"


# --- PDF: API complaint ------------------------------------------------------

def build_pdf(path: Path) -> None:
    styles = getSampleStyleSheet()
    header = ParagraphStyle(
        "hdr", parent=styles["Heading1"], fontSize=15, alignment=TA_CENTER, spaceAfter=2
    )
    sub = ParagraphStyle(
        "sub", parent=styles["Normal"], fontSize=8.5, alignment=TA_CENTER,
        textColor=colors.grey, spaceAfter=12,
    )
    section = ParagraphStyle(
        "sec", parent=styles["Heading2"], fontSize=10.5, spaceBefore=10, spaceAfter=4
    )
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, leading=13.5)

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
        title="Customer Complaint - Metformin Hydrochloride IP/BP",
    )

    def kv_table(rows: list[tuple[str, str]]) -> Table:
        table = Table([[Paragraph(f"<b>{k}</b>", body), Paragraph(v, body)] for k, v in rows],
                      colWidths=[58 * mm, 105 * mm])
        table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#dddddd")),
            ])
        )
        return table

    story = [
        Paragraph("VERTEX FORMULATIONS PRIVATE LIMITED", header),
        Paragraph(
            "Plot 44-46, Pharma SEZ, Vishakhapatnam 530046, Andhra Pradesh, India<br/>"
            "Quality Assurance Department &nbsp;|&nbsp; qa@vertexformulations.co.in",
            sub,
        ),
        Paragraph("CUSTOMER COMPLAINT NOTIFICATION", section),
        kv_table([
            ("Complaint Reference", "VFPL/QA/CC/2026-0187"),
            ("Date of Complaint", "18 July 2026"),
            ("Raised By", "Sunita Raghavan, Head - Quality Assurance"),
            ("Addressed To", "Head, Quality Assurance, Nandini Life Sciences Ltd."),
            ("Mode of Receipt", "Formal written complaint (courier + email)"),
        ]),
        Paragraph("1. PRODUCT AND BATCH DETAILS", section),
        kv_table([
            ("Material", "Metformin Hydrochloride API"),
            ("Grade / Compendial Standard", "IP/BP"),
            ("Batch / Lot Number", "MFH26C"),
            ("Manufacturing Date", "12 March 2026"),
            ("Retest / Expiry Date", "11 March 2029"),
            ("Quantity Received", "200 kg (8 HDPE drums of 25 kg each)"),
            ("Quantity Affected", "25 kg (1 HDPE drum)"),
            ("Purchase Order", "VFPL/PO/2026/1142"),
            ("Goods Receipt Note", "GRN-2026-04471"),
        ]),
        Paragraph("2. DESCRIPTION OF THE COMPLAINT", section),
        Paragraph(
            "During pre-dispensing verification of the above consignment, our warehouse "
            "quality inspection team observed that the material in one HDPE drum showed a "
            "distinct off-white to pale beige discolouration when compared against the "
            "retained reference standard and against the remaining drums of the same "
            "consignment, which were uniformly white.", body,
        ),
        Spacer(1, 5),
        Paragraph(
            "On closer examination under white light, isolated dark particulate matter was "
            "observed adhering to the inner surface of the polyethylene liner. The liner "
            "seal of the affected drum appeared to have been compromised, showing a partial "
            "tear approximately 40 mm in length along the upper fold. The tamper-evident "
            "seal on the drum lid was intact.", body,
        ),
        Spacer(1, 5),
        Paragraph(
            "The affected drum has been quarantined under hold label QH-2026-0331 pending "
            "your investigation. The material has not been dispensed and no product "
            "manufactured using this consignment has been released.", body,
        ),
        Paragraph("3. ANALYTICAL OBSERVATIONS", section),
        kv_table([
            ("Description (IP)", "Does not comply - off-white to pale beige, reference is white"),
            ("Assay (on dried basis)", "99.2% - complies (98.5-101.0%)"),
            ("Loss on Drying", "0.42% - complies (NMT 0.5%)"),
            ("Related Substances", "Under test, result awaited"),
            ("Foreign / Particulate Matter", "Dark particulate observed - does not comply"),
        ]),
        Paragraph("4. ACTION REQUESTED", section),
        Paragraph(
            "We request a formal investigation into the root cause of the discolouration and "
            "particulate contamination, a written investigation report with your CAPA plan "
            "within 30 calendar days, confirmation of whether other batches from the same "
            "campaign are affected, and replacement of the affected quantity.", body,
        ),
        Spacer(1, 12),
        Paragraph(
            "<i>Sunita Raghavan</i><br/>Head - Quality Assurance<br/>"
            "Vertex Formulations Private Limited<br/>"
            "Tel: +91 891 274 5500 &nbsp;|&nbsp; qa@vertexformulations.co.in", body,
        ),
    ]
    doc.build(story)


# --- EML: FDF complaint ------------------------------------------------------

def build_eml(path: Path) -> None:
    message = EmailMessage()
    message["From"] = "Rajesh Menon <rajesh.menon@apollopharmacy.example>"
    message["To"] = "complaints@nandinilifesciences.example"
    message["Cc"] = "qa.head@apollopharmacy.example"
    message["Subject"] = "Complaint - Discoloured capsules, Amoxicillin 500mg, Batch BMX240602"
    message["Date"] = "Mon, 20 Jul 2026 09:42:11 +0530"
    message.set_content(
        """Dear Quality Assurance Team,

We are writing to formally report a quality complaint concerning stock supplied
to our central distribution centre in Chennai.

Product          : Amoxicillin Capsules IP 500 mg
Batch Number     : BMX240602
Manufacturing Date: 02 June 2026
Expiry Date      : 01 June 2028
Quantity Supplied: 12,000 capsules (400 strips of 30)
Quantity Affected: 48 capsules (2 strips)
Invoice          : APL/INV/2026/88213

Three separate retail outlets have returned strips from this batch reporting
that the capsule bodies show an uneven pink to light brown discolouration.
The affected capsules were compared against strips from batch BMX240515,
which appear normal. Two of the returned strips also show slight softening of
the capsule shell, suggesting possible moisture ingress. The blister foil did
not appear punctured on visual inspection.

No patient has reported an adverse reaction to date. We have placed the
remaining stock of this batch on hold across our network pending your response.

We request your investigation report and confirmation on whether a market
recall of this batch is being considered. Please also advise on replacement of
the affected quantity.

Regards,

Rajesh Menon
Senior Manager - Quality & Compliance
Apollo Pharmacy, Chennai
+91 44 2829 3400
"""
    )
    path.write_bytes(message.as_bytes())


# --- TXT: packaging defect ---------------------------------------------------

def build_txt(path: Path) -> None:
    path.write_text(
        """COMPLAINT INTAKE FORM - TELEPHONE RECORD

Received by   : N. Fernandes, Complaint Coordinator
Date received : 22 July 2026, 14:20 IST
Source        : Telephone
Caller        : Dr. Anand Krishnan, Chief Pharmacist
Organisation  : Cipla Distribution, Hyderabad

PRODUCT
  Name        : Pantoprazole Gastro-resistant Tablets IP
  Strength    : 40 mg
  Batch       : PNT26D118
  Mfg date    : 05 April 2026
  Expiry      : 04 April 2028
  Qty affected: 120 tablets (4 boxes)

COMPLAINT
  Caller reports that the outer carton for four boxes carries a printed expiry
  date of 04/2028 while the blister foil inside the same cartons is printed
  04/2027. The batch number on carton and foil match. No physical defect was
  observed in the tablets themselves.

  Caller states the discrepancy was noticed during routine goods-in checks and
  that the affected cartons have been segregated. He has asked for urgent
  clarification as the stock is otherwise ready for dispatch to retail.

INITIAL REMARKS
  Potential labelling/artwork control issue. Escalated to QA the same day.
""",
        encoding="utf-8",
    )


def main() -> None:
    OUT.mkdir(exist_ok=True)
    targets = [
        (OUT / "metformin_api_complaint.pdf", build_pdf),
        (OUT / "apollo_amoxicillin.eml", build_eml),
        (OUT / "cipla_packaging_defect.txt", build_txt),
    ]
    for path, builder in targets:
        builder(path)
        print(f"  {path.name:34} {path.stat().st_size:>7,} bytes")
    print(f"\nWrote {len(targets)} sample(s) to {OUT}")


if __name__ == "__main__":
    main()
