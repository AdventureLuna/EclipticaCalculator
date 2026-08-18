const assert = require("node:assert/strict");
const Engine = require("../calculation-engine.js");

const statusDefinitions = {
  burning: { id: "burning", name: "Burning", baseDamage: 25, damageStat: "fireDamage", tickInterval: .5, baseStacks: 20, stacksPerSticky: 2, durationPerStack: .5, bossApplicationPenalty: 3 },
  poisoned: { id: "poisoned", name: "Poison", baseDamage: 30, damageStat: "poisonDamage", tickInterval: .75, baseStacks: 8, stacksPerSticky: 2, durationPerStack: .75, bossApplicationPenalty: 1, damageScaling: .75 }
};

const baseInput = {
  criticalChance: .2,
  criticalDamageMultiplier: 1.5,
  overallMultiplier: 1,
  elementalMultipliers: { physical: 1, fire: 1, poison: 1 },
  statusDefinitions,
  stickyStacks: 0
};

const result = Engine.calculate({
  ...baseInput,
  sources: [
    { id: "foul", name: "Foul Pustule", element: "poison", baseDamage: 30, canCrit: true, activationRate: .75, instancesPerActivation: 2, projectiles: 2, statuses: [{ id: "poisoned", chance: .1 }] },
    { id: "spirit", name: "Flaming Spirit", element: "fire", baseDamage: 16, canCrit: true, activationRate: .75, instancesPerActivation: 1, overallDamageApplies: false, statuses: [{ id: "burning", chance: .1 / 3 }] },
    { id: "charged", name: "Charged Strike", element: "physical", baseDamage: 25, canCrit: false, sourceMultiplierStrategy: "weightedCritSources", trigger: { type: "onCrit", instancesPerTrigger: 1 }, statuses: [] }
  ]
});

assert.equal(result.attackSources.find(source => source.id === "foul").damage.activationRate, .75);
assert.equal(result.attackSources.find(source => source.id === "foul").damage.hitsPerSecond, 1.5);
assert.equal(result.attackSources.find(source => source.id === "foul").damage.averageDamagePerHit, 33);
assert.equal(result.attackSources.find(source => source.id === "foul").damage.averageDamage, 66);
assert.equal(result.attackSources.find(source => source.id === "spirit").damage.activationRate, .75);
assert.equal(result.criticalInstanceRate, 2.25);
assert.equal(result.criticalHitsPerSecond, .45);
assert.equal(result.attackSources.find(source => source.id === "charged").damage.activationRate, .45);
assert.ok(result.statuses.some(status => status.id === "poisoned"));
assert.ok(result.statuses.some(status => status.id === "burning"));
assert.equal(result.statuses.find(status => status.id === "burning").sources[0].name, "Flaming Spirit");
assert.equal(result.statuses.find(status => status.id === "burning").sources[0].bossApplicationPenalty, 3);
assert.equal(result.statuses.find(status => status.id === "burning").sources[0].baseApplicationChance, .1 / 3);
assert.equal(result.statusSources.find(source => source.statusId === "burning").damage.activationRate, 2);

const excludedSpirit = Engine.calculate({
  ...baseInput,
  sources: [
    { id: "foul", name: "Foul Pustule", element: "poison", baseDamage: 30, canCrit: true, activationRate: .75, instancesPerActivation: 2, statuses: [{ id: "poisoned", chance: .1 }] },
    { id: "spirit", name: "Flaming Spirit", element: "fire", baseDamage: 16, canCrit: true, activationRate: .75, excluded: true, statuses: [{ id: "burning", chance: .1 / 3 }] },
    { id: "charged", name: "Charged Strike", element: "physical", baseDamage: 25, canCrit: false, trigger: { type: "onCrit" }, statuses: [] }
  ]
});
assert.ok(excludedSpirit.attackSources.some(source => source.id === "spirit" && source.excluded));
assert.ok(excludedSpirit.activeAttackSources.every(source => source.id !== "spirit"));
assert.equal(excludedSpirit.criticalHitEligibleRate, 1.5);
assert.equal(excludedSpirit.criticalHitsPerSecond, .3);
assert.equal(excludedSpirit.attackSources.find(source => source.id === "charged").damage.activationRate, .3);
assert.ok(excludedSpirit.statuses.some(status => status.id === "poisoned"));
assert.ok(!excludedSpirit.statuses.some(status => status.id === "burning"));

const volley = Engine.calculate({
  ...baseInput,
  criticalChance: .2,
  sources: [{ id: "volley", name: "Volley", element: "physical", baseDamage: 10, canCrit: true, activationRate: .2, instancesPerActivation: 5, projectiles: 5, statuses: [{ id: "burning", chance: .1 }] }]
});
const volleySource = volley.attackSources[0];
assert.equal(volleySource.damage.nonCriticalDamage, 10);
assert.equal(volleySource.damage.criticalDamage, 15);
assert.equal(volleySource.damage.averageDamagePerHit, 11);
assert.equal(volleySource.damage.averageDamage, 55);
assert.equal(volleySource.damage.activationRate, .2);
assert.equal(volleySource.damage.hitsPerSecond, 1);
assert.equal(volleySource.damage.dps, 11);
assert.equal(volley.criticalHitsPerSecond, .2);
assert.equal(volley.statuses[0].applicationsPerSecond, .1);

const weightedTrigger = Engine.calculate({
  ...baseInput,
  sources: [
    { id: "fast", name: "Fast hand", element: "fire", baseDamage: 10, canCrit: true, activationRate: 2, sourceMultiplier: 1.2, statuses: [] },
    { id: "slow", name: "Slow hand", element: "frost", baseDamage: 10, canCrit: true, activationRate: 1, sourceMultiplier: .8, statuses: [] },
    { id: "charged", name: "Charged Strike", element: "physical", baseDamage: 25, canCrit: false, sourceMultiplierStrategy: "weightedCritSources", trigger: { type: "onCrit" }, statuses: [] }
  ]
});
assert.equal(weightedTrigger.weightedCriticalSourceMultiplier, (2 * 1.2 + 1 * .8) / 3);
assert.equal(weightedTrigger.attackSources.find(source => source.id === "charged").sourceMultiplier, weightedTrigger.weightedCriticalSourceMultiplier);

const noImplicitStatus = Engine.calculate({
  ...baseInput,
  sources: [{ id: "plain-fire", name: "Plain Fire", element: "fire", baseDamage: 10, canCrit: true, activationRate: 1, statuses: [] }]
});
assert.equal(noImplicitStatus.statuses.length, 0);


console.log("Unified calculation engine tests passed.");
