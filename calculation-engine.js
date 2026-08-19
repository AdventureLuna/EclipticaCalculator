(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.EclipticaCalculationEngine = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const attenuate = (multiplier, magnitude) => 1 + (finite(multiplier, 1) - 1) * finite(magnitude, 1);
  const DAMAGE_TYPE_ALIASES = Object.freeze({ lightning: "electric" });

  function normalizeDamageType(value) {
    const damageType = String(value || "").trim().toLowerCase();
    return DAMAGE_TYPE_ALIASES[damageType] || damageType;
  }

  function normalizeElementalMultipliers(value) {
    const input = value && typeof value === "object" ? value : {};
    const normalized = {};
    Object.entries(input).forEach(([damageType, multiplier]) => {
      const canonical = normalizeDamageType(damageType);
      if (canonical !== damageType && Object.hasOwn(input, canonical)) return;
      normalized[canonical] = finite(multiplier, 1);
    });
    return normalized;
  }

  function calculateDamage(source, criticalChance, criticalDamageMultiplier) {
    const overallMultiplier = source.overallDamageApplies === false ? 1 : finite(source.overallMultiplier, 1);
    const elementalMultiplier = finite(source.elementalMultiplier, 1);
    const sourceMultiplier = finite(source.sourceMultiplier, 1);
    const bareDamage = finite(source.baseDamage) * overallMultiplier * elementalMultiplier * sourceMultiplier;
    const nonCriticalDamage = Math.round(bareDamage);
    const criticalDamage = source.canCrit ? Math.round(bareDamage * criticalDamageMultiplier) : nonCriticalDamage;
    const averageDamagePerHit = source.canCrit
      ? nonCriticalDamage * (1 - criticalChance) + criticalDamage * criticalChance
      : nonCriticalDamage;
    const effectiveCriticalMultiplier = source.canCrit ? 1 + (criticalDamageMultiplier - 1) * criticalChance : 1;
    return {
      bareDamage,
      nonCriticalDamage,
      criticalDamage,
      averageDamagePerHit,
      effectiveCriticalMultiplier,
      overallMultiplier,
      elementalMultiplier,
      sourceMultiplier
    };
  }

  function resolveActivationRate(spec, criticalHitsPerSecond = 0) {
    if (spec.trigger?.type === "onCrit") return criticalHitsPerSecond;
    if (spec.instanceRate != null) return Math.max(0, finite(spec.instanceRate));
    return Math.max(0, finite(spec.activationRate));
  }

  function resolveSource(spec, context, criticalHitsPerSecond = 0) {
    const element = normalizeDamageType(spec.element);
    const normalizedSpec = {
      ...spec,
      element,
      damageStat: spec.damageStat || (element ? `${element}Damage` : ""),
      elementalMultiplier: spec.elementalMultiplier == null
        ? finite(context.elementalMultipliers[element], 1)
        : spec.elementalMultiplier
    };
    const activationRate = resolveActivationRate(spec, criticalHitsPerSecond);
    const configuredHits = spec.hitsPerActivation
      ?? (spec.trigger?.type === "onCrit" ? spec.trigger.instancesPerTrigger : null)
      ?? spec.instancesPerActivation
      ?? 1;
    const hitsPerActivation = Math.max(0, finite(configuredHits, 1));
    const hitsPerSecond = activationRate * hitsPerActivation;
    const damage = calculateDamage(normalizedSpec, context.criticalChance, context.criticalDamageMultiplier);
    const averageDamage = damage.averageDamagePerHit * hitsPerActivation;
    const dps = averageDamage * activationRate;
    const uptime = spec.uptime == null ? 1 : Math.max(0, Math.min(1, finite(spec.uptime, 1)));
    return {
      ...normalizedSpec,
      hitsPerActivation,
      instancesPerActivation: hitsPerActivation,
      projectiles: Math.max(1, finite(spec.projectiles, hitsPerActivation || 1)),
      statuses: Array.isArray(spec.statuses) ? spec.statuses.filter(status => Number.isFinite(status.chance) && status.chance > 0) : [],
      damage: {
        ...damage,
        averageDamage,
        activationRate,
        hitsPerSecond,
        dps,
        uptime,
        totalDps: dps * uptime,
        overallDamageApplies: spec.overallDamageApplies !== false
      }
    };
  }

  function weightedSourceMultiplier(sources, statusId) {
    const weighted = sources.reduce((total, source) => {
      const status = source.statuses.find(item => item.id === statusId);
      const sourceMultiplier = source.statusSourceMultiplierApplies === false ? 1 : finite(source.damage.sourceMultiplier, 1);
      return total + source.damage.hitsPerSecond * finite(status?.chance) * sourceMultiplier;
    }, 0);
    const weight = sources.reduce((total, source) => {
      const status = source.statuses.find(item => item.id === statusId);
      return total + source.damage.hitsPerSecond * finite(status?.chance);
    }, 0);
    return weight > 0 ? weighted / weight : 1;
  }

  function resolveStatuses(attackSources, context) {
    const statusIds = [...new Set(attackSources.flatMap(source => source.statuses.map(status => status.id)))];
    return statusIds.map(statusId => {
      const definition = context.statusDefinitions[statusId] || { id: statusId, name: statusId };
      const penalty = Math.max(1, finite(definition.bossApplicationPenalty, 1));
      const sources = attackSources.flatMap(source => {
        const status = source.statuses.find(item => item.id === statusId);
        if (!status) return [];
        const baseApplicationChance = finite(status.chance);
        const applicationChance = baseApplicationChance / penalty;
        return [{
          sourceId: source.id,
          name: source.name,
          hitsPerSecond: source.damage.hitsPerSecond,
          baseApplicationChance,
          bossApplicationPenalty: penalty,
          applicationChance,
          applicationsPerSecond: source.damage.hitsPerSecond * applicationChance
        }];
      });
      const applicationsPerSecond = sources.reduce((sum, source) => sum + source.applicationsPerSecond, 0);
      const applicationInterval = applicationsPerSecond > 0 ? 1 / applicationsPerSecond : Infinity;
      const stacksPerApplication = definition.baseStacks == null
        ? null
        : finite(definition.baseStacks) + finite(context.stickyStacks) * finite(definition.stacksPerSticky);
      const duration = definition.durationPerStack == null || stacksPerApplication == null
        ? null
        : stacksPerApplication * finite(definition.durationPerStack);
      const rawUptime = duration == null ? null : duration * applicationsPerSecond;
      const uptime = rawUptime == null ? null : Math.min(1, rawUptime);
      return {
        ...definition,
        id: statusId,
        penalty,
        sources,
        applicationsPerSecond,
        applicationInterval,
        stacksPerApplication,
        duration,
        rawUptime,
        uptime,
        sourceMultiplier: weightedSourceMultiplier(attackSources, statusId)
      };
    }).filter(status => status.applicationsPerSecond > 0);
  }

  function createStatusDamageSource(status, context) {
    if (status.baseDamage == null || status.tickInterval == null) return null;
    const magnitude = status.damageScaling == null ? 1 : finite(status.damageScaling, 1);
    const element = normalizeDamageType(status.damageStat.replace(/Damage$/, ""));
    return resolveSource({
      id: `status-${status.id}`,
      name: status.name,
      position: "Status effect",
      element,
      damageStat: status.damageStat,
      baseDamage: status.baseDamage,
      canCrit: false,
      instanceRate: 1 / status.tickInterval,
      overallMultiplier: attenuate(context.overallMultiplier, magnitude),
      elementalMultiplier: attenuate(context.elementalMultipliers[element], magnitude),
      sourceMultiplier: status.sourceMultiplier,
      uptime: status.uptime == null ? 1 : status.uptime,
      isStatusEffect: true,
      statusId: status.id,
      rateInterval: status.tickInterval,
      rateIntervalLabel: "tick interval",
      statusDuration: status.duration,
      statusInterval: status.applicationInterval,
      damageScaling: magnitude,
      statuses: []
    }, context);
  }

  function calculate(input) {
    const context = {
      criticalChance: Math.max(0, finite(input.criticalChance)),
      criticalDamageMultiplier: finite(input.criticalDamageMultiplier, 1),
      overallMultiplier: finite(input.overallMultiplier, 1),
      elementalMultipliers: normalizeElementalMultipliers(input.elementalMultipliers),
      statusDefinitions: input.statusDefinitions || {},
      stickyStacks: finite(input.stickyStacks)
    };
    const directSpecs = input.sources.filter(source => source.trigger?.type !== "onCrit");
    const onCritSpecs = input.sources.filter(source => source.trigger?.type === "onCrit");
    const directSources = directSpecs.map(source => resolveSource(source, context));
    const activeDirectSources = directSources.filter(source => source.excluded !== true);
    const criticalSources = activeDirectSources.filter(source => source.canCrit);
    const criticalHitEligibleRate = criticalSources.reduce((sum, source) => sum + source.damage.hitsPerSecond, 0);
    const criticalHitsPerSecond = criticalHitEligibleRate * context.criticalChance;
    const weightedCriticalSourceMultiplier = criticalHitEligibleRate > 0
      ? criticalSources.reduce((sum, source) => sum + source.damage.hitsPerSecond * source.damage.sourceMultiplier, 0) / criticalHitEligibleRate
      : 1;
    const triggeredSources = onCritSpecs.map(source => resolveSource({
      ...source,
      sourceMultiplier: source.sourceMultiplierStrategy === "weightedCritSources" ? weightedCriticalSourceMultiplier : source.sourceMultiplier
    }, context, criticalHitsPerSecond));
    const attackSources = [...directSources, ...triggeredSources];
    const activeAttackSources = [...activeDirectSources, ...triggeredSources.filter(source => source.excluded !== true)];
    const statuses = resolveStatuses(activeAttackSources, context);
    const statusSources = statuses.map(status => createStatusDamageSource(status, context)).filter(Boolean);
    statusSources.forEach((source, index) => { source.isStatusGroupStart = index === 0; });
    const damageSources = [...attackSources, ...statusSources];
    const combinedTotalDps = damageSources.filter(source => source.excluded !== true)
      .reduce((sum, source) => sum + source.damage.totalDps, 0);
    return {
      context,
      attackSources,
      activeAttackSources,
      statusSources,
      damageSources,
      statuses,
      criticalSources,
      criticalHitEligibleRate,
      criticalInstanceRate: criticalHitEligibleRate,
      criticalHitsPerSecond,
      weightedCriticalSourceMultiplier,
      combinedTotalDps
    };
  }

  return { calculate, calculateDamage, resolveRate: resolveActivationRate, resolveActivationRate, attenuate, normalizeDamageType, normalizeElementalMultipliers };
});
