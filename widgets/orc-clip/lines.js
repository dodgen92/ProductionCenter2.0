// Orc voice lines for Play a Clip.
// Edit the words in "text" to fix a line. Leave "file" matched to the mp3 in audio/.
// voice_start_s / voice_end_s are seconds from the start of the file.
// The music bed starts first, the orc talks, then the music fades out.
// The countdown and the clip both wait until voice_end_s.
//
// The file numbers run backwards from the rank:
//   WoW1.mp3 is WoW #10 (10th in World of Warcraft). WoW10.mp3 is WoW #1.
//   Twitch1.mp3 is Twitch #5. Twitch5.mp3 is Twitch #1.
// Save this file, then refresh the browser source in OBS.
// Keep each line in double quotes. Use ' inside a line, not ".
window.ORC_LINES = {
  "wow": [
    {"file": "WoW1.mp3", "rank": 10, "text": "This is the 10th most popular clip in Azeroth today.", "voice_start_s": 1.0, "voice_end_s": 4.71},
    {"file": "WoW2.mp3", "rank": 9, "text": "The ninth most popular clip in Azeroth. The grunts are watching. Do not disappoint them.", "voice_start_s": 1.0, "voice_end_s": 7.24},
    {"file": "WoW3.mp3", "rank": 8, "text": "8th most popular clip in Azeroth, respectable numbers.", "voice_start_s": 1.0, "voice_end_s": 6.11},
    {"file": "WoW4.mp3", "rank": 7, "text": "7. The most popular clip in Azeroth. The war drums stir.", "voice_start_s": 1.0, "voice_end_s": 6.53},
    {"file": "WoW5.mp3", "rank": 6, "text": "Sharpen your axe. This one has teeth. Number six in Azeroth today.", "voice_start_s": 1.0, "voice_end_s": 7.22},
    {"file": "WoW6.mp3", "rank": 5, "text": "Fifth most popular clip in Azeroth. Not bad, puny one.", "voice_start_s": 1.0, "voice_end_s": 5.69},
    {"file": "WoW7.mp3", "rank": 4, "text": "This is the fourth most popular clip in World of Warcraft today. Grom would be mildly impressed.", "voice_start_s": 1.0, "voice_end_s": 8.95},
    {"file": "WoW8.mp3", "rank": 3, "text": "Third greatest moment in Azeroth. This one has honor.", "voice_start_s": 1.0, "voice_end_s": 5.41},
    {"file": "WoW9.mp3", "rank": 2, "text": "This is the second most popular moment in all of Azeroth. So close to the glory.", "voice_start_s": 1.0, "voice_end_s": 7.33},
    {"file": "WoW10.mp3", "rank": 1, "text": "The number one moment in Azeroth today, Lokhtar!", "voice_start_s": 1.0, "voice_end_s": 5.49}
  ],
  "twitch": [
    {"file": "Twitch1.mp3", "rank": 5, "text": "The fifth best clip in all of Twitch right here, Lok'tar.", "voice_start_s": 1.0, "voice_end_s": 5.15},
    {"file": "Twitch2.mp3", "rank": 4, "text": "The fourth most popular clip on Twitch, Lok'tar Keep Climbing Whelps.", "voice_start_s": 1.0, "voice_end_s": 6.32},
    {"file": "Twitch3.mp3", "rank": 3, "text": "Third most popular clip on Twitch. The war drums grow louder.", "voice_start_s": 1.0, "voice_end_s": 5.94},
    {"file": "Twitch4.mp3", "rank": 2, "text": "The second mightiest clip on all of Twitch right here.", "voice_start_s": 1.0, "voice_end_s": 5.78},
    {"file": "Twitch5.mp3", "rank": 1, "text": "This is the most popular clip on all of Twitch. The Bards will sing of this. Poorly, but they will sing.", "voice_start_s": 1.0, "voice_end_s": 9.62}
  ]
};
