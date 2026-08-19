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
    assert page.title() == "AdventureLuna's Ecliptica Build Forge"
    assert page.locator("h1").inner_text() == "AdventureLuna's Ecliptica Build Forge"
    assert "Left-click to add an artifact" not in page.locator("#tab-artifacts").inner_text()
    assert page.locator("#combined-dps-summary").is_visible()
    initial_combined_dps = page.evaluate("EclipticaBuildForge.buildUnifiedCalculationModel().combinedTotalDps")
    assert float(page.locator("#combined-dps-summary").get_attribute("data-exact-value")) == initial_combined_dps

    codec_checks = page.evaluate("""() => {
      const base = ShareBuildCodec.encodeBuild({ version: 3, characterId: 1, upgrades: [], configuration: {} });
      const baseBytes = ShareBuildCodec.base64UrlToBytes(base);
      const configured = ShareBuildCodec.encodeBuild({
        version: 3, characterId: 1, upgrades: [],
        configuration: { twinmage: { primary: 5, secondary: 1, primaryDamage: true, secondaryDamage: false } }
      });
      const configuredBytes = ShareBuildCodec.base64UrlToBytes(configured);
      const payload = configuredBytes[configuredBytes.length - 1];
      const makeCode = bytes => ShareBuildCodec.bytesToBase64Url(Uint8Array.from(bytes));
      const unknown = ShareBuildCodec.decodeBuild(makeCode([
        ...configuredBytes.slice(0, -4), 6, 2, 1, payload, 99, 1, 7
      ]));
      const duplicate = ShareBuildCodec.decodeBuild(makeCode([
        ...configuredBytes.slice(0, -4), 6, 2, 1, payload, 2, 1, 0
      ]));
      const rejected = [];
      for (const bytes of [
        [...baseBytes.slice(0, -1), 2, 2, 1],
        [...baseBytes.slice(0, -1), 3, 2, 1, 0],
        [...baseBytes, 0]
      ]) {
        try { ShareBuildCodec.decodeBuild(makeCode(bytes)); rejected.push(false); }
        catch { rejected.push(true); }
      }
      const v2 = ShareBuildCodec.encodeBuild({ version: 2, characterId: 1, upgrades: [] });
      const spellsword = ShareBuildCodec.decodeBuild(ShareBuildCodec.encodeBuild({
        version: 3, characterId: 0, upgrades: [],
        configuration: { spellsword: { damageGroup: 1, chargeMode: 3, customChargeMs: 2375, bleedChance: 27.5, whirlwindHits: 12 } }
      }));
      return {
        unknownConfiguration: unknown.configuration,
        unknownWarning: unknown.warnings[0],
        duplicateConfiguration: duplicate.configuration,
        duplicateWarning: duplicate.warnings[0],
        rejected,
        defaultGrowth: baseBytes.length - ShareBuildCodec.base64UrlToBytes(v2).length,
        configuredGrowth: configured.length - base.length,
        spellswordConfiguration: spellsword.configuration.spellsword
      };
    }""")
    assert codec_checks["unknownConfiguration"] == {"twinmage": {"primary": 5, "secondary": 1, "primaryDamage": True, "secondaryDamage": False}}
    assert "unknown configuration field 99" in codec_checks["unknownWarning"]
    assert codec_checks["duplicateConfiguration"] == codec_checks["unknownConfiguration"]
    assert "duplicate configuration field 2" in codec_checks["duplicateWarning"]
    assert codec_checks["rejected"] == [True, True, True]
    assert codec_checks["defaultGrowth"] == 1
    assert codec_checks["configuredGrowth"] <= 6
    assert codec_checks["spellswordConfiguration"] == {"damageGroup": 1, "chargeMode": 3, "customChargeMs": 2375, "bleedChance": 27.5, "whirlwindHits": 12}

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

    # Health Regeneration keeps its visible percentage while showing derived
    # HP/s beneath it. Big and Lazy is a separate hidden multiplier.
    regeneration_row = page.locator('[data-stat="healthRegeneration"]')
    assert regeneration_row.locator('.value').inner_text().splitlines() == ["100%", "(0.5 hp/s)"]
    assert regeneration_row.locator('[data-health-regeneration-rate]').get_attribute('data-health-regeneration-rate') == "0.5"
    upgrade(page, "Vitality")
    assert regeneration_row.locator('.value').inner_text().splitlines() == ["180%+80", "(0.9 hp/s)"]
    upgrade(page, "Big_and_Lazy")
    assert regeneration_row.locator('.value').inner_text().splitlines() == ["180%+80", "(2.7 hp/s)"]
    regeneration_row.hover()
    regeneration_tooltip = page.locator('#stat-tooltip').inner_text()
    assert "Base regeneration: 0.5 hp/s" in regeneration_tooltip
    assert "100% + 200% = 300% = ×3" in regeneration_tooltip
    assert "0.5 × 1.8 × 3 = 2.7 hp/s" in regeneration_tooltip
    upgrade(page, "Big_and_Lazy", 2)
    assert regeneration_row.locator('[data-health-regeneration-rate]').inner_text() == "(3.15 hp/s)"
    regeneration_row.hover()
    assert "100% + 200% + (1 × 50%) = 350% = ×3.5" in page.locator('#stat-tooltip').inner_text()
    upgrade(page, "Vitality", 0)
    upgrade(page, "Big_and_Lazy", 0)

    # Spellsword switches exclusively between its primary and charged secondary.
    # Whirlwind is represented as a multi-hit full-charge source.
    page.select_option("#class-select", "Spellsword")
    page.locator('[data-tab="configuration"]').click()
    assert page.locator('input[name="spellsword-dps"][value="primary"]').is_checked()
    assert not page.locator('input[name="spellsword-dps"][value="secondary"]').is_checked()
    assert page.locator('#configuration-content img').evaluate_all("images => images.every(image => image.complete && image.naturalWidth > 0)")
    assert page.locator('#configuration-content p').count() == 0
    spellsword_model = page.evaluate("EclipticaBuildForge.buildUnifiedCalculationModel()")
    primary = next(source for source in spellsword_model["attackSources"] if source["id"] == "spellsword-telekinetic-strike")
    assert primary["baseDamage"] == 65
    assert primary["damage"]["activationRate"] == 1
    assert primary["statuses"][0]["id"] == "bleeding"
    assert primary["statuses"][0]["chance"] == .1
    upgrade(page, "Spellsword_Shieldbreaker")
    assert page.locator('[data-calculation-key="damage:spellsword-telekinetic-strike:base"]').get_attribute("data-exact-value") == "82"

    page.locator('label.spellsword-attack-option', has_text="Piercing Strike").click()
    assert not page.locator('input[name="spellsword-dps"][value="primary"]').is_checked()
    assert page.locator('input[name="spellsword-charge-mode"][value="dps"]').is_checked()
    assert page.locator('.spellsword-compact-input', has_text="Cooldown").inner_text() == "Cooldown\n1.5s"
    piercing = page.evaluate("EclipticaBuildForge.buildUnifiedCalculationModel().attackSources.find(source => source.id === 'spellsword-piercing-strike')")
    assert piercing["baseDamage"] == 108
    assert abs(piercing["damage"]["activationRate"] - .5) < 1e-12
    assert piercing["canCrit"] is True
    assert abs(piercing["statuses"][0]["chance"] - (.5 * 108 / 170)) < 1e-12
    assert page.locator('.spellsword-compact-input', has_text="Bleeding chance").inner_text() == "Bleeding chance\n31.8%"
    assert page.evaluate("[SPELLSWORD_SECONDARY.minimumCharge, SPELLSWORD_SECONDARY.optimalCharge, SPELLSWORD_SECONDARY.maximumCharge]") == [.17, .5, 5.075]
    assert page.evaluate("[spellswordPiercingDamage(.17), spellswordPiercingDamage(5.075)]") == [87, 170]

    upgrade(page, "Spellsword_Whirlwind")
    page.locator("label.spellsword-charge-option", has_text="Full").click()
    whirlwind_hits = page.locator('input[name="spellsword-whirlwind-hits"]')
    whirlwind_hits.fill("4")
    whirlwind_hits.blur()
    spellsword_model = page.evaluate("EclipticaBuildForge.buildUnifiedCalculationModel()")
    spellsword_sources = {source["id"]: source for source in spellsword_model["attackSources"]}
    piercing = spellsword_sources["spellsword-piercing-strike"]
    whirlwind = spellsword_sources["spellsword-whirlwind"]
    expected_spellsword_rate = 1 / (5.075 * 1.3 + 1.5)
    assert piercing["baseDamage"] == 170
    assert abs(piercing["damage"]["activationRate"] - expected_spellsword_rate) < 1e-12
    assert whirlwind["baseDamage"] == 11
    assert whirlwind["canCrit"] is False
    assert whirlwind["hitsPerActivation"] == 4
    assert whirlwind["damage"]["averageDamage"] == 44
    assert whirlwind["damage"]["activationRate"] == piercing["damage"]["activationRate"]
    assert whirlwind["statuses"][0]["chance"] == .5
    assert abs(spellsword_model["criticalHitEligibleRate"] - piercing["damage"]["hitsPerSecond"]) < 1e-12
    assert page.locator('th.damage-label', has_text="Hits / Activation").count() == 1

    spellsword_code = page.evaluate("new URLSearchParams(location.hash.slice(1)).get('b')")
    shared_spellsword = page.evaluate("code => decodeBuild(code).configuration.spellsword", spellsword_code)
    assert shared_spellsword == {"damageGroup": 1, "chargeMode": 2, "customChargeMs": 500, "bleedChance": None, "whirlwindHits": 4}
    page.locator("#reset-configuration").click()
    assert page.evaluate("buildOptions.spellswordDamageGroup") == "primary"
    page.goto(f"{URL}#b={spellsword_code}")
    page.reload()
    page.locator('[data-tab="configuration"]').click()
    assert page.locator('input[name="spellsword-dps"][value="secondary"]').is_checked()
    assert page.locator('input[name="spellsword-charge-mode"][value="full"]').is_checked()
    assert page.locator('input[name="spellsword-whirlwind-hits"]').input_value() == "4"
    page.locator("#reset-build").click()
    page.select_option("#class-select", "Thaumaturge")

    # Thaumaturge: splitshot multiplies only Foul Pustule projectiles. Flaming Spirit
    # follows primary activations once and contributes Burning on the same shared path.
    upgrade(page, "Thaumaturge_Splitshot")
    upgrade(page, "Flaming_Spirit")
    upgrade(page, "Charged_Strike")
    upgrade(page, "Pocket_Abacus")
    assert source_rate(page, "thaumaturge-foul-pustule-projectile") == "0.75"
    assert source_rate(page, "thaumaturge-flaming-spirit") == "0.75"
    assert page.locator('[data-calculation-key="damage:thaumaturge-flaming-spirit:base"]').get_attribute("data-exact-value") == "16"
    upgrade(page, "Flaming_Spirit", 2)
    assert page.locator('[data-calculation-key="damage:thaumaturge-flaming-spirit:base"]').get_attribute("data-exact-value") == "24"
    upgrade(page, "Flaming_Spirit")
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

    # Excluded columns stay visible but no longer contribute to damage, crits,
    # status applications, or downstream on-crit sources.
    page.locator('[data-tab="calculations"]').click()
    spirit_toggle = page.locator('[data-source-exclusion="thaumaturge-flaming-spirit"]')
    assert page.locator('.source-inclusion-toggle').count() == 0
    assert spirit_toggle.get_attribute('class') == 'source-column-toggle'
    assert "✓" not in spirit_toggle.inner_text()
    combined_before = float(page.locator('[data-calculation-key="damage:combined:total-dps"]').get_attribute("data-exact-value"))
    assert float(page.locator("#combined-dps-summary").get_attribute("data-exact-value")) == combined_before
    spirit_total = float(page.locator('[data-calculation-key="damage:thaumaturge-flaming-spirit:total-dps"]').get_attribute("data-exact-value"))
    crit_rate_before = float(page.locator('[data-calculation-key="crit:rate"]').inner_text())
    charged_rate_before = float(page.locator('[data-calculation-key="damage:thaumaturge-charged-strike:rate"]').get_attribute("data-exact-value"))
    spirit_toggle.click()
    combined_after = float(page.locator('[data-calculation-key="damage:combined:total-dps"]').get_attribute("data-exact-value"))
    assert float(page.locator("#combined-dps-summary").get_attribute("data-exact-value")) == combined_after
    assert combined_after < combined_before - spirit_total
    assert page.locator('th.source-excluded [data-source-exclusion="thaumaturge-flaming-spirit"]').count() == 1
    assert page.locator('[data-source-exclusion="thaumaturge-flaming-spirit"]').get_attribute("aria-pressed") == "false"
    assert page.locator('td.source-excluded [data-calculation-key="damage:thaumaturge-flaming-spirit:total-dps"]').count() == 1
    crit_rate_after = float(page.locator('[data-calculation-key="crit:rate"]').inner_text())
    charged_rate_after = float(page.locator('[data-calculation-key="damage:thaumaturge-charged-strike:rate"]').get_attribute("data-exact-value"))
    assert crit_rate_after < crit_rate_before
    assert charged_rate_after < charged_rate_before
    assert abs(charged_rate_after - crit_rate_after) < 1e-12
    assert page.locator('[data-status="burning"]').count() == 0
    assert page.locator('[data-source-exclusion="status-burning"]').count() == 0
    exclusion_code = page.evaluate("new URLSearchParams(location.hash.slice(1)).get('b')")
    excluded_share_id = page.evaluate("DAMAGE_SOURCE_SHARE_ID.get('thaumaturge-flaming-spirit')")
    assert excluded_share_id in page.evaluate("code => decodeBuild(code).configuration.excludedDamageSources", exclusion_code)
    page.locator('[data-source-exclusion="thaumaturge-flaming-spirit"]').click()
    page.goto(f"{URL}#b={exclusion_code}")
    page.reload()
    page.locator('[data-tab="calculations"]').click()
    assert page.locator('th.source-excluded [data-source-exclusion="thaumaturge-flaming-spirit"]').count() == 1
    page.locator('[data-source-exclusion="thaumaturge-flaming-spirit"]').click()

    burning_toggle = page.locator('[data-source-exclusion="status-burning"]')
    burning_combined_before = float(page.locator('[data-calculation-key="damage:combined:total-dps"]').get_attribute("data-exact-value"))
    burning_total = float(page.locator('[data-calculation-key="damage:status-burning:total-dps"]').get_attribute("data-exact-value"))
    burning_toggle.click()
    burning_combined_after = float(page.locator('[data-calculation-key="damage:combined:total-dps"]').get_attribute("data-exact-value"))
    assert abs(burning_combined_after - (burning_combined_before - burning_total)) < 1e-9
    assert page.locator('[data-status="burning"]').count() == 1
    page.locator('[data-source-exclusion="status-burning"]').click()

    # Frozen Heart uses the same shared primary-activation path, but has its
    # own damage scaling and Frozen application chance.
    upgrade(page, "Flaming_Spirit", 0)
    upgrade(page, "Frozen_Heart")
    assert source_rate(page, "thaumaturge-frozen-heart") == "0.75"
    assert page.locator('[data-calculation-key="damage:thaumaturge-frozen-heart:base"]').get_attribute("data-exact-value") == "18"
    frozen_source = page.evaluate("EclipticaBuildForge.buildUnifiedCalculationModel().attackSources.find(source => source.id === 'thaumaturge-frozen-heart')")
    assert frozen_source["element"] == "frost"
    assert frozen_source["canCrit"] is True
    assert frozen_source["statuses"][0]["id"] == "frozen"
    assert frozen_source["statuses"][0]["chance"] == .10
    assert page.locator('[data-status="frozen"]').count() == 1
    upgrade(page, "Frozen_Heart", 2)
    assert page.locator('[data-calculation-key="damage:thaumaturge-frozen-heart:base"]').get_attribute("data-exact-value") == "27"
    upgrade(page, "Frozen_Heart", 0)
    upgrade(page, "Flaming_Spirit")

    # Switching classes must replace—not merely recolor—the configuration and table.
    page.select_option("#class-select", "Gunmancer")
    assert page.locator("#calculation-content").inner_text().find("Gunmancer") >= 0
    assert page.locator("#calculation-content").inner_text().find("Foul Pustule") < 0
    assert page.locator("#configuration-content").inner_text().find("VA-11 Blast Cannon") >= 0
    configuration_text = page.locator("#configuration-content").inner_text()
    assert "Gunmancer calculation setup" not in configuration_text
    assert "Sources:" not in configuration_text
    assert "This gets calculated as using the charged shot on cooldown in addition to whatever is selected above" in configuration_text
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
    assert page.evaluate("GUNMANCER_ABILITIES.secondary.find(ability => ability.id === 'firebomb').status.chance") == .10
    charged_fire = page.evaluate("window.EclipticaBuildForge.buildUnifiedCalculationModel().attackSources.filter(source => source.id.startsWith('gunmancer-airblast-secondary-firebomb'))")
    assert len(charged_fire) == 2
    assert all(source["hitsPerActivation"] == 1 for source in charged_fire)
    assert charged_fire[0]["statuses"][0]["id"] == "burning"

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

    # Nekomancer always uses its staff and aggregates independently attacking
    # minions by type without turning them into a projectile volley.
    page.locator("#reset-build").click()
    page.select_option("#class-select", "Nekomancer")
    page.locator('[data-tab="configuration"]').click()
    assert page.locator("#configuration-content").inner_text().find("Staff of Feline Mortality") >= 0
    assert page.locator('#configuration-content input[name="nekomancer-souls"]').input_value() == "5"
    assert page.locator("#configuration-content .ability-effect").count() == 0
    assert page.locator("#configuration-content p").count() == 0
    assert page.locator("#configuration-content img").evaluate_all("images => images.every(image => image.complete && image.naturalWidth > 0)")
    assert page.evaluate("buildOptions.nekomancerMinions") == {"zombie": 0, "balloon": 0, "ballista": 0}
    assert "conditional-unavailable" in page.locator("[data-id=\"Berserker's_Soul_Melee\"]").get_attribute("class")
    assert "conditional-unavailable" in page.locator("[data-id=\"Berserker's_Soul_Ranged\"]").get_attribute("class")
    assert not page.evaluate("isUpgradeConditionallyAvailable(upgradeIndex.get(\"Berserker's_Soul_Melee\"))")
    assert not page.evaluate("isUpgradeConditionallyAvailable(upgradeIndex.get(\"Berserker's_Soul_Ranged\"))")

    zombie_add = page.locator('[data-nekomancer-minion-action="add"][data-minion-id="zombie"]')
    zombie_add.click()
    zombie_add.click()
    page.locator('[data-nekomancer-minion-action="add"][data-minion-id="balloon"]').click()
    assert page.evaluate("buildOptions.nekomancerMinions") == {"zombie": 2, "balloon": 1, "ballista": 0}
    assert page.locator('[data-nekomancer-minion-action="add"][data-minion-id="ballista"]').is_disabled()
    neko_model = page.evaluate("window.EclipticaBuildForge.buildUnifiedCalculationModel()")
    neko_sources = {source["id"]: source for source in neko_model["attackSources"]}
    assert set(neko_sources) == {"nekomancer-staff-projectile", "nekomancer-minion-zombie", "nekomancer-minion-balloon"}
    assert neko_sources["nekomancer-staff-projectile"]["baseDamage"] == 20
    assert neko_sources["nekomancer-staff-projectile"]["damage"]["activationRate"] == .6
    assert neko_sources["nekomancer-minion-zombie"]["baseDamage"] == 25
    assert neko_sources["nekomancer-minion-zombie"]["damage"]["activationRate"] == 1.2
    assert neko_sources["nekomancer-minion-zombie"]["hitsPerActivation"] == 1
    assert neko_sources["nekomancer-minion-zombie"]["damage"]["averageDamage"] == neko_sources["nekomancer-minion-zombie"]["damage"]["averageDamagePerHit"]
    assert neko_sources["nekomancer-minion-balloon"]["baseDamage"] == 36
    assert neko_sources["nekomancer-minion-balloon"]["damage"]["activationRate"] == .4
    assert abs(neko_model["criticalHitEligibleRate"] - 2.2) < 1e-12
    ballista = page.evaluate("NEKOMANCER_MINIONS.find(minion => minion.id === 'ballista')")
    assert ballista["damage"] == 25
    assert ballista["baseActivationRate"] == .5
    assert ballista["element"] == "physical"
    assert ballista["status"]["id"] == "bleeding"
    assert ballista["status"]["chance"] == .1
    assert page.locator('[data-calculation-key="source:nekomancer-minion-zombie"]').inner_text().find("×2") >= 0
    zombie_rate_formula = page.locator('[data-calculation-key="damage:nekomancer-minion-zombie:rate"]').get_attribute("data-calculation-formula")
    assert "0.60 base activations/s" in zombie_rate_formula
    assert "x2.00 Minions" in zombie_rate_formula
    assert "x1.00 Attack Speed" in zombie_rate_formula
    assert page.locator('[data-calculation-key="source:nekomancer-minion-zombie"]').get_attribute("data-calculation-source-icon") == "pictures/Neko_Zombie.png"
    assert page.locator('[data-status="breached"]').count() == 1
    assert page.locator('[data-status="burning"]').count() == 1

    upgrade(page, "Swift_Hands")
    assert abs(float(source_rate(page, "nekomancer-minion-zombie")) - 1.38) < 1e-12
    upgrade(page, "Swift_Hands", 0)

    upgrade(page, "Flaming_Spirit")
    upgrade(page, "Charged_Strike")
    neko_model = page.evaluate("window.EclipticaBuildForge.buildUnifiedCalculationModel()")
    neko_sources = {source["id"]: source for source in neko_model["attackSources"]}
    assert neko_sources["nekomancer-flaming-spirit"]["damage"]["activationRate"] == .6
    assert neko_sources["nekomancer-charged-strike"]["damage"]["activationRate"] == neko_model["criticalHitsPerSecond"]
    assert neko_model["criticalHitEligibleRate"] > .6

    upgrade(page, "Nekomancer_Soul_Detonation")
    assert not any("detonation" in source["id"] for source in page.evaluate("window.EclipticaBuildForge.buildUnifiedCalculationModel().attackSources"))
    page.locator("#reset-build").click()
    upgrade(page, "Nekomancer_Mastery", 2)
    assert page.evaluate("latestCalculation.stats.overallDamage") == 120
    assert page.evaluate("latestCalculation.stats.healthRegeneration") == 300
    page.evaluate("buildOptions.nekomancerSouls = 0; saveBuildOptions(); render();")
    assert page.evaluate("latestCalculation.stats.overallDamage") == 100
    assert page.evaluate("latestCalculation.stats.healthRegeneration") == 100

    page.evaluate("buildOptions.nekomancerMinions = { zombie: 1, balloon: 1, ballista: 1 }; buildOptions.nekomancerSouls = 3; saveBuildOptions(); render();")
    mixed_model = page.evaluate("window.EclipticaBuildForge.buildUnifiedCalculationModel()")
    assert {source["id"] for source in mixed_model["attackSources"]} == {
        "nekomancer-staff-projectile", "nekomancer-minion-zombie", "nekomancer-minion-balloon", "nekomancer-minion-ballista"
    }
    assert {status["id"] for status in mixed_model["statuses"]} == {"breached", "burning", "bleeding"}
    page.reload()
    assert page.evaluate("buildOptions.nekomancerMinions") == {"zombie": 1, "balloon": 1, "ballista": 1}
    assert page.evaluate("buildOptions.nekomancerSouls") == 3
    page.locator('[data-tab="configuration"]').click()
    page.locator("#reset-configuration").click()
    assert page.evaluate("buildOptions.nekomancerMinions") == {"zombie": 0, "balloon": 0, "ballista": 0}
    assert page.evaluate("buildOptions.nekomancerSouls") == 5

    page.locator('[data-tab="upgrades"]').click()
    page.locator("#dps-ranking-toggle").click()
    page.locator(".dps-ranking-loading").wait_for(state="detached", timeout=15000)
    assert page.locator('[data-dps-upgrade-id="Nekomancer_Mastery"]').count() == 1
    assert page.locator('[data-dps-upgrade-id="Berserker\'s_Soul_Melee"]').count() == 0
    assert page.locator('[data-dps-upgrade-id="Berserker\'s_Soul_Ranged"]').count() == 0
    page.locator("#dps-ranking-toggle").click()

    upgrade(page, "Flaming_Spirit")
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

    # V3 share links carry active class configuration and non-default
    # Berserker stacks, then reproduce it independently of local settings.
    page.evaluate("""() => {
      counts["Berserker's_Soul_Ranged"] = 2;
      buildOptions.twinmagePrimary = 'shadow';
      buildOptions.twinmageSecondary = 'frost';
      buildOptions.twinmagePrimaryDamage = false;
      buildOptions.twinmageSecondaryDamage = true;
      buildOptions.berserkerSoulStacks = 35;
      saveCounts(); saveBuildOptions(); render();
    }""")
    twin_code = page.evaluate("new URLSearchParams(location.hash.slice(1)).get('b')")
    twin_decoded = page.evaluate("code => decodeBuild(code)", twin_code)
    assert twin_decoded["version"] == 3
    assert twin_decoded["configuration"] == {
        "berserkerSoulStacks": 35,
        "twinmage": {"primary": 5, "secondary": 1, "primaryDamage": False, "secondaryDamage": True}
    }
    page.evaluate("""() => {
      buildOptions.twinmagePrimary = 'fire';
      buildOptions.twinmageSecondary = 'lightning';
      buildOptions.twinmagePrimaryDamage = true;
      buildOptions.twinmageSecondaryDamage = true;
      buildOptions.berserkerSoulStacks = 140;
      saveBuildOptions();
    }""")
    page.goto(f"{URL}#b={twin_code}")
    page.reload()
    twin_loaded_state = page.evaluate("({ selectedClass, primary: buildOptions.twinmagePrimary, stacks: buildOptions.berserkerSoulStacks, status: document.querySelector('#copy-status').textContent })")
    assert twin_loaded_state["selectedClass"] == "Twinmage", twin_loaded_state
    assert twin_loaded_state["primary"] == "shadow", twin_loaded_state
    assert twin_loaded_state["stacks"] == 35, twin_loaded_state
    assert page.evaluate("buildOptions.twinmageSecondary") == "frost"
    assert not page.evaluate("buildOptions.twinmagePrimaryDamage")
    assert page.evaluate("buildOptions.twinmageSecondaryDamage")

    page.select_option("#class-select", "Gunmancer")
    page.evaluate("""() => {
      buildOptions.gunmancerPrimary = 'kinetic';
      buildOptions.gunmancerSecondary = 'antimatter';
      buildOptions.gunmancerPrimaryDamage = false;
      buildOptions.gunmancerSecondaryDamage = true;
      buildOptions.gunmancerAirblastTarget = 'secondary';
      saveBuildOptions(); render();
    }""")
    gun_code = page.evaluate("new URLSearchParams(location.hash.slice(1)).get('b')")
    assert page.evaluate("code => decodeBuild(code).configuration.gunmancer", gun_code) == {
        "primary": 1, "secondary": 2, "damageGroup": 1, "airblastTarget": 2
    }
    page.evaluate("() => { buildOptions.gunmancerPrimary = 'va11'; buildOptions.gunmancerSecondary = 'photon'; buildOptions.gunmancerPrimaryDamage = true; buildOptions.gunmancerSecondaryDamage = false; buildOptions.gunmancerAirblastTarget = 'none'; saveBuildOptions(); }")
    page.goto(f"{URL}#b={gun_code}")
    page.reload()
    page.wait_for_function("buildOptions.gunmancerPrimary === 'kinetic' && buildOptions.gunmancerAirblastTarget === 'secondary'")
    assert page.evaluate("buildOptions.gunmancerSecondary") == "antimatter"
    assert page.evaluate("buildOptions.gunmancerSecondaryDamage")

    page.select_option("#class-select", "Nekomancer")
    page.evaluate("""() => {
      buildOptions.nekomancerMinions = { zombie: 2, balloon: 0, ballista: 1 };
      buildOptions.nekomancerSouls = 2;
      saveBuildOptions(); render();
    }""")
    neko_code = page.evaluate("new URLSearchParams(location.hash.slice(1)).get('b')")
    assert page.evaluate("code => decodeBuild(code).configuration.nekomancer", neko_code) == {
        "zombie": 2, "balloon": 0, "ballista": 1, "souls": 2
    }
    page.evaluate("() => { buildOptions.nekomancerMinions = { zombie: 0, balloon: 3, ballista: 0 }; buildOptions.nekomancerSouls = 5; saveBuildOptions(); }")
    page.goto(f"{URL}#b={neko_code}")
    page.reload()
    page.wait_for_function("buildOptions.nekomancerMinions.zombie === 2 && buildOptions.nekomancerSouls === 2")
    assert page.evaluate("buildOptions.nekomancerMinions") == {"zombie": 2, "balloon": 0, "ballista": 1}

    # Older links deterministically reset the active class instead of inheriting
    # non-default configuration from local storage.
    legacy_v2 = page.evaluate("ShareBuildCodec.encodeBuild({ version: 2, characterId: 1, upgrades: [{ id: upgradeIndex.get(\"Berserker's_Soul_Ranged\").globalId, count: 2 }], artifacts: [], runes: [null, null, null, null], curses: [null, null, null, null] })")
    page.evaluate("code => { buildOptions.twinmagePrimary = 'shadow'; buildOptions.twinmageSecondary = 'frost'; buildOptions.twinmagePrimaryDamage = false; buildOptions.twinmageSecondaryDamage = true; buildOptions.berserkerSoulStacks = 7; saveBuildOptions(); location.hash = `b=${code}`; }", legacy_v2)
    page.wait_for_function("selectedClass === 'Twinmage' && buildOptions.twinmagePrimary === 'fire'")
    assert page.evaluate("buildOptions.twinmageSecondary") == "lightning"
    assert page.evaluate("buildOptions.twinmagePrimaryDamage && buildOptions.twinmageSecondaryDamage")
    assert page.evaluate("buildOptions.berserkerSoulStacks") == 140

    legacy_v1 = page.evaluate("ShareBuildCodec.encodeBuild({ version: 1, characterId: 2, upgrades: [] })")
    page.evaluate("code => { buildOptions.gunmancerPrimary = 'kinetic'; buildOptions.gunmancerSecondary = 'antimatter'; buildOptions.gunmancerPrimaryDamage = false; buildOptions.gunmancerSecondaryDamage = true; buildOptions.gunmancerAirblastTarget = 'secondary'; saveBuildOptions(); location.hash = `b=${code}`; }", legacy_v1)
    page.wait_for_function("selectedClass === 'Gunmancer' && buildOptions.gunmancerPrimary === 'va11'")
    assert page.evaluate("buildOptions.gunmancerSecondary") == "photon"
    assert page.evaluate("buildOptions.gunmancerPrimaryDamage && !buildOptions.gunmancerSecondaryDamage")
    assert page.evaluate("buildOptions.gunmancerAirblastTarget") == "none"

    unimplemented_message = "I havent decided on how this class should produce a useful DPS number yet, lol"
    for class_name in ["Fistmage", "Spellhammer", "Shield Mage"]:
        page.select_option("#class-select", class_name)
        assert unimplemented_message in page.locator("#configuration-content").inner_text()
        assert unimplemented_message in page.locator("#calculation-content").inner_text()
        assert not page.locator("#combined-dps-panel").is_visible()
    page.select_option("#class-select", "Gunmancer")
    assert page.locator("#combined-dps-panel").is_visible()

    assert not errors, errors
    browser.close()

print("Cross-class browser smoke tests passed.")
