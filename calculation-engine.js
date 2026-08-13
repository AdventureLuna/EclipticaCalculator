(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.EclipticaCalculationEngine = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const finite = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
  const attenuate = (multiplier, magnitude) => 1 + (finite(multiplier, 1) - 1) * finite(magnitude, 1);

  function calculateDamage(source, criticalChance, criticalDamageMultiplier) {
    const overallMultiplier = source.overallDamageApplies === false ? 1 : finite(source.overallMultiplier, 1);
    const elementalMultiplier = finite(source.elementalMultiplier, 1);
    const sourceMultiplier = finite(source.sourceMultiplier, 1);
    const bareDamage = finite(source.baseDamage) * overallMultiplier * elementalMultiplier * sourceMultiplier;
    const nonCriticalDamage = Math.round(bareDamage);
    const criticalDamage = source.canCrit ? Math.round(bareDamage * criticalDamageMultiplier) : nonCriticalDamage;
    const averageDamage = source.canCrit
      ? nonCriticalDamage * (1 - criticalChance) + criticalDamage * criticalChance
      : nonCriticalDamage;
    const effectiveCriticalMultiplier = source.canCrit ? 1 + (criticalDamageMultiplier - 1) * criticalChance : 1;
    return {
      bareDamage,
      nonCriticalDamage,
      criticalDamage,
      averageDamage,
      effectiveCriticalMultiplier,
      overallMultiplier,
      elementalMultiplier,
      sourceMultiplier
    };
  }

  function resolveRate(spec, criticalHitsPerSecond = 0) {
    if (spec.trigger?.type === "onCrit") return criticalHitsPerSecond * finite(spec.trigger.instancesPerTrigger, 1);
    if (spec.instanceRate != null) return Math.max(0, finite(spec.instanceRate));
    return Math.max(0, finite(spec.activationRate) * Math.max(0, finite(spec.instancesPerActivation, 1)));
  }

  function resolveSource(spec, context, criticalHitsPerSecond = 0) {
    const instancesPerSecond = resolveRate(spec, criticalHitsPerSecond);
    const damage = calculateDamage(spec, context.criticalChance, context.criticalDamageMultiplier);
    const dps = damage.averageDamage * instancesPerSecond;
    const uptime = spec.uptime == null ? 1 : Math.max(0, Math.min(1, finite(spec.uptime, 1)));
    return {
      ...spec,
      instancesPerActivation: Math.max(0, finite(spec.instancesPerActivation, 1)),
      projectiles: Math.max(1, finite(spec.projectiles, spec.instancesPerActivation || 1)),
      statuses: Array.isArray(spec.statuses) ? spec.statuses.filter(status => Number.isFinite(status.chance) && status.chance > 0) : [],
      damage: {
        ...damage,
        instancesPerSecond,
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
      return total + source.damage.instancesPerSecond * finite(status?.chance) * finite(source.damage.sourceMultiplier, 1);
    }, 0);
    const weight = sources.reduce((total, source) => {
      const status = source.statuses.find(item => item.id === statusId);
      return total + source.damage.instancesPerSecond * finite(status?.chance);
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
        const applicationChance = finite(status.chance) / penalty;
        return [{
          sourceId: source.id,
          name: source.name,
          instancesPerSecond: source.damage.instancesPerSecond,
          applicationChance,
          applicationsPerSecond: source.damage.instancesPerSecond * applicationChance
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
    const element = status.damageStat.replace(/Damage$/, "");
    return resolveSource({
      id: `status-${status.id}`,
      name: status.name,
      position: "Status effect",
      element,
      baseDamage: status.baseDamage,
      canCrit: false,
      instanceRate: 1 / status.tickInterval,
      overallMultiplier: attenuate(context.overallMultiplier, magnitude),
      elementalMultiplier: attenuate(context.elementalMultipliers[element], magnitude),
      sourceMultiplier: status.sourceMultiplier,
      uptime: status.uptime == null ? 1 : status.uptime,
      isStatusEffect: true,
      statusId: status.id,
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
      elementalMultipliers: input.elementalMultipliers || {},
      statusDefinitions: input.statusDefinitions || {},
      stickyStacks: finite(input.stickyStacks)
    };
    const directSpecs = input.sources.filter(source => source.trigger?.type !== "onCrit");
    const onCritSpecs = input.sources.filter(source => source.trigger?.type === "onCrit");
    const directSources = directSpecs.map(source => resolveSource(source, context));
    const criticalSources = directSources.filter(source => source.canCrit);
    const criticalInstanceRate = criticalSources.reduce((sum, source) => sum + source.damage.instancesPerSecond, 0);
    const criticalHitsPerSecond = criticalInstanceRate * context.criticalChance;
    const weightedCriticalSourceMultiplier = criticalInstanceRate > 0
      ? criticalSources.reduce((sum, source) => sum + source.damage.instancesPerSecond * source.damage.sourceMultiplier, 0) / criticalInstanceRate
      : 1;
    const triggeredSources = onCritSpecs.map(source => resolveSource({
      ...source,
      sourceMultiplier: source.sourceMultiplierStrategy === "weightedCritSources" ? weightedCriticalSourceMultiplier : source.sourceMultiplier
    }, context, criticalHitsPerSecond));
    const attackSources = [...directSources, ...triggeredSources];
    const statuses = resolveStatuses(attackSources, context);
    const statusSources = statuses.map(status => createStatusDamageSource(status, context)).filter(Boolean);
    statusSources.forEach((source, index) => { source.isStatusGroupStart = index === 0; });
    const damageSources = [...attackSources, ...statusSources];
    const combinedTotalDps = damageSources.reduce((sum, source) => sum + source.damage.totalDps, 0);
    return {
      context,
      attackSources,
      statusSources,
      damageSources,
      statuses,
      criticalSources,
      criticalInstanceRate,
      criticalHitsPerSecond,
      weightedCriticalSourceMultiplier,
      combinedTotalDps
    };
  }

  return { calculate, calculateDamage, resolveRate, attenuate };
});

