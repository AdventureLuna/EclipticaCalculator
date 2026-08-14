from pathlib import Path
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
URL = (ROOT / "index.html").as_uri()
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def upgrade(page, upgrade_id, count=1):
    page.evaluate("([id, count]) => { counts[id] = count; render(); }", [upgrade_id, count])


def source_rate(page, source_id):
    return page.locator(f'[data-calculation-key="damage:{source_id}:rate"]').get_attribute("data-exact-value")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=EDGE, headless=True)
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL)

    # Thaumaturge: splitshot multiplies only Foul Pustule projectiles. Flaming Spirit
    # follows primary activations once and contributes Burning on the same shared path.
    upgrade(page, "Thaumaturge_Splitshot")
    upgrade(page, "Flaming_Spirit")
    upgrade(page, "Charged_Strike")
    upgrade(page, "Pocket_Abacus")
    assert source_rate(page, "thaumaturge-foul-pustule-projectile") == "1.5"
    assert source_rate(page, "thaumaturge-flaming-spirit") == "0.75"
    assert page.locator('[data-status="burning"]').count() == 1
    assert page.locator('[data-status="poisoned"]').count() == 1
    assert page.locator('[data-calculation-key="crit:rate"]').inner_text() == "0.45"
    assert source_rate(page, "thaumaturge-charged-strike") == "0.45"

    # Switching classes must replace—not merely recolor—the configuration and table.
    page.select_option("#class-select", "Gunmancer")
    assert page.locator("#calculation-content").inner_text().find("Gunmancer") >= 0
    assert page.locator("#calculation-content").inner_text().find("Foul Pustule") < 0
    assert page.locator("#configuration-content").inner_text().find("VA-11 Blast Cannon") >= 0

    # Shared upgrades remain shared for Gunmancer, including their status sources.
    assert page.locator('[data-calculation-source-upgrade="Flaming_Spirit"]').count() > 0
    assert page.locator('[data-status="burning"]').count() == 1

    page.select_option("#class-select", "Twinmage")
    assert page.locator("#calculation-content").inner_text().find("Twinmage") >= 0
    assert page.locator("#configuration-content").inner_text().find("Primary element") >= 0
    assert page.locator('[data-calculation-source-upgrade="Flaming_Spirit"]').count() > 0

    assert not errors, errors
    browser.close()

print("Cross-class browser smoke tests passed.")
