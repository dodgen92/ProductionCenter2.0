# Ask Benito widget

OBS browser source (not a local file):

```
http://localhost:5000/widgets/benito-answer/index.html
```

The card starts below the frame and slides up when a `benito_answer` event arrives. It reads the question and the answer, then plays `/tts` with the `voice`, `rate`, and `pitch` on that event (`en-US-ChristopherNeural`, `-10%`, `-60Hz`).

A `benito_command` event shows a short callout: who cast it, the command, the keybind, and the target. A `benito_control` event updates the corner label (all of chat, or the viewer who has him).

`?test=1` slides a sample answer without Twitch. `?tts=0` keeps it quiet. `?duration=6` is how long the card stays after the voice ends.

There is no Benito picture in this repo. The card is text only. Do not drop in a random portrait; a real tauren render of Benito is still missing.
