#!/usr/bin/env python3
"""Refresh the static Ecliptica research dataset from the English Miraheze wiki.

Raw wiki pages are retained in sources.json. Imported records only contain
derived signals plus a precise source excerpt, so source text, interpretation,
hypothesis and confirmation remain separate concepts.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TODAY = date.today().isoformat()
WIKI = "https://ecliptica.miraheze.org"
JA_WIKI = "https://wikiwiki.jp/ecliptica"
CLASS_PAGES = ["Spellsword", "Twinmage", "Gunmancer", "Fistmage", "Spellhammer", "Shield Mage", "Thaumaturge", "Nekomancer"]
DIRECT_PAGES = ["Upgrades", "Classes", "Stats", "Stack Types", "Status Effects"]
JA_PAGES = ["Æ'½ÆŸŸÆŸ-Æ'øÆŸªÆŸ¬ÆŸ%", "Æ'îÆŸ¸Æ'û", "Æ'ûÆŸÅÆŸ¬Æ'¨Æ'û", "ÆŸ?ÆŸÆŸ¯ÆŸÎÆŸ?ÆŸ", "Æ'ûÆŸsÆŸ®Æ'«ÆŸ¬ÆŸ%", "ÆŸ"Æ'ÏÆŸüÆŸ­Æ'ÏÆ'÷", "Æ'ªÆŸüÆŸzÆŸüÆ'æÆŸ¬", "ÆŸÆ'œÆ'ûÆŸ^ÆŸ­Æ'ÏÆ'÷", "Æ'ûÆŸsÆŸ®ÆŸ?ÆŸüÆŸzÆŸ¬", "Æ'úÆŸ¬ÆŸ®ÆŸ%ÆŸ­Æ'ÏÆ'÷", "Æ'æÆ'ÝÆŸzÆ'¨ÆŸ¬Æ'÷", "ÆŸ?Æ'üÆŸzÆŸüÆ'æÆŸ¬"]


def slug(value: str) -> str:
    value = str(value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", value))


def stable_id(prefix: str, *parts: str) -> str:
    return "-".join([prefix, *[slug(part) for part in parts if part]])


def source_id(title: str) -> str:
    return f"wiki-{slug(title)}"


def japanese_source_id(title: str) -> str:
    return f"ja-wiki-{hashlib.sha1(title.encode('utf-8')).hexdigest()[:12]}"


def page_url(title: str) -> str:
    return f"{WIKI}/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def raw_url(title: str) -> str:
    return f"{WIKI}/w/index.php?title={urllib.parse.quote(title)}&action=raw"


def japanese_page_url(title: str) -> str:
    return f"{JA_WIKI}/{urllib.parse.quote(title)}"


def read_json(name: str, fallback):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback


def write_json(name: str, value) -> None:
    (DATA / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_browser_bundle() -> None:
    """Create a file-protocol-friendly bundle while keeping JSON authoritative."""
    names = ["upgrades", "classes", "questions", "claims", "evidence", "tests", "sources", "import-report"]
    bundle = {name: read_json(f"{name}.json", []) for name in names}
    (DATA / "data.js").write_text(
        "window.ECLIPTICA_RESEARCH_DATA = " + json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )


def fetch_raw(title: str) -> str:
    request = urllib.request.Request(raw_url(title), headers={"User-Agent": "EclipticaResearchWiki/0.1 (local research importer)"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read().decode("utf-8")


def fetch_japanese_page(title: str) -> str:
    request = urllib.request.Request(japanese_page_url(title), headers={"User-Agent": "EclipticaResearchWiki/0.1 (local research importer)"})
    with urllib.request.urlopen(request, timeout=40) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        raw_html = response.read().decode(charset, errors="replace")
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw_html, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
    text = re.sub(r"</(?:p|div|li|tr|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def decode_entities(value: str) -> str:
    return html.unescape(value.replace("&nbsp;", " "))


def clean_wiki_text(value: str | None) -> str:
    text = str(value or "")
    text = re.sub(r"\[\[(?:File|Image):[^\]]+\]\]", "", text, flags=re.I)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"<ref[^>]*>[\s\S]*?</ref>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = decode_entities(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def extract_file(value: str | None) -> str | None:
    match = re.search(r"\[\[(?:File|Image):([^|\]]+)", str(value or ""), flags=re.I)
    return match.group(1).strip() if match else None


def local_file_name(file_name: str | None) -> str | None:
    if not file_name:
        return None
    return re.sub(r"_+", "_", re.sub(r'[<>:"/\\|?*]', "_", re.sub(r"\s+", "_", file_name)))


def parse_cells(block: str) -> list[str]:
    cells: list[str] = []
    current: str | None = None
    for line in block.splitlines():
        if re.match(r"^[|!](?!})", line):
            if current is not None:
                cells.append(current.strip())
            body = line[1:].strip()
            if line.startswith("!") and "|" in body:
                body = body.rsplit("|", 1)[-1].strip()
            current = body
        elif current is not None and line.strip():
            current += "\n" + line.strip()
    if current is not None:
        cells.append(current.strip())
    return cells


def parse_tables(raw: str) -> list[dict]:
    tables = []
    for match in re.finditer(r"\{\|[\s\S]*?\n\|\}", raw):
        section = None
        for line in raw[: match.start()].splitlines():
            heading = re.match(r"^(={2,4})\s*([^=].*?)\s*\1\s*$", line)
            if heading:
                section = clean_wiki_text(heading.group(2))
        body = match.group(0)[2:-2]
        rows = [parse_cells(block) for block in re.split(r"\n\|-\s*", body)]
        rows = [row for row in rows if len(row) >= 2]
        if rows:
            tables.append({"section": section, "rows": rows})
    return tables


def page_title(raw: str) -> str | None:
    match = re.search(r"^={1,2}\s*([^=].*?)\s*={1,2}\s*$", raw, flags=re.M)
    return clean_wiki_text(match.group(1)) if match else None


def signals(text: str) -> dict:
    normalized = re.sub(r"\bDDamage\b", "Damage", clean_wiki_text(text), flags=re.I)
    unknown = sorted(set(token.strip() for token in re.findall(r"\bX(?:\s*[%+]?)\b|\?|\b(?:TBD|unknown|unspecified|N/A)\b", normalized, flags=re.I)))
    numeric = sorted(set(re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|m/s|m|HP|seconds?|second|meters?|meter|stacks?|stack)?\b", normalized, flags=re.I)))
    has_periodic = bool(re.search(r"\bperiodically\b|\bevery\s+\d+\s*(?:second|seconds|ms|minutes?)\b|\bevery\s+second\b", normalized, flags=re.I))
    has_interval = bool(re.search(r"\bevery\s+\d+\s*(?:second|seconds|ms|minutes?)\b|\b\d+(?:\.\d+)?\s*(?:second|seconds|ms|minutes?)\s*(?:cooldown|interval)?\b", normalized, flags=re.I))
    has_damage = bool(re.search(r"\bdamage\b", normalized, flags=re.I))
    has_damage_number = bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:%|damage|HP)?\b[^\n]{0,16}\bdamage\b|\bdamage\b[^\n]{0,16}\b\d+(?:\.\d+)?", normalized, flags=re.I))
    explicit_damage_amount = bool(re.search(r"\b(?:deal|deals|dealing|inflict|inflicts)\s+(?:\d|X|\?)[^\n]{0,60}\bdamage\b", normalized, flags=re.I))
    qualified_dealing = bool(re.search(r"\bdealing\s+(?!damage\b)[^\n]{0,80}\bdamage\b", normalized, flags=re.I))
    additional_damage = bool(re.search(r"\b(?:deal|deals|dealing|cause|causes|performing)\b[^\n]{0,70}\b(?:additional|extra)\b[^\n]{0,30}\bdamage\b", normalized, flags=re.I))
    targeted_damage = bool(re.search(r"\b(?:deal|deals|dealing|inflict|inflicts)\b[^\n]{0,80}\bdamage\s+(?:to|around|at|on)\b", normalized, flags=re.I))
    damage_source_noun = bool(re.search(r"\b(?:explosion|projectile|fireball|icicle|whirlwind|aura|beam|attack|area of effect|reflected damage)\b[^\n]{0,80}\bdamage\b", normalized, flags=re.I))
    creates_damage_source = bool(re.search(r"\b(?:spawn|spawns|create|creates|fires|fire|launch|launches)\b[^\n]{0,80}\b(?:area of effect|explosion|projectile|damage)\b", normalized, flags=re.I))
    has_outgoing_damage = explicit_damage_amount or qualified_dealing or additional_damage or targeted_damage or damage_source_noun or creates_damage_source
    return {
        "unknownTokens": unknown,
        "numericMentions": numeric,
        "hasPeriodic": has_periodic,
        "hasExplicitInterval": has_interval,
        "hasDamage": has_damage,
        "hasDamageNumber": has_damage_number,
        "hasOutgoingDamage": has_outgoing_damage,
        "hasChance": bool(re.search(r"\bchance\b|\bprobability\b", normalized, flags=re.I)),
        "hasDuration": bool(re.search(r"\bduration\b|\bfor\s+\d+(?:\.\d+)?\s*(?:second|seconds|ms)\b", normalized, flags=re.I)),
        "hasCooldown": bool(re.search(r"\bcooldown\b", normalized, flags=re.I)),
        "hasStackScaling": bool(re.search(r"\bper\s+stack\b|\beach\s+stack\b|\badditional\s+stack", normalized, flags=re.I)),
        "hasFormulaLanguage": bool(re.search(r"\bformula\b|\badditive\b|\bmultiplicative\b|\bhyperbolic\b|\bexponential\b", normalized, flags=re.I)),
        "hasUnknown": bool(unknown),
    }


def damage_behavior(text: str, signal_data: dict) -> dict | None:
    """Keep crit/status behavior explicit without inferring unknown mechanics."""
    normalized = re.sub(r"\bDDamage\b", "Damage", clean_wiki_text(text), flags=re.I)
    creates_extra_instance = bool(re.search(r"\b(?:extra|additional)\s+projectile\b|\bspawn\b[^\n]{0,80}\b(?:area of effect|explosion)\b", normalized, flags=re.I))
    if re.search(r"\bnext skill\b", normalized, flags=re.I) and not re.search(r"\b(?:explosion|projectile|fireball|icicle|whirlwind|aura|beam|reflected damage)\b", normalized, flags=re.I):
        return {
            "createsDamageInstance": False,
            "canCrit": "not_applicable",
            "critChance": None,
            "critNotes": "This ability modifies another skill's damage and does not create its own damage instance.",
            "canApplyStatusEffects": "not_applicable",
            "statusEffectChance": None,
            "statusNotes": "Status application belongs to the modified skill, not this modifier itself.",
        }
    if not signal_data["hasOutgoingDamage"] and not creates_extra_instance:
        return None
    status_match = re.search(r"((?:\d+(?:\.\d+)?%\s*)?(?:chance|probability)[^\n]{0,80}(?:status effect|BLEEDING|BURNING|FROZEN|POISONED|WEAKENED|BREACHED|PARALYZED))", normalized, flags=re.I)
    explicit_status_chance = status_match.group(1).strip() if status_match else None
    if explicit_status_chance and not re.search(r"\d", explicit_status_chance):
        explicit_status_chance = "Chance stated, magnitude not parsed"
    crit_match = re.search(r"(\d+(?:\.\d+)?%)[^\n]{0,40}(?:chance to )?(?:crit|critically strike|critical hit)", normalized, flags=re.I)
    explicit_crit_chance = crit_match.group(1) if crit_match else None
    explicit_crit_capability = bool(explicit_crit_chance or re.search(r"\b(?:can|may)\s+(?:crit|critically strike)|\balways\s+crit|guaranteed\s+critical\s+(?:hit|strike)", normalized, flags=re.I))
    explicit_crit_exclusion = bool(re.search(r"cannot\s+(?:crit|critically strike)|cannot be critical", normalized, flags=re.I))
    return {
        "createsDamageInstance": True,
        "canCrit": True if explicit_crit_capability else False if explicit_crit_exclusion else None,
        "critChance": explicit_crit_chance,
        "critNotes": "Explicitly stated in source." if explicit_crit_capability or explicit_crit_exclusion else "The English wiki does not state whether this damage instance can critically strike.",
        "canApplyStatusEffects": True if explicit_status_chance else None,
        "statusEffectChance": explicit_status_chance,
        "statusNotes": "Explicit status-effect chance wording retained from source." if explicit_status_chance else "The English wiki does not state whether this damage instance can apply status effects or what chance applies.",
    }


def source_ref(page: str, section: str | None, excerpt: str, fields: list[str]) -> dict:
    return {"sourceId": source_id(page), "sourcePage": page, "section": section, "retrievedAt": TODAY, "excerpt": excerpt, "derivedFields": fields}


def japanese_source_ref(page: str, section: str | None, excerpt: str, translation: str, fields: list[str]) -> dict:
    return {"sourceId": japanese_source_id(page), "sourcePage": page, "section": section, "retrievedAt": TODAY, "excerpt": excerpt, "translation": translation, "derivedFields": fields}


def japanese_evidence(record_id: str, mechanic_id: str, mechanic_name: str, question_id: str, question_ids: list[str], page: str, section: str, original: str, translation: str, interpretation: str, supports: list[str], fields: list[str], reliability: str) -> dict:
    return {
        "id": record_id,
        "mechanicId": mechanic_id,
        "mechanicName": mechanic_name,
        "questionId": question_id,
        "questionIds": question_ids,
        "type": "Japanese wiki",
        "source": f"Ecliptica Wiki* / {page}",
        "date": TODAY,
        "originalInformation": original,
        "translation": translation,
        "interpretation": interpretation,
        "supportsClaimIds": supports,
        "contradictsClaimIds": [],
        "reliabilityNotes": reliability,
        "sourceRefs": [japanese_source_ref(page, section, original, translation, fields)],
        "attachments": [],
    }


def upgrade_section(section: str | None) -> str:
    if not section:
        return "Uncategorized"
    if re.search("perseverance", section, flags=re.I):
        return "Crystal of Perseverance"
    if re.search("mobility", section, flags=re.I):
        return "Crystal of Mobility"
    if re.search("chrono", section, flags=re.I):
        return "Chrono Wizard"
    return section


def functional_interpretation(name: str, description: str, signal_data: dict, behavior: dict | None, entity_label: str) -> dict:
    """Create a clearly labeled working model without turning inference into fact."""
    clauses = []
    if signal_data["hasPeriodic"]:
        clauses.append("The wording suggests an automatic recurring trigger rather than a manually activated one.")
    if behavior and behavior.get("createsDamageInstance") is False:
        clauses.append("It appears to modify another skill's damage rather than create its own damage instance.")
    elif behavior:
        clauses.append("It appears to create a distinct damage instance when its stated trigger occurs.")
        if behavior["canCrit"] is True:
            clauses.append("The source explicitly allows critical hits for that instance.")
        elif behavior["canCrit"] is False:
            clauses.append("The source explicitly excludes critical hits for that instance.")
        else:
            clauses.append("Whether that damage instance can critically strike is not stated.")
        if behavior["canApplyStatusEffects"] is True:
            clauses.append("The source gives status-effect application wording or a chance.")
        else:
            clauses.append("Whether that damage instance can apply status effects is not stated.")
    elif signal_data["hasDamage"]:
        clauses.append("The description appears to modify or cause damage, but it is not parsed as a separate damage instance.")
    else:
        clauses.append("The description appears to function as a passive modifier, condition, or utility effect rather than a direct damage source.")
    if signal_data["hasStackScaling"]:
        clauses.append("Additional stacks appear to change the effect, although the exact stacking operation must follow the source wording.")
    if signal_data["hasUnknown"]:
        clauses.append("The working model remains incomplete because the source contains unknown or placeholder values.")
    if signal_data["hasDuration"]:
        clauses.append("The effect appears to persist for a finite duration where stated.")
    if signal_data["hasCooldown"]:
        clauses.append("The source describes a cooldown-gated action.")
    return {
        "status": "Working interpretation",
        "summary": f"Working interpretation for {name}: " + " ".join(clauses),
        "basis": f"Conservative paraphrase of the English wiki description for this {entity_label}; it is not a confirmed in-game mechanic.",
        "uncertainties": signal_data["unknownTokens"],
    }


def make_upgrade(row: list[str], page: str, section: str | None, class_name: str | None = None) -> dict:
    image_cell, rarity, name, description, stack_type = row[:5]
    image = extract_file(image_cell)
    clean_name = clean_wiki_text(name)
    clean_description = clean_wiki_text(description)
    family = class_name or upgrade_section(section)
    signal_data = signals(clean_description)
    behavior = damage_behavior(clean_description, signal_data)
    interpretation = functional_interpretation(clean_name, clean_description, signal_data, behavior, "upgrade")
    derived = ["name", "rarity", "description", "stackType", "category", "functionalInterpretation"] + (["icon"] if image else []) + (["damageBehavior"] if behavior else [])
    return {
        "id": stable_id("upgrade", family, clean_name),
        "entityType": "upgrade",
        "name": clean_name,
        "family": family,
        "category": "Class Specific" if class_name else upgrade_section(section),
        "rarity": clean_wiki_text(rarity),
        "icon": local_file_name(image),
        "imageFile": image,
        "imageUrl": f"{WIKI}/wiki/Special:FilePath/{urllib.parse.quote(image)}" if image else None,
        "description": clean_description,
        "mechanics": {"stackType": clean_wiki_text(stack_type), "sourceText": clean_description, "signals": signal_data, "damageBehavior": behavior, "functionalInterpretation": interpretation, "arbitrary": []},
        "researchStatus": "Needs Testing" if signal_data["hasUnknown"] or (signal_data["hasPeriodic"] and not signal_data["hasExplicitInterval"]) else "Unknown",
        "sourceRefs": [source_ref(page, section or "Upgrades", clean_description, derived)],
        "importedAt": TODAY,
        "importedFrom": "English Ecliptica Wiki",
    }


def table_upgrades(raw: str, page: str, class_name: str | None = None) -> list[dict]:
    records = []
    for table in parse_tables(raw):
        for row in table["rows"]:
            if len(row) < 5:
                continue
            rarity = clean_wiki_text(row[1])
            if not re.fullmatch(r"Common|Rare|Legendary", rarity, flags=re.I):
                continue
            if clean_wiki_text(row[2]):
                records.append(make_upgrade(row, page, table["section"], class_name))
    return records


def classes_index(raw: str) -> list[dict]:
    table = next((item for item in parse_tables(raw) if any(re.search(r"Spellsword|Twinmage|Gunmancer", clean_wiki_text(" ".join(row))) for row in item["rows"])), None)
    if not table:
        return []
    known = CLASS_PAGES
    result = []
    for index, row in enumerate(table["rows"]):
        if len(row) < 2:
            continue
        link = re.search(r"link=(?:https?://[^/]+/wiki/)?([^|\]]+)", row[0], flags=re.I)
        name = urllib.parse.unquote(link.group(1)).replace("_", " ") if link else (known[index] if index < len(known) else None)
        image = extract_file(row[0])
        if not image and not link:
            continue
        if name not in known:
            continue
        result.append({"name": name, "icon": local_file_name(image), "imageFile": image, "description": clean_wiki_te…21812 tokens truncated…ental-hand status chance", "10% for each listed hand/status pair", "EVID-JA-TWINMAGE-HANDS"),
        ],
        "EVID-JA-TWINMAGE-MASTERY": [fact("Splash damage ratio", "25% of the triggering skill damage", "EVID-JA-TWINMAGE-MASTERY"), fact("Base splash radius", "UNKNOWN", "EVID-JA-TWINMAGE-MASTERY", note="Japanese source retains ? m."), fact("Per-stack radius increase", "UNKNOWN", "EVID-JA-TWINMAGE-MASTERY", note="Japanese source retains +? m.")],
        "EVID-JA-TWINMAGE-HAND-MODIFIERS": [fact("Sinistra/Dextra hand damage modifier", "+5% to favored hand and -3% to the other hand per stack", "EVID-JA-TWINMAGE-HAND-MODIFIERS"), fact("Modifier calculation group", "Group B is calculated multiplicatively with Group A", "EVID-JA-TWINMAGE-HAND-MODIFIERS")],
        "EVID-JA-CHARGED-STRIKE": [fact("Explosion base damage", "25 Physical", "EVID-JA-CHARGED-STRIKE", note="Conflicts with the English wiki X placeholder."), fact("Explosion damage per stack", "+10 Physical", "EVID-JA-CHARGED-STRIKE", note="Conflicts with the English wiki X placeholder."), fact("Explosion damage scaling", "Affected by dealt Physical Damage", "EVID-JA-CHARGED-STRIKE")],
        "EVID-JA-BIG-LAZY": [fact("Regeneration formula", "Existing regeneration Ç- (1 + Big and Lazy stack count)", "EVID-JA-BIG-LAZY"), fact("Movement condition", "Movement input disables the regeneration effect; inertia/skill movement is excluded", "EVID-JA-BIG-LAZY")],
        "EVID-JA-BENISON": [fact("Target range", "64 m", "EVID-JA-BENISON"), fact("Additional-stack behavior", "Additional copies shorten the firing interval", "EVID-JA-BENISON"), fact("Projectile damage", "UNKNOWN", "EVID-JA-BENISON", note="Japanese source retains ? damage.")],
        "EVID-JA-CURSE-OF-WRATH": [fact("Base interval", "4 seconds", "EVID-JA-CURSE-OF-WRATH", note="Conflicts with the English page's incomplete interval wording."), fact("Base damage", "30 Shadow", "EVID-JA-CURSE-OF-WRATH", note="Conflicts with the English page's 25 (+X) wording."), fact("Target range", "32 m", "EVID-JA-CURSE-OF-WRATH"), fact("Critical-hit rule", "A critical-hit check exists", "EVID-JA-CURSE-OF-WRATH"), fact("BREACHED chance", "UNKNOWN", "EVID-JA-CURSE-OF-WRATH", note="Japanese source retains ?%.")],
        "EVID-JA-THUNDER-AURA": [fact("Activation interval", "1 second", "EVID-JA-THUNDER-AURA"), fact("Base radius", "4 m", "EVID-JA-THUNDER-AURA"), fact("Base damage", "23 Electric", "EVID-JA-THUNDER-AURA", note="Conflicts with the English page's 25 base damage."), fact("Critical-hit rule", "A critical-hit check exists", "EVID-JA-THUNDER-AURA"), fact("Status chance", "UNKNOWN", "EVID-JA-THUNDER-AURA", note="Japanese source says chance exists but gives no percentage.")],
        "EVID-JA-BERSERKER-MELEE": [fact("Maximum stacks", "70", "EVID-JA-BERSERKER-MELEE"), fact("Dealt damage per stack", "+0.64%", "EVID-JA-BERSERKER-MELEE"), fact("Attack Speed per stack", "+1.28%", "EVID-JA-BERSERKER-MELEE"), fact("Regeneration per stack", "-0.71%", "EVID-JA-BERSERKER-MELEE")],
        "EVID-JA-BERSERKER-RANGED": [fact("Maximum stacks", "70", "EVID-JA-BERSERKER-RANGED"), fact("Dealt damage per stack", "+0.32%", "EVID-JA-BERSERKER-RANGED"), fact("Attack Speed per stack", "+0.64%", "EVID-JA-BERSERKER-RANGED"), fact("Projectile spread per stack", "+0.0285%", "EVID-JA-BERSERKER-RANGED")],
        "EVID-JA-SPELLSWORD-PIERCING": [fact("Charge time", "0.170ƒ?"5.075 seconds", "EVID-JA-SPELLSWORD-PIERCING"), fact("Damage", "87ƒ?"170", "EVID-JA-SPELLSWORD-PIERCING"), fact("Cooldown", "1.5 seconds", "EVID-JA-SPELLSWORD-PIERCING"), fact("Bleeding chance", "Up to 50%", "EVID-JA-SPELLSWORD-PIERCING"), fact("Attack Speed scaling", "Approximately 1.5% shorter charge time per 1% Attack Speed", "EVID-JA-SPELLSWORD-PIERCING")],
        "EVID-JA-SPELLSWORD-WHIRLWIND": [fact("Damage tick interval", "Approximately 0.1 seconds", "EVID-JA-SPELLSWORD-WHIRLWIND"), fact("Bleeding behavior", "Inherits Bleeding chance", "EVID-JA-SPELLSWORD-WHIRLWIND"), fact("Critical-hit rule", "Cannot critically strike", "EVID-JA-SPELLSWORD-WHIRLWIND")],
        "EVID-USER-BERSERKER-MELEE-TOTAL": [fact("User full-stack hypothesis", "Approximately +45% Overall Damage, +90% Attack Speed, and -50% Health Regeneration at 70 stacks", "EVID-USER-BERSERKER-MELEE-TOTAL", status="Reported", confidence="Reported")],
        "EVID-USER-BERSERKER-RANGED-TOTAL": [fact("User full-stack hypothesis", "Approximately +45% Overall Damage, +90% Attack Speed, and +2% Projectile Spread at 70 stacks", "EVID-USER-BERSERKER-RANGED-TOTAL", status="Reported", confidence="Reported")],
        "EVID-USER-BIG-LAZY-STACKS": [fact("User observed multiplier", "Approximately 3Ç- at 1 stack and 3.5Ç- at 2 stacks, continuing linearly", "EVID-USER-BIG-LAZY-STACKS", status="Reported", confidence="Reported")],
        "EVID-USER-BIG-ROUND-STACKING": [fact("User stacking observation", "Appears linear as described", "EVID-USER-BIG-ROUND-STACKING", status="Reported", confidence="Reported")],
        "EVID-USER-BIG-WRATHFUL-STACKING": [fact("User stacking hypothesis", "Probably linear; additive-versus-multiplicative operation remains unresolved", "EVID-USER-BIG-WRATHFUL-STACKING", status="Reported", confidence="Reported")],
    }
    evidence_by_id = {item["id"]: item for item in evidence}
    all_records = list(upgrades) + [skill for cls in classes for skill in cls["skills"]] + classes
    for record in all_records:
        record_id = record["id"]
        related_questions = [item for item in questions if record_id in item.get("mechanicIds", [item.get("mechanicId")])]
        related_question_ids = {item["id"] for item in related_questions}
        related_evidence = [item for item in evidence if item.get("mechanicId") == record_id or item.get("mechanicId") in {link.get("id") for question in related_questions for link in question.get("mechanicLinks", [])} or related_question_ids.intersection(item.get("questionIds", [item.get("questionId")]))]
        findings = []
        source_tags = [{"category": "English wiki", "confidence": "Source-stated", "evidenceId": None}] if record.get("sourceRefs") else []
        for item in related_evidence:
            category, default_confidence = evidence_source_metadata(item.get("type", ""))
            source_tags.append({"category": category, "confidence": default_confidence, "evidenceId": item["id"]})
            direct_fact_evidence = item.get("mechanicId") == record_id
            shared_hand_modifier_evidence = item["id"] == "EVID-JA-TWINMAGE-HAND-MODIFIERS" and record_id in {"upgrade-twinmage-twinmage-sinistra", "upgrade-twinmage-twinmage-dextra"}
            for item_fact in facts_by_evidence.get(item["id"], []) if direct_fact_evidence or shared_hand_modifier_evidence else []:
                finding = dict(item_fact)
                finding["sourceCategory"] = category
                if finding.get("confidence") == "Medium" and default_confidence != "Reported":
                    finding["confidence"] = default_confidence
                findings.append(finding)
        # Apply the Twinmage hand facts directly to each hand ability as well as the class record.
        if record.get("type") == "Hand" and record.get("id", "").startswith("skill-twinmage-"):
            for item_fact in facts_by_evidence["EVID-JA-TWINMAGE-HANDS"]:
                finding = dict(item_fact)
                finding["sourceCategory"] = "Japanese wiki"
                findings.append(finding)
                source_tags.append({"category": "Japanese wiki", "confidence": "Reported", "evidenceId": "EVID-JA-TWINMAGE-HANDS"})
        signals_data = record.get("mechanics", {}).get("signals", {})
        explicit_values = signals_data.get("numericMentions", [])
        unresolved = list(dict.fromkeys(signals_data.get("unknownTokens", []) + [item["id"] for item in related_questions if item.get("status") not in {"Confirmed", "Supported"}]))
        record["researchAudit"] = {"status": "Reviewed", "explicitEnglishValues": explicit_values, "findings": list({(item["label"], item["value"], item["evidenceId"]): item for item in findings}.values()), "unresolved": unresolved, "sourceTags": list({(item["category"], item["evidenceId"]): item for item in source_tags}.values()), "notes": "Findings are source-tagged and do not overwrite the original wiki description or placeholder values."}
    for item in evidence:
        category, confidence = evidence_source_metadata(item.get("type", ""))
        item["sourceCategory"] = category
        item["confidence"] = confidence


def populate_source_hypotheses(questions: list[dict], evidence: list[dict]) -> None:
    """Create clearly labelled, evidence-backed hypotheses without changing manual hypotheses."""
    for question in questions:
        question_id = question["id"]
        linked = [
            item for item in evidence
            if question_id == item.get("questionId") or question_id in item.get("questionIds", [])
        ]
        statements = []
        source_tags = []
        evidence_ids = []
        for item in linked:
            statement = item.get("translation") or item.get("interpretation") or item.get("originalInformation")
            if not statement:
                continue
            statement = " ".join(str(statement).split())
            if len(statement) > 320:
                statement = statement[:317].rstrip() + "..."
            category = item.get("sourceCategory") or item.get("type") or "Unknown source"
            confidence = item.get("confidence") or "Unrated"
            key = (category, statement)
            if key not in {(entry["category"], entry["statement"]) for entry in statements}:
                statements.append({"category": category, "statement": statement, "evidenceId": item["id"]})
            source_tags.append({"category": category, "confidence": confidence, "evidenceId": item["id"]})
            evidence_ids.append(item["id"])
        if not statements:
            continue
        question["sourceHypothesis"] = " ".join(f"{entry['category']} ({entry['evidenceId']}) suggests: {entry['statement']}" for entry in statements[:4])
        question["hypothesisEvidenceIds"] = list(dict.fromkeys(evidence_ids))
        question["hypothesisSourceTags"] = list({(item["category"], item["confidence"]): item for item in source_tags}.values())


def dedupe(records: list[dict]) -> list[dict]:
    return list({record["id"]: record for record in records}.values())


def question_topics(text: str) -> set[str]:
    topics = set()
    if re.search(r"interval|periodic|how often|frequency", text, flags=re.I):
        topics.add("interval")
    if re.search(r"damage", text, flags=re.I):
        topics.add("damage")
    if re.search(r"stack|scal|formula|additive|multiplicative", text, flags=re.I):
        topics.add("scaling")
    if re.search(r"chance|proc", text, flags=re.I):
        topics.add("chance")
    if re.search(r"cooldown", text, flags=re.I):
        topics.add("cooldown")
    if re.search(r"unknown|placeholder|\bX\b|\?", text, flags=re.I):
        topics.add("unknown")
    return topics


def remove_manual_duplicates(generated: list[dict], manual: list[dict]) -> list[dict]:
    """Let a seeded/user question own a topic instead of creating a synonym."""
    result = []
    for item in generated:
        item_topics = question_topics(item["question"])
        covered = any(
            item.get("mechanicId") == existing.get("mechanicId")
            and item_topics
            and item_topics.intersection(question_topics(existing.get("question", "")))
            for existing in manual
        )
        if not covered:
            result.append(item)
    return result


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    existing_questions = read_json("questions.json", [])
    for item in existing_questions:
        if item.get("mechanicId") == "upgrade-chronowizard-charged-strike":
            item["mechanicId"] = "upgrade-chrono-wizard-charged-strike"
        item["mechanicIds"] = ["upgrade-chrono-wizard-charged-strike" if value == "upgrade-chronowizard-charged-strike" else value for value in item.get("mechanicIds", [])]
        for link in item.get("mechanicLinks", []):
            if link.get("id") == "upgrade-chronowizard-charged-strike":
                link["id"] = "upgrade-chrono-wizard-charged-strike"
    existing_sources = read_json("sources.json", [])
    existing_claims = read_json("claims.json", [])
    existing_evidence = read_json("evidence.json", [])
    existing_tests = read_json("tests.json", [])
    fetched: dict[str, str] = {}
    failures = []
    for title in [*DIRECT_PAGES, *CLASS_PAGES]:
        try:
            fetched[title] = fetch_raw(title)
            print(f"Fetched {title}")
        except Exception as error:  # noqa: BLE001 - report each page and continue
            failures.append({"title": title, "url": raw_url(title), "error": str(error)})
            print(f"Failed {title}: {error}", file=sys.stderr)
    japanese_fetched: dict[str, str] = {}
    japanese_failures = []
    for title in JA_PAGES:
        try:
            japanese_fetched[title] = fetch_japanese_page(title)
            print(f"Fetched Japanese {title}")
        except Exception as error:  # noqa: BLE001 - report each page and continue
            japanese_failures.append({"title": title, "url": japanese_page_url(title), "error": str(error)})
            print(f"Failed Japanese {title}: {error}", file=sys.stderr)

    prior_upgrades = read_json("upgrades.json", [])
    prior_classes = read_json("classes.json", [])
    upgrades = table_upgrades(fetched["Upgrades"], "Upgrades") if "Upgrades" in fetched else []
    index = classes_index(fetched["Classes"]) if "Classes" in fetched else []
    classes = []
    class_upgrades = []
    for title in CLASS_PAGES:
        if title in fetched:
            record, specific = parse_class(fetched[title], title, next((item for item in index if item["name"] == title), None))
            classes.append(record)
            class_upgrades.extend(specific)
    upgrades = dedupe(upgrades + class_upgrades)
    failed_titles = {item["title"] for item in failures}
    if failed_titles:
        upgrades = dedupe(upgrades + [item for item in prior_upgrades if any(ref.get("sourcePage") in failed_titles for ref in item.get("sourceRefs", []))])
        classes = dedupe(classes + [item for item in prior_classes if any(ref.get("sourcePage") in failed_titles for ref in item.get("sourceRefs", []))])

    seed_questions, seed_claims, seed_evidence, seed_tests = manual_seed()
    manual_questions = [item for item in existing_questions if item.get("manual") or item.get("kind") == "user-research" or item.get("generated") is False]
    generated = remove_manual_duplicates(generate_questions(upgrades, classes), manual_questions + seed_questions)
    questions = dedupe(seed_questions + manual_questions + generated)
    apply_interaction_links(questions)
    question_mechanic_ids = {mechanic_id for item in questions for mechanic_id in item.get("mechanicIds", [item.get("mechanicId")])}
    for upgrade in upgrades:
        has_unknown = upgrade["mechanics"]["signals"]["hasUnknown"]
        if not has_unknown and upgrade["id"] not in question_mechanic_ids:
            upgrade["researchStatus"] = "Complete"
            upgrade["confirmationStatus"] = "Unconfirmed by source alone"
            upgrade["completionNote"] = "The imported English-wiki record has no detected missing value or linked open question. This does not by itself confirm in-game behavior."
        elif not has_unknown and upgrade["id"] in question_mechanic_ids:
            upgrade["researchStatus"] = "Needs Testing"
    claims = dedupe(seed_claims + existing_claims)
    evidence = dedupe(seed_evidence + existing_evidence)
    question_aliases = {
        "question-upgrade-crystal-of-mobility-thunder-aura-damage": "question-upgrade-crystal-of-mobility-thunder-aura-interval",
        "question-skill-spellsword-piercing-strike-unknown": "question-skill-spellsword-piercing-strike-attack-interval",
    }
    for item in evidence:
        if item.get("questionId") in question_aliases:
            item["questionId"] = question_aliases[item["questionId"]]
        item["questionIds"] = list(dict.fromkeys(question_aliases.get(value, value) for value in item.get("questionIds", [])))
    tests = existing_tests or seed_tests
    apply_research_fact_audit(upgrades, classes, questions, evidence)
    populate_source_hypotheses(questions, evidence)
    apply_japanese_audit(questions, evidence, [japanese_source_id(title) for title in JA_PAGES], japanese_failures)
    imported_ids = {source_id(title) for title in [*DIRECT_PAGES, *CLASS_PAGES]} | {japanese_source_id(title) for title in JA_PAGES}
    sources = [item for item in existing_sources if item.get("id") not in imported_ids]
    for title, raw in fetched.items():
        sources.append({"id": source_id(title), "type": "English Ecliptica Wiki", "title": title, "pageUrl": page_url(title), "rawUrl": raw_url(title), "retrievedAt": TODAY, "retrievalStatus": "retrieved", "contentFormat": "MediaWiki source", "rawText": raw, "notes": "Primary upgrade table source; class-specific upgrades are on individual class pages." if title == "Upgrades" else None})
    sources.extend(item for item in existing_sources if item.get("id") in {source_id(title) for title in failed_titles})
    for title, text in japanese_fetched.items():
        sources.append({"id": japanese_source_id(title), "type": "Japanese Ecliptica Wiki*", "title": title, "pageUrl": japanese_page_url(title), "rawUrl": japanese_page_url(title), "retrievedAt": TODAY, "retrievalStatus": "retrieved", "contentFormat": "Rendered HTML text", "rawText": text, "notes": "Japanese community wiki page retained for bilingual research audit."})
    for title in JA_PAGES:
        if title not in japanese_fetched:
            sources.append({"id": japanese_source_id(title), "type": "Japanese Ecliptica Wiki*", "title": title, "pageUrl": japanese_page_url(title), "rawUrl": japanese_page_url(title), "retrievedAt": TODAY, "retrievalStatus": "browser-reviewed", "contentFormat": "Bilingual evidence excerpts", "rawText": "Automated page retrieval failed during this refresh. Relevant Japanese excerpts reviewed during the audit are preserved verbatim in evidence records, together with English translations.", "notes": "Source page retained for provenance; see linked Japanese-wiki evidence records for the reviewed excerpts."})

    report = {"generatedAt": datetime.now(timezone.utc).isoformat(), "retrievalDate": TODAY, "sourcePolicy": "English Miraheze wiki remains the factual import boundary; Japanese Wiki* pages are stored as separate bilingual audit evidence and are not silently merged into English-derived fields.", "pagesRequested": [*DIRECT_PAGES, *CLASS_PAGES], "pagesRetrieved": list(fetched), "failures": failures, "japanesePagesRequested": JA_PAGES, "japanesePagesRetrieved": list(japanese_fetched), "japanesePagesBrowserReviewed": JA_PAGES, "japaneseFailures": japanese_failures, "counts": {"upgrades": len(upgrades), "classes": len(classes), "generatedResearchQuestions": len(generated), "totalResearchQuestions": len(questions), "sources": len(sources), "japanesePages": len(JA_PAGES)}, "placeholderRecords": [item["id"] for item in upgrades if item["mechanics"]["signals"]["hasUnknown"]], "warning": "One or more pages failed; existing records from failed pages were preserved." if failures or japanese_failures else None}
    for name, value in [("upgrades.json", upgrades), ("classes.json", classes), ("questions.json", questions), ("claims.json", claims), ("evidence.json", evidence), ("tests.json", tests), ("sources.json", dedupe(sources)), ("import-report.json", report)]:
        write_json(name, value)
    write_browser_bundle()
    print(json.dumps(report["counts"], indent=2))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
