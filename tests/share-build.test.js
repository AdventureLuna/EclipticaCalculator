const assert = require("node:assert/strict");
const {
  BitWriter, FORMAT_VERSION, CONFIG_FIELD_IDS, encodeBuild, decodeBuild, bytesToBase64Url, base64UrlToBytes
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
unsupported.writeBits(4, 3);
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

const completeBuild = {
  version: 2,
  characterId: 5,
  upgrades: [{ id: 4, count: 3 }, { id: 92, count: 17 }],
  artifacts: [{ id: 0, count: 2 }, { id: 6, count: 100 }],
  runes: [0, 17, null, 5],
  curses: [13, null, 0, 5]
};
const completeResult = decodeBuild(encodeBuild(completeBuild), { ...options, artifactCount: 7, runeCount: 18, curseCount: 14 });
assert.deepEqual({ ...completeResult, warnings: undefined }, { ...completeBuild, configuration: {}, warnings: undefined });

// Version 1 links remain valid and receive empty build-option defaults.
const legacy = decodeBuild(encodeBuild({ version: 1, characterId: 2, upgrades: [] }), options);
assert.deepEqual(legacy.artifacts, []);
assert.deepEqual(legacy.runes, [null, null, null, null]);
assert.deepEqual(legacy.curses, [null, null, null, null]);
assert.deepEqual(legacy.configuration, {});

function roundTripV3(characterId, configuration) {
  const build = {
    version: FORMAT_VERSION,
    characterId,
    upgrades: [{ id: 4, count: 3 }],
    artifacts: [{ id: 2, count: 2 }],
    runes: [0, null, 5, null],
    curses: [null, 3, null, 1],
    configuration
  };
  const result = decodeBuild(encodeBuild(build), { ...options, artifactCount: 7, runeCount: 18, curseCount: 14 });
  assert.deepEqual({ ...result, warnings: undefined }, { ...build, warnings: undefined });
}

roundTripV3(1, {
  berserkerSoulStacks: 137,
  twinmage: { primary: 5, secondary: 1, primaryDamage: false, secondaryDamage: true }
});
roundTripV3(2, {
  gunmancer: { primary: 1, secondary: 2, damageGroup: 1, airblastTarget: 2 },
  excludedDamageSources: [6, 18, 32]
});
roundTripV3(7, {
  nekomancer: { zombie: 2, balloon: 0, ballista: 1, souls: 3 }
});
roundTripV3(0, {
  berserkerSoulStacks: 70,
  spellsword: { damageGroup: 1, chargeMode: 3, customChargeMs: 2375, bleedChance: 27.5, whirlwindHits: 12 },
  excludedDamageSources: [39, 40]
});

// Default class values are represented by the empty configuration marker.
const defaultV2 = encodeBuild({ version: 2, characterId: 1, upgrades: [] });
const defaultV3 = encodeBuild({
  version: 3,
  characterId: 1,
  upgrades: [],
  configuration: { twinmage: { primary: 0, secondary: 2, primaryDamage: true, secondaryDamage: true } }
});
assert.equal(base64UrlToBytes(defaultV3).length, base64UrlToBytes(defaultV2).length + 1);
assert.deepEqual(decodeBuild(defaultV3, options).configuration, {});

function replaceConfigurationBlock(code, blockBytes) {
  const bytes = base64UrlToBytes(code);
  return bytesToBase64Url(Uint8Array.from([...bytes.slice(0, -1), ...blockBytes]));
}

// Unknown fields remain forward-compatible and duplicate fields keep the first value.
const unknownConfiguration = decodeBuild(replaceConfigurationBlock(defaultV3, [3, 99, 1, 7]), options);
assert.deepEqual(unknownConfiguration.configuration, {});
assert.match(unknownConfiguration.warnings[0], /unknown configuration field 99/);

const twinmageCode = encodeBuild({
  version: 3,
  characterId: 1,
  upgrades: [],
  configuration: { twinmage: { primary: 5, secondary: 1, primaryDamage: true, secondaryDamage: false } }
});
const twinmageBytes = base64UrlToBytes(twinmageCode);
const twinmagePayload = twinmageBytes[twinmageBytes.length - 1];
const duplicateConfiguration = bytesToBase64Url(Uint8Array.from([
  ...twinmageBytes.slice(0, -4), 6,
  CONFIG_FIELD_IDS.TWINMAGE, 1, twinmagePayload,
  CONFIG_FIELD_IDS.TWINMAGE, 1, 0
]));
const duplicateResult = decodeBuild(duplicateConfiguration, options);
assert.deepEqual(duplicateResult.configuration.twinmage, { primary: 5, secondary: 1, primaryDamage: true, secondaryDamage: false });
assert.match(duplicateResult.warnings[0], /duplicate configuration field 2/);

assert.throws(() => decodeBuild(replaceConfigurationBlock(defaultV3, [2, CONFIG_FIELD_IDS.TWINMAGE, 1]), options), /Truncated configuration entry/);
assert.throws(() => decodeBuild(replaceConfigurationBlock(defaultV3, [3, CONFIG_FIELD_IDS.TWINMAGE, 1, 0]), options), /Invalid Twinmage/);
assert.throws(() => decodeBuild(bytesToBase64Url(Uint8Array.from([...base64UrlToBytes(defaultV3), 0])), options), /trailing build data/i);
assert.throws(() => encodeBuild({
  version: 3,
  characterId: 7,
  upgrades: [],
  configuration: { nekomancer: { zombie: 2, balloon: 2, ballista: 0, souls: 5 } }
}), /Invalid Nekomancer/);
assert.throws(() => encodeBuild({ version: 3, characterId: 2, upgrades: [], configuration: { excludedDamageSources: [4, 4] } }), /Invalid excluded damage sources/);
assert.throws(() => decodeBuild(replaceConfigurationBlock(defaultV3, [2, CONFIG_FIELD_IDS.EXCLUDED_DAMAGE_SOURCES, 0]), options), /Invalid excluded damage sources payload/);
assert.throws(() => encodeBuild({ version: 3, characterId: 0, upgrades: [], configuration: { spellsword: { damageGroup: 1, chargeMode: 3, customChargeMs: 1999, bleedChance: null, whirlwindHits: 1 } } }), /Invalid Spellsword/);
const legacySpellswordCharge = decodeBuild(replaceConfigurationBlock(defaultV3, [6, CONFIG_FIELD_IDS.SPELLSWORD, 4, 96, 1, 244, 255]), options);
assert.equal(legacySpellswordCharge.configuration.spellsword.customChargeMs, 500);
assert.throws(() => decodeBuild(replaceConfigurationBlock(defaultV3, [6, CONFIG_FIELD_IDS.SPELLSWORD, 4, 0, 0, 100, 255]), options), /Invalid Spellsword/);

console.log("Share-build codec tests passed.");
