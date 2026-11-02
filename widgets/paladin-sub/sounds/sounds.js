// BACKGROUND BED
// These mp3s play under the recorded voice line (audio/ via lines.js).
// The bed is quieter than the voice. Follows do not play it.
// If an alert has no voice line, the same file plays at full volume instead.
// A follow with no line stays silent.
// 1. Drop .mp3 files into this "sounds" folder.
// 2. Type each file name below, in quotes, with a comma after each one.
// 3. Save, then refresh the browser source in OBS.
// One random sound plays (never the same one twice in a row).
// Leave the list empty to use files named 1.mp3, 2.mp3, 3.mp3 ... (up to 50).
window.PALADIN_SOUNDS = [
  // "for-the-light.mp3",
  // "thanks-sub.mp3",
];
