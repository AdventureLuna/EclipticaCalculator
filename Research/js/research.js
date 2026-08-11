(() => {
  "use strict";

  const FILES = ["upgrades", "classes", "questions", "claims", "evidence", "tests", "sources", "import-report"];
  const STATUS_ORDER = ["Unknown", "Needs Testing", "Reported", "Supported", "Confirmed", "Contradicted", "Needs Retest"];
  const NOTES_STORAGE_KEY = "ecliptica-research-page-notes-v1";
  const NOTES_VISIBILITY_KEY = "ecliptica-research-page-notes-hidden-v1";
  const app = document.getElementById("app");
  const state = { route: "overview", detail: null, globalQuery: "", upgradeSearch: "", upgradeFamily: "", upgradeRarity: "", upgradeStatus: "", upgradeSort: "name", classSearch: "", abilitySearch: "", abilityType: "", questionSearch: "", questionStatus: "", questionType: "", questionSort: "priority", missingOnly: false };
  let data = null;
  let pageNotes = {};
  let notesHidden = false;

  try {
    pageNotes = JSON.parse(localStorage.getItem(NOTES_STORAGE_KEY) || "{}");
    notesHidden = localStorage.getItem(NOTES_VISIBILITY_KEY) === "true";
  } catch (error) {
    pageNotes = {};
    notesHidden = false;
  }

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
  }

  function normalized(value) { return String(value ?? "").toLocaleLowerCase(); }
  function matches(value, query) { return !query || normalized(value).includes(normalized(query)); }
  function statusClass(value) { return normalized(value).replace(/\s+/g, "-"); }
  function badge(value, kind = "status") { return `<span class="${kind} ${kind === "status" ? statusClass(value) : normalized(value)}">${escapeHtml(value)}</span>`; }
  function sourceById(id) { return data.sources.find(source => source.id === id); }
  function upgradeById(id) { return data.upgrades.find(item => item.id === id); }
  function classById(id) { return data.classes.find(item => item.id === id); }
  function abilities() { return data.classes.flatMap(cls => cls.skills.map(skill => ({ ...skill, classId: cls.id, className: cls.name }))); }
  function abilityById(id) { return abilities().find(item => item.id === id); }
  function questionById(id) { return data.questions.find(item => item.id === id); }
  function questionLinks(question) {
    if (question.mechanicLinks?.length) return question.mechanicLinks;
    const ids = question.mechanicIds || (question.mechanicId ? [question.mechanicId] : []);
    return ids.map(id => id === question.mechanicId ? { id, type: question.mechanicType, name: question.mechanicName } : { id, type: "other", name: id });
  }
  function linkedMechanicsMarkup(question) {
    return questionLinks(question).map(link => {
      const href = link.type === "upgrade" && upgradeById(link.id) ? routeHref("upgrade", link.id) : link.type === "class" && classById(link.id) ? routeHref("class", link.id) : link.type === "ability" && abilityById(link.id) ? routeHref("ability", link.id) : null;
      return href ? `<a class="mechanic-link" href="${href}">${escapeHtml(link.name)}</a>` : `<span class="mechanic-link">${escapeHtml(link.name)}</span>`;
    }).join(`<span class="mechanic-separator">Ç-</span>`);
  }
  function recordStatus(record) { return record.researchStatus || "Unknown"; }
  function encode(value) { return encodeURIComponent(value); }
  function routeHref(kind, id) { return `#${kind}:${encode(id)}`; }
  function currentNoteKey() { return location.hash.slice(1) || "overview"; }
  function pageLabelForKey(key) {
    const match = key.match(/^(upgrade|class|ability|question):(.+)$/);
    if (!match || !data) return key === "overview" ? "Overview" : key;
    const id = decodeURIComponent(match[2]);
    const record = match[1] === "upgrade" ? upgradeById(id) : match[1] === "class" ? classById(id) : match[1] === "ability" ? abilityById(id) : questionById(id);
    const kind = match[1].charAt(0).toUpperCase() + match[1].slice(1);
    return `${kind} ¶ú ${record?.name || record?.question || id}`;
  }
  function saveNoteState() {
    try { localStorage.setItem(NOTES_STORAGE_KEY, JSON.stringify(pageNotes)); } catch (error) { /* file:// or private browsing may block persistence */ }
  }
  function updateNotesPanel(status = "") {
    const panel = $("#page-notes");
    const toggle = $("#notes-visibility-toggle");
    const field = $("#page-note");
    if (!panel || !toggle || !field) return;
    const key = currentNoteKey();
    panel.classList.toggle("is-hidden", notesHidden);
    panel.parentElement.classList.toggle("notes-hidden", notesHidden);
    toggle.textContent = notesHidden ? "Show notes" : "Hide notes";
    toggle.setAttribute("aria-expanded", String(!notesHidden));
    $("#notes-page-label").textContent = pageLabelForKey(key);
    if (document.activeElement !== field) field.value = pageNotes[key] || "";
    $("#notes-count").textContent = `${Object.values(pageNotes).filter(value => String(value).trim()).length} saved`;
    $("#notes-status").textContent = status;
  }
  function saveCurrentNote(value) {
    const key = currentNoteKey();
    if (String(value).trim()) pageNotes[key] = value;
    else delete pageNotes[key];
    saveNoteState();
    updateNotesPanel();
  }
  function notesExportText() {
    const entries = Object.entries(pageNotes).filter(([, value]) => String(value).trim());
    if (!entries.length) return "Ecliptica Research Wiki notes\n\nNo page notes have been saved yet.";
    return `Ecliptica Research Wiki notes\n\n${entries.map(([key, value], index) => `${index + 1}. ${pageLabelForKey(key)}\nRoute: #${key}\nNote:\n${String(value).trim()}`).join("\n\n---\n\n")}`;
  }
  async function copyAllNotes() {
    const text = notesExportText();
    try {
      await navigator.clipboard.writeText(text);
    } catch (error) {
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.focus();
      helper.select();
      document.execCommand("copy");
      helper.remove();
    }
    updateNotesPanel("All saved page notes copied.");
  }
  function clearAllNotes() {
    if (!Object.values(pageNotes).some(value => String(value).trim()) || window.confirm("Clear all saved page notes?")) {
      pageNotes = {};
      saveNoteState();
      updateNotesPanel("All page notes cleared.");
    }
  }
  function toggleNotes() {
    notesHidden = !notesHidden;
    try { localStorage.setItem(NOTES_VISIBILITY_KEY, String(notesHidden)); } catch (error) { /* optional persistence */ }
    updateNotesPanel();
  }
  function parseHash() {
    const value = location.hash.slice(1) || "overview";
    const match = value.match(/^(upgrade|class|ability|question):(.+)$/);
    if (match) return { route: match[1], detail: decodeURIComponent(match[2]) };
    return { route: ["overview", "upgrades", "classes", "abilities", "questions", "evidence", "tests"].includes(value) ? value : "overview", detail: null };
  }

  function iconMarkup(record, className = "record-icon") {
    const file = record?.icon;
    if (!file) return `<span class="${className}" aria-hidden="true">${escapeHtml((record?.name || "?").slice(0, 1))}</span>`;
    return `<span class="${className}"><img src="assets/icons/${encodeURIComponent(file)}" alt=""></span>`;
  }

  function highlightUnknown(value, signals = {}) {
    let text = escapeHtml(value);
    text = text.replace(/\bX(?:\s*[%+]?)?\b/g, match => `<span class="unknown-value">${match}</span>`);
    if (signals.unknownTokens?.includes("?")) text = text.replace(/\?/g, `<span class="unknown-value">?</span>`);
    return text;
  }

  function sourceLink(source) {
    return source ? `<a href="${escapeHtml(source.pageUrl)}" target="_blank" rel="noopener">Open ${escapeHtml(source.title)} ƒÅ-</a>` : "";
  }

  function provenance(refs = []) {
    if (!refs.length) return `<div class="source-card"><p>No source provenance has been attached yet.</p></div>`;
    return refs.map(ref => {
      const source = sourceById(ref.sourceId);
      return `<article class="source-card">
        <header><div><h3>${escapeHtml(ref.sourcePage || source?.title || "Source")}</h3><span class="meta">${escapeHtml(ref.section || "Unsectioned")} ¶ú retrieved ${escapeHtml(ref.retrievedAt || "unknown")}</span></div>${sourceLink(source)}</header>
       <blockquote>${highlightUnknown(ref.excerpt || "No excerpt stored.", { unknownTokens: ["?"] })}</blockquote>
        ${ref.translation ? `<p class="translation"><strong>English translation:</strong> ${escapeHtml(ref.translation)}</p>` : ""}
       <p class="meta">Derived fields: ${escapeHtml((ref.derivedFields || []).join(", ") || "none")}</p>
      </article>`;
    }).join("");
  }

  function signalBadges(record) {
    const signals = record.mechanics?.signals || {};
    const tags = [];
    if (signals.hasUnknown) tags.push(`<span class="unknown-box">UNKNOWN ¶ú ${escapeHtml((signals.unknownTokens || []).join(", "))}</span>`);
    if (signals.hasPeriodic && !signals.hasExplicitInterval) tags.push(`<span class="unknown-box">INTERVAL NOT STATED</span>`);
    if (signals.hasDamage && !signals.hasDamageNumber) tags.push(`<span class="unknown-box">DAMAGE NOT STATED</span>`);
    if (signals.hasStackScaling && signals.hasUnknown) tags.push(`<span class="unknown-box">STACK RULE INCOMPLETE</span>`);
    return tags.length ? `<div class="signal-row">${tags.join("")}</div>` : "";
  }

  function unknownOr(value, yes = "YES", no = "NO") {
    if (value === true) return yes;
    if (value === false) return no;
    if (value === "not_applicable") return "N/A";
    return `<span class="unknown-value">UNKNOWN</span>`;
  }

  function damageBehaviorMarkup(record) {
    const behavior = record?.mechanics?.damageBehavior;
    if (!behavior) return "";
    return `<section class="detail-section damage-behavior"><h2>Damage behavior <small>RESEARCH FIELDS</small></h2><div class="mechanic-lines"><div class="mechanic-line"><span>Creates a damage instance</span><strong>${unknownOr(behavior.createsDamageInstance)}</strong></div><div class="mechanic-line"><span>Can critically strike</span><strong>${unknownOr(behavior.canCrit)}</strong></div><div class="mechanic-line"><span>Critical-strike chance</span><strong>${behavior.critChance ? escapeHtml(behavior.critChance) : `<span class="unknown-value">UNKNOWN</span>`}</strong></div><div class="mechanic-line"><span>Can apply status effects</span><strong>${unknownOr(behavior.canApplyStatusEffects)}</strong></div><div class="mechanic-line"><span>Status-effect chance</span><strong>${behavior.statusEffectChance ? escapeHtml(behavior.statusEffectChance) : `<span class="unknown-value">UNKNOWN</span>`}</strong></div></div><p class="footnote"><strong>Crit notes:</strong> ${escapeHtml(behavior.critNotes || "Unknown.")} <strong>Status notes:</strong> ${escapeHtml(behavior.statusNotes || "Unknown.")}</p></section>`;
  }

  function damageBehaviorMiniMarkup(record) {
    const behavior = record?.mechanics?.damageBehavior;
    if (!behavior) return "";
    return `<div class="damage-behavior-mini"><span>Crit: ${unknownOr(behavior.canCrit)}</span><span>Crit chance: ${behavior.critChance ? escapeHtml(behavior.critChance) : `<span class="unknown-value">UNKNOWN</span>`}</span><span>Status: ${unknownOr(behavior.canApplyStatusEffects)}</span><span>Status chance: ${behavior.statusEffectChance ? escapeHtml(behavior.statusEffectChance) : `<span class="unknown-value">UNKNOWN</span>`}</span></div>`;
  }

  function questionRowsForMechanic(id) {
    return data.questions.filter(question => (question.mechanicIds || [question.mechanicId]).includes(id));
  }

  function claimsForQuestion(question) {
    const ids = new Set(question.claimIds || []);
    return data.claims.filter(claim => ids.has(claim.id) || claim.questionId === question.id);
  }

  function evidenceForQuestion(question) {
    const ids = new Set(question.evidenceIds || []);
    return data.evidence.filter(item => ids.has(item.id) || item.questionId === question.id || (item.questionIds || []).includes(question.id) || item.mechanicId === question.mechanicId || (item.mechanicIds || []).includes(question.mechanicId));
  }

  function testsForQuestion(question) {
    return data.tests.filter(test => (test.questionIds || []).includes(question.id));
  }

  function stats() {
    const open = data.questions.filter(item => item.status !== "Confirmed");
    const missing = data.upgrades.filter(item => item.mechanics?.signals?.hasUnknown).length + data.classes.flatMap(item => item.skills).filter(item => item.mechanics?.signals?.hasUnknown).length;
    return { upgrades: data.upgrades.length, classes: data.classes.length, open: open.length, confirmed: data.questions.filter(item => item.status === "Confirmed").length, contradicted: data.questions.filter(item => item.status === "Contradicted").length, missing, testing: data.questions.filter(item => item.status === "Needs Testing" || (item.priority === "High" && item.status === "Unknown")).length };
  }

  function renderNav() {
    const counts = stats();
    $("#nav-upgrades").textContent = counts.upgrades;
    $("#nav-classes").textContent = counts.classes;
    $("#nav-abilities").textContent = abilities().length;
    $("#nav-questions").textContent = counts.open;
    $("#nav-evidence").textContent = data.evidence.length;
    $("#nav-tests").textContent = data.tests.length;
    $$(".main-nav a").forEach(link => link.classList.toggle("active", link.dataset.route === state.route && !state.detail));
    $("#import-date").textContent = `Import ${data["import-report"]?.retrievalDate || "undated"}`;
    $("#site-version").textContent = "Research v0.1.0";
  }

  function renderStats() {
    const counts = stats();
    const cards = [
      [counts.upgrades, "upgrades imported", ""], [counts.classes, "classes imported", ""], [counts.open, "open questions", "alert"], [counts.confirmed, "confirmed questions", ""], [counts.contradicted, "contradicted questions", "danger"], [counts.missing, "mechanics with unknowns", "alert"],
    ];
    return `<div class="stat-grid">${cards.map(([value, label, kind]) => `<div class="stat-card ${kind}"><span class="eyebrow">RESEARCH INDEX</span><span class="stat-value">${value}</span><span class="stat-label">${label}</span></div>`).join("")}</div>`;
  }

  function renderOverview() {
    const counts = stats();
    const needs = [...data.questions].filter(item => item.status !== "Confirmed").sort((a, b) => STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) || (a.priority === "High" ? -1 : 1)).slice(0, 8);
    const sourceCount = data.sources.filter(source => source.type === "English Ecliptica Wiki").length;
    return `<div class="page-head"><div><span class="section-kicker">ECLIPTICA / RESEARCH INDEX</span><h1>Reverse-engineer the unknowns.</h1><p>A compact, provenance-first workspace for turning wiki text, observations and controlled tests into defensible mechanics.</p></div><div class="head-actions"><a class="button" href="#questions">Open research backlog ƒÅ'</a><a class="button" href="README.md">Read the field guide</a></div></div>
      ${renderStats()}
      <div class="source-note"><strong>Import boundary:</strong> ${counts.upgrades} upgrade records and ${counts.classes} class records were parsed from the English Ecliptica Wiki. Wiki statements are evidence, not automatic confirmation. ${sourceCount} source pages retain raw MediaWiki text and retrieval dates.</div>
      <section class="section"><div class="section-title-row"><h2>Needs research</h2><a href="#questions">View full backlog ƒÅ'</a></div><div class="dashboard-grid"><div class="panel"><h3>Highest-value open questions</h3><p class="panel-subtitle">Unknown values are kept visible; competing claims are never collapsed.</p><div class="needs-list">${needs.map(item => `<a class="needs-item" href="${routeHref("question", item.id)}">${badge(item.status)}<span class="question-text">${escapeHtml(item.question)}</span><span class="mechanic">${escapeHtml(item.mechanicName)}</span></a>`).join("") || `<div class="empty-state">No open questions.</div>`}</div></div><div class="panel"><h3>Import health</h3><p class="panel-subtitle">A quick audit of what the source does and does not provide.</p><div class="mechanic-lines"><div class="mechanic-line"><span>Missing numerical data</span><strong>${counts.missing}</strong></div><div class="mechanic-line"><span>High-priority questions</span><strong>${counts.testing}</strong></div><div class="mechanic-line"><span>Evidence records</span><strong>${data.evidence.length}</strong></div><div class="mechanic-line"><span>Planned test records</span><strong>${data.tests.filter(test => test.status === "Planned").length}</strong></div><div class="mechanic-line"><span>Confirmed questions</span><strong>${counts.confirmed}</strong></div></div></div></div></section>
      <section class="section"><div class="section-title-row"><h2>Research rules</h2></div><div class="record-grid"><article class="panel"><span class="section-kicker">01 / SOURCE</span><h3>Quote what the wiki says</h3><p class="panel-subtitle">Each imported field points to a page, section, retrieval date and excerpt.</p></article><article class="panel"><span class="section-kicker">02 / GAP</span><h3>Show what is missing</h3><p class="panel-subtitle">X, ?, vague timing and absent values become explicit research questions.</p></article><article class="panel"><span class="section-kicker">03 / TEST</span><h3>Earn confirmation</h3><p class="panel-subtitle">A player report or hypothesis stays distinct until repeatable evidence supports it.</p></article></div></section>
      <p class="footnote">Dataset refreshed ${escapeHtml(data["import-report"]?.retrievalDate || "unknown")}. See Sources within each record for the exact English-wiki provenance.</p>`;
  }

  function upgradeCard(item) {
    const questions = questionRowsForMechanic(item.id);
    const signals = item.mechanics?.signals || {};
    return `<article class="record-card clickable" data-href="${routeHref("upgrade", item.id)}">${iconMarkup(item)}<div class="record-top"><div><h3><a href="${routeHref("upgrade", item.id)}">${escapeHtml(item.name)}</a></h3><div class="meta">${escapeHtml(item.family)}</div></div></div><p class="description">${highlightUnknown(item.description, signals)}</p><div class="record-footer">${badge(item.rarity, "rarity")}${badge(recordStatus(item))}${questions.length ? `<span class="unknown-box">${questions.length} open ${questions.length === 1 ? "question" : "questions"}</span>` : ""}</div></article>`;
  }

  function renderUpgrades() {
    let items = data.upgrades.filter(item => matches(`${item.name} ${item.family} ${item.description} ${item.category}`, state.upgradeSearch));
    if (state.upgradeFamily) items = items.filter(item => item.family === state.upgradeFamily);
    if (state.upgradeRarity) items = items.filter(item => item.rarity === state.upgradeRarity);
    if (state.upgradeStatus) items = items.filter(item => recordStatus(item) === state.upgradeStatus);
    items.sort((a, b) => state.upgradeSort === "rarity" ? ["Common", "Rare", "Legendary"].indexOf(a.rarity) - ["Common", "Rare", "Legendary"].indexOf(b.rarity) || a.name.localeCompare(b.name) : state.upgradeSort === "questions" ? questionRowsForMechanic(b.id).length - questionRowsForMechanic(a.id).length || a.name.localeCompare(b.name) : a.name.localeCompare(b.name));
    const families = [...new Set(data.upgrades.map(item => item.family))].sort();
    return `<div class="page-head"><div><span class="section-kicker">RESEARCH INDEX / CATALOG</span><h1>All upgrades</h1><p>Wiki-derived upgrade records, including class-specific tables. <strong>Complete</strong> means the imported record has no detected missing value; it does not mean the mechanic has been experimenta…6550 tokens truncated…n full"><h2>Current claims <small>${claims.length}</small></h2>${renderClaims(claims)}</section><section class="detail-section full"><h2>Evidence <small>${evidence.length}</small></h2>${renderEvidenceList(evidence)}</section><section class="detail-section full"><h2>Tests <small>${tests.length}</small></h2>${tests.length ? tests.map(testCard).join("") : `<div class="empty-state">No test record is linked yet.</div>`}</section><section class="detail-section full"><h2>Provenance <small>ENGLISH WIKI</small></h2>${provenance(item.sourceRefs)}</section></div>`;
  }

  function renderUpgradeDetail(item) {
    const questions = questionRowsForMechanic(item.id);
    const claims = questions.flatMap(claimsForQuestion);
    const evidence = [...new Map([...data.evidence.filter(record => record.mechanicId === item.id), ...questions.flatMap(evidenceForQuestion)].map(item => [item.id, item])).values()];
    const tests = [...new Map(questions.flatMap(testsForQuestion).map(item => [item.id, item])).values()];
    const sig = item.mechanics?.signals || {};
    return `<a class="back-link" href="#upgrades">ƒÅ? Back to all upgrades</a><div class="detail-head">${iconMarkup(item)}<div><span class="section-kicker">UPGRADE RECORD / ${escapeHtml(item.category)}</span><h1>${escapeHtml(item.name)}</h1><div class="meta-line">${badge(item.rarity, "rarity")} ${badge(item.family, "tag")} ${badge(recordStatus(item))}</div>${signalBadges(item)}</div></div><div class="detail-grid"><div><section class="detail-section"><h2>Wiki description <small>SOURCED TEXT</small></h2><div class="wiki-description">${highlightUnknown(item.description, sig)}</div></section><section class="detail-section"><h2>Known mechanics <small>STRUCTURED SIGNALS</small></h2><div class="mechanic-lines"><div class="mechanic-line"><span>Stack type</span><strong>${escapeHtml(item.mechanics?.stackType || "<span class=unknown-value>UNKNOWN</span>")}</strong></div><div class="mechanic-line"><span>Numeric mentions</span><strong>${sig.numericMentions?.length ? escapeHtml(sig.numericMentions.join(" ¶ú ")) : `<span class="unknown-value">NONE STATED</span>`}</strong></div><div class="mechanic-line"><span>Unknown tokens</span><strong>${sig.unknownTokens?.length ? `<span class="unknown-value">${escapeHtml(sig.unknownTokens.join(" ¶ú "))}</span>` : "None detected"}</strong></div><div class="mechanic-line"><span>Interval / frequency</span><strong>${sig.hasPeriodic && !sig.hasExplicitInterval ? `<span class="unknown-value">NOT STATED</span>` : sig.hasExplicitInterval ? "Mentioned in source" : "Not applicable / not detected"}</strong></div></div>${signalBadges(item)}</section></div><aside><section class="detail-section"><h2>Research questions <small>${questions.length}</small></h2>${relatedQuestionList(questions)}</section></aside><section class="detail-section full"><h2>Current claims <small>COMPETING INTERPRETATIONS</small></h2>${renderClaims(claims)}</section><section class="detail-section full"><h2>Evidence <small>${evidence.length}</small></h2>${renderEvidenceList(evidence)}</section><section class="detail-section full"><h2>Tests <small>${tests.length}</small></h2>${tests.length ? tests.map(testCard).join("") : `<div class="empty-state">No test record is linked yet.</div>`}</section><section class="detail-section full"><h2>Provenance <small>ENGLISH WIKI</small></h2>${provenance(item.sourceRefs)}</section></div>`;
  }

  function renderClassDetail(item) {
    const questions = [...new Map([...item.skills.flatMap(skill => questionRowsForMechanic(skill.id)), ...questionRowsForMechanic(item.id)].map(question => [question.id, question])).values()];
    const upgrades = item.upgradeIds.map(upgradeById).filter(Boolean);
    const handRates = item.reportedMechanics?.elementalHandAttackRates;
    return `<a class="back-link" href="#classes">ƒÅ? Back to all classes</a><div class="detail-head">${iconMarkup(item)}<div><span class="section-kicker">CLASS RECORD / ENGLISH WIKI</span><h1>${escapeHtml(item.name)}</h1><div class="meta-line">${badge(recordStatus(item))}<span class="tag">${item.skills.length} skills</span><span class="tag">${upgrades.length} class upgrades</span></div></div></div><div class="detail-grid"><div><section class="detail-section"><h2>Wiki description <small>SOURCED TEXT</small></h2><div class="wiki-description">${escapeHtml(item.description)}</div></section>${handRates ? `<section class="detail-section"><h2>Reported hand-rate mechanic <small>RESEARCH CLAIM</small></h2><div class="mechanic-lines"><div class="mechanic-line"><span>Both hands active</span><strong>${handRates.bothHands.attacksPerSecond} attacks/s per hand</strong></div><div class="mechanic-line"><span>Single hand active</span><strong>${handRates.singleHand.attacksPerSecond} attacks/s per hand</strong></div><div class="mechanic-line"><span>Applies to</span><strong>${escapeHtml(handRates.appliesTo.join(", "))}</strong></div></div><div class="signal-row">${badge(handRates.status)}<span class="tag">${escapeHtml(handRates.sourceType)}</span></div><p class="footnote">${escapeHtml(handRates.interpretationNote)}</p></section>` : ""}<section class="detail-section"><h2>Skills and abilities <small>${item.skills.length}</small></h2><div class="skill-grid">${item.skills.map(skill => `<article class="skill-card"><header><div><h3>${escapeHtml(skill.name)}</h3><span class="skill-type">${escapeHtml(skill.type)}</span></div>${skill.mechanics.signals.hasUnknown ? `<span class="unknown-box">UNKNOWN</span>` : ""}</header><p>${highlightUnknown(skill.description, skill.mechanics.signals)}</p>${signalBadges(skill)}</article>`).join("")}</div></section></div><aside><section class="detail-section"><h2>Starting stats</h2><div class="mechanic-lines"><div class="mechanic-line"><span>Starting stats</span><strong><span class="unknown-value">NOT STATED</span></strong></div><div class="mechanic-line"><span>Stat modifiers</span><strong>None stated numerically</strong></div></div></section><section class="detail-section"><h2>Class research <small>${questions.length}</small></h2>${relatedQuestionList(questions)}</section></aside><section class="detail-section full"><h2>Class-specific upgrades <small>${upgrades.length}</small></h2><div class="record-grid">${upgrades.map(upgradeCard).join("")}</div></section><section class="detail-section full"><h2>Provenance <small>ENGLISH WIKI</small></h2>${provenance(item.sourceRefs)}${item.skills.flatMap(skill => skill.sourceRefs).map(ref => provenance([ref])).join("")}${handRates ? provenance(handRates.sourceRefs) : ""}</section></div>`;
  }

  function renderQuestionDetail(item) {
    const claims = claimsForQuestion(item);
    const evidence = evidenceForQuestion(item);
    const tests = testsForQuestion(item);
    const linkedMechanics = linkedMechanicsMarkup(item);
    return `<a class="back-link" href="#questions">ƒÅ? Back to research questions</a><div class="detail-head"><span class="record-icon">?</span><div><span class="section-kicker">RESEARCH QUESTION / ${escapeHtml(item.kind === "missing-wiki-information" ? "AUTO-DETECTED GAP" : "USER RESEARCH")}</span><h1>${escapeHtml(item.question)}</h1><div class="meta-line">${badge(item.status)}<span class="tag">${escapeHtml(item.priority)} priority</span><span class="tag">${escapeHtml(item.mechanicName)}</span></div></div></div><div class="detail-grid"><div><section class="detail-section"><h2>Current hypothesis <small>INTERPRETATION, NOT FACT</small></h2><div class="wiki-description">${item.currentHypothesis ? escapeHtml(item.currentHypothesis) : `<span class="unknown-value">NO HYPOTHESIS RECORDED</span>`}</div></section><section class="detail-section"><h2>Competing claims <small>${claims.length}</small></h2>${renderClaims(claims)}</section><section class="detail-section"><h2>Evidence <small>${evidence.length}</small></h2>${renderEvidenceList(evidence)}</section><section class="detail-section"><h2>Tests <small>${tests.length}</small></h2>${tests.length ? tests.map(testCard).join("") : `<div class="empty-state">No test record linked yet.</div>`}</section></div><aside><section class="detail-section"><h2>Research metadata</h2><div class="mechanic-lines"><div class="mechanic-line"><span>Mechanic</span><strong>${escapeHtml(item.mechanicName)}</strong></div><div class="mechanic-line"><span>Scope</span><strong>${escapeHtml(item.mechanicType)}</strong></div><div class="mechanic-line"><span>Origin</span><strong>${escapeHtml(item.kind)}</strong></div><div class="mechanic-line"><span>Last updated</span><strong>${escapeHtml(item.updatedAt || "ƒ?"")}</strong></div></div></section><section class="detail-section"><h2>Source evidence <small>${item.sourceRefs.length}</small></h2>${provenance(item.sourceRefs)}</section></aside></div>`;
  }

  function renderQuestionDetailLinked(item) {
    const claims = claimsForQuestion(item);
    const evidence = evidenceForQuestion(item);
    const tests = testsForQuestion(item);
    const links = linkedMechanicsMarkup(item);
    return `<a class="back-link" href="#questions">ƒÅ? Back to research questions</a><div class="detail-head"><span class="record-icon">?</span><div><span class="section-kicker">RESEARCH QUESTION / ${escapeHtml(item.kind === "missing-wiki-information" ? "AUTO-DETECTED GAP" : "USER RESEARCH")}</span><h1>${escapeHtml(item.question)}</h1><div class="meta-line">${badge(item.status)}<span class="tag">${escapeHtml(item.priority)} priority</span></div><div class="question-links-head">${links}</div></div></div><div class="detail-grid"><div><section class="detail-section"><h2>Current hypothesis <small>INTERPRETATION, NOT FACT</small></h2><div class="wiki-description">${item.currentHypothesis ? escapeHtml(item.currentHypothesis) : `<span class="unknown-value">NO HYPOTHESIS RECORDED</span>`}</div></section><section class="detail-section"><h2>Competing claims <small>${claims.length}</small></h2>${renderClaims(claims)}</section><section class="detail-section"><h2>Evidence <small>${evidence.length}</small></h2>${renderEvidenceList(evidence)}</section><section class="detail-section"><h2>Tests <small>${tests.length}</small></h2>${tests.length ? tests.map(testCard).join("") : `<div class="empty-state">No test record linked yet.</div>`}</section></div><aside><section class="detail-section"><h2>Research metadata</h2><div class="mechanic-lines"><div class="mechanic-line"><span>Linked mechanics</span><strong>${links}</strong></div><div class="mechanic-line"><span>Scope</span><strong>${escapeHtml(item.mechanicType)}</strong></div><div class="mechanic-line"><span>Origin</span><strong>${escapeHtml(item.kind)}</strong></div><div class="mechanic-line"><span>Last updated</span><strong>${escapeHtml(item.updatedAt || "-")}</strong></div></div></section><section class="detail-section"><h2>Source evidence <small>${item.sourceRefs.length}</small></h2>${provenance(item.sourceRefs)}</section></aside></div>`;
  }

  function globalResults() {
    if (!state.globalQuery) return "";
    const query = state.globalQuery;
    const results = [
      ...data.upgrades.filter(item => matches(`${item.name} ${item.description} ${item.family}`, query)).map(item => ({ label: item.name, note: `Upgrade ¶ú ${item.family}`, href: routeHref("upgrade", item.id) })),
      ...data.classes.filter(item => matches(`${item.name} ${item.description} ${item.skills.map(skill => skill.description).join(" ")}`, query)).map(item => ({ label: item.name, note: "Class", href: routeHref("class", item.id) })),
      ...abilities().filter(item => matches(`${item.name} ${item.className} ${item.description} ${item.mechanics?.functionalInterpretation?.summary || ""}`, query)).map(item => ({ label: item.name, note: `Ability ¶ú ${item.className}`, href: routeHref("ability", item.id) })),
      ...data.questions.filter(item => matches(`${item.question} ${item.mechanicName} ${item.currentHypothesis || ""} ${item.sourceHypothesis || ""}`, query)).map(item => ({ label: item.question, note: `Question ¶ú ${item.mechanicName}`, href: routeHref("question", item.id) })),
      ...data.claims.filter(item => matches(item.text, query)).map(item => ({ label: item.text, note: `Claim ¶ú ${item.type}`, href: item.questionId ? routeHref("question", item.questionId) : "#questions" })),
      ...data.evidence.filter(item => matches(`${item.originalInformation} ${item.translation || ""} ${item.interpretation} ${item.mechanicName}`, query)).map(item => ({ label: item.originalInformation, note: `Evidence ¶ú ${item.id}`, href: "#evidence" })),
    ].slice(0, 14);
    return `<section class="search-results"><div class="section-title-row"><h2>Search results for "${escapeHtml(query)}"</h2><a href="#${state.route}">Close search</a></div><div class="search-result-list">${results.map(item => `<a class="search-result" href="${item.href}"><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.note)}</span></a>`).join("") || `<div class="empty-state">No matching records.</div>`}</div></section>`;
  }

  function japaneseAuditMarkup(item) {
    const audit = item?.japaneseAudit;
    if (!audit) return "";
    const evidenceLinks = (audit.evidenceIds || []).map(id => `<a href="${routeHref("question", item.id)}">${escapeHtml(id)}</a>`).join(" ¶ú ");
    const found = audit.findingStatus === "Relevant information found";
    return `<section class="detail-section japanese-audit ${found ? "audit-found" : "audit-none"}"><h2>Japanese wiki audit <small>${escapeHtml(audit.checkedAt || "undated")}</small></h2><p><strong>${escapeHtml(audit.findingStatus || "Checked")}</strong> across ${audit.sourceIds?.length || 0} reviewed Japanese source page(s).</p><p>${escapeHtml(audit.notes || "")}</p>${evidenceLinks ? `<p><strong>Linked bilingual evidence:</strong> ${evidenceLinks}</p>` : ""}</section>`;
  }

  function render() {
    renderNav();
    let page;
    if (state.detail?.type === "upgrade") page = renderUpgradeDetail(upgradeById(state.detail.id));
    else if (state.detail?.type === "class") page = renderClassDetail(classById(state.detail.id));
    else if (state.detail?.type === "ability") page = renderAbilityDetail(abilityById(state.detail.id));
    else if (state.detail?.type === "question") page = renderQuestionDetailLinked(questionById(state.detail.id));
    else if (state.route === "upgrades") page = renderUpgrades();
    else if (state.route === "classes") page = renderClasses();
    else if (state.route === "abilities") page = renderAbilities();
    else if (state.route === "questions") page = renderQuestions();
    else if (state.route === "evidence") page = renderEvidence();
    else if (state.route === "tests") page = renderTests();
    else page = renderOverview();
    app.innerHTML = globalResults() + page;
    updateNotesPanel();
    if (state.detail?.type === "question") {
      const item = questionById(state.detail.id);
      const host = app.querySelector(".detail-grid > div");
      if (host && item) {
        host.insertAdjacentHTML("afterbegin", questionSourceTagsMarkup(item));
        host.insertAdjacentHTML("afterbegin", japaneseAuditMarkup(item));
        const hypothesis = [...host.querySelectorAll(".detail-section")].find(section => section.querySelector("h2")?.textContent.includes("Current hypothesis"));
        if (hypothesis) hypothesis.insertAdjacentHTML("afterend", sourceHypothesisMarkup(item));
      }
    }
    if (state.detail?.type === "upgrade") {
      const host = app.querySelector(".detail-grid > div");
      const item = upgradeById(state.detail.id);
      if (host && item) {
        host.insertAdjacentHTML("afterbegin", functionalInterpretationMarkup(item));
        host.insertAdjacentHTML("afterbegin", researchAuditMarkup(item));
        host.insertAdjacentHTML("afterbegin", workingDescriptionMarkup(item));
        host.insertAdjacentHTML("beforeend", damageBehaviorMarkup(item));
      }
    }
    if (state.detail?.type === "ability") {
      const host = app.querySelector(".detail-grid > div");
      const item = abilityById(state.detail.id);
      if (host && item) host.insertAdjacentHTML("afterbegin", researchAuditMarkup(item));
    }
    if (state.detail?.type === "class") {
      const item = classById(state.detail.id);
      if (item) {
        const host = app.querySelector(".detail-grid > div");
        if (host) host.insertAdjacentHTML("afterbegin", researchAuditMarkup(item));
      }
      $$(".skill-card", app).forEach((card, index) => {
        const skill = item?.skills[index];
        const heading = $("h3", card);
        if (heading && skill) heading.innerHTML = `<a href="${routeHref("ability", skill.id)}">${escapeHtml(skill.name)}</a>`;
        if (skill) card.insertAdjacentHTML("beforeend", damageBehaviorMiniMarkup(skill));
      });
    }
    bindEvents();
  }

  function bindEvents() {
    $$('[data-href]').forEach(element => element.addEventListener("click", event => { if (event.target.closest("a")) return; location.hash = element.dataset.href.slice(1); }));
    $$('[data-filter]').forEach(element => element.addEventListener(element.type === "checkbox" ? "change" : "input", event => { state[element.dataset.filter] = element.type === "checkbox" ? event.target.checked : event.target.value; renderPreservingFocus(element); }));
    $$(".main-nav a").forEach(link => link.addEventListener("click", () => { state.detail = null; }));
    const noteField = $("#page-note");
    if (noteField) noteField.oninput = event => saveCurrentNote(event.target.value);
    const visibilityToggle = $("#notes-visibility-toggle");
    if (visibilityToggle) visibilityToggle.onclick = toggleNotes;
    const copyButton = $("#copy-notes");
    if (copyButton) copyButton.onclick = copyAllNotes;
    const clearButton = $("#clear-notes");
    if (clearButton) clearButton.onclick = clearAllNotes;
  }

  function renderPreservingFocus(element) {
    const filterName = element.dataset.filter;
    const wasFocused = document.activeElement === element;
    const start = typeof element.selectionStart === "number" ? element.selectionStart : null;
    const end = typeof element.selectionEnd === "number" ? element.selectionEnd : null;
    const direction = element.selectionDirection;
    render();
    const replacement = $$('[data-filter]').find(candidate => candidate.dataset.filter === filterName);
    if (!replacement || !wasFocused) return;
    replacement.focus();
    if (start !== null && typeof replacement.setSelectionRange === "function") replacement.setSelectionRange(start, end, direction);
  }

  async function loadData() {
    if (window.ECLIPTICA_RESEARCH_DATA) return window.ECLIPTICA_RESEARCH_DATA;
    const entries = await Promise.all(FILES.map(async name => [name, await fetch(`data/${name}.json`).then(response => response.json())]));
    return Object.fromEntries(entries);
  }

  function routeChanged() {
    const parsed = parseHash();
    state.route = parsed.route;
    state.detail = parsed.detail ? { type: parsed.route, id: parsed.detail } : null;
    if (data) {
      window.scrollTo(0, 0);
      render();
    }
  }

  document.addEventListener("keydown", event => {
    if (event.key === "/" && document.activeElement?.tagName !== "INPUT") { event.preventDefault(); $("#global-search").focus(); }
    if (event.key === "Escape" && state.globalQuery) { state.globalQuery = ""; $("#global-search").value = ""; render(); }
  });
  $("#global-search").addEventListener("input", event => { state.globalQuery = event.target.value; render(); });
  window.addEventListener("hashchange", routeChanged);

  (async () => {
    try {
      data = await loadData();
      const parsed = parseHash();
      state.route = parsed.route;
      state.detail = parsed.detail ? { type: parsed.route, id: parsed.detail } : null;
      render();
    } catch (error) {
      app.innerHTML = `<div class="empty-state"><div><h2>Dataset could not be loaded.</h2><p>${escapeHtml(error.message)}<br>Use the importer/build instructions in <a href="README.md">README.md</a>.</p></div></div>`;
    }
  })();
})();
