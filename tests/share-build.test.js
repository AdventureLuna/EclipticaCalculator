const assert = require("node:assert/strict");
const {
  BitWriter, encodeBuild, decodeBuild, bytesToBase64Url
} = require("../share-build.js");

const options = {
  characterCount: 8,
  upgradeCount: 115,
  // Test character 0 rejects upgrade 1; production supplies its real eligibility table.
  isUpgradeAllowed: (upgradeId, characterId) => !(characterId === 0 && upgradeId === 1)
};

function roundTrip(characterId, upgrades) {
  const build = { version: 1, characterId, upgrades };
  const result = decodeBuild(encodeBuild(build), options);
  assert.deepEqual({ version: result.version, characterId: result.characterId, upgrades: result.upgrades }, build);
}

roundTrip(0, []); // Empty build.
roundTrip(1, [{ id: 0, count: 1 }]);
roundTrip(7, [1, 2, 3, 4, 100].map((count, index) => ({ id: index + 2, count })));
roundTrip(4, [{ id: 0, count: 2 }, { id: 114, count: 100 }]);
roundTrip(3, Array.from({ length: 15 }, (_, id) => ({ id: id + 10, count: id + 1 })));
for (let characterId = 0; characterId < 8; characterId++) roundTrip(characterId, []);

assert.throws(() => decodeBuild("not+base64", options), /Base64URL/);
assert.throws(() => decodeBuild(encodeBuild({ version: 1, characterId: 2, upgrades: [{ id: 2, count: 100 }] }).slice(0, -2), options), /Truncated|stack count/);

const unsupported = new BitWriter();
unsupported.writeBits(2, 3);
assert.throws(() => decodeBuild(bytesToBase64Url(unsupported.toBytes()), options), /Unsupported/);

const unknown = decodeBuild(encodeBuild({ version: 1, characterId: 2, upgrades: [{ id: 120, count: 1 }] }), options);
assert.deepEqual(unknown.upgrades, []);
assert.equal(unknown.warnings.length, 1);

const ineligible = decodeBuild(encodeBuild({ version: 1, characterId: 0, upgrades: [{ id: 1, count: 2 }] }), options);
assert.deepEqual(ineligible.upgrades, []);
assert.match(ineligible.warnings[0], /not valid/);

// A fresh-page adapter receives exactly the character and counts present in the URL code.
const original = { version: 1, characterId: 6, upgrades: [{ id: 0, count: 4 }, { id: 114, count: 100 }] };
const freshState = { characterId: null, counts: {} };
const loaded = decodeBuild(encodeBuild(original), options);
freshState.characterId = loaded.characterId;
freshState.counts = Object.fromEntries(loaded.upgrades.map(entry => [entry.id, entry.count]));
assert.deepEqual(freshState, { characterId: 6, counts: { 0: 4, 114: 100 } });

console.log("Share-build codec tests passed.");
