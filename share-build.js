(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ShareBuildCodec = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // V1 layout: version(3), character(3), entry count(7), then ID(7) + stack prefix per entry.
  // V2 appends artifacts and the four positional rune/curse selections.
  const FORMAT_VERSION = 2;
  const LEGACY_FORMAT_VERSION = 1;
  const VERSION_BITS = 3;       // Versions 0-7; version 1 is the first supported format.
  const CHARACTER_ID_BITS = 3;  // Eight current/supported character IDs (0-7).
  const ENTRY_COUNT_BITS = 7;   // Up to 115 upgrades, whose permanent IDs are 0-114.
  const UPGRADE_ID_BITS = 7;
  const MAX_STACK_COUNT = 100;
  const ARTIFACT_ID_BITS = 3;
  const ARTIFACT_COUNT_BITS = 3;
  const RUNE_ID_BITS = 5;
  const CURSE_ID_BITS = 4;
  const RUNE_SLOT_COUNT = 4;

  class BitWriter {
    constructor() { this.bits = []; }

    writeBits(value, bitCount) {
      if (!Number.isInteger(value) || value < 0 || value >= 2 ** bitCount)
        throw new RangeError(`${value} does not fit in ${bitCount} bits`);
      for (let bit = bitCount - 1; bit >= 0; bit--) this.bits.push((value >> bit) & 1);
    }

    writeStackCount(count) {
      if (!Number.isInteger(count) || count < 1 || count > MAX_STACK_COUNT)
        throw new RangeError("Stack count must be an integer from 1 to 100");
      if (count === 1) this.writeBits(0, 1);
      else if (count === 2) this.writeBits(2, 2);       // 10
      else if (count === 3) this.writeBits(6, 3);       // 110
      else { this.writeBits(7, 3); this.writeBits(count, 7); } // 111 + actual count
    }

    toBytes() {
      const bytes = new Uint8Array(Math.ceil(this.bits.length / 8));
      this.bits.forEach((bit, index) => { bytes[index >> 3] |= bit << (7 - (index & 7)); });
      return bytes;
    }
  }

  class BitReader {
    constructor(bytes) { this.bytes = bytes; this.position = 0; }

    readBits(bitCount) {
      if (this.position + bitCount > this.bytes.length * 8) throw new Error("Truncated build data");
      let value = 0;
      for (let index = 0; index < bitCount; index++, this.position++)
        value = (value << 1) | ((this.bytes[this.position >> 3] >> (7 - (this.position & 7))) & 1);
      return value;
    }

    readStackCount() {
      if (this.readBits(1) === 0) return 1;
      if (this.readBits(1) === 0) return 2;
      if (this.readBits(1) === 0) return 3;
      const count = this.readBits(7);
      if (count < 4 || count > MAX_STACK_COUNT) throw new Error("Invalid extended stack count");
      return count;
    }
  }

  function bytesToBase64Url(bytes) {
    let binary = "";
    bytes.forEach(byte => { binary += String.fromCharCode(byte); });
    const base64 = typeof btoa === "function" ? btoa(binary) : Buffer.from(bytes).toString("base64");
    return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function base64UrlToBytes(code) {
    if (typeof code !== "string" || !code.length || !/^[A-Za-z0-9_-]+$/.test(code) || code.length % 4 === 1)
      throw new Error("Invalid Base64URL build code");
    const padded = code.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - code.length % 4) % 4);
    let binary;
    try { binary = typeof atob === "function" ? atob(padded) : Buffer.from(padded, "base64").toString("binary"); }
    catch { throw new Error("Invalid Base64URL build code"); }
    return Uint8Array.from(binary, character => character.charCodeAt(0));
  }

  function encodeBuildV1(build) {
    if (!build || !Number.isInteger(build.characterId) || build.characterId < 0 || build.characterId >= 2 ** CHARACTER_ID_BITS)
      throw new Error("Invalid character ID");
    const upgrades = (build.upgrades || []).filter(entry => entry.count !== 0).slice().sort((a, b) => a.id - b.id);
    if (upgrades.length >= 2 ** ENTRY_COUNT_BITS) throw new Error("Too many selected upgrades");
    const seen = new Set();
    const writer = new BitWriter();
    writer.writeBits(LEGACY_FORMAT_VERSION, VERSION_BITS);
    writer.writeBits(build.characterId, CHARACTER_ID_BITS);
    writer.writeBits(upgrades.length, ENTRY_COUNT_BITS);
    for (const entry of upgrades) {
      if (!Number.isInteger(entry.id) || entry.id < 0 || entry.id >= 2 ** UPGRADE_ID_BITS || seen.has(entry.id))
        throw new Error("Upgrade IDs must be unique 7-bit integers");
      seen.add(entry.id);
      writer.writeBits(entry.id, UPGRADE_ID_BITS);
      writer.writeStackCount(entry.count);
    }
    return bytesToBase64Url(writer.toBytes());
  }

  function writeOptionalId(writer, id, bitCount, label) {
    if (id == null) { writer.writeBits(0, 1); return; }
    if (!Number.isInteger(id) || id < 0 || id >= 2 ** bitCount) throw new Error(`Invalid ${label} ID`);
    writer.writeBits(1, 1);
    writer.writeBits(id, bitCount);
  }

  function encodeBuildV2(build) {
    const writer = new BitWriter();
    if (!build || !Number.isInteger(build.characterId) || build.characterId < 0 || build.characterId >= 2 ** CHARACTER_ID_BITS)
      throw new Error("Invalid character ID");
    const upgrades = (build.upgrades || []).filter(entry => entry.count !== 0).slice().sort((a, b) => a.id - b.id);
    if (upgrades.length >= 2 ** ENTRY_COUNT_BITS) throw new Error("Too many selected upgrades");
    writer.writeBits(FORMAT_VERSION, VERSION_BITS);
    writer.writeBits(build.characterId, CHARACTER_ID_BITS);
    writer.writeBits(upgrades.length, ENTRY_COUNT_BITS);
    const upgradeIds = new Set();
    for (const entry of upgrades) {
      if (!Number.isInteger(entry.id) || entry.id < 0 || entry.id >= 2 ** UPGRADE_ID_BITS || upgradeIds.has(entry.id))
        throw new Error("Upgrade IDs must be unique 7-bit integers");
      upgradeIds.add(entry.id);
      writer.writeBits(entry.id, UPGRADE_ID_BITS);
      writer.writeStackCount(entry.count);
    }

    const artifacts = (build.artifacts || []).filter(entry => entry.count !== 0).slice().sort((a, b) => a.id - b.id);
    if (artifacts.length >= 2 ** ARTIFACT_COUNT_BITS) throw new Error("Too many selected artifacts");
    writer.writeBits(artifacts.length, ARTIFACT_COUNT_BITS);
    const seen = new Set();
    for (const entry of artifacts) {
      if (!Number.isInteger(entry.id) || entry.id < 0 || entry.id >= 2 ** ARTIFACT_ID_BITS || seen.has(entry.id))
        throw new Error("Artifact IDs must be unique 3-bit integers");
      seen.add(entry.id);
      writer.writeBits(entry.id, ARTIFACT_ID_BITS);
      writer.writeStackCount(entry.count);
    }
    for (let slot = 0; slot < RUNE_SLOT_COUNT; slot++) {
      writeOptionalId(writer, build.runes?.[slot], RUNE_ID_BITS, "rune");
      writeOptionalId(writer, build.curses?.[slot], CURSE_ID_BITS, "curse");
    }
    return bytesToBase64Url(writer.toBytes());
  }

  function encodeBuild(build) {
    const version = build && build.version == null ? FORMAT_VERSION : build && build.version;
    if (version === LEGACY_FORMAT_VERSION) return encodeBuildV1(build);
    if (version === FORMAT_VERSION) return encodeBuildV2(build);
    throw new Error(`Unsupported build format version: ${version}`);
  }

  function decodeBuildV1(reader) {
    const characterId = reader.readBits(CHARACTER_ID_BITS);
    const entryCount = reader.readBits(ENTRY_COUNT_BITS);
    const upgrades = [];
    for (let index = 0; index < entryCount; index++)
      upgrades.push({ id: reader.readBits(UPGRADE_ID_BITS), count: reader.readStackCount() });
    return { version: LEGACY_FORMAT_VERSION, characterId, upgrades, artifacts: [], runes: Array(RUNE_SLOT_COUNT).fill(null), curses: Array(RUNE_SLOT_COUNT).fill(null) };
  }

  function readOptionalId(reader, bitCount) { return reader.readBits(1) ? reader.readBits(bitCount) : null; }

  function decodeBuildV2(reader) {
    const decoded = decodeBuildV1(reader);
    decoded.version = FORMAT_VERSION;
    const artifactCount = reader.readBits(ARTIFACT_COUNT_BITS);
    decoded.artifacts = [];
    for (let index = 0; index < artifactCount; index++)
      decoded.artifacts.push({ id: reader.readBits(ARTIFACT_ID_BITS), count: reader.readStackCount() });
    decoded.runes = [];
    decoded.curses = [];
    for (let slot = 0; slot < RUNE_SLOT_COUNT; slot++) {
      decoded.runes.push(readOptionalId(reader, RUNE_ID_BITS));
      decoded.curses.push(readOptionalId(reader, CURSE_ID_BITS));
    }
    return decoded;
  }

  function decodeBuild(code, options = {}) {
    const reader = new BitReader(base64UrlToBytes(code));
    const version = reader.readBits(VERSION_BITS);
    if (version !== LEGACY_FORMAT_VERSION && version !== FORMAT_VERSION) throw new Error(`Unsupported build format version: ${version}`);
    const decoded = version === FORMAT_VERSION ? decodeBuildV2(reader) : decodeBuildV1(reader);
    if (options.characterCount != null && decoded.characterId >= options.characterCount)
      throw new Error(`Unknown character ID: ${decoded.characterId}`);
    const warnings = [];
    const seen = new Set();
    decoded.upgrades = decoded.upgrades.filter(entry => {
      if ((options.upgradeCount != null && entry.id >= options.upgradeCount) || seen.has(entry.id)) {
        warnings.push(`Ignored unknown or duplicate upgrade ID ${entry.id}`);
        return false;
      }
      seen.add(entry.id);
      if (options.isUpgradeAllowed && !options.isUpgradeAllowed(entry.id, decoded.characterId)) {
        warnings.push(`Ignored upgrade ID ${entry.id}, which is not valid for this character`);
        return false;
      }
      return true;
    });
    const artifactSeen = new Set();
    decoded.artifacts = decoded.artifacts.filter(entry => {
      const invalid = (options.artifactCount != null && entry.id >= options.artifactCount) || artifactSeen.has(entry.id);
      if (invalid) warnings.push(`Ignored unknown or duplicate artifact ID ${entry.id}`);
      artifactSeen.add(entry.id);
      return !invalid;
    });
    decoded.runes = decoded.runes.map(id => id != null && options.runeCount != null && id >= options.runeCount ? (warnings.push(`Ignored unknown rune ID ${id}`), null) : id);
    decoded.curses = decoded.curses.map(id => id != null && options.curseCount != null && id >= options.curseCount ? (warnings.push(`Ignored unknown curse ID ${id}`), null) : id);
    decoded.warnings = warnings;
    return decoded;
  }

  return {
    FORMAT_VERSION, LEGACY_FORMAT_VERSION, VERSION_BITS, CHARACTER_ID_BITS, ENTRY_COUNT_BITS, UPGRADE_ID_BITS,
    BitWriter, BitReader, encodeBuildV1, encodeBuildV2, decodeBuildV1, decodeBuildV2, encodeBuild, decodeBuild,
    bytesToBase64Url, base64UrlToBytes
  };
});
