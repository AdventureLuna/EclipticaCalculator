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
JA_PAGES = ["アップグレード", "クラス", "ステータス", "バフ・デバフ", "スペルソード", "ツインメイジ", "ガンマンサー", "フィストメイジ", "スペルハンマー", "シールドメイジ", "サウマタージ", "ネコマンサー"]


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
        result.append({"name": name, "icon": local_file_name(image), "imageFile": image, "description": clean_wiki_text(row[1])})
    return result


def section_body(raw: str, section: str) -> str:
    heading = re.search(rf"^==\s*{re.escape(section)}\s*==\s*$", raw, flags=re.I | re.M)
    if not heading:
        return ""
    rest = raw[heading.end():]
    next_heading = re.search(r"^==\s*[^=].*?\s*==\s*$", rest, flags=re.M)
    return rest[: next_heading.start() if next_heading else len(rest)]


def parse_skills(raw: str, class_name: str) -> list[dict]:
    body = section_body(raw, "Skills")
    headings = list(re.finditer(r"^===\s*(.*?)\s*===\s*$", body, flags=re.M))
    skills = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        raw_heading = heading.group(1)
        image = extract_file(raw_heading)
        title = clean_wiki_text(raw_heading)
        description = clean_wiki_text(body[heading.end():end])
        match = re.match(r"^(Passive|Primary|Secondary|Utility|Hand)(?::\s+|\s+)(.*)$", title, flags=re.I)
        if match:
            kind = match.group(1)
            name = match.group(2).strip() or kind
        elif title.lower() in {"passive", "primary", "secondary", "utility", "hand"}:
            kind = title
            name = title
        else:
            kind = "Mechanic"
            name = title
        if title.rstrip().endswith(":") and not description:
            continue
        text = f"{title}\n{description}"
        signal_data = signals(text)
        behavior = damage_behavior(description, signal_data)
        interpretation = functional_interpretation(f"{class_name}: {name}", description, signal_data, behavior, "class ability")
        skills.append({
            "id": stable_id("skill", class_name, name),
            "name": name,
            "type": kind,
            "icon": local_file_name(image),
            "imageFile": image,
            "imageUrl": f"{WIKI}/wiki/Special:FilePath/{urllib.parse.quote(image)}" if image else None,
            "description": description,
            "mechanics": {"sourceText": description, "signals": signal_data, "damageBehavior": behavior, "functionalInterpretation": interpretation, "arbitrary": []},
            "sourceRefs": [source_ref(class_name, f"Skills > {title}", description or title, ["name", "type", "description", "icon", "functionalInterpretation"] + (["damageBehavior"] if behavior else []))],
        })
    return skills


def parse_class(raw: str, page: str, index_record: dict | None) -> tuple[dict, list[dict]]:
    class_name = page_title(raw) or page
    skills = parse_skills(raw, class_name)
    skills_heading = re.search(r"^==\s*Skills\s*==\s*$", raw, flags=re.I | re.M)
    first_heading = re.search(r"^={1,2}[^=].*?$", raw, flags=re.M)
    description = clean_wiki_text(raw[first_heading.end(): skills_heading.start()] if first_heading and skills_heading else index_record.get("description", "") if index_record else "")
    class_upgrades = table_upgrades(raw, page, class_name)
    reported_mechanics = None
    if class_name == "Twinmage":
        hand_names = [skill["name"] for skill in skills if skill["type"].lower() == "hand"]
        reported_mechanics = {
            "elementalHandAttackRates": {
                "status": "Reported",
                "appliesTo": hand_names,
                "bothHands": {"attacksPerSecond": 0.8, "perHand": True},
                "singleHand": {"attacksPerSecond": 1.4, "perHand": True},
                "rawUserStatement": "0.8 attack speed per hand when using both hands and 1.4 attacks per second when only using both hands.",
                "interpretationNote": "Stored as the two-hands versus single-hand states; the user's wording repeats 'both hands' for the second state and should be verified.",
                "sourceType": "User-reported reading of the English wiki",
                "sourceRefs": [source_ref(page, "Skills", "Firing only one hand will increase your attack speed by 75%", ["qualitative one-hand attack-speed rule"])],
            }
        }
    record = {
        "id": stable_id("class", class_name),
        "entityType": "class",
        "name": class_name,
        "icon": index_record.get("icon") if index_record else None,
        "imageFile": index_record.get("imageFile") if index_record else None,
        "imageUrl": f"{WIKI}/wiki/Special:FilePath/{urllib.parse.quote(index_record['imageFile'])}" if index_record and index_record.get("imageFile") else None,
        "description": description,
        "startingStats": None,
        "statModifiers": [],
        "reportedMechanics": reported_mechanics,
        "skills": skills,
        "upgradeIds": [item["id"] for item in class_upgrades],
        "unknownFields": ["starting stats", "movement characteristics not stated numerically"],
        "researchStatus": "Needs Testing" if any(skill["mechanics"]["signals"]["hasUnknown"] for skill in skills) else "Unknown",
        "sourceRefs": [source_ref(page, "Class overview", description or (index_record or {}).get("description", ""), ["name", "description", "icon", "skills", "startingStats"])],
        "importedAt": TODAY,
        "importedFrom": "English Ecliptica Wiki",
    }
    return record, class_upgrades


def question(fields: dict) -> dict:
    primary_id = fields.get("mechanicId")
    links = fields.get("mechanicLinks")
    if links is None and primary_id:
        links = [{"id": primary_id, "type": fields.get("mechanicType", "upgrade"), "name": fields["mechanicName"]}]
    links = links or []
    mechanic_ids = fields.get("mechanicIds") or [item["id"] for item in links]
    return {"id": fields["id"], "mechanicId": primary_id, "mechanicIds": mechanic_ids, "mechanicLinks": links, "mechanicType": fields.get("mechanicType", "upgrade"), "mechanicName": fields["mechanicName"], "question": fields["question"], "status": fields.get("status", "Unknown"), "priority": fields.get("priority", "Medium"), "kind": fields.get("kind", "missing-wiki-information"), "generated": fields.get("generated", True), "manual": fields.get("manual", False), "currentHypothesis": fields.get("currentHypothesis"), "claimIds": fields.get("claimIds", []), "evidenceIds": fields.get("evidenceIds", []), "sourceRefs": fields.get("sourceRefs", []), "createdAt": TODAY, "updatedAt": TODAY}


def generate_questions(upgrades: list[dict], classes: list[dict]) -> list[dict]:
    result = []
    seen = set()

    def add(item: dict) -> None:
        key = (item.get("mechanicId"), item["question"])
        if key not in seen:
            seen.add(key)
            result.append(question(item))

    for upgrade in upgrades:
        sig = upgrade["mechanics"]["signals"]
        behavior = upgrade["mechanics"].get("damageBehavior")
        start_count = len(result)
        base = {"mechanicId": upgrade["id"], "mechanicType": "upgrade", "mechanicName": upgrade["name"], "sourceRefs": upgrade["sourceRefs"], "priority": "Medium"}
        if sig["hasPeriodic"] and not sig["hasExplicitInterval"]:
            add({**base, "id": stable_id("question", upgrade["id"], "interval"), "question": f"How often does {upgrade['name']} activate with one stack, and how does its interval scale with additional stacks?", "priority": "High"})
        if sig["hasOutgoingDamage"] and not sig["hasDamageNumber"]:
            add({**base, "id": stable_id("question", upgrade["id"], "damage"), "question": f"What exact damage value or formula does {upgrade['name']} use, including its additional-stack scaling?", "priority": "High"})
        if sig["hasChance"] and sig["hasUnknown"]:
            add({**base, "id": stable_id("question", upgrade["id"], "chance"), "question": f"What is the exact chance or proc rule represented by the unknown value in {upgrade['name']}?", "priority": "High"})
        if sig["hasCooldown"] and sig["hasUnknown"]:
            add({**base, "id": stable_id("question", upgrade["id"], "cooldown"), "question": f"What is the exact cooldown and cooldown-scaling rule for {upgrade['name']}?", "priority": "High"})
        if sig["hasDuration"] and sig["hasUnknown"]:
            add({**base, "id": stable_id("question", upgrade["id"], "duration"), "question": f"What is the exact duration represented by the unknown value in {upgrade['name']}?"})
        if sig["hasStackScaling"] and sig["hasUnknown"]:
            add({**base, "id": stable_id("question", upgrade["id"], "stack-scaling"), "question": f"How does {upgrade['name']} scale at each additional stack, and what is its maximum stack count?", "priority": "High"})
        if re.search(r"exponential|hyperbolic", upgrade["mechanics"]["stackType"], flags=re.I) and not sig["hasFormulaLanguage"]:
            add({**base, "id": stable_id("question", upgrade["id"], "formula"), "question": f"What exact stacking formula does {upgrade['name']} use in game?"})
        if behavior and behavior.get("createsDamageInstance") is not False and behavior["canCrit"] is None:
            add({**base, "id": stable_id("question", upgrade["id"], "crit-behavior"), "question": f"Can {upgrade['name']} create a critical hit, and what is the critical-hit rule for its damage instance?", "priority": "Medium"})
        if behavior and behavior.get("createsDamageInstance") is not False and behavior["canApplyStatusEffects"] is None:
            add({**base, "id": stable_id("question", upgrade["id"], "status-behavior"), "question": f"Can {upgrade['name']} apply status effects, and what determines the chance for each applicable status?", "priority": "Medium"})
        if sig["hasUnknown"] and len(result) == start_count:
            add({**base, "id": stable_id("question", upgrade["id"], "unknown"), "question": f"What value does each X or ? placeholder in {upgrade['name']} represent?", "priority": "High"})
    for cls in classes:
        for skill in cls["skills"]:
            sig = skill["mechanics"]["signals"]
            behavior = skill["mechanics"].get("damageBehavior")
            start_count = len(result)
            base = {"mechanicId": skill["id"], "mechanicType": "class", "mechanicName": f"{cls['name']}: {skill['name']}", "sourceRefs": skill["sourceRefs"], "priority": "Medium"}
            if sig["hasOutgoingDamage"] and not sig["hasDamageNumber"] and skill["type"].lower() != "passive":
                add({**base, "id": stable_id("question", skill["id"], "damage"), "question": f"What damage value does {cls['name']}'s {skill['name']} deal?", "priority": "High"})
            if sig["hasPeriodic"] and not sig["hasExplicitInterval"]:
                add({**base, "id": stable_id("question", skill["id"], "interval"), "question": f"How often does {cls['name']}'s {skill['name']} activate?", "priority": "High"})
            if sig["hasDamage"] and not sig["hasCooldown"] and re.match(r"^(Primary|Secondary|Hand)$", skill["type"], flags=re.I) and not (cls["name"] == "Twinmage" and skill["type"].lower() == "hand"):
                add({**base, "id": stable_id("question", skill["id"], "attack-interval"), "question": f"What is the repeat interval or attack speed behavior of {cls['name']}'s {skill['name']}?"})
            if behavior and behavior.get("createsDamageInstance") is not False and behavior["canCrit"] is None:
                add({**base, "id": stable_id("question", skill["id"], "crit-behavior"), "question": f"Can {cls['name']}'s {skill['name']} critically strike, and what is the critical-hit rule for its damage instance?", "priority": "Medium"})
            if behavior and behavior.get("createsDamageInstance") is not False and behavior["canApplyStatusEffects"] is None:
                add({**base, "id": stable_id("question", skill["id"], "status-behavior"), "question": f"Can {cls['name']}'s {skill['name']} apply status effects, and what determines the chance for each applicable status?", "priority": "Medium"})
            if sig["hasUnknown"] and len(result) == start_count:
                add({**base, "id": stable_id("question", skill["id"], "unknown"), "question": f"What specific mechanic value is missing from {cls['name']}'s {skill['name']}, and how should it be modeled?", "priority": "High"})
    return result


def manual_seed() -> tuple[list[dict], list[dict], list[dict]]:
    evidence = [
        {"id": "EVID-USER-BERSERKER-MELEE-TOTAL", "mechanicId": "upgrade-crystal-of-mobility-berserker-s-soul-melee", "mechanicName": "Berserker's Soul (Melee)", "questionId": "question-upgrade-crystal-of-mobility-berserker-s-soul-melee-stack-scaling", "questionIds": ["question-upgrade-crystal-of-mobility-boberserker-s-soul-melee-stack-scaling", "question-upgrade-crystal-of-mobility-berserker-s-soul-melee-stack-scaling"], "type": "user observation", "source": "User research note handoff", "date": TODAY, "originalInformation": "The displayed per-stack numbers may actually represent approximately 45% Overall Damage, 90% Attack Speed, and 50% Health Regeneration reduction at 70 stacks, divided by 70 for each stack.", "interpretation": "User hypothesis: approximately +0.6429% Overall Damage, +1.2857% Attack Speed, and -0.7143% Health Regeneration per stack. This is close to the Japanese wiki's reported values, but is not itself a confirmed measurement.", "supportsClaimIds": ["CLAIM-USER-BERSERKER-MELEE-TOTAL"], "contradictsClaimIds": [], "reliabilityNotes": "User interpretation from the page note; requires controlled measurements at known stack counts.", "attachments": []},
        {"id": "EVID-USER-BERSERKER-RANGED-TOTAL", "mechanicId": "upgrade-crystal-of-mobility-berserker-s-soul-ranged", "mechanicName": "Berserker's Soul (Ranged)", "questionId": "question-upgrade-crystal-of-mobility-berserker-s-soul-ranged-stack-scaling", "questionIds": ["question-upgrade-crystal-of-mobility-berserker-s-soul-ranged-stack-scaling"], "type": "user observation", "source": "User research note handoff", "date": TODAY, "originalInformation": "The displayed per-stack numbers may actually represent approximately 45% Overall Damage, 90% Attack Speed, and 2% Projectile Spread at 70 stacks, divided by 70 for each stack.", "interpretation": "User hypothesis: approximately +0.6429% Overall Damage, +1.2857% Attack Speed, and +0.0286% Projectile Spread per stack. The Japanese wiki reports different damage and Attack Speed totals, so both remain separate claims.", "supportsClaimIds": ["CLAIM-USER-BERSERKER-RANGED-TOTAL"], "contradictsClaimIds": [], "reliabilityNotes": "User interpretation from the page note; conflicts with the Japanese per-stack report and requires controlled measurements.", "attachments": []},
        {"id": "EVID-USER-BIG-LAZY-STACKS", "mechanicId": "upgrade-crystal-of-perseverance-big-and-lazy", "mechanicName": "Big and Lazy", "questionId": "Q-USER-BIG-LAZY-VITALITY", "questionIds": ["Q-USER-BIG-LAZY-VITALITY"], "type": "user observation", "source": "User research note handoff", "date": TODAY, "originalInformation": "Big and Lazy appears to multiply the total regeneration value after Vitality and other regeneration effects by 3 at 1 stack, 3.5 at 2 stacks, and so on. This multiplier is not reflected in the displayed regeneration value but affects regeneration directly.", "interpretation": "User hypothesis: the effective regeneration multiplier may be 2.5 + 0.5 × stack count while stationary, applied after other regeneration modifiers. This needs an isolated comparison of displayed and observed regeneration.", "supportsClaimIds": ["CLAIM-USER-BIG-LAZY-STACKS"], "contradictsClaimIds": [], "reliabilityNotes": "User observation; exact order of operations and display behavior remain unverified.", "attachments": []},
        {"id": "EVID-USER-BIG-ROUND-STACKING", "mechanicId": "upgrade-crystal-of-perseverance-big-and-round", "mechanicName": "Big and Round", "questionId": None, "questionIds": [], "type": "user observation", "source": "User research note handoff", "date": TODAY, "originalInformation": "Big and Round appears to stack linearly as its description states.", "interpretation": "User observation supporting the English description's linear stacking interpretation; no separate unresolved question was created because the note treats this mechanic as sufficiently clear.", "supportsClaimIds": ["CLAIM-USER-BIG-ROUND-STACKING"], "contradictsClaimIds": [], "reliabilityNotes": "Reported user observation, not a controlled confirmation.", "attachments": []},
        {"id": "EVID-USER-BIG-WRATHFUL-STACKING", "mechanicId": "upgrade-crystal-of-perseverance-big-and-wrathful", "mechanicName": "Big and Wrathful", "questionId": "Q-USER-BIG-WRATHFUL-STACKING", "questionIds": ["Q-USER-BIG-WRATHFUL-STACKING"], "type": "user observation", "source": "User research note handoff", "date": TODAY, "originalInformation": "It is unclear whether Big and Wrathful's damage dealt at LOW HP is an additional multiplier or simply adds 50% to the overall damage value. It probably stacks linearly.", "interpretation": "User hypothesis: the +50% LOW HP damage effect probably stacks linearly, but the operation may be additive to Overall Damage or a separate multiplier.", "supportsClaimIds": ["CLAIM-USER-BIG-WRATHFUL-STACKING"], "contradictsClaimIds": [], "reliabilityNotes": "User hypothesis; needs tests comparing base damage, Overall Damage modifiers, and multiple Big and Wrathful stacks at LOW HP.", "attachments": []},
        {"id": "EVID-USER-001", "mechanicId": "external-shedding", "mechanicName": "Shedding", "questionId": "Q-USER-SHEDDING", "type": "user observation", "source": "User research note", "date": TODAY, "originalInformation": "Experimental observations appear potentially closer to approximately 7% than the previously interpreted 5% value.", "interpretation": "Preliminary observation; not a confirmed value and not an English-wiki citation.", "supportsClaimIds": ["CLAIM-SHEDDING-7"], "contradictsClaimIds": ["CLAIM-SHEDDING-5"], "reliabilityNotes": "Uncontrolled initial observation; needs an isolated test.", "attachments": []},
        {"id": "EVID-USER-002", "mechanicId": "external-big-and-lazy-vitality", "mechanicName": "Big and Lazy × Vitality", "questionId": "Q-USER-BIG-LAZY-VITALITY", "type": "user observation", "source": "User research note", "date": TODAY, "originalInformation": "The interaction appears to be multiplicative in some way.", "interpretation": "Hypothesis only; the exact order and cap behavior remain unknown.", "supportsClaimIds": ["CLAIM-BIG-LAZY-VITALITY-MULT"], "contradictsClaimIds": [], "reliabilityNotes": "Needs tests with neither effect, each effect individually, and both together.", "attachments": []},
        {"id": "EVID-USER-TWINMAGE-RATE", "mechanicId": "class-twinmage", "mechanicName": "Twinmage", "questionId": "Q-USER-TWINMAGE-HAND-RATE", "type": "user-reported wiki reading", "source": "User-provided reading of the English Twinmage wiki", "date": TODAY, "originalInformation": "0.8 attack speed per hand when using both hands and 1.4 attacks per second when only using both hands. The values apply to all six elemental hands.", "interpretation": "Stored as 0.8 attacks per second per hand with both hands active and 1.4 attacks per second per hand with a single hand active. The second state wording needs confirmation.", "supportsClaimIds": ["CLAIM-TWINMAGE-HAND-RATE"], "contradictsClaimIds": [], "reliabilityNotes": "The retrieved raw page preserves the qualitative one-hand +75% base-speed rule but not these literal numbers; retain as reported until the numeric wording is independently checked.", "sourceRefs": [{"sourceId": "wiki-twinmage", "sourcePage": "Twinmage", "section": "Skills", "retrievedAt": TODAY, "excerpt": "Firing only one hand will increase your attack speed by 75%", "derivedFields": ["qualitative one-hand attack-speed rule"]}], "attachments": []},
        {"id": "EVID-JA-TWINMAGE-HANDS", "mechanicId": "class-twinmage", "mechanicName": "Twinmage", "questionId": "Q-USER-TWINMAGE-HAND-RATE", "questionIds": ["Q-USER-TWINMAGE-HAND-RATE", "Q-USER-TWINMAGE-MASTERY-STATUS-CHANCE", "Q-USER-TWINMAGE-SINISTRA-STATUS-DAMAGE", "Q-USER-TWINMAGE-DEXTRA-STATUS-DAMAGE"], "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / ツインメイジ", "date": TODAY, "originalInformation": "連射速度  | 0.8/s（片手攻撃中は1.4/s）\n片方のみ攻撃中は攻撃速度が75%増加する。\nファイヤーボール：10%の確率で炎上を付与する。\nフロストミサイル：10%の確率で凍結を付与する。\nサンダーボルト：10%の確率で麻痺を付与する。\nウィンドブレード：10%の確率で出血を付与する。\nライトボール：10%の確率で弱体化を付与する。\nシャドウミサイル：10%の確率で崩壊を付与する。", "translation": "Fire rate: 0.8/s (1.4/s while attacking with one hand). While attacking with only one hand, attack speed increases by 75%. Each listed elemental hand attack has a 10% chance to apply its associated status effect.", "interpretation": "The Japanese page independently records the reported Twinmage rates and gives 10% status-effect chances for the base elemental hand attacks. It does not state the status chance of Twinmage: Mastery or whether Sinistra/Dextra changes status damage.", "supportsClaimIds": ["CLAIM-TWINMAGE-HAND-RATE"], "contradictsClaimIds": [], "reliabilityNotes": "Japanese wiki source; translated for this record. The Mastery and hand-modifier interaction remains unresolved.", "sourceRefs": [japanese_source_ref("ツインメイジ", "PRIMARY & SECONDARY", "連射速度  | 0.8/s（片手攻撃中は1.4/s）\n片方のみ攻撃中は攻撃速度が75%増加する。\n各属性攻撃の状態異常付与確率は10%。", "Fire rate: 0.8/s (1.4/s while attacking with one hand). While attacking with only one hand, attack speed increases by 75%. The listed elemental attacks each have a 10% status-effect chance.", ["reported hand rates", "base hand status-effect chance"])], "attachments": []},
        {"id": "EVID-JA-TWINMAGE-MASTERY", "mechanicId": "upgrade-twinmage-twinmage-mastery", "mechanicName": "Twinmage: Mastery", "questionId": "question-upgrade-twinmage-twinmage-mastery-stack-scaling", "questionIds": ["question-upgrade-twinmage-twinmage-mastery-stack-scaling", "Q-USER-TWINMAGE-MASTERY-STATUS-CHANCE", "Q-USER-TWINMAGE-SINISTRA-MASTERY", "Q-USER-TWINMAGE-DEXTRA-MASTERY"], "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / ツインメイジ", "date": TODAY, "originalInformation": "スキルでダメージを与えた時、半径?M(+?M)の爆発が起き、25%のダメージを与える。", "translation": "When a skill deals damage, an explosion occurs with a radius of ? m (+? m), dealing 25% of the damage.", "interpretation": "This confirms the 25% splash-damage ratio and preserves the base/per-stack radius as unknown. It does not state whether the explosion can crit, apply status effects, or inherit a hand's status chance.", "supportsClaimIds": [], "contradictsClaimIds": [], "reliabilityNotes": "Japanese wiki source; translation is an interpretation aid, not a replacement for the original.", "sourceRefs": [japanese_source_ref("ツインメイジ", "固有アップグレード / ツインメイジ：極意", "スキルでダメージを与えた時、半径?M(+?M)の爆発が起き、25%のダメージを与える。", "When a skill deals damage, an explosion occurs with a radius of ? m (+? m), dealing 25% of the damage.", ["splash ratio", "base radius", "per-stack radius"])], "attachments": []},
        {"id": "EVID-JA-TWINMAGE-HAND-MODIFIERS", "mechanicId": "upgrade-twinmage-twinmage-sinistra", "mechanicName": "Twinmage: Sinistra / Dextra", "questionId": "Q-USER-TWINMAGE-SINISTRA-MASTERY", "questionIds": ["Q-USER-TWINMAGE-SINISTRA-MASTERY", "Q-USER-TWINMAGE-SINISTRA-CHARGED-STRIKE", "Q-USER-TWINMAGE-SINISTRA-STATUS-DAMAGE", "Q-USER-TWINMAGE-DEXTRA-MASTERY", "Q-USER-TWINMAGE-DEXTRA-CHARGED-STRIKE", "Q-USER-TWINMAGE-DEXTRA-STATUS-DAMAGE"], "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / ツインメイジ", "date": TODAY, "originalInformation": "ツインメイジ：シニストラ：左手のダメージ+5% (+5%)、左手の攻撃速度+5% (+5%)、右手のダメージ -3% (-3%)、右手の攻撃速度 -3% (-3%)。\nツインメイジ：デクストラ：右手のダメージ+5% (+5%)、右手の攻撃速度+5% (+5%)、左手のダメージ -3% (-3%)、左手の攻撃速度 -3% (-3%)。\n片手のみの強化であり、この上昇分は通常の計算とは異なりグループBの為、グループAとは乗算で計算される。", "translation": "Sinistra: left-hand damage +5% per stack and left-hand attack speed +5%; right-hand damage -3% and right-hand attack speed -3%. Dextra reverses those hand assignments. These are one-hand-only enhancements, and their increases are Group B, calculated multiplicatively with Group A rather than by the normal calculation.", "interpretation": "The page confirms the hand-specific modifiers and their stacking group. It does not explicitly say whether those modifiers affect Mastery splash damage, Charged Strike explosions, or status-effect damage.", "supportsClaimIds": [], "contradictsClaimIds": [], "reliabilityNotes": "Relevant context, not a direct resolution of the interaction questions.", "sourceRefs": [japanese_source_ref("ツインメイジ", "固有アップグレード / シニストラ・デクストラ", "片手のみの強化であり、この上昇分は通常の計算とは異なりグループBの為、グループAとは乗算で計算される。", "These are one-hand-only enhancements, and their increases are Group B, calculated multiplicatively with Group A rather than by the normal calculation.", ["hand-specific modifiers", "stacking group"])], "attachments": []},
        {"id": "EVID-JA-CHARGED-STRIKE", "mechanicId": "upgrade-chrono-wizard-charged-strike", "mechanicName": "Charged Strike", "questionId": "Q-USER-CHARGED-STRIKE-DAMAGE", "questionIds": ["Q-USER-CHARGED-STRIKE-DAMAGE", "Q-USER-CHARGED-STRIKE-STACK", "Q-USER-CHARGED-STRIKE-OTHER", "Q-USER-TWINMAGE-SINISTRA-CHARGED-STRIKE", "Q-USER-TWINMAGE-DEXTRA-CHARGED-STRIKE"], "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / アップグレード", "date": TODAY, "originalInformation": "チャージドストライク：クリティカルヒット時に25(+10)物理ダメージの爆発が発生する。\nクリティカルヒット率 -5% (-5%)\n備考：与・物理ダメージの影響を受ける。", "translation": "Charged Strike: On a critical hit, an explosion dealing 25 (+10) Physical damage occurs. Critical-hit rate -5% per stack. Note: it is affected by dealt Physical Damage.", "interpretation": "This is a direct conflict with the English wiki's X placeholders for the explosion base and per-stack damage. The Japanese note supports Physical Damage scaling, but does not explicitly resolve whether Sinistra/Dextra hand-specific damage modifiers are included.", "supportsClaimIds": ["CLAIM-JA-CHARGED-STRIKE-DAMAGE", "CLAIM-JA-CHARGED-STRIKE-STACK"], "contradictsClaimIds": [], "reliabilityNotes": "Japanese and English pages disagree on the numeric values; retain both as source-specific claims.", "sourceRefs": [japanese_source_ref("アップグレード", "クロノウィザード / チャージドストライク", "クリティカルヒット時に25(+10)物理ダメージの爆発が発生する。\n備考：与・物理ダメージの影響を受ける。", "On a critical hit, an explosion dealing 25 (+10) Physical damage occurs. Note: it is affected by dealt Physical Damage.", ["base explosion damage", "per-stack damage", "physical-damage scaling"])], "attachments": []},
        {"id": "EVID-JA-BIG-LAZY", "mechanicId": "upgrade-crystal-of-perseverance-big-and-lazy", "mechanicName": "Big and Lazy / Vitality", "questionId": "Q-USER-BIG-LAZY-VITALITY", "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / アップグレード", "date": TODAY, "originalInformation": "自然回復量×(1+巨大な怠惰スタック数)、これ自体に自然回復量はない。\n移動とは移動入力を指しており、慣性やスキルによる移動は対象とならない。", "translation": "Health regeneration is multiplied by (1 + the number of Big and Lazy stacks); Big and Lazy itself does not provide regeneration. Movement means movement input, so inertia and skill-based movement do not count.", "interpretation": "This supports a multiplicative interaction with an existing regeneration source such as Vitality, but it does not state the exact order or cap behavior when other modifiers are present.", "supportsClaimIds": ["CLAIM-BIG-LAZY-VITALITY-MULT"], "contradictsClaimIds": [], "reliabilityNotes": "Japanese source gives a formula for Big and Lazy; the full Vitality interaction remains a research question.", "sourceRefs": [japanese_source_ref("アップグレード", "忍耐のクリスタル / 巨大な怠惰", "自然回復量×(1+巨大な怠惰スタック数)、これ自体に自然回復量はない。", "Health regeneration is multiplied by (1 + the number of Big and Lazy stacks); Big and Lazy itself does not provide regeneration.", ["Big and Lazy formula", "multiplicative interaction"])], "attachments": []},
        {"id": "EVID-JA-BENISON", "mechanicId": "upgrade-crystal-of-perseverance-benison-of-purification", "mechanicName": "Benison of Purification", "questionId": "Q-USER-BENISON-ONE-STACK-INTERVAL", "questionIds": ["Q-USER-BENISON-ONE-STACK-INTERVAL", "Q-USER-BENISON-FREQUENCY-SCALING", "Q-USER-BENISON-DAMAGE", "Q-USER-BENISON-OTHER-SCALING", "Q-USER-ATTACK-SPEED-STATUS-INTERACTION"], "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / アップグレード", "date": TODAY, "originalInformation": "定期的に、64メートル以内の最も近い敵へ?ダメージを与える聖属性魔法を発射する。\n複数取得すると発射間隔が短縮される。", "translation": "Periodically fires a Holy magic projectile at the nearest enemy within 64 meters, dealing ? damage. With multiple copies, the firing interval is shortened.", "interpretation": "The Japanese page confirms that additional stacks shorten the interval, but leaves the one-stack interval and projectile damage unknown. It does not state whether Attack Speed affects the proc or its status-effect chance.", "supportsClaimIds": [], "contradictsClaimIds": [], "reliabilityNotes": "Partial answer only; the Japanese placeholder remains explicit.", "sourceRefs": [japanese_source_ref("アップグレード", "忍耐のクリスタル / 聖なる祝福", "定期的に、64メートル以内の最も近い敵へ?ダメージを与える聖属性魔法を発射する。\n複数取得すると発射間隔が短縮される。", "Periodically fires a Holy magic projectile at the nearest enemy within 64 meters, dealing ? damage. With multiple copies, the firing interval is shortened.", ["interval scaling", "damage remains unknown"])], "attachments": []},
        {"id": "EVID-JA-CURSE-OF-WRATH", "mechanicId": "upgrade-crystal-of-perseverance-curse-of-wrath", "mechanicName": "Curse of Wrath", "questionId": "question-upgrade-crystal-of-perseverance-curse-of-wrath-interval", "questionIds": ["question-upgrade-crystal-of-perseverance-curse-of-wrath-interval", "question-upgrade-crystal-of-perseverance-curse-of-wrath-damage", "question-upgrade-crystal-of-perseverance-curse-of-wrath-stack-scaling", "Q-USER-ATTACK-SPEED-STATUS-INTERACTION"], "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / アップグレード", "date": TODAY, "originalInformation": "4秒毎に、半径32メートル以内の最も近い敵へ30ダメージを与える闇属性魔法を発射する。\nクリティカル判定があり、?%の確率で崩壊を付与する。\n複数取得すると発射間隔が短縮される。", "translation": "Every 4 seconds, fires a Shadow magic projectile at the nearest enemy within a 32-meter radius, dealing 30 damage. It has a critical-hit check and a ?% chance to apply BREACHED. With multiple copies, the firing interval is shortened.", "interpretation": "This conflicts with the English page's 25 (+X) damage wording and supplies a four-second base interval. The status chance remains unknown, while the Japanese page explicitly says a critical-hit check exists.", "supportsClaimIds": ["CLAIM-JA-CURSE-OF-WRATH"], "contradictsClaimIds": [], "reliabilityNotes": "Japanese and English numeric damage values conflict; do not merge them into one answer.", "sourceRefs": [japanese_source_ref("アップグレード", "忍耐のクリスタル / 憤怒の呪い", "4秒毎に、半径32メートル以内の最も近い敵へ30ダメージを与える闇属性魔法を発射する。\nクリティカル判定があり、?%の確率で崩壊を付与する。", "Every 4 seconds, fires a Shadow magic projectile at the nearest enemy within a 32-meter radius, dealing 30 damage. It has a critical-hit check and a ?% chance to apply BREACHED.", ["base interval", "base damage", "critical check", "status chance remains unknown"])], "attachments": []},
        {"id": "EVID-JA-THUNDER-AURA", "mechanicId": "upgrade-crystal-of-mobility-thunder-aura", "mechanicName": "Thunder Aura", "questionId": "question-upgrade-crystal-of-mobility-thunder-aura-interval", "questionIds": ["question-upgrade-crystal-of-mobility-thunder-aura-interval", "question-upgrade-crystal-of-mobility-thunder-aura-damage", "question-upgrade-crystal-of-mobility-thunder-aura-stack-scaling", "Q-USER-ATTACK-SPEED-STATUS-INTERACTION"], "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / アップグレード", "date": TODAY, "originalInformation": "毎秒、4m(+?m)内にいる敵へ23(+?)雷属性ダメージを与える\n与ダメ減少後のダメージ。クリティカル判定があり、確率で麻痺を付与する。\n与・雷属性ダメージの影響を受ける。", "translation": "Every second, deals 23 (+?) Electric damage to enemies within 4 m (+? m). This is damage after the dealt-damage reduction. It has a critical-hit check and can apply PARALYZED with an unspecified chance. It is affected by dealt Electric damage.", "interpretation": "This supplies a one-second interval, 4 m base radius, 23 base damage, critical-hit check, and Electric Damage scaling. It conflicts with the English page's 25 base damage and leaves stack/radius/status chance values incomplete.", "supportsClaimIds": ["CLAIM-JA-THUNDER-AURA"], "contradictsClaimIds": [], "reliabilityNotes": "Japanese and English pages differ on base damage; preserve both.", "sourceRefs": [japanese_source_ref("アップグレード", "モビリティのクリスタル / サンダーオーラ", "毎秒、4m(+?m)内にいる敵へ23(+?)雷属性ダメージを与える。\nクリティカル判定があり、確率で麻痺を付与する。", "Every second, deals 23 (+?) Electric damage to enemies within 4 m (+? m). It has a critical-hit check and can apply PARALYZED with an unspecified chance.", ["base interval", "radius", "base damage", "critical check", "status chance remains vague"])], "attachments": []},
        {"id": "EVID-JA-BERSERKER-MELEE", "mechanicId": "upgrade-crystal-of-mobility-berserker-s-soul-melee", "mechanicName": "Berserker's Soul (Melee)", "questionId": "question-upgrade-crystal-of-mobility-berserker-s-soul-melee-stack-scaling", "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / アップグレード", "date": TODAY, "originalInformation": "ダメージを与えると、バーサーカーソウルを最大70スタックまで獲得する。\n1スタックにつき与ダメージ +0.64%\n1スタックにつき攻撃速度 +1.28%\n1スタックにつき自然回復量 -0.71%\nドットダメージでは貯まらない。", "translation": "Dealing damage grants Berserker's Soul, up to 70 stacks. Each stack gives +0.64% dealt damage, +1.28% Attack Speed, and -0.71% regeneration. Damage-over-time does not build stacks.", "interpretation": "This supplies a concrete maximum stack count and per-stack values that differ from the English page's X placeholders.", "supportsClaimIds": ["CLAIM-JA-BERSERKER-MELEE"], "contradictsClaimIds": [], "reliabilityNotes": "Japanese source; exact game-version applicability should still be checked.", "sourceRefs": [japanese_source_ref("アップグレード", "モビリティのクリスタル / バーサーカーソウル（近接）", "最大70スタック。1スタックにつき与ダメージ+0.64%、攻撃速度+1.28%、自然回復量-0.71%。ドットダメージでは貯まらない。", "Maximum 70 stacks. Each stack gives +0.64% dealt damage, +1.28% Attack Speed, and -0.71% regeneration. Damage-over-time does not build stacks.", ["maximum stacks", "per-stack scaling", "DoT exclusion"])], "attachments": []},
        {"id": "EVID-JA-BERSERKER-RANGED", "mechanicId": "upgrade-crystal-of-mobility-berserker-s-soul-ranged", "mechanicName": "Berserker's Soul (Ranged)", "questionId": "question-upgrade-crystal-of-mobility-berserker-s-soul-ranged-stack-scaling", "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / アップグレード", "date": TODAY, "originalInformation": "ダメージを与えると、バーサーカーソウルを最大70スタックまで獲得する。\n1スタックにつき与ダメージ +0.32%\n1スタックにつき攻撃速度 +0.64%\n1スタックにつき弾の拡散率 +0.0285%\nドットダメージでは貯まらない。", "translation": "Dealing damage grants Berserker's Soul, up to 70 stacks. Each stack gives +0.32% dealt damage, +0.64% Attack Speed, and +0.0285% projectile spread. Damage-over-time does not build stacks.", "interpretation": "This supplies a concrete maximum stack count and per-stack values that differ from the English page's X placeholders.", "supportsClaimIds": ["CLAIM-JA-BERSERKER-RANGED"], "contradictsClaimIds": [], "reliabilityNotes": "Japanese source; exact game-version applicability should still be checked.", "sourceRefs": [japanese_source_ref("アップグレード", "モビリティのクリスタル / バーサーカーソウル（遠距離）", "最大70スタック。1スタックにつき与ダメージ+0.32%、攻撃速度+0.64%、弾の拡散率+0.0285%。ドットダメージでは貯まらない。", "Maximum 70 stacks. Each stack gives +0.32% dealt damage, +0.64% Attack Speed, and +0.0285% projectile spread. Damage-over-time does not build stacks.", ["maximum stacks", "per-stack scaling", "DoT exclusion"])], "attachments": []},
        {"id": "EVID-JA-SPELLSWORD-PIERCING", "mechanicId": "skill-spellsword-piercing-strike", "mechanicName": "Spellsword: Piercing Strike", "questionId": "question-skill-spellsword-piercing-strike-unknown", "questionIds": ["question-skill-spellsword-piercing-strike-unknown", "question-skill-spellsword-piercing-strike-attack-interval"], "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / スペルソード", "date": TODAY, "originalInformation": "チャージ時間  | 0.170 ～ 5.075秒（攻撃速度1%毎に約1.5%短縮）\nダメージ  | 87 ～ 170\nクールタイム  | 1.5秒\n最大50%の確率で出血を付与する。\nチャージ速度は攻撃速度でスケールする。", "translation": "Charge time: 0.170–5.075 seconds, shortened by approximately 1.5% per 1% Attack Speed. Damage: 87–170. Cooldown: 1.5 seconds. Bleeding can be applied with up to a 50% chance. Charge speed scales with Attack Speed.", "interpretation": "This supplies concrete charge-time, damage, cooldown, and status-chance information for the English placeholders/attack-speed question.", "supportsClaimIds": ["CLAIM-JA-SPELLSWORD-PIERCING"], "contradictsClaimIds": [], "reliabilityNotes": "Japanese source; the page presents the values as guide information rather than an experimentally verified record.", "sourceRefs": [japanese_source_ref("スペルソード", "SECONDARY / ピアシング・ストライク", "チャージ時間 0.170～5.075秒（攻撃速度1%毎に約1.5%短縮）。ダメージ87～170。クールタイム1.5秒。最大50%の確率で出血を付与する。", "Charge time 0.170–5.075 seconds (approximately 1.5% shorter per 1% Attack Speed), damage 87–170, cooldown 1.5 seconds, and up to a 50% Bleeding chance.", ["charge time", "damage", "cooldown", "status chance", "Attack Speed scaling"])], "attachments": []},
        {"id": "EVID-JA-SPELLSWORD-WHIRLWIND", "mechanicId": "upgrade-spellsword-spellsword-whirlwind", "mechanicName": "Spellsword: Whirlwind", "questionId": "question-upgrade-spellsword-spellsword-whirlwind-damage", "questionIds": ["question-upgrade-spellsword-spellsword-whirlwind-damage", "question-upgrade-spellsword-spellsword-whirlwind-stack-scaling"], "type": "Japanese wiki", "source": "Ecliptica日本語 Wiki* / スペルソード", "date": TODAY, "originalInformation": "旋風は球状内の敵に約0.1秒毎にダメージを与える為、大型の敵にはとんでもないダメージが入る。\nまた出血確率も継承しており、ヒット数が桁違いになる事から出血付与も容易となる。\n旋風のダメージ自体はクリティカル判定が一切ない。", "translation": "The Whirlwind deals damage to enemies inside the sphere approximately every 0.1 seconds, causing enormous damage to large enemies. It inherits the Bleeding chance, and the much higher hit count makes Bleeding easy to apply. The Whirlwind's damage itself never has a critical-hit check.", "interpretation": "This supplies a tick interval and explicitly says the Whirlwind cannot critically strike, but it does not give the damage per tick or a stack formula.", "supportsClaimIds": ["CLAIM-JA-SPELLSWORD-WHIRLWIND"], "contradictsClaimIds": [], "reliabilityNotes": "Japanese source; damage magnitude remains unresolved.", "sourceRefs": [japanese_source_ref("スペルソード", "固有アップグレード / スペルソード：旋風", "旋風は球状内の敵に約0.1秒毎にダメージを与える。\n出血確率も継承する。\n旋風のダメージ自体はクリティカル判定が一切ない。", "The Whirlwind deals damage approximately every 0.1 seconds, inherits Bleeding chance, and its damage never has a critical-hit check.", ["tick interval", "Bleeding inheritance", "cannot crit"])], "attachments": []},
        # Correct bilingual records are appended after the original seed entries so
        # dedupe() replaces any older seed while preserving stable record IDs.
        japanese_evidence("EVID-JA-TWINMAGE-HANDS", "class-twinmage", "Twinmage", "Q-USER-TWINMAGE-HAND-RATE", ["Q-USER-TWINMAGE-HAND-RATE", "Q-USER-TWINMAGE-MASTERY-STATUS-CHANCE", "Q-USER-TWINMAGE-SINISTRA-STATUS-DAMAGE", "Q-USER-TWINMAGE-DEXTRA-STATUS-DAMAGE"], "\u30c4\u30a4\u30f3\u30e1\u30a4\u30b8", "PRIMARY & SECONDARY", "\u9023\u5c04\u901f\u5ea6 | 0.8/s\uff08\u7247\u624b\u653b\u6483\u4e2d\u306f1.4/s\uff09\n\u7247\u65b9\u306e\u307f\u653b\u6483\u4e2d\u306f\u653b\u6483\u901f\u5ea6\u304c75%\u5897\u52a0\u3059\u308b\u3002\n\u30d5\u30a1\u30a4\u30a2\u30dc\u30fc\u30eb\uff1a10%\u306e\u78ba\u7387\u3067\u71c3\u713c\n\u30d5\u30ed\u30b9\u30c8\u30df\u30b5\u30a4\u30eb\uff1a10%\u306e\u78ba\u7387\u3067\u51cd\u7d50\n\u30b5\u30f3\u30c0\u30fc\u30dc\u30eb\u30c8\uff1a10%\u306e\u78ba\u7387\u3067\u9ebb\u75fa\n\u30a6\u30a3\u30f3\u30c9\u30d6\u30ec\u30fc\u30c9\uff1a10%\u306e\u78ba\u7387\u3067\u51fa\u8840\n\u30e9\u30a4\u30c8\u30dc\u30fc\u30eb\uff1a10%\u306e\u78ba\u7387\u3067\u5f31\u4f53\u5316\n\u30b7\u30e3\u30c9\u30a6\u30df\u30b5\u30a4\u30eb\uff1a10%\u306e\u78ba\u7387\u3067\u5d29\u58ca", "Fire rate: 0.8/s (1.4/s while attacking with one hand). While attacking with only one hand, attack speed increases by 75%. Each listed elemental hand attack has a 10% chance to apply its associated status effect.", "The Japanese page independently records the reported Twinmage rates and gives 10% status-effect chances for the base elemental hand attacks. It does not state the status chance of Twinmage: Mastery or whether Sinistra/Dextra changes status damage.", ["CLAIM-TWINMAGE-HAND-RATE"], ["reported hand rates", "base hand status-effect chance"], "Japanese wiki source; translated for this record. The Mastery and hand-modifier interaction remains unresolved."),
        japanese_evidence("EVID-JA-TWINMAGE-MASTERY", "upgrade-twinmage-twinmage-mastery", "Twinmage: Mastery", "question-upgrade-twinmage-twinmage-mastery-stack-scaling", ["question-upgrade-twinmage-twinmage-mastery-stack-scaling", "Q-USER-TWINMAGE-MASTERY-STATUS-CHANCE", "Q-USER-TWINMAGE-SINISTRA-MASTERY", "Q-USER-TWINMAGE-DEXTRA-MASTERY"], "\u30c4\u30a4\u30f3\u30e1\u30a4\u30b8", "\u30c4\u30a4\u30f3\u30e1\u30a4\u30b8\uff1a\u30de\u30b9\u30bf\u30ea\u30fc", "\u30b9\u30ad\u30eb\u3067\u30c0\u30e1\u30fc\u30b8\u3092\u4e0e\u3048\u305f\u6642\u3001\u534a\u5f84?M(+?M)\u306e\u7206\u767a\u304c\u8d77\u304d\u300125%\u306e\u30c0\u30e1\u30fc\u30b8\u3092\u4e0e\u3048\u308b\u3002", "When a skill deals damage, an explosion occurs with a radius of ? m (+? m), dealing 25% of the damage.", "This preserves the 25% splash-damage ratio and keeps the base/per-stack radius unknown. It does not state whether the explosion can crit, apply status effects, or inherit a hand's status chance.", [], ["splash ratio", "base radius", "per-stack radius"], "Japanese wiki source; translation is an interpretation aid, not a replacement for the original."),
        japanese_evidence("EVID-JA-TWINMAGE-HAND-MODIFIERS", "upgrade-twinmage-twinmage-sinistra", "Twinmage: Sinistra / Dextra", "Q-USER-TWINMAGE-SINISTRA-MASTERY", ["Q-USER-TWINMAGE-SINISTRA-MASTERY", "Q-USER-TWINMAGE-SINISTRA-CHARGED-STRIKE", "Q-USER-TWINMAGE-SINISTRA-STATUS-DAMAGE", "Q-USER-TWINMAGE-DEXTRA-MASTERY", "Q-USER-TWINMAGE-DEXTRA-CHARGED-STRIKE", "Q-USER-TWINMAGE-DEXTRA-STATUS-DAMAGE"], "\u30c4\u30a4\u30f3\u30e1\u30a4\u30b8", "\u30b7\u30cb\u30b9\u30c8\u30e9 / \u30c7\u30af\u30b9\u30c8\u30e9", "\u30c4\u30a4\u30f3\u30e1\u30a4\u30b8\uff1a\u30b7\u30cb\u30b9\u30c8\u30e9\uff1a\u5de6\u624b\u306e\u30c0\u30e1\u30fc\u30b8+5% (+5%)\u3001\u5de6\u624b\u306e\u653b\u6483\u901f\u5ea6+5% (+5%)\u3001\u53f3\u624b\u306e\u30c0\u30e1\u30fc\u30b8-3% (-3%)\u3001\u53f3\u624b\u306e\u653b\u6483\u901f\u5ea6-3% (-3%)\u3002\n\u30c4\u30a4\u30f3\u30e1\u30a4\u30b8\uff1a\u30c7\u30af\u30b9\u30c8\u30e9\uff1a\u53f3\u624b\u306e\u30c0\u30e1\u30fc\u30b8+5% (+5%)\u3001\u53f3\u624b\u306e\u653b\u6483\u901f\u5ea6+5% (+5%)\u3001\u5de6\u624b\u306e\u30c0\u30e1\u30fc\u30b8-3% (-3%)\u3001\u5de6\u624b\u306e\u653b\u6483\u901f\u5ea6-3% (-3%)\u3002\n\u7247\u624b\u306e\u307f\u306e\u5f37\u5316\u3067\u3042\u308a\u3001\u30b0\u30eb\u30fc\u30d7B\u306b\u5c5e\u3057\u3001\u30b0\u30eb\u30fc\u30d7A\u3068\u306f\u4e57\u7b97\u3067\u8a08\u7b97\u3055\u308c\u308b\u3002", "Sinistra: left-hand damage +5% per stack and left-hand attack speed +5%; right-hand damage -3% and right-hand attack speed -3%. Dextra reverses those hand assignments. These are one-hand-only enhancements, and their increases are Group B, calculated multiplicatively with Group A rather than by the normal calculation.", "The page confirms the hand-specific modifiers and their stacking group. It does not explicitly say whether those modifiers affect Mastery splash damage, Charged Strike explosions, or status-effect damage.", [], ["hand-specific modifiers", "stacking group"], "Relevant context, not a direct resolution of the interaction questions."),
        japanese_evidence("EVID-JA-CHARGED-STRIKE", "upgrade-chrono-wizard-charged-strike", "Charged Strike", "Q-USER-CHARGED-STRIKE-DAMAGE", ["Q-USER-CHARGED-STRIKE-DAMAGE", "Q-USER-CHARGED-STRIKE-STACK", "Q-USER-CHARGED-STRIKE-OTHER", "Q-USER-TWINMAGE-SINISTRA-CHARGED-STRIKE", "Q-USER-TWINMAGE-DEXTRA-CHARGED-STRIKE"], "\u30a2\u30c3\u30d7\u30b0\u30ec\u30fc\u30c9", "\u30c1\u30e3\u30fc\u30b8\u30c9\u30b9\u30c8\u30e9\u30a4\u30af", "\u30af\u30ea\u30c6\u30a3\u30ab\u30eb\u30d2\u30c3\u30c8\u6642\u306b25(+10)\u7269\u7406\u30c0\u30e1\u30fc\u30b8\u306e\u7206\u767a\u304c\u767a\u751f\u3059\u308b\u3002\n\u30af\u30ea\u30c6\u30a3\u30ab\u30eb\u30d2\u30c3\u30c8\u7387 -5% (-5%)\n\u5099\u8003\uff1a\u4e0e\u30fb\u7269\u7406\u30c0\u30e1\u30fc\u30b8\u306e\u5f71\u97ff\u3092\u53d7\u3051\u308b\u3002", "On a critical hit, an explosion dealing 25 (+10) Physical damage occurs. Critical-hit rate is -5% (-5%) per stack. Note: it is affected by dealt Physical Damage.", "This directly conflicts with the English wiki's X placeholders for the explosion base and per-stack damage. The Japanese note supports Physical Damage scaling, but does not resolve whether Sinistra/Dextra hand-specific damage modifiers are included.", ["CLAIM-JA-CHARGED-STRIKE-DAMAGE", "CLAIM-JA-CHARGED-STRIKE-STACK"], ["base explosion damage", "per-stack damage", "physical-damage scaling"], "Japanese and English pages disagree on the numeric values; retain both as source-specific claims."),
        japanese_evidence("EVID-JA-BIG-LAZY", "upgrade-crystal-of-perseverance-big-and-lazy", "Big and Lazy / Vitality", "Q-USER-BIG-LAZY-VITALITY", ["Q-USER-BIG-LAZY-VITALITY"], "\u30a2\u30c3\u30d7\u30b0\u30ec\u30fc\u30c9", "\u5de8\u5927\u306a\u6020\u60f0", "\u81ea\u7136\u56de\u5fa9\u91cf\u00d7(1+\u5de8\u5927\u306a\u6020\u60f0\u30b9\u30bf\u30c3\u30af\u6570)\u3001\u3053\u308c\u81ea\u4f53\u306b\u81ea\u7136\u56de\u5fa9\u91cf\u306f\u306a\u3044\u3002\n\u79fb\u52d5\u3068\u306f\u79fb\u52d5\u5165\u529b\u3092\u6307\u3057\u3066\u304a\u308a\u3001\u6163\u6027\u3084\u30b9\u30ad\u30eb\u306b\u3088\u308b\u79fb\u52d5\u306f\u5bfe\u8c61\u3068\u306a\u3089\u306a\u3044\u3002", "Health regeneration is multiplied by (1 + the number of Big and Lazy stacks); Big and Lazy itself does not provide regeneration. Movement means movement input, so inertia and skill-based movement do not count.", "This supports a multiplicative interaction with an existing regeneration source such as Vitality, but it does not state the exact order or cap behavior when other modifiers are present.", ["CLAIM-BIG-LAZY-VITALITY-MULT"], ["Big and Lazy formula", "multiplicative interaction"], "Japanese source gives a formula for Big and Lazy; the full Vitality interaction remains a research question."),
        japanese_evidence("EVID-JA-BENISON", "upgrade-crystal-of-perseverance-benison-of-purification", "Benison of Purification", "Q-USER-BENISON-ONE-STACK-INTERVAL", ["Q-USER-BENISON-ONE-STACK-INTERVAL", "Q-USER-BENISON-FREQUENCY-SCALING", "Q-USER-BENISON-DAMAGE", "Q-USER-BENISON-OTHER-SCALING", "Q-USER-ATTACK-SPEED-STATUS-INTERACTION"], "\u30a2\u30c3\u30d7\u30b0\u30ec\u30fc\u30c9", "\u8056\u306a\u308b\u795d\u798f", "\u5b9a\u671f\u7684\u306b\u300164\u30e1\u30fc\u30c8\u30eb\u4ee5\u5185\u306e\u6700\u3082\u8fd1\u3044\u6575\u3078?\u30c0\u30e1\u30fc\u30b8\u3092\u4e0e\u3048\u308b\u8056\u5c5e\u6027\u9b54\u6cd5\u3092\u767a\u5c04\u3059\u308b\u3002\n\u8907\u6570\u53d6\u5f97\u3059\u308b\u3068\u767a\u5c04\u9593\u9694\u304c\u77ed\u7e2e\u3059\u308b\u3002", "Periodically fires a Holy magic projectile at the nearest enemy within 64 meters, dealing ? damage. With multiple copies, the firing interval is shortened.", "The Japanese page confirms that additional stacks shorten the interval, but leaves the one-stack interval and projectile damage unknown. It does not state whether Attack Speed affects the proc or its status-effect chance.", [], ["interval scaling", "damage remains unknown"], "Partial answer only; the Japanese placeholder remains explicit."),
        japanese_evidence("EVID-JA-CURSE-OF-WRATH", "upgrade-crystal-of-perseverance-curse-of-wrath", "Curse of Wrath", "question-upgrade-crystal-of-perseverance-curse-of-wrath-interval", ["question-upgrade-crystal-of-perseverance-curse-of-wrath-interval", "question-upgrade-crystal-of-perseverance-curse-of-wrath-damage", "question-upgrade-crystal-of-perseverance-curse-of-wrath-stack-scaling", "Q-USER-ATTACK-SPEED-STATUS-INTERACTION"], "\u30a2\u30c3\u30d7\u30b0\u30ec\u30fc\u30c9", "\u6012\u308a\u306e\u546a\u3044", "4\u79d2\u6bce\u306b\u3001\u534a\u5f8432\u30e1\u30fc\u30c8\u30eb\u4ee5\u5185\u306e\u6700\u3082\u8fd1\u3044\u6575\u307830\u30c0\u30e1\u30fc\u30b8\u3092\u4e0e\u3048\u308b\u95c7\u5c5e\u6027\u9b54\u6cd5\u3092\u767a\u5c04\u3059\u308b\u3002\n\u30af\u30ea\u30c6\u30a3\u30ab\u30eb\u5224\u5b9a\u304c\u3042\u308a\u3001?%\u306e\u78ba\u7387\u3067\u5d29\u58ca\u3092\u4ed8\u4e0e\u3059\u308b\u3002\n\u8907\u6570\u53d6\u5f97\u3059\u308b\u3068\u767a\u5c04\u9593\u9694\u304c\u77ed\u7e2e\u3059\u308b\u3002", "Every 4 seconds, fires a Shadow magic projectile at the nearest enemy within a 32-meter radius, dealing 30 damage. It has a critical-hit check and a ?% chance to apply BREACHED. With multiple copies, the firing interval is shortened.", "This conflicts with the English page's 25 (+X) damage wording and supplies a four-second base interval. The status chance remains unknown, while the Japanese page explicitly says a critical-hit check exists.", ["CLAIM-JA-CURSE-OF-WRATH"], ["base interval", "base damage", "critical check", "status chance remains unknown"], "Japanese and English numeric damage values conflict; do not merge them into one answer."),
        japanese_evidence("EVID-JA-THUNDER-AURA", "upgrade-crystal-of-mobility-thunder-aura", "Thunder Aura", "question-upgrade-crystal-of-mobility-thunder-aura-interval", ["question-upgrade-crystal-of-mobility-thunder-aura-interval", "question-upgrade-crystal-of-mobility-thunder-aura-damage", "question-upgrade-crystal-of-mobility-thunder-aura-stack-scaling", "Q-USER-ATTACK-SPEED-STATUS-INTERACTION"], "\u30a2\u30c3\u30d7\u30b0\u30ec\u30fc\u30c9", "\u96f7\u306e\u30aa\u30fc\u30e9", "\u6bce\u79d2\u30014m(+?m)\u5185\u306b\u3044\u308b\u6575\u307823(+?)\u96f7\u5c5e\u6027\u30c0\u30e1\u30fc\u30b8\u3092\u4e0e\u3048\u308b\u3002\n\u4e0e\u30c0\u30e1\u6e1b\u5c11\u5f8c\u306e\u30c0\u30e1\u30fc\u30b8\u3002\u30af\u30ea\u30c6\u30a3\u30ab\u30eb\u5224\u5b9a\u304c\u3042\u308a\u3001\u78ba\u7387\u3067\u9ebb\u75fa\u3092\u4ed8\u4e0e\u3059\u308b\u3002\n\u4e0e\u30fb\u96f7\u5c5e\u6027\u30c0\u30e1\u30fc\u30b8\u306e\u5f71\u97ff\u3092\u53d7\u3051\u308b\u3002", "Every second, deals 23 (+?) Electric damage to enemies within 4 m (+? m). This is damage after dealt-damage reduction. It has a critical-hit check and can apply PARALYZED with an unspecified chance. It is affected by dealt Electric damage.", "This supplies a one-second interval, 4 m base radius, 23 base damage, critical-hit check, and Electric Damage scaling. It conflicts with the English page's 25 base damage and leaves stack/radius/status chance values incomplete.", ["CLAIM-JA-THUNDER-AURA"], ["base interval", "radius", "base damage", "critical check", "status chance remains vague"], "Japanese and English pages differ on base damage; preserve both."),
        japanese_evidence("EVID-JA-BERSERKER-MELEE", "upgrade-crystal-of-mobility-berserker-s-soul-melee", "Berserker's Soul (Melee)", "question-upgrade-crystal-of-mobility-berserker-s-soul-melee-stack-scaling", ["question-upgrade-crystal-of-mobility-berserker-s-soul-melee-stack-scaling"], "\u30a2\u30c3\u30d7\u30b0\u30ec\u30fc\u30c9", "\u30d0\u30fc\u30b5\u30fc\u30ab\u30fc\u30bd\u30a6\u30eb\uff08\u8fd1\u63a5\uff09", "\u30c0\u30e1\u30fc\u30b8\u3092\u4e0e\u3048\u308b\u3068\u3001\u30d0\u30fc\u30b5\u30fc\u30ab\u30fc\u30bd\u30a6\u30eb\u3092\u6700\u592770\u30b9\u30bf\u30c3\u30af\u307e\u3067\u7372\u5f97\u3059\u308b\u3002\n1\u30b9\u30bf\u30c3\u30af\u306b\u3064\u304d\u4e0e\u30c0\u30e1\u30fc\u30b8 +0.64%\n1\u30b9\u30bf\u30c3\u30af\u306b\u3064\u304d\u653b\u6483\u901f\u5ea6 +1.28%\n1\u30b9\u30bf\u30c3\u30af\u306b\u3064\u304d\u81ea\u7136\u56de\u5fa9\u91cf -0.71%\n\u30c9\u30c3\u30c8\u30c0\u30e1\u30fc\u30b8\u3067\u306f\u8caf\u307e\u3089\u306a\u3044\u3002", "Dealing damage grants Berserker's Soul, up to 70 stacks. Each stack gives +0.64% dealt damage, +1.28% Attack Speed, and -0.71% regeneration. Damage-over-time does not build stacks.", "This supplies a concrete maximum stack count and per-stack values that differ from the English page's X placeholders.", ["CLAIM-JA-BERSERKER-MELEE"], ["maximum stacks", "per-stack scaling", "DoT exclusion"], "Japanese source; exact game-version applicability should still be checked."),
        japanese_evidence("EVID-JA-BERSERKER-RANGED", "upgrade-crystal-of-mobility-berserker-s-soul-ranged", "Berserker's Soul (Ranged)", "question-upgrade-crystal-of-mobility-berserker-s-soul-ranged-stack-scaling", ["question-upgrade-crystal-of-mobility-berserker-s-soul-ranged-stack-scaling"], "\u30a2\u30c3\u30d7\u30b0\u30ec\u30fc\u30c9", "\u30d0\u30fc\u30b5\u30fc\u30ab\u30fc\u30bd\u30a6\u30eb\uff08\u9060\u8ddd\u96e2\uff09", "\u30c0\u30e1\u30fc\u30b8\u3092\u4e0e\u3048\u308b\u3068\u3001\u30d0\u30fc\u30b5\u30fc\u30ab\u30fc\u30bd\u30a6\u30eb\u3092\u6700\u592770\u30b9\u30bf\u30c3\u30af\u307e\u3067\u7372\u5f97\u3059\u308b\u3002\n1\u30b9\u30bf\u30c3\u30af\u306b\u3064\u304d\u4e0e\u30c0\u30e1\u30fc\u30b8 +0.32%\n1\u30b9\u30bf\u30c3\u30af\u306b\u3064\u304d\u653b\u6483\u901f\u5ea6 +0.64%\n1\u30b9\u30bf\u30c3\u30af\u306b\u3064\u304d\u6295\u5c04\u7269\u62e1\u6563 +0.0285%\n\u30c9\u30c3\u30c8\u30c0\u30e1\u30fc\u30b8\u3067\u306f\u8caf\u307e\u3089\u306a\u3044\u3002", "Dealing damage grants Berserker's Soul, up to 70 stacks. Each stack gives +0.32% dealt damage, +0.64% Attack Speed, and +0.0285% projectile spread. Damage-over-time does not build stacks.", "This supplies a concrete maximum stack count and per-stack values that differ from the English page's X placeholders.", ["CLAIM-JA-BERSERKER-RANGED"], ["maximum stacks", "per-stack scaling", "DoT exclusion"], "Japanese source; exact game-version applicability should still be checked."),
        japanese_evidence("EVID-JA-SPELLSWORD-PIERCING", "skill-spellsword-piercing-strike", "Spellsword: Piercing Strike", "question-skill-spellsword-piercing-strike-unknown", ["question-skill-spellsword-piercing-strike-unknown", "question-skill-spellsword-piercing-strike-attack-interval"], "\u30b9\u30da\u30eb\u30bd\u30fc\u30c9", "SECONDARY / \u30d4\u30a2\u30b7\u30f3\u30b0\u30b9\u30c8\u30e9\u30a4\u30af", "\u30c1\u30e3\u30fc\u30b8\u6642\u9593 | 0.170\uff5e5.075\u79d2\uff08\u653b\u6483\u901f\u5ea61%\u306b\u3064\u304d\u7d041.5%\u77ed\u7e2e\uff09\n\u30c0\u30e1\u30fc\u30b8 | 87\uff5e170\n\u30af\u30fc\u30eb\u30c0\u30a6\u30f3 | 1.5\u79d2\n\u6700\u592750%\u306e\u78ba\u7387\u3067\u51fa\u8840\u3092\u4ed8\u4e0e\u3059\u308b\u3002\n\u653b\u6483\u901f\u5ea6\u306e\u5f71\u97ff\u3092\u53d7\u3051\u308b\u3002", "Charge time: 0.170-5.075 seconds, shortened by approximately 1.5% per 1% Attack Speed. Damage: 87-170. Cooldown: 1.5 seconds. Bleeding can be applied with up to a 50% chance. Charge speed scales with Attack Speed.", "This supplies concrete charge-time, damage, cooldown, and status-chance information for the English placeholders and Attack Speed question.", ["CLAIM-JA-SPELLSWORD-PIERCING"], ["charge time", "damage", "cooldown", "status chance", "Attack Speed scaling"], "Japanese source; the page presents the values as guide information rather than an experimentally verified record."),
        japanese_evidence("EVID-JA-SPELLSWORD-WHIRLWIND", "upgrade-spellsword-spellsword-whirlwind", "Spellsword: Whirlwind", "question-upgrade-spellsword-spellsword-whirlwind-damage", ["question-upgrade-spellsword-spellsword-whirlwind-damage", "question-upgrade-spellsword-spellsword-whirlwind-stack-scaling"], "\u30b9\u30da\u30eb\u30bd\u30fc\u30c9", "\u30b9\u30da\u30eb\u30bd\u30fc\u30c9\uff1a\u30ef\u30fc\u30eb\u30a6\u30a3\u30f3\u30c9", "\u30d5\u30eb\u30c1\u30e3\u30fc\u30b8\u306e\u30d4\u30a2\u30b7\u30f3\u30b0\u30b9\u30c8\u30e9\u30a4\u30af\u3067\u3001\u7403\u72b6\u306e\u65cb\u98a8\u3092\u767a\u5c04\u3059\u308b\u3002\n\u7d040.1\u79d2\u6bce\u306b\u7d99\u7d9a\u7684\u306b\u30c0\u30e1\u30fc\u30b8\u3092\u4e0e\u3048\u308b\u3002\n\u51fa\u8840\u78ba\u7387\u3092\u5f15\u304d\u7d99\u3050\u3002\u65cb\u98a8\u306e\u30c0\u30e1\u30fc\u30b8\u81ea\u4f53\u306b\u306f\u30af\u30ea\u30c6\u30a3\u30ab\u30eb\u5224\u5b9a\u304c\u306a\u3044\u3002", "The Whirlwind deals damage approximately every 0.1 seconds, inherits Bleeding chance, and its damage never has a critical-hit check.", "This supplies a tick interval and explicitly says the Whirlwind cannot critically strike, but it does not give the damage per tick or a stack formula.", ["CLAIM-JA-SPELLSWORD-WHIRLWIND"], ["tick interval", "Bleeding inheritance", "cannot crit"], "Japanese source; damage magnitude remains unresolved."),
    ]
    for item in evidence:
        item["questionIds"] = [value.replace("boberserker", "berserker") for value in item.get("questionIds", [])]
    claims = [
        {"id": "CLAIM-USER-BERSERKER-MELEE-TOTAL", "questionId": "question-upgrade-crystal-of-mobility-berserker-s-soul-melee-stack-scaling", "text": "User hypothesis: Berserker's Soul (Melee) reaches approximately +45% Overall Damage, +90% Attack Speed, and -50% Health Regeneration at 70 stacks, divided linearly per stack.", "type": "user hypothesis", "status": "Unknown", "evidenceIds": ["EVID-USER-BERSERKER-MELEE-TOTAL"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-USER-BERSERKER-RANGED-TOTAL", "questionId": "question-upgrade-crystal-of-mobility-berserker-s-soul-ranged-stack-scaling", "text": "User hypothesis: Berserker's Soul (Ranged) reaches approximately +45% Overall Damage, +90% Attack Speed, and +2% Projectile Spread at 70 stacks, divided linearly per stack.", "type": "user hypothesis", "status": "Unknown", "evidenceIds": ["EVID-USER-BERSERKER-RANGED-TOTAL"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-USER-BIG-LAZY-STACKS", "questionId": "Q-USER-BIG-LAZY-VITALITY", "text": "User hypothesis: Big and Lazy may apply an effective regeneration multiplier of 3 at 1 stack, 3.5 at 2 stacks, and then continue linearly, after Vitality and other regeneration effects.", "type": "user hypothesis", "status": "Unknown", "evidenceIds": ["EVID-USER-BIG-LAZY-STACKS"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-USER-BIG-ROUND-STACKING", "questionId": None, "text": "User observation: Big and Round appears to stack linearly as its English description states.", "type": "user observation", "status": "Reported", "evidenceIds": ["EVID-USER-BIG-ROUND-STACKING"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-USER-BIG-WRATHFUL-STACKING", "questionId": "Q-USER-BIG-WRATHFUL-STACKING", "text": "User hypothesis: Big and Wrathful probably stacks linearly, but it remains unclear whether the LOW HP damage bonus is additive to Overall Damage or a separate multiplier.", "type": "user hypothesis", "status": "Unknown", "evidenceIds": ["EVID-USER-BIG-WRATHFUL-STACKING"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-SHEDDING-5", "questionId": "Q-USER-SHEDDING", "text": "Shedding may reduce Overall Defense by 5% per stack.", "type": "reported interpretation", "status": "Contradicted", "evidenceIds": ["EVID-USER-001"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-SHEDDING-7", "questionId": "Q-USER-SHEDDING", "text": "Shedding may reduce Overall Defense by approximately 7% per stack.", "type": "hypothesis", "status": "Unknown", "evidenceIds": ["EVID-USER-001"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-BIG-LAZY-VITALITY-MULT", "questionId": "Q-USER-BIG-LAZY-VITALITY", "text": "Big and Lazy and Vitality interact multiplicatively in some way.", "type": "hypothesis", "status": "Reported", "evidenceIds": ["EVID-USER-002"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-TWINMAGE-HAND-RATE", "questionId": "Q-USER-TWINMAGE-HAND-RATE", "text": "Each Twinmage elemental hand attacks at 0.8 attacks per second when both hands are active and 1.4 attacks per second when a single hand is active.", "type": "reported wiki reading", "status": "Reported", "evidenceIds": ["EVID-USER-TWINMAGE-RATE"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-JA-CHARGED-STRIKE-DAMAGE", "questionId": "Q-USER-CHARGED-STRIKE-DAMAGE", "text": "The Japanese wiki reports 25 base Physical explosion damage for Charged Strike.", "type": "Japanese wiki claim", "status": "Reported", "evidenceIds": ["EVID-JA-CHARGED-STRIKE"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-JA-CHARGED-STRIKE-STACK", "questionId": "Q-USER-CHARGED-STRIKE-STACK", "text": "The Japanese wiki reports +10 Physical explosion damage per Charged Strike stack.", "type": "Japanese wiki claim", "status": "Reported", "evidenceIds": ["EVID-JA-CHARGED-STRIKE"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-JA-CURSE-OF-WRATH", "questionId": "question-upgrade-crystal-of-perseverance-curse-of-wrath-interval", "text": "The Japanese wiki reports a 4-second base interval and 30 base damage for Curse of Wrath, with a critical-hit check and an unspecified BREACHED chance.", "type": "Japanese wiki claim", "status": "Reported", "evidenceIds": ["EVID-JA-CURSE-OF-WRATH"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-JA-THUNDER-AURA", "questionId": "question-upgrade-crystal-of-mobility-thunder-aura-interval", "text": "The Japanese wiki reports a one-second interval and 23 base Electric damage for Thunder Aura, with a 4 m base radius and a critical-hit check.", "type": "Japanese wiki claim", "status": "Reported", "evidenceIds": ["EVID-JA-THUNDER-AURA"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-JA-BERSERKER-MELEE", "questionId": "question-upgrade-crystal-of-mobility-berserker-s-soul-melee-stack-scaling", "text": "The Japanese wiki reports 70 maximum Berserker's Soul (Melee) stacks with +0.64% dealt damage, +1.28% Attack Speed, and -0.71% regeneration per stack.", "type": "Japanese wiki claim", "status": "Reported", "evidenceIds": ["EVID-JA-BERSERKER-MELEE"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-JA-BERSERKER-RANGED", "questionId": "question-upgrade-crystal-of-mobility-berserker-s-soul-ranged-stack-scaling", "text": "The Japanese wiki reports 70 maximum Berserker's Soul (Ranged) stacks with +0.32% dealt damage, +0.64% Attack Speed, and +0.0285% projectile spread per stack.", "type": "Japanese wiki claim", "status": "Reported", "evidenceIds": ["EVID-JA-BERSERKER-RANGED"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-JA-SPELLSWORD-PIERCING", "questionId": "question-skill-spellsword-piercing-strike-unknown", "text": "The Japanese wiki reports Piercing Strike charge time 0.170–5.075 seconds, damage 87–170, 1.5-second cooldown, and up to 50% Bleeding chance.", "type": "Japanese wiki claim", "status": "Reported", "evidenceIds": ["EVID-JA-SPELLSWORD-PIERCING"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
        {"id": "CLAIM-JA-SPELLSWORD-WHIRLWIND", "questionId": "question-upgrade-spellsword-spellsword-whirlwind-damage", "text": "The Japanese wiki reports that Spellsword: Whirlwind ticks approximately every 0.1 seconds, inherits Bleeding chance, and cannot critically strike.", "type": "Japanese wiki claim", "status": "Reported", "evidenceIds": ["EVID-JA-SPELLSWORD-WHIRLWIND"], "sourceRefs": [], "createdAt": TODAY, "updatedAt": TODAY},
    ]
    known = [
        ("Q-USER-SHEDDING", "external-shedding", "other", "Shedding", "What is the actual value/effect magnitude of Shedding?", "Contradicted", "High", "Experimental observations may be closer to approximately 7%, but this is not established.", ["CLAIM-SHEDDING-5", "CLAIM-SHEDDING-7"], ["EVID-USER-001"]),
        ("Q-USER-BIG-LAZY-VITALITY", "external-big-and-lazy-vitality", "other", "Big and Lazy × Vitality", "How exactly does Big and Lazy interact with Vitality?", "Unknown", "High", "The interaction appears multiplicative in some way.", ["CLAIM-BIG-LAZY-VITALITY-MULT"], ["EVID-USER-002"]),
        ("Q-USER-BIG-WRATHFUL-STACKING", "upgrade-crystal-of-perseverance-big-and-wrathful", "upgrade", "Big and Wrathful", "Does Big and Wrathful's LOW HP damage bonus stack linearly, and is it additive to Overall Damage or a separate multiplier?", "Unknown", "High", "The user note suggests linear stacking, but the operation relative to Overall Damage remains unresolved.", ["CLAIM-USER-BIG-WRATHFUL-STACKING"], ["EVID-USER-BIG-WRATHFUL-STACKING"]),
        ("Q-USER-TWINMAGE-HAND-RATE", "class-twinmage", "class", "Twinmage", "What are Twinmage's exact per-hand attack rates when one versus two hands are active?", "Reported", "High", "0.8 attacks per second per hand with both hands active; 1.4 attacks per second per hand with a single hand active, applying to all six elemental hands.", ["CLAIM-TWINMAGE-HAND-RATE"], ["EVID-USER-TWINMAGE-RATE"]),
        ("Q-USER-CHARGED-STRIKE-DAMAGE", "upgrade-chrono-wizard-charged-strike", "upgrade", "Charged Strike", "How much physical damage does the Charged Strike explosion deal?", "Unknown", "High", None, [], []),
        ("Q-USER-CHARGED-STRIKE-STACK", "upgrade-chrono-wizard-charged-strike", "upgrade", "Charged Strike", "How much additional damage is gained per stack?", "Unknown", "High", None, [], []),
        ("Q-USER-CHARGED-STRIKE-OTHER", "upgrade-chrono-wizard-charged-strike", "upgrade", "Charged Strike", "Are there any other undocumented scaling rules for Charged Strike?", "Unknown", "Medium", None, [], []),
    ]
    for suffix, text in [("STOP-MODIFIERS", "What are the exact STOP-state modifiers?"), ("GO-MODIFIERS", "What are the exact GO-state modifiers?"), ("INTERVAL", "What is the exact switching interval?"), ("STACK-SCALING", "How do additional stacks scale each modifier?"), ("ADDITIVE", "Are the effects strictly additive?")]:
        known.append((f"Q-USER-WAY-OF-LAW-{suffix}", "upgrade-crystal-of-mobility-way-of-the-law", "upgrade", "Way of the Law", text, "Unknown", "High", None, [], []))
    for suffix, text in [("ONE-STACK-INTERVAL", "What is the firing interval with one stack?"), ("FREQUENCY-SCALING", "How does firing frequency scale with additional stacks?"), ("DAMAGE", "What damage does the projectile deal?"), ("OTHER-SCALING", "Are there other relevant scaling rules?")]:
        known.append((f"Q-USER-BENISON-{suffix}", "upgrade-crystal-of-perseverance-benison-of-purification", "upgrade", "Benison of Purification", text, "Unknown", "High", None, [], []))
    known.extend([
        ("Q-USER-ATTACK-SPEED-STATUS-INTERACTION", "stat-attack-speed", "other", "Attack Speed × Status Effect Chance", "Does Attack Speed affect status-effect chance for damage sources that do not become faster from Attack Speed, such as Thaumaturge: Splashback, Benison of Purification, Curse of Wrath, or Thunder Aura?", "Unknown", "High", None, [], []),
        ("Q-USER-STATUS-CHANCE-PER-SHOT", "stat-status-effect-chance", "other", "Status Effect Chance × Attack Speed", "Does Status Effect Chance increase on each individual shot or proc when Attack Speed is below 100%?", "Unknown", "High", None, [], []),
        ("Q-USER-TWINMAGE-MASTERY-STATUS-CHANCE", "upgrade-twinmage-twinmage-mastery", "upgrade", "Twinmage: Mastery", "Does Twinmage: Mastery's splash explosion use the same status-effect chance as the primary/secondary attack, or a reduced value such as 25% of that chance?", "Unknown", "High", None, [], []),
        ("question-upgrade-twinmage-twinmage-mastery-stack-scaling", "upgrade-twinmage-twinmage-mastery", "upgrade", "Twinmage: Mastery", "What are the base explosion radius and the per-stack explosion-radius increase for Twinmage: Mastery?", "Unknown", "High", None, [], []),
    ])
    for upgrade_id, hand_label, modifier_label in [
        ("upgrade-twinmage-twinmage-sinistra", "Left Hand", "Sinistra"),
        ("upgrade-twinmage-twinmage-dextra", "Right Hand", "Dextra"),
    ]:
        known.extend([
            (f"Q-USER-TWINMAGE-{modifier_label.upper()}-MASTERY", upgrade_id, "upgrade", f"Twinmage: {modifier_label}", f"Does {modifier_label}'s {hand_label} Damage modifier affect the Twinmage: Mastery splash/explosion damage from that hand?", "Unknown", "High", None, [], []),
            (f"Q-USER-TWINMAGE-{modifier_label.upper()}-CHARGED-STRIKE", upgrade_id, "upgrade", f"Twinmage: {modifier_label}", f"Does {modifier_label}'s {hand_label} Damage modifier affect the Charged Strike explosion triggered by a critical hit from that hand?", "Unknown", "High", None, [], []),
            (f"Q-USER-TWINMAGE-{modifier_label.upper()}-STATUS-DAMAGE", upgrade_id, "upgrade", f"Twinmage: {modifier_label}", f"Does {modifier_label}'s {hand_label} Damage modifier increase damage-over-time status effects applied by that hand, especially BLEEDING or BURNING?", "Unknown", "High", None, [], []),
        ])
    questions = [question({"id": item[0], "mechanicId": item[1], "mechanicType": item[2], "mechanicName": item[3], "question": item[4], "status": item[5], "priority": item[6], "currentHypothesis": item[7], "claimIds": item[8], "evidenceIds": item[9], "kind": "user-research", "manual": True, "generated": False}) for item in known]
    tests = [
        {"id": "TEST-PLAN-SHEDDING-001", "questionIds": ["Q-USER-SHEDDING"], "status": "Planned", "date": None, "gameVersion": None, "setup": "Run identical observations with no defense modifiers, then add one Shedding stack at a time.", "upgrades": ["Shedding"], "class": None, "relevantStats": ["Overall Defense"], "enemyContext": None, "controlledVariables": ["class", "difficulty", "enemy", "incoming attack", "health state"], "rawObservations": None, "expectedResults": ["5% per stack", "approximately 7% per stack"], "conclusion": None, "limitations": "No result has been recorded yet."},
        {"id": "TEST-PLAN-BIG-LAZY-VITALITY-001", "questionIds": ["Q-USER-BIG-LAZY-VITALITY"], "status": "Planned", "date": None, "gameVersion": None, "setup": "Measure regeneration with neither effect, Big and Lazy alone, Vitality alone, and both together while stationary and moving.", "upgrades": ["Big and Lazy", "Vitality"], "class": None, "relevantStats": ["Health Regeneration"], "enemyContext": None, "controlledVariables": ["class", "health", "standing/moving state", "time interval"], "rawObservations": None, "expectedResults": ["additive interaction", "multiplicative interaction", "override or cap behavior"], "conclusion": None, "limitations": "Need a time-stamped health log."},
        {"id": "TEST-PLAN-CHARGED-STRIKE-001", "questionIds": ["Q-USER-CHARGED-STRIKE-DAMAGE", "Q-USER-CHARGED-STRIKE-STACK", "Q-USER-CHARGED-STRIKE-OTHER"], "status": "Planned", "date": None, "gameVersion": None, "setup": "Trigger critical hits against a controlled target with zero, one, and multiple Charged Strike stacks; isolate explosion damage from base hit.", "upgrades": ["Charged Strike"], "class": None, "relevantStats": ["Critical Strike Chance", "Physical Damage"], "enemyContext": "Controlled target with known defenses", "controlledVariables": ["attack", "target", "critical hit", "distance", "stack count"], "rawObservations": None, "expectedResults": ["base explosion damage", "per-stack increment", "any hidden scaling"], "conclusion": None, "limitations": "Target mitigation and floating-point rounding may need to be controlled."},
    ]
    return questions, claims, evidence, tests


def interaction_links() -> dict[str, list[dict]]:
    """Canonical links for questions that investigate more than one mechanic."""
    return {
        "Q-USER-ATTACK-SPEED-STATUS-INTERACTION": [
            {"id": "stat-attack-speed", "type": "stat", "name": "Attack Speed"},
            {"id": "stat-status-effect-chance", "type": "stat", "name": "Status Effect Chance"},
            {"id": "upgrade-thaumaturge-thaumaturge-splashback", "type": "upgrade", "name": "Thaumaturge: Splashback"},
            {"id": "upgrade-crystal-of-perseverance-benison-of-purification", "type": "upgrade", "name": "Benison of Purification"},
            {"id": "upgrade-crystal-of-perseverance-curse-of-wrath", "type": "upgrade", "name": "Curse of Wrath"},
            {"id": "upgrade-crystal-of-mobility-thunder-aura", "type": "upgrade", "name": "Thunder Aura"},
        ],
        "Q-USER-STATUS-CHANCE-PER-SHOT": [
            {"id": "stat-status-effect-chance", "type": "stat", "name": "Status Effect Chance"},
            {"id": "stat-attack-speed", "type": "stat", "name": "Attack Speed"},
        ],
        "Q-USER-TWINMAGE-MASTERY-STATUS-CHANCE": [
            {"id": "upgrade-twinmage-twinmage-mastery", "type": "upgrade", "name": "Twinmage: Mastery"},
            {"id": "class-twinmage", "type": "class", "name": "Twinmage"},
            {"id": "skill-twinmage-flaming-hand", "type": "class-skill", "name": "Flaming Hand"},
            {"id": "skill-twinmage-ice-hand", "type": "class-skill", "name": "Ice Hand"},
            {"id": "skill-twinmage-electric-hand", "type": "class-skill", "name": "Electric Hand"},
            {"id": "skill-twinmage-wind-blade", "type": "class-skill", "name": "Wind Blade"},
            {"id": "skill-twinmage-divine-hand", "type": "class-skill", "name": "Divine Hand"},
            {"id": "skill-twinmage-profane-hand", "type": "class-skill", "name": "Profane Hand"},
        ],
        "question-upgrade-twinmage-twinmage-mastery-stack-scaling": [
            {"id": "upgrade-twinmage-twinmage-mastery", "type": "upgrade", "name": "Twinmage: Mastery"},
        ],
        "Q-USER-BIG-LAZY-VITALITY": [
            {"id": "upgrade-crystal-of-perseverance-big-and-lazy", "type": "upgrade", "name": "Big and Lazy"},
            {"id": "upgrade-crystal-of-perseverance-vitality", "type": "upgrade", "name": "Vitality"},
        ],
        "Q-USER-TWINMAGE-SINISTRA-MASTERY": [
            {"id": "upgrade-twinmage-twinmage-sinistra", "type": "upgrade", "name": "Twinmage: Sinistra"},
            {"id": "upgrade-twinmage-twinmage-mastery", "type": "upgrade", "name": "Twinmage: Mastery"},
        ],
        "Q-USER-TWINMAGE-SINISTRA-CHARGED-STRIKE": [
            {"id": "upgrade-twinmage-twinmage-sinistra", "type": "upgrade", "name": "Twinmage: Sinistra"},
            {"id": "upgrade-chrono-wizard-charged-strike", "type": "upgrade", "name": "Charged Strike"},
        ],
        "Q-USER-TWINMAGE-SINISTRA-STATUS-DAMAGE": [
            {"id": "upgrade-twinmage-twinmage-sinistra", "type": "upgrade", "name": "Twinmage: Sinistra"},
            {"id": "status-effect-bleeding", "type": "status-effect", "name": "BLEEDING"},
            {"id": "status-effect-burning", "type": "status-effect", "name": "BURNING"},
        ],
        "Q-USER-TWINMAGE-DEXTRA-MASTERY": [
            {"id": "upgrade-twinmage-twinmage-dextra", "type": "upgrade", "name": "Twinmage: Dextra"},
            {"id": "upgrade-twinmage-twinmage-mastery", "type": "upgrade", "name": "Twinmage: Mastery"},
        ],
        "Q-USER-TWINMAGE-DEXTRA-CHARGED-STRIKE": [
            {"id": "upgrade-twinmage-twinmage-dextra", "type": "upgrade", "name": "Twinmage: Dextra"},
            {"id": "upgrade-chrono-wizard-charged-strike", "type": "upgrade", "name": "Charged Strike"},
        ],
        "Q-USER-TWINMAGE-DEXTRA-STATUS-DAMAGE": [
            {"id": "upgrade-twinmage-twinmage-dextra", "type": "upgrade", "name": "Twinmage: Dextra"},
            {"id": "status-effect-bleeding", "type": "status-effect", "name": "BLEEDING"},
            {"id": "status-effect-burning", "type": "status-effect", "name": "BURNING"},
        ],
    }


def apply_interaction_links(records: list[dict]) -> None:
    for item in records:
        links = interaction_links().get(item["id"])
        if links:
            item["mechanicId"] = links[0]["id"]
            item["mechanicIds"] = [link["id"] for link in links]
            item["mechanicLinks"] = links
            if item.get("mechanicType") == "other":
                item["mechanicType"] = links[0]["type"]
        elif not item.get("mechanicIds") and item.get("mechanicId"):
            item["mechanicIds"] = [item["mechanicId"]]
            item["mechanicLinks"] = [{"id": item["mechanicId"], "type": item.get("mechanicType", "upgrade"), "name": item.get("mechanicName", "Unknown mechanic")}]


def apply_japanese_audit(records: list[dict], evidence: list[dict], available_source_ids: list[str], failures: list[dict]) -> None:
    evidence_by_question: dict[str, list[str]] = {}
    for item in evidence:
        for question_id in item.get("questionIds", [item.get("questionId")]):
            if question_id:
                evidence_by_question.setdefault(question_id, []).append(item["id"])
    failure_note = " Some requested Japanese pages failed to load; see import-report.json." if failures else ""
    for item in records:
        linked = list(dict.fromkeys(evidence_by_question.get(item["id"], [])))
        item["japaneseAudit"] = {
            "status": "Checked",
            "checkedAt": TODAY,
            "sourceIds": available_source_ids,
            "findingStatus": "Relevant information found" if linked else "No direct answer found",
            "evidenceIds": linked,
            "notes": "Japanese upgrade, class, and individual class pages were reviewed for a directly relevant statement. Japanese evidence is stored with the original text and an English translation." + failure_note,
        }


def evidence_source_metadata(evidence_type: str) -> tuple[str, str]:
    label = (evidence_type or "Unknown").lower()
    if "japanese wiki" in label:
        return "Japanese wiki", "Reported"
    if "english wiki" in label or "wiki" in label:
        return "English wiki", "Source-stated"
    if "test" in label or "experiment" in label:
        return "User testing", "Test record"
    if "discord" in label:
        return "Discord", "Reported"
    if "user" in label or "observation" in label:
        return "User observation/speculation", "Reported"
    return evidence_type or "Unknown source", "Unrated"


def fact(label: str, value: str, evidence_id: str, status: str = "Reported", confidence: str = "Medium", note: str | None = None) -> dict:
    result = {"label": label, "value": value, "evidenceId": evidence_id, "status": status, "confidence": confidence}
    if note:
        result["note"] = note
    return result


def apply_research_fact_audit(upgrades: list[dict], classes: list[dict], questions: list[dict], evidence: list[dict]) -> None:
    """Attach source-tagged findings without overwriting wiki descriptions or unknown tokens."""
    facts_by_evidence = {
        "EVID-JA-TWINMAGE-HANDS": [
            fact("Both hands active rate", "0.8 attacks/s per hand", "EVID-JA-TWINMAGE-HANDS"),
            fact("Single hand active rate", "1.4 attacks/s per hand", "EVID-JA-TWINMAGE-HANDS"),
            fact("Single-hand speed change", "+75% attack speed", "EVID-JA-TWINMAGE-HANDS"),
            fact("Base elemental-hand status chance", "10% for each listed hand/status pair", "EVID-JA-TWINMAGE-HANDS"),
        ],
        "EVID-JA-TWINMAGE-MASTERY": [fact("Splash damage ratio", "25% of the triggering skill damage", "EVID-JA-TWINMAGE-MASTERY"), fact("Base splash radius", "UNKNOWN", "EVID-JA-TWINMAGE-MASTERY", note="Japanese source retains ? m."), fact("Per-stack radius increase", "UNKNOWN", "EVID-JA-TWINMAGE-MASTERY", note="Japanese source retains +? m.")],
        "EVID-JA-TWINMAGE-HAND-MODIFIERS": [fact("Sinistra/Dextra hand damage modifier", "+5% to favored hand and -3% to the other hand per stack", "EVID-JA-TWINMAGE-HAND-MODIFIERS"), fact("Modifier calculation group", "Group B is calculated multiplicatively with Group A", "EVID-JA-TWINMAGE-HAND-MODIFIERS")],
        "EVID-JA-CHARGED-STRIKE": [fact("Explosion base damage", "25 Physical", "EVID-JA-CHARGED-STRIKE", note="Conflicts with the English wiki X placeholder."), fact("Explosion damage per stack", "+10 Physical", "EVID-JA-CHARGED-STRIKE", note="Conflicts with the English wiki X placeholder."), fact("Explosion damage scaling", "Affected by dealt Physical Damage", "EVID-JA-CHARGED-STRIKE")],
        "EVID-JA-BIG-LAZY": [fact("Regeneration formula", "Existing regeneration × (1 + Big and Lazy stack count)", "EVID-JA-BIG-LAZY"), fact("Movement condition", "Movement input disables the regeneration effect; inertia/skill movement is excluded", "EVID-JA-BIG-LAZY")],
        "EVID-JA-BENISON": [fact("Target range", "64 m", "EVID-JA-BENISON"), fact("Additional-stack behavior", "Additional copies shorten the firing interval", "EVID-JA-BENISON"), fact("Projectile damage", "UNKNOWN", "EVID-JA-BENISON", note="Japanese source retains ? damage.")],
        "EVID-JA-CURSE-OF-WRATH": [fact("Base interval", "4 seconds", "EVID-JA-CURSE-OF-WRATH", note="Conflicts with the English page's incomplete interval wording."), fact("Base damage", "30 Shadow", "EVID-JA-CURSE-OF-WRATH", note="Conflicts with the English page's 25 (+X) wording."), fact("Target range", "32 m", "EVID-JA-CURSE-OF-WRATH"), fact("Critical-hit rule", "A critical-hit check exists", "EVID-JA-CURSE-OF-WRATH"), fact("BREACHED chance", "UNKNOWN", "EVID-JA-CURSE-OF-WRATH", note="Japanese source retains ?%.")],
        "EVID-JA-THUNDER-AURA": [fact("Activation interval", "1 second", "EVID-JA-THUNDER-AURA"), fact("Base radius", "4 m", "EVID-JA-THUNDER-AURA"), fact("Base damage", "23 Electric", "EVID-JA-THUNDER-AURA", note="Conflicts with the English page's 25 base damage."), fact("Critical-hit rule", "A critical-hit check exists", "EVID-JA-THUNDER-AURA"), fact("Status chance", "UNKNOWN", "EVID-JA-THUNDER-AURA", note="Japanese source says chance exists but gives no percentage.")],
        "EVID-JA-BERSERKER-MELEE": [fact("Maximum stacks", "70", "EVID-JA-BERSERKER-MELEE"), fact("Dealt damage per stack", "+0.64%", "EVID-JA-BERSERKER-MELEE"), fact("Attack Speed per stack", "+1.28%", "EVID-JA-BERSERKER-MELEE"), fact("Regeneration per stack", "-0.71%", "EVID-JA-BERSERKER-MELEE")],
        "EVID-JA-BERSERKER-RANGED": [fact("Maximum stacks", "70", "EVID-JA-BERSERKER-RANGED"), fact("Dealt damage per stack", "+0.32%", "EVID-JA-BERSERKER-RANGED"), fact("Attack Speed per stack", "+0.64%", "EVID-JA-BERSERKER-RANGED"), fact("Projectile spread per stack", "+0.0285%", "EVID-JA-BERSERKER-RANGED")],
        "EVID-JA-SPELLSWORD-PIERCING": [fact("Charge time", "0.170–5.075 seconds", "EVID-JA-SPELLSWORD-PIERCING"), fact("Damage", "87–170", "EVID-JA-SPELLSWORD-PIERCING"), fact("Cooldown", "1.5 seconds", "EVID-JA-SPELLSWORD-PIERCING"), fact("Bleeding chance", "Up to 50%", "EVID-JA-SPELLSWORD-PIERCING"), fact("Attack Speed scaling", "Approximately 1.5% shorter charge time per 1% Attack Speed", "EVID-JA-SPELLSWORD-PIERCING")],
        "EVID-JA-SPELLSWORD-WHIRLWIND": [fact("Damage tick interval", "Approximately 0.1 seconds", "EVID-JA-SPELLSWORD-WHIRLWIND"), fact("Bleeding behavior", "Inherits Bleeding chance", "EVID-JA-SPELLSWORD-WHIRLWIND"), fact("Critical-hit rule", "Cannot critically strike", "EVID-JA-SPELLSWORD-WHIRLWIND")],
        "EVID-USER-BERSERKER-MELEE-TOTAL": [fact("User full-stack hypothesis", "Approximately +45% Overall Damage, +90% Attack Speed, and -50% Health Regeneration at 70 stacks", "EVID-USER-BERSERKER-MELEE-TOTAL", status="Reported", confidence="Reported")],
        "EVID-USER-BERSERKER-RANGED-TOTAL": [fact("User full-stack hypothesis", "Approximately +45% Overall Damage, +90% Attack Speed, and +2% Projectile Spread at 70 stacks", "EVID-USER-BERSERKER-RANGED-TOTAL", status="Reported", confidence="Reported")],
        "EVID-USER-BIG-LAZY-STACKS": [fact("User observed multiplier", "Approximately 3× at 1 stack and 3.5× at 2 stacks, continuing linearly", "EVID-USER-BIG-LAZY-STACKS", status="Reported", confidence="Reported")],
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
