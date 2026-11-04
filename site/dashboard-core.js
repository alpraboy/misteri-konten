/* Logika murni dashboard Agen Misteri (bisa diuji dengan Node). */
(function (root) {
  "use strict";
  var WORKFLOW = "make-video.yml";
  var THEMES = [
    ["sejarah", "Sejarah Misteri"], ["cerita", "Cerita Misteri"], ["berita", "Berita Misteri"],
    ["horor_nusantara", "Horor Nusantara"], ["legenda_urban", "Legenda Urban"],
    ["kasus_tak_terpecahkan", "Kasus Tak Terpecahkan"], ["ufo_uap", "UFO & Fenomena Langit"],
    ["kriptid", "Makhluk Misterius (Kriptid)"], ["tempat_angker", "Tempat Angker & Terlarang"],
    ["peradaban_hilang", "Peradaban Hilang & Situs Kuno"], ["artefak_terkutuk", "Artefak & Benda Terkutuk"],
    ["fenomena_alam", "Fenomena Alam Misterius"]
  ];
  var STYLES = [
    ["auto", "Otomatis (agen memilih satu dari 3)"],
    ["MYSTERY_VHS", "VHS - ketakutan personal, rekaman bocor"],
    ["MYSTERY_CONSPIRACY", "Papan konspirasi - investigasi"],
    ["MYSTERY_WAYANG", "Wayang - sakral, ritual, leluhur"]
  ];

  function validateConfig(c) {
    var errs = [];
    if (!/^[A-Za-z0-9-]{1,39}$/.test((c.owner || "").trim())) errs.push("Nama pengguna GitHub tidak valid.");
    if (!/^[A-Za-z0-9._-]{1,100}$/.test((c.repo || "").trim())) errs.push("Nama repositori tidak valid.");
    if (!(c.token || "").trim() || (c.token || "").trim().length < 20) errs.push("Token GitHub belum diisi dengan benar.");
    return errs;
  }

  function buildDispatchBody(ref, v) {
    var theme = THEMES.some(function (t) { return t[0] === v.theme; }) ? v.theme : "horor_nusantara";
    var style = STYLES.some(function (s) { return s[0] === v.style; }) ? v.style : "auto";
    return {
      ref: ref || "main",
      inputs: {
        theme: theme, style: style,
        post: v.post === "tidak" ? "tidak" : "ya",
        topic: String(v.topic || "").replace(/\s+/g, " ").trim().slice(0, 200)
      }
    };
  }

  function statusInfo(run) {
    var s = run.status, c = run.conclusion;
    if (s === "queued" || s === "waiting" || s === "requested" || s === "pending") return { icon: "\u23F3", label: "Mengantre", cls: "wait", active: true };
    if (s === "in_progress") return { icon: "\uD83D\uDD04", label: "Berjalan", cls: "run", active: true };
    if (c === "success") return { icon: "\u2705", label: "Selesai", cls: "ok", active: false };
    if (c === "failure" || c === "timed_out") return { icon: "\u274C", label: "Gagal", cls: "bad", active: false };
    if (c === "cancelled") return { icon: "\u26D4", label: "Dibatalkan", cls: "bad", active: false };
    return { icon: "\u2754", label: s || "?", cls: "wait", active: false };
  }

  function relTime(iso, now) {
    var t = Date.parse(iso);
    if (isNaN(t)) return "";
    var d = Math.max(0, Math.round(((now || Date.now()) - t) / 1000));
    if (d < 45) return "baru saja";
    if (d < 3600) return Math.round(d / 60) + " mnt lalu";
    if (d < 86400) return Math.round(d / 3600) + " jam lalu";
    return Math.round(d / 86400) + " hari lalu";
  }

  function explain(status, body) {
    var msg = (body && body.message) ? " (" + body.message + ")" : "";
    switch (status) {
      case 204: case 200: case 201: return "OK";
      case 401: return "Token ditolak. Buat token baru lalu simpan lagi." + msg;
      case 403: return "Izin token kurang. Pastikan izin Actions = Read and write untuk repo ini." + msg;
      case 404: return "Repo atau workflow tidak ditemukan. Periksa nama pengguna/repo, dan pastikan token diberi akses ke repo itu." + msg;
      case 422: return "GitHub menolak permintaan. Pastikan file workflow terbaru sudah terpasang (ada kolom style dan post)." + msg;
      default: return "Gagal (kode " + status + ")." + msg;
    }
  }

  var core = { WORKFLOW: WORKFLOW, THEMES: THEMES, STYLES: STYLES, validateConfig: validateConfig,
               buildDispatchBody: buildDispatchBody, statusInfo: statusInfo, relTime: relTime, explain: explain };
  if (typeof module !== "undefined" && module.exports) module.exports = core; else root.AMCore = core;
})(typeof window !== "undefined" ? window : globalThis);
