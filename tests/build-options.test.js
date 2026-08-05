const assert = require("node:assert/strict");
const fs = require("node:fs");

const page = fs.readFileSync(`${__dirname}/../index.html`, "utf8");

assert.match(page, /if \(result\.health < 1\) result\.health = 1/);
assert.match(page, /exact approaching-hard-cap formula is not yet known/);
assert.equal((page.match(/name: "(?:Encrypted Archive|Goblet of the Sun|HC Armor Plating|Heart of Cinders|Essence of Malice|Wheel of Reincarnation|Sealed Megium)"/g) || []).length, 7);
assert.match(page, /const RUNE_SLOTS = \["Penumbra", "Antumbra", "Umbra", "Eclipse"\]/);
assert.equal((page.match(/id: "(?:fragility|smolder|fever|conductor|profane|divine|rot|tremor|drain|shedding|anaemia|hypoxia|light|asthma)", name:/g) || []).length, 14);
assert.doesNotMatch(page, /artifactMultiplier|Gambit ×/);
assert.match(page, /const totalMultiplier = artifactCount/);
assert.match(page, /buildOptions\.artifacts\[card\.dataset\.id\] = Math\.min\(100/);
assert.match(page, /Shown defense:.*100% ÷ \$\{n\(calculation\.damageTaken\)\} = \$\{n\(calculation\.defense\)\}/);
assert.doesNotMatch(page, /Shown defense:.*÷ 100%/);
assert.match(page, /artifacts: ARTIFACTS\.map/);
assert.match(page, /runes: buildOptions\.runes\.map/);
assert.match(page, /curses: buildOptions\.curses\.map/);
assert.match(page, /id: "hypoxia", name: "Hypoxia", effect: "Healing Received -15% per stack\.", stats: p => \(\{ healingReceived: -15 \* p \}\)/);
assert.match(page, /id: "shedding", name: "Shedding", effect: "Overall Defense -7% per stack\.", stats: p => \(\{ overallDefense: -7 \* p \}\)/);
assert.match(page, /id="reset-build"[^>]*>Reset build<\/button>/);
assert.match(page, /data-remove-rune="\$\{index\}"/);
assert.match(page, /buildOptions\.artifacts = \{\};[\s\S]*buildOptions\.runes = RUNE_SLOTS\.map\(\(\) => null\);[\s\S]*buildOptions\.curses = RUNE_SLOTS\.map\(\(\) => null\);/);

console.log("Build option regression tests passed.");
