# Ecliptica Research Wiki

This is a small, static research database for reverse-engineering the VRChat world **Ecliptica**. It is intended to support a calculator without turning wiki wording, player observations, hypotheses, and confirmed mechanics into one indistinguishable set of facts.

The initial import uses the English [Ecliptica Wiki on Miraheze](https://ecliptica.miraheze.org/wiki/Main_Page). The raw MediaWiki source for each imported page is retained in `data/sources.json`, and each record points back to a page, section, retrieval date, excerpt, and derived fields.

## Open the site

The simplest option is to double-click `index.html` or open it in a browser. `data/data.js` is a generated browser bundle so the site also works from a `file://` URL, where browser `fetch()` requests for JSON are commonly blocked. The authoritative, human-editable records remain the JSON files in `data/`.

For a local HTTP preview, from this `Research/` directory run:

```text
python -m http.server 8000
```

Then visit <http://localhost:8000/>. The same folder is suitable for GitHub Pages; no backend or build framework is required.

## Data model

- `upgrades.json` ƒ?" one record for each upgrade in the English Upgrades table plus class-specific upgrade tables.
- `classes.json` - the eight class records, their skills, and links to class-specific upgrade records. Every skill is also addressable through the dedicated Abilities section and an `ability:<id>` detail route.
- `questions.json` ƒ?" research questions. Automatically detected gaps use `kind: "missing-wiki-information"`; manually seeded or user-added work uses `kind: "user-research"` and `manual: true`.
- `claims.json` ƒ?" competing proposed answers. A claim is not a fact merely because it exists.
- `evidence.json` ƒ?" source excerpts, player observations, screenshots, videos, spreadsheets, or test results that support or contradict claims.
- `tests.json` ƒ?" planned or completed experiments with setup, controlled variables, raw observations, expected results, conclusions, and limitations.
- `sources.json` - page-level provenance and raw English-wiki text, plus separately retained Japanese Wiki* source pages.
- `data/data.js` ƒ?" generated file-protocol bundle; regenerate it after changing JSON.

Some class records also contain `reportedMechanics` for numeric claims that are useful to the calculator but are not present as literal values in the retained raw source excerpt. For example, Twinmage records the reported 0.8 attacks/second per hand with both hands active and 1.4 attacks/second per hand with one hand active for all six elemental hands. These remain visibly marked as `Reported` until the numeric wording is independently verified.

Values that the wiki writes as `X`, `?`, `TBD`, or leaves vague are kept as unknown signals. They are not replaced with `0`, an empty value, or an inferred number.

Every upgrade and ability also has `mechanics.functionalInterpretation`. This is a conservative, automatically generated working model based on the English wiki wordingƒ?"for example, that a described projectile appears to create a separate damage instance or that a periodic effect appears to use an automatic recurring trigger. It is labeled **Working interpretation / Not confirmed** and must not be treated as source text, evidence, or a confirmed mechanic.

The Abilities section is a separate catalog of every class skill. Each ability page shows its source description, working interpretation, damage behavior fields, related research questions, claims, evidence, tests, and provenance. Class pages link each skill name to its ability page.

Interaction questions can reference more than one mechanic. `mechanicId` remains the primary/legacy link, while `mechanicIds` and `mechanicLinks` list every involved upgrade, class, ability, or status effect. The question appears on each linked record. For example, a Dextra/Charged Strike question stores both the Dextra upgrade and Charged Strike IDs instead of treating Dextra as the only mechanic.

Damage-producing upgrades and class abilities also expose `mechanics.damageBehavior`. Its `canCrit`, `critChance`, `canApplyStatusEffects`, and `statusEffectChance` values are explicit source-derived values when stated; otherwise they remain `null` and render as `UNKNOWN`. The importer never assumes that a damage instance can crit or apply a status effect merely because it deals damage.

Every upgrade, class, and ability also receives a `researchAudit` layer. Clear values found during the question review are displayed there without overwriting the English record. Each finding includes a source category, status, confidence label, and evidence ID. Categories include `English wiki`, `Japanese wiki`, `User observation/speculation`, `User testing`, and `Discord`, so later reports do not get mixed into sourced facts. Japanese findings keep their original text and English translation in the linked evidence record. For example, Japanese `25 Physical` appears as a reported source-specific finding while the English wiki's `X` remains visibly unknown.

Upgrade detail pages begin with a **Working description**. It keeps the original English description visible and places every available sourced numeric clarification directly beneath it, with the source category, confidence, and evidence ID attached. The **Answer audit** immediately below lists the full source-specific findings and unresolved values. If sources disagree, both values remain visible.

The working description prioritizes user observations/hypotheses over Japanese-wiki findings, then English-wiki values, when substituting a likely number for an `X`. Unresolved placeholders are rendered as `?` in the working description; the untouched English wording remains available as the sourced record below.

## Page notes for follow-up messages

Every page has a **Note to Codex** field in the right-hand panel. Type a request or correction while viewing that page; it is saved in the browser's local storage under the current route. Use **Copy all notes** to copy a handoff containing every saved note, its page name, and its route. Use **Clear all** to remove them, or **Hide notes** in the top bar to hide the panel without deleting anything. Notes are local to the browser and are not written into the research dataset.

## Add a research question

Add an object to `data/questions.json` with a stable ID. Keep the mechanic reference and status explicit:

```json
{
  "id": "Q-USER-BENISON-INTERVAL",
  "mechanicId": "upgrade-crystal-of-perseverance-benison-of-purification",
  "mechanicIds": ["upgrade-crystal-of-perseverance-benison-of-purification"],
  "mechanicLinks": [
    { "id": "upgrade-crystal-of-perseverance-benison-of-purification", "type": "upgrade", "name": "Benison of Purification" }
  ],
  "mechanicType": "upgrade",
  "mechanicName": "Benison of Purification",
  "question": "How often does Benison of Purification fire with one stack?",
  "status": "Needs Testing",
  "priority": "High",
  "kind": "user-research",
  "manual": true,
  "generated": false,
  "currentHypothesis": null,
  "claimIds": [],
  "evidenceIds": [],
  "sourceRefs": []
}
```

Use one of `Unknown`, `Needs Testing`, `Reported`, `Supported`, `Confirmed`, `Contradicted`, or `Needs Retest`. Do not use `Confirmed` just because the wiki states something.

Upgrade cards may also show **Complete**. This means the imported wiki record has no detected missing value or linked open question; it is a data-completeness label, not experimental confirmation.

## Add evidence

Add an object to `data/evidence.json` and link it from the question and claim IDs. Evidence can be an English or Japanese wiki excerpt added later, a Discord message, screenshot, video, spreadsheet, or in-game observation:

```json
{
  "id": "EVID-002",
  "mechanicId": "upgrade-crystal-of-perseverance-benison-of-purification",
  "mechanicName": "Benison of Purification",
  "questionId": "Q-USER-BENISON-INTERVAL",
  "type": "in-game test",
  "source": "Test record TEST-002",
  "date": "2026-08-08",
  "originalInformation": "Observed three activations in 18 seconds.",
  "interpretation": "Suggests an approximately 6 second interval; needs repeats and a controlled stack count.",
  "supportsClaimIds": ["CLAIM-BENISON-6S"],
  "contradictsClaimIds": [],
  "reliabilityNotes": "One run; projectile travel and target selection were not isolated.",
  "attachments": []
}
```

## Attach a screenshot

Put the file in `assets/evidence/`, for example `assets/evidence/EVID-002.png`, and add:

```json
"attachments": [
  { "path": "assets/evidence/EVID-002.png", "caption": "Combat log screenshot" }
]
```

Evidence cards render image attachments as clickable thumbnails. Keep original/source information separate from interpretation.

## Record an experiment

Add a test to `data/tests.json`:

```json
{
  "id": "TEST-002",
  "questionIds": ["Q-USER-BENISON-INTERVAL"],
  "status": "Planned",
  "date": null,
  "gameVersion": null,
  "setup": "One Benison stack against a stationary target.",
  "upgrades": ["Benison of Purification"],
  "class": "Spellsword",
  "relevantStats": ["Luminous Damage"],
  "enemyContext": "Known target in a controlled room",
  "controlledVariables": ["stack count", "target", "distance", "game version"],
  "rawObservations": null,
  "expectedResults": ["6 seconds", "another interval"],
  "conclusion": null,
  "limitations": "Not run yet."
}
```

## Refresh wiki data

From `Research/` run:

```text
python tools/import_wiki.py
```

The importer fetches the English `Upgrades`, `Classes`, `Stats`, `Stack Types`, and `Status Effects` pages plus all eight individual class pages through their public raw MediaWiki endpoints. It updates imported upgrade/class/source records, regenerates missing-information questions, asks targeted questions for unresolved damage, critical-hit, status-effect, interval, cooldown, duration, and stack behavior, writes `data/import-report.json`, and rebuilds `data/data.js`.

Generated questions are deliberately specific. A source phrase such as ƒ?ofires periodicallyƒ?? produces an interval question; an unknown damage value produces a damage question; an unqualified damage instance produces a separate crit/status behavior question. Generic placeholder questions are used only when no more specific gap was detected.

Manual questions, claims, evidence, and tests are preserved. If a page fails to fetch, its previous records are retained and the failure is reported instead of silently deleting data. The refresh also audits every question against the Japanese Ecliptica Wiki* at <https://wikiwiki.jp/ecliptica/>. Japanese pages remain outside the English factual import boundary: they are stored as separate source records and bilingual evidence/claims with `status: "Reported"` where applicable.

## Japanese wiki audit

The Japanese audit uses the Japanese community wiki separately from the English Miraheze import. Each question receives a `japaneseAudit` object with the check date, reviewed source IDs, finding status, and linked evidence IDs. A Japanese evidence record must preserve both fields below:

When linked evidence contains useful information, the importer also creates `sourceHypothesis`, `hypothesisEvidenceIds`, and `hypothesisSourceTags` on the question. The site displays this as a separate **Source-backed hypothesis** and labels it as unconfirmed. Existing manual `currentHypothesis` text is preserved separately.

```json
{
  "type": "Japanese wiki",
  "originalInformation": "Æ'îÆŸ¦ÆŸÅÆ'œÆ'®ÆŸ®ÆŸ'ÆŸŸÆŸ^‘T'Æ?®25(+10)‡%¸‡?ÅÆŸ?ÆŸ­ÆŸ¬Æ'÷Æ?©‡^Å‡T§Æ?O‡T§‡"YÆ?TÆ'<Æ?'",
  "translation": "On a critical hit, an explosion dealing 25 (+10) Physical damage occurs.",
  "sourceRefs": [
    {
      "sourceId": "ja-wiki-...",
      "sourcePage": "Æ'½ÆŸŸÆŸ-Æ'øÆŸªÆŸ¬ÆŸ%",
      "excerpt": "Æ'îÆŸ¦ÆŸÅÆ'œÆ'®ÆŸ®ÆŸ'ÆŸŸÆŸ^‘T'Æ?®25(+10)‡%¸‡?ÅÆŸ?ÆŸ­ÆŸ¬Æ'÷Æ?©‡^Å‡T§Æ?O‡T§‡"YÆ?TÆ'<Æ?'",
      "translation": "On a critical hit, an explosion dealing 25 (+10) Physical damage occurs."
    }
  ]
}
```

The original Japanese text is evidence; the English translation is an accessibility and interpretation aid. Neither is silently merged into an English-wiki value. If Japanese and English disagree, both records remain visible and the Japanese claim stays `Reported`, not `Confirmed`. Automated refresh failures are retained in `data/import-report.json`; when a page cannot be fetched by the importer, its provenance record remains with a `browser-reviewed` status and the reviewed excerpts remain in the linked bilingual evidence records.

## Status semantics

- **Unknown** ƒ?" no defensible answer is recorded.
- **Needs Testing** ƒ?" the gap is actionable and requires an experiment.
- **Reported** ƒ?" a player or external report exists, without enough support to treat it as established.
- **Supported** ƒ?" evidence currently favors the claim.
- **Confirmed** ƒ?" repeatable evidence has closed the question.
- **Contradicted** ƒ?" evidence conflicts with the claim or source.
- **Needs Retest** ƒ?" an earlier result should be reproduced after a change or conflict.

The UI highlights `UNKNOWN`, `?`, missing intervals, missing damage, and incomplete stack rules so they cannot be mistaken for numeric values.

## Initial source pages

The import currently retains raw source text from:

- `Upgrades`
- `Classes`
- `Spellsword`, `Twinmage`, `Gunmancer`, `Fistmage`, `Spellhammer`, `Shield Mage`, `Thaumaturge`, `Nekomancer`
- `Stats`, `Stack Types`, and `Status Effects` as directly linked mechanics context
- Japanese Wiki* `Æ'½ÆŸŸÆŸ-Æ'øÆŸªÆŸ¬ÆŸ%`, `Æ'îÆŸ¸Æ'û`, `Æ'ûÆŸÅÆŸ¬Æ'¨Æ'û`, `ÆŸ?ÆŸÆŸ¯ÆŸÎÆŸ?ÆŸ`, and the eight individual class pages, reviewed as a separate bilingual audit source

The retrieval date and URL for each page are visible in `data/sources.json` and in record detail views.
