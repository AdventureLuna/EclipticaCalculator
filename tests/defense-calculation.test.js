const assert = require("node:assert/strict");
const { calculateDefense } = require("../defense-calculation.js");

assert.deepEqual(calculateDefense(0), {
  defense: 100, damageTaken: 100, rawDamageTaken: 100, defenseModifier: 0,
  isSoftCapped: false, softCap: 50, numerator: 2500
});
assert.equal(calculateDefense(20).damageTaken, 80);
assert.equal(calculateDefense(20).defense, 125);
assert.equal(calculateDefense(-20).damageTaken, 120);
assert.equal(calculateDefense(-20).defense, 10000 / 120);
assert.equal(calculateDefense(50).defense, 200);
assert.equal(calculateDefense(100).damageTaken, 25);
assert.equal(calculateDefense(100).defense, 400);
assert.equal(calculateDefense(200).damageTaken, 12.5);
assert.equal(calculateDefense(200).defense, 800);

console.log("Defense calculation tests passed.");
