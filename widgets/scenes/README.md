# Scene screens (Starting Soon / BRB / End)
Full-screen 1920x1080 opaque scenes in the tavern/gold-trim style. No network, no secrets.

**Background layer:** drop `bg/tavern.jpg` (1920x1080) in and it is used automatically (slow parallax drift); otherwise an animated CSS/canvas background (warm hearth gradient + rotating rune circle) shows. `?bg=other.jpg` overrides.
**Overlays:** edit `scenes-config.js`: `fires` / `candles` (x, y, r in px; flickering screen-blended glows), `embers`, `dust`, `emberFrom`. Also holds `SCENE_TIPS` (rotating lines).

## Params
All: `?test=1`, `?title=`, `?embers=N`, `?dust=N`, `?bg=`.
- starting.html: `?min=5` countdown from N minutes, or `?at=19:30` to a local time; at zero shows "Any second now...". Test mode = 6 s countdown.
- brb.html: `?side=left|right` (default left, over the tauren), `?shortdelay=10` (frame slides in after N s; shorts start then), `?tagline=` (default 'Enjoy these classic Remyfriend moments'), `?mute=1`, `?vol=0.6` (default), `?cap=text` (`?cap=` hides caption), `?dir=` shorts folder. Plays `brb/shorts/` files listed in `shorts.js`, else probes 1.mp4..50.mp4. Shuffled, no repeats until all played, advances on end, skips broken files. Placeholder if none; test mode animates a canvas preview.
- end.html: `?sub=` (default "Stream over"), `?raid=NAME` → "Raiding NAME next!", `?socials=` override.

## Tavern (bg/tavern.jpg, approved)
Overlays in `scenes-config.js` (1920x1080 coords = image px x 1.5): fireplace glow (300,420) + firelight dancing on the wall (330,330) + embers from the hearth; candle flicker at both table candles (1142,758)/(1322,784), wall candle (187,128), window candle (1059,395); lantern sway/pulse (718,146)/(1121,132); dust motes biased into lantern light. Cropped feathered layers: `bg/dwarf-hands.png` (rag polish loop), `bg/dwarf-mug.png` and `bg/gnome-mug.png` (slight slosh tilt + rim glint). Overlays ride the slow bg drift.
## Ambience
Procedural WebAudio (no audio files): fire crackle bed + pops, faint room tone, occasional mug clink / slosh. `?ambience=0` off, `?avol=0.35`. BRB ducks it to 30% while a short plays with sound. Tick 'Control audio via OBS' on all three sources.
