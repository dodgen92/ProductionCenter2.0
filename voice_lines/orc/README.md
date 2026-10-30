# Orc voice lines

Drop your recorded `.mp3` or `.wav` files in this folder.

When someone redeems **Play a Clip**, the server picks one file at random and puts its path on the clip event as `voice_line` (for example `/voice_lines/orc/hello.mp3`). The orc widget loads that from `http://localhost:5000`.

If this folder has two or more audio files, the same line will not play twice in a row.

These recordings stay on your machine. Git ignores everything in this folder except this README and `.gitkeep`.
