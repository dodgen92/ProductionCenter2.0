// Edit in Notepad. Positions are in pixels on the 1920x1080 screen (line them up with the fireplace/candles in bg/tavern.jpg).
window.SCENE_FX={
  fires:[{x:300,y:420,r:200}],                // fireplace glow (left)
  candles:[{x:1142,y:758,r:55},{x:1322,y:784,r:50},{x:187,y:128,r:45},{x:1059,y:395,r:40}],  // 2 table candles, wall candle, window-sill candle
  embers:45, dust:40,
  emberFrom:{x:300,y:500,w:170}               // embers rise from the hearth
};
// Tavern-only extras (used when bg/tavern.jpg loads). Coords are 1920x1080.
window.TAVERN_FX={
  wall:[{x:330,y:330,r:330}],                 // firelight dancing on the stone wall
  lanterns:[{x:718,y:146,r:110},{x:1121,y:132,r:110}],
  sprites:[                                   // cropped painting pieces, gently animated
    {src:"bg/dwarf-hands.png",x:444,y:384,w:156,anim:"polish"},
    {src:"bg/dwarf-mug.png",x:615,y:339,w:135,anim:"slosh"},
    {src:"bg/gnome-mug.png",x:1416,y:576,w:135,anim:"slosh"}
  ],
  glints:[{x:668,y:375},{x:1478,y:612}]       // shimmer on the mug rims
};
// Rotating flavor lines (Starting Soon + BRB). One per line, keep the quotes and commas.
window.SCENE_TIPS=[
  "Grab a drink, the hearth is warm.",
  "Tip: !commands lists the chat commands.",
  "Repair your gear before the pull.",
  "Lok'tar... or whatever. Get comfy.",
  "Don't stand in the fire. Sit by it instead."
];
