(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.DefenseCalculation = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const BASE_DAMAGE_TAKEN = 100;
  const LOWER_SOFT_CAP = 50;

  function calculateDefense(defenseModifier) {
    const rawDamageTaken = BASE_DAMAGE_TAKEN - defenseModifier;
    const isSoftCapped = defenseModifier > LOWER_SOFT_CAP;
    const damageTaken = isSoftCapped
      ? LOWER_SOFT_CAP ** 2 / defenseModifier
      : rawDamageTaken;

    return {
      defense: BASE_DAMAGE_TAKEN ** 2 / damageTaken,
      damageTaken,
      rawDamageTaken,
      defenseModifier,
      isSoftCapped,
      softCap: LOWER_SOFT_CAP,
      numerator: LOWER_SOFT_CAP ** 2
    };
  }

  return { BASE_DAMAGE_TAKEN, LOWER_SOFT_CAP, calculateDefense };
});
