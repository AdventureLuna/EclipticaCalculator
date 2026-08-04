const assert = require("node:assert/strict");
const fs = require("node:fs");

const page = fs.readFileSync(`${__dirname}/../index.html`, "utf8");

assert.match(page, /if \(result\.health < 1\) result\.health = 1/);
assert.match(page, /exact approaching-hard-cap formula is not yet known/);
assert.equal((page.match(/name: "(?:Encrypted Archive|Goblet of the Sun|HC Armor Plating|Heart of Cinders|Essence of Malice|Wheel of Reincarnation|Sealed Megium)"/g) || []).length, 7);
assert.match(page, /const RUNE_SLOTS = \["Penumbra", "Antumbra", "Umbra", "Eclipse"\]/);
assert.equal((page.match(/id: "(?:fragility|smolder|fever|conductor|profane|divine|rot|tremor|drain|shedding|anaemia|hypoxia|light|asthma)", name:/g) || []).length, 14);
assert.match(page, /const artifactMultiplier = gambitSlot < 0 \? 1 : gambitSlot \+ 3/);

console.log("Build option regression tests passed.");
