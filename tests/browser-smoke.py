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

    # Shared engine: volley damage is per activation, while crit/status chances
    # still use every hit in the volley.
    volley = page.evaluate("""() => {
      const result = EclipticaCalculationEngine.calculate({
        criticalChance: .2,
        criticalDamageMultiplier: 1.5,
        overallMultiplier: 1,
        elementalMultipliers: { physical: 1, fire: 1 },
        statusDefinitions: { burning: { id: 'burning', name: 'Burning', baseDamage: 25, damageStat: 'fireDamage', tickInterval: .5 } },
        stickyStacks: 0,
        sources: [{ id: 'volley', name: 'Volley', element: 'physical', baseDamage: 10, canCrit: true, activationRate: .2, instancesPerActivation: 5, projectiles: 5, statuses: [{ id: 'burning', chance: .1 }] }]
      });
      const source = result.attackSources[0];
      return {
        nonCrit: source.damage.nonCriticalDamage,
        crit: source.damage.criticalDamage,
        averagePerHit: source.damage.averageDamagePerHit,
        average: source.damage.averageDamage,
        activationRate: source.damage.activationRate,
        hitsPerSecond: source.damage.hitsPerSecond,
        dps: source.damage.dps,
        critsPerSecond: result.criticalHitsPerSecond,
        applicationsPerSecond: result.statuses[0].applicationsPerSecond
      };
    }""")
    assert volley == {"nonCrit": 10, "crit": 15, "averagePerHit": 11, "average": 55, "activationRate": .2, "hitsPerSecond": 1, "dps": 11, "critsPerSecond": .2, "applicationsPerSecond": .1}

    # Thaumaturge: splitshot multiplies only Foul Pustule projectiles. Flaming Spirit
    # follows primary activations once and contributes Burning on the same shared path.
    upgrade(page, "Thaumaturge_Splitshot")
    upgrade(page, "Flaming_Spirit")
    upgrade(page, "Charged_Strike")
    upgrade(page, "Pocket_Abacus")
    assert source_rate(page, "thaumaturge-foul-pustule-projectile") == "0.75"
    assert source_rate(page, "thaumaturge-flaming-spirit") == "0.75"
    foul_key = "thaumaturge-foul-pustule-projectile"
    assert page.locator(f'[data-calculation-key="damage:{foul_key}:overall"]').inner_text().startswith("x")
    assert page.locator(f'[data-calculation-key="damage:{foul_key}:elemental"]').inner_text().startswith("x")
    assert page.locator(f'[data-calculation-key="damage:{foul_key}:crit"]').inner_text().startswith("x")
    assert not page.locator(f'[data-calculation-key="damage:{foul_key}:projectiles"]').inner_text().startswith("x")
    assert not page.locator(f'[data-calculation-key="damage:{foul_key}:rate"]').inner_text().startswith("x")
    foul_rate_formula = page.locator(f'[data-calculation-key="damage:{foul_key}:rate"]').get_attribute("data-calculation-formula")
    assert "0.75 base activations/s" in foul_rate_formula
    assert "x1.00 Attack Speed" in foul_rate_formula
    assert "instances/activation" not in foul_rate_formula
    foul_average_formula = page.locator(f'[data-calculation-key="damage:{foul_key}:average"]').get_attribute("data-calculation-formula")
    assert "Non-crit per hit:" in foul_average_formula
    assert "Crit per hit:" in foul_average_formula
    assert "× 2 hits" in foul_average_formula
    spirit_rate_formula = page.locator('[data-calculation-key="damage:thaumaturge-flaming-spirit:rate"]').get_attribute("data-calculation-formula")
    assert "0.75 base activations/s" in spirit_rate_formula
    assert "instances/activation" not in spirit_rate_formula
    assert page.locator('[data-status="burning"]').count() == 1
    assert page.locator('[data-status="poisoned"]').count() == 1
    assert page.locator('[data-calculation-key="crit:rate"]').inner_text() == "0.45"
    assert source_rate(page, "thaumaturge-charged-strike") == "0.45"

    # Switching classes must replace—not merely recolor—the configuration and table.
    page.select_option("#class-select", "Gunmancer")
    assert page.locator("#calculation-content").inner_text().find("Gunmancer") >= 0
    assert page.locator("#calculation-content").inner_text().find("Foul Pustule") < 0
    assert page.locator("#configuration-content").inner_text().find("VA-11 Blast Cannon") >= 0
    configuration_text = page.locator("#configuration-content").inner_text()
    assert "Gunmancer calculation setup" not in configuration_text
    assert "Sources:" not in configuration_text
    page.locator('[data-tab="configuration"]').click()
    assert page.locator('[data-gunmancer-picker="primary"] input[name="gunmancer-dps"]').is_checked()
    assert not page.locator('[data-gunmancer-picker="secondary"] input[name="gunmancer-dps"]').is_checked()
    page.locator('[data-gunmancer-picker="secondary"] input[name="gunmancer-dps"]').check()
    assert not page.locator('[data-gunmancer-picker="primary"] input[name="gunmancer-dps"]').is_checked()
    assert page.locator('[data-gunmancer-picker="secondary"] input[name="gunmancer-dps"]').is_checked()
    assert page.locator('[data-calculation-key^="source:gunmancer-photon"]').count() > 0
    assert page.locator('[data-calculation-source-upgrade="Flaming_Spirit"]').count() == 0

    # Normal and charged selections are independent. Charged projectile volleys
    # use Utility Cooldown Rate for activation rate and projectile count for hits.
    page.locator('input[name="gunmancer-dps"][value="primary"]').check()
    assert page.locator('[data-calculation-source-upgrade="Flaming_Spirit"]').count() > 0
    page.locator('input[name="gunmancer-airblast"][value="secondary"]').check()
    charged_photon = "gunmancer-airblast-secondary-photon-projectile"
    assert page.locator('[data-calculation-key="source:gunmancer-va11-beam"]').count() == 1
    assert page.locator(f'[data-calculation-key="source:{charged_photon}"]').count() == 1
    assert source_rate(page, charged_photon) == str(1 / 12)
    assert page.locator(f'[data-calculation-key="damage:{charged_photon}:projectiles"]').inner_text() == "3"
    charged_rate_formula = page.locator(f'[data-calculation-key="damage:{charged_photon}:rate"]').get_attribute("data-calculation-formula")
    assert "Utility Cooldown Rate" in charged_rate_formula
    assert page.evaluate("isUpgradeConditionallyAvailable(upgradeIndex.get('Gunmancer_Proficiency_Photon'))")
    assert not page.evaluate("isUpgradeConditionallyAvailable(upgradeIndex.get('Gunmancer_Proficiency_Firebomb'))")
    assert not page.evaluate("isUpgradeConditionallyAvailable(upgradeIndex.get('Gunmancer_Proficiency_Antimatter'))")
    assert "conditional-unavailable" not in page.locator('[data-id="Gunmancer_Proficiency_Photon"]').get_attribute("class")
    assert "conditional-unavailable" in page.locator('[data-id="Gunmancer_Proficiency_Firebomb"]').get_attribute("class")
    assert "conditional-unavailable" in page.locator('[data-id="Gunmancer_Proficiency_Antimatter"]').get_attribute("class")
    charged_model = page.evaluate("window.EclipticaBuildForge.buildUnifiedCalculationModel()")
    charged_source = next(source for source in charged_model["attackSources"] if source["id"] == charged_photon)
    assert charged_source["damage"]["hitsPerSecond"] == 3 / 12
    assert any(source["sourceId"] == charged_photon for status in charged_model["statuses"] if status["id"] == "weakened" for source in status["sources"])
    assert page.locator('[data-calculation-key="paralyzed:stacks"]').get_attribute("data-exact-value") == "8"
    assert page.locator('[data-calculation-key="paralyzed:duration"]').get_attribute("data-exact-value") == "2.4"
    assert page.locator('[data-calculation-key="weakened:stacks"]').get_attribute("data-exact-value") == "10"
    assert page.locator('[data-calculation-key="weakened:duration"]').get_attribute("data-exact-value") == "8"
    paralyzed_breakdown = page.locator('[data-calculation-key="paralyzed:interval"]').get_attribute("data-application-breakdown")
    assert "10× boss penalty" in paralyzed_breakdown
    weakened_breakdown = page.locator('[data-calculation-key="weakened:interval"]').get_attribute("data-application-breakdown")
    assert "2× boss penalty" in weakened_breakdown

    upgrade(page, "Gunmancer_Proficiency_Photon")
    assert page.locator(f'[data-calculation-key="damage:{charged_photon}:projectiles"]').inner_text() == "5"
    page.locator('input[name="gunmancer-dps"][value="secondary"]').check()
    assert page.locator('[data-calculation-key="damage:gunmancer-photon-projectile:projectiles"]').inner_text() == "1"
    page.locator('input[name="gunmancer-dps"][value="primary"]').check()
    upgrade(page, "Quick_Breath")
    assert abs(float(source_rate(page, charged_photon)) - 1.1 / 12) < 1e-12

    page.evaluate("buildOptions.gunmancerSecondary = 'antimatter'; saveBuildOptions(); render();")
    assert not page.evaluate("isUpgradeConditionallyAvailable(upgradeIndex.get('Gunmancer_Proficiency_Photon'))")
    assert page.evaluate("isUpgradeConditionallyAvailable(upgradeIndex.get('Gunmancer_Proficiency_Antimatter'))")
    upgrade(page, "Gunmancer_Proficiency_Antimatter")
    charged_antimatter = "gunmancer-airblast-secondary-antimatter-projectile"
    assert page.locator(f'[data-calculation-key="damage:{charged_antimatter}:projectiles"]').inner_text() == "4"
    page.locator('input[name="gunmancer-dps"][value="secondary"]').check()
    assert page.locator('[data-calculation-key="damage:gunmancer-antimatter-projectile:projectiles"]').inner_text() == "5"
    page.locator('input[name="gunmancer-dps"][value="primary"]').check()

    page.evaluate("buildOptions.gunmancerSecondary = 'firebomb'; counts.Gunmancer_Proficiency_Firebomb = 3; saveBuildOptions(); render();")
    charged_fire = page.evaluate("window.EclipticaBuildForge.buildUnifiedCalculationModel().attackSources.filter(source => source.id.startsWith('gunmancer-airblast-secondary-firebomb'))")
    assert len(charged_fire) == 2
    assert all(source["hitsPerActivation"] == 1 for source in charged_fire)

    page.locator('[data-tab="upgrades"]').click()
    page.locator("#dps-ranking-toggle").click()
    page.locator(".dps-ranking-loading").wait_for(state="detached", timeout=15000)
    assert page.locator('[data-dps-upgrade-id="Gunmancer_Proficiency_Firebomb"]').count() == 1
    assert page.locator('[data-dps-upgrade-id="Gunmancer_Proficiency_Photon"]').count() == 0
    assert page.locator('[data-dps-upgrade-id="Gunmancer_Proficiency_Antimatter"]').count() == 0
    page.locator("#dps-ranking-toggle").click()

    # Shared upgrades remain shared for Gunmancer, including their status sources.
    assert page.locator('[data-calculation-source-upgrade="Flaming_Spirit"]').count() > 0
    assert page.locator('[data-status="burning"]').count() == 1

    page.select_option("#class-select", "Twinmage")
    assert page.locator("#calculation-content").inner_text().find("Twinmage") >= 0
    twinmage_configuration_text = page.locator("#configuration-content").inner_text()
    assert "PRIMARY ELEMENT" in twinmage_configuration_text.upper(), twinmage_configuration_text
    assert page.locator('[data-calculation-source-upgrade="Flaming_Spirit"]').count() > 0
    twinmage_rate_formula = page.locator('[data-calculation-key="damage:twinmage-hand-0:rate"]').get_attribute("data-calculation-formula")
    assert "base activations/s" in twinmage_rate_formula
    assert "Attack Speed" in twinmage_rate_formula
    assert "Hand Attack Speed" in twinmage_rate_formula

    page.evaluate("buildOptions.twinmagePrimary = 'frost'; buildOptions.twinmageSecondary = 'shadow'; saveBuildOptions(); render();")
    assert page.locator('[data-calculation-key="frozen:stacks"]').get_attribute("data-exact-value") == "8"
    assert page.locator('[data-calculation-key="frozen:duration"]').get_attribute("data-exact-value") == "4.8"
    assert page.locator('[data-calculation-key="breached:stacks"]').get_attribute("data-exact-value") == "10"
    assert page.locator('[data-calculation-key="breached:duration"]').get_attribute("data-exact-value") == "7"
    assert page.locator('[data-calculation-key="frozen:uptime"]').get_attribute("data-exact-value") != "unknown"
    assert page.locator('[data-calculation-key="breached:uptime"]').get_attribute("data-exact-value") != "unknown"

    # Build reset preserves class configuration; the Configuration reset button
    # restores only the active class's configuration defaults.
    page.evaluate("buildOptions.twinmagePrimaryDamage = false; counts.Quick_Breath = 1; saveBuildOptions(); saveCounts(); render();")
    page.locator("#reset-build").click()
    assert page.evaluate("rawCount('Quick_Breath')") == 0
    assert page.evaluate("buildOptions.twinmagePrimary") == "frost"
    assert page.evaluate("buildOptions.twinmageSecondary") == "shadow"
    assert not page.evaluate("buildOptions.twinmagePrimaryDamage")
    assert page.evaluate("buildOptions.twinmageSecondaryDamage")
    page.locator('[data-tab="configuration"]').click()
    page.locator("#reset-configuration").click()
    assert page.evaluate("buildOptions.twinmagePrimary") == "fire"
    assert page.evaluate("buildOptions.twinmageSecondary") == "lightning"
    assert page.evaluate("buildOptions.twinmagePrimaryDamage")
    assert page.evaluate("buildOptions.twinmageSecondaryDamage")

    assert not errors, errors
    browser.close()

print("Cross-class browser smoke tests passed.")
