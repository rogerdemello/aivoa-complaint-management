"""Drive the real UI in a browser and assert the demo actually works.

    .venv/Scripts/python.exe scripts/verify_ui.py

Requires both servers running. Screenshots land in `artifacts/`, which is handy
for checking the layout without recording anything.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.async_api import async_playwright  # noqa: E402

UI = "http://localhost:5173"
SHOTS = Path(__file__).resolve().parents[2] / "artifacts"
TURN_TIMEOUT = 180_000

LOG_PROMPT = "Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules 500mg."
EDIT_PROMPT = "Sorry, the batch number is BMX240602 and the affected quantity is 48 capsules."

failures: list[str] = []


def check(condition: bool, label: str) -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        failures.append(label)


async def send(page, text: str) -> None:
    """Send a message and wait for the assistant's reply to land.

    Waiting on the Send button is wrong: it is correctly disabled whenever the
    draft is empty, and sending clears the draft. So count assistant bubbles
    instead - the turn is done when a new one appears.
    """
    before = await page.locator(".msg.assistant").count()

    await page.fill("textarea[placeholder*='Describe the complaint']", text)
    await page.click("button[aria-label='Send']")

    deadline = TURN_TIMEOUT
    step = 500
    while deadline > 0:
        # The streaming placeholder is also .msg.assistant, so require a real
        # reply: one more bubble than before, with the spinner gone.
        if (
            await page.locator(".msg.assistant").count() > before
            and not await page.locator(".messages .spinner").count()
        ):
            break
        await page.wait_for_timeout(step)
        deadline -= step
    else:
        raise TimeoutError(f"no assistant reply within {TURN_TIMEOUT}ms")

    await page.wait_for_timeout(800)


async def value_of(page, field: str) -> str:
    return await page.input_value(f"#{field}")


async def main() -> None:
    SHOTS.mkdir(exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1500, "height": 1150})

        console_errors: list[str] = []
        page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        print("\n1. Load")
        await page.goto(UI, wait_until="networkidle")
        await page.wait_for_selector("text=Log Customer Complaint", timeout=30_000)
        check(await page.is_visible("text=AIVOA Copilot"), "Copilot panel rendered")
        check(await page.is_visible("text=Session active"), "session started")
        check(
            await page.is_visible("text=/model.*substituted|models live/i"),
            "model badge shown",
        )
        await page.screenshot(path=SHOTS / "01-initial.png", full_page=True)

        print("\n2. Form is not manually editable")
        # The strongest check available: ask the browser to type into it.
        try:
            await page.fill("#product_name", "TYPED BY HAND", timeout=4000)
        except Exception:
            pass
        check(await value_of(page, "product_name") == "", "typing into the form does nothing")
        check(
            await page.get_attribute("#product_name", "readonly") is not None,
            "inputs carry readOnly",
        )

        print(f"\n3. Log Complaint  -  {LOG_PROMPT[:52]}...")
        await send(page, LOG_PROMPT)
        product = await value_of(page, "product_name")
        customer = await value_of(page, "customer_name")
        print(f"     product_name  = {product!r}")
        print(f"     customer_name = {customer!r}")
        check("Amoxicillin" in product, "product extracted into the form")
        check(bool(customer), "customer extracted into the form")
        check(await page.is_visible("text=AI Copilot Risk Assessment"), "risk panel rendered")
        check(await page.is_visible("text=LangGraph Execution"), "agent trace rendered")
        check(await page.is_visible("text=Complaint Completeness"), "completeness rendered")
        await page.screenshot(path=SHOTS / "02-logged.png", full_page=True)

        before = {
            f: await value_of(page, f)
            for f in ("product_name", "customer_name", "product_strength_grade",
                      "complaint_type", "detailed_complaint_description")
        }

        print("\n4. Evidence tooltip")
        triggers = page.locator(".evidence-trigger")
        if await triggers.count():
            await triggers.first.hover()
            await page.wait_for_timeout(400)
            check(await page.is_visible(".evidence-tip"), "evidence tooltip appears on hover")
            await page.screenshot(path=SHOTS / "03-evidence.png")
        else:
            check(False, "evidence trigger present")

        print(f"\n5. Edit Complaint  -  {EDIT_PROMPT[:52]}...")
        await send(page, EDIT_PROMPT)
        batch = await value_of(page, "batch_lot_number")
        qty = await value_of(page, "quantity_affected")
        print(f"     batch_lot_number  = {batch!r}")
        print(f"     quantity_affected = {qty!r}")
        check(batch == "BMX240602", "batch number updated")
        check("48" in qty, "quantity updated")

        after = {f: await value_of(page, f) for f in before}
        lost = [f for f, v in before.items() if after[f] != v]
        check(not lost, f"prior fields preserved (altered: {lost or 'none'})")
        await page.screenshot(path=SHOTS / "04-edited.png", full_page=True)

        print("\n6. Audit trail")
        await page.click("button:has-text('Audit Trail')")
        await page.wait_for_selector(".audit-row", timeout=30_000)
        rows = await page.locator(".audit-row").count()
        print(f"     {rows} audit row(s)")
        check(rows >= 5, "audit trail populated")
        check(await page.is_visible("text=21 CFR Part 11"), "Part 11 attribution shown")
        await page.screenshot(path=SHOTS / "05-audit.png", full_page=True)

        print("\n7. Document Extraction (fresh session, real dropzone)")
        pdf = Path(__file__).resolve().parents[2] / "samples" / "metformin_api_complaint.pdf"
        await page.reload(wait_until="networkidle")
        await page.wait_for_selector("text=Log Customer Complaint", timeout=30_000)

        before_upload = await page.locator(".msg.assistant").count()
        # The file input is visually hidden behind the dropzone; Playwright can
        # still set files on it, which is exactly what clicking it would do.
        await page.set_input_files("input[type=file]", str(pdf))

        deadline = TURN_TIMEOUT
        while deadline > 0:
            if (
                await page.locator(".msg.assistant").count() > before_upload
                and not await page.locator(".messages .spinner").count()
            ):
                break
            await page.wait_for_timeout(500)
            deadline -= 500
        await page.wait_for_timeout(800)

        doc_product = await value_of(page, "product_name")
        doc_grade = await value_of(page, "product_strength_grade")
        doc_batch = await value_of(page, "batch_lot_number")
        print(f"     product_name           = {doc_product!r}")
        print(f"     product_strength_grade = {doc_grade!r}")
        print(f"     batch_lot_number       = {doc_batch!r}")
        check("Metformin" in doc_product, "API product extracted from the PDF")
        check("IP" in doc_grade.upper(), "compendial grade extracted from the PDF")
        check(bool(doc_batch), "batch extracted from the PDF")
        check(
            await page.locator(".src-badge.document").count() > 0,
            "fields attributed to the document source",
        )
        await page.screenshot(path=SHOTS / "06-document.png", full_page=True)

        print("\n8. Console")
        real = [e for e in console_errors if "favicon" not in e.lower()]
        check(not real, f"no console errors ({real[:2] if real else 'clean'})")

        await browser.close()

    print(f"\n{'=' * 62}")
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL UI CHECKS PASSED")
    print(f"screenshots: {SHOTS}")


if __name__ == "__main__":
    asyncio.run(main())
