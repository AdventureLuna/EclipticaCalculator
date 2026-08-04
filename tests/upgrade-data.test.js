const assert = require("node:assert/strict");
const fs = require("node:fs");

const page = fs.readFileSync(`${__dirname}/../index.html`, "utf8");

// Regression checks for the numerical changes in the August 2026 English wiki data.
assert.match(page, /"Thaumaturge: Proficiency","[^"]*Cooldown: -10% \(-10% per stack\)"/);
assert.match(page, /"Spellsword: Proficiency","Piercing Strike range: \+4/);
assert.match(page, /"Spellsword: Mastery","Restore 2 \(\+2 per stack\) HP/);
assert.match(page, /"Spellsword: Whirlwind","[^"]*Charge Time \+30% \(\+30% per stack\)"/);
assert.match(page, /"Gunmancer: Proficiency \(Photon Condenser\)","Photon Condenser Projectile Count \+2/);
assert.match(page, /"Thunder Aura","Every second inflict 25/);
assert.match(page, /"Big and Wrathful","[^"]*Defense at LOW HP -25%"/);
assert.match(page, /\["healingReceived", "Poison_Aspect", -5\]/);
assert.match(page, /\["healthRegeneration", "Spellsword_Mastery", -100\]/);
assert.match(page, /"Pocket Abacus","[^"]*Overall Damage -10% \(-10% per stack\)/);
assert.match(page, /\["overallDamage", "Pocket_Abacus", -10\]/);
assert.equal((page.match(/Defense -10% per stack\.\", stats: p => \(\{ \w+Defense: -10 \* p \}\)/g) || []).length, 7);

console.log("Upgrade data regression tests passed.");
