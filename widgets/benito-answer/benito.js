(function () {
  "use strict";
  // Ask Benito. Reads GET /events. Speaks benito_answer through /tts.
  // No Twitch token lives here. There is no portrait file in this folder.
  const params = new URLSearchParams(location.search);
  const get = (key) => params.get(key);
  const server = (get("server") || "http://localhost:5000").replace(/\/+$/, "");
  const test = get("test") === "1";
  const mute = get("tts") === "0";
  const holdMs = Math.max(3, +(get("duration") || 6)) * 1000;
  const card = document.getElementById("card");
  const callout = document.getElementById("callout");
  const status = document.getElementById("status");
  status.textContent = "All of chat";

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function text(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  async function speak(answer, voice, rate, pitch) {
    if (mute || !answer) return;
    const query = new URLSearchParams({
      text: answer,
      voice: voice || "en-US-ChristopherNeural",
      rate: rate || "-10%",
      pitch: pitch || "-60Hz",
    });
    const response = await fetch(server + "/tts?" + query, { cache: "no-store" });
    if (!response.ok) throw new Error("tts " + response.status);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    await new Promise((resolve, reject) => {
      audio.onended = resolve;
      audio.onerror = () => reject(new Error("audio"));
      audio.play().catch(reject);
    });
    URL.revokeObjectURL(url);
  }

  async function showAnswer(event) {
    document.getElementById("who").textContent = text(event.user || event.login) || "Someone";
    document.getElementById("question").textContent = text(event.question);
    document.getElementById("answer").textContent = text(event.answer);
    card.classList.remove("out");
    card.classList.add("in");
    try {
      await speak(text(event.answer), event.voice, event.rate, event.pitch);
    } catch (err) {
      console.warn("Benito voice failed", err && err.message);
    }
    await wait(holdMs);
    card.classList.remove("in");
    card.classList.add("out");
    await wait(520);
  }

  function showCallout(line) {
    callout.hidden = false;
    callout.textContent = line;
    callout.classList.remove("show");
    void callout.offsetWidth;
    callout.classList.add("show");
    clearTimeout(showCallout.timer);
    showCallout.timer = setTimeout(() => {
      callout.hidden = true;
    }, 4000);
  }

  function showControl(event) {
    if (event.mode === "all" || event.reason === "open") {
      status.textContent = "All of chat";
      return;
    }
    const who = text(event.user || event.login) || "Someone";
    if (event.reason === "queued") {
      status.textContent = who + " is in line";
      return;
    }
    status.textContent = who + " has Benito";
  }

  const queue = [];
  let busy = false;

  async function run() {
    busy = true;
    while (queue.length) {
      const event = queue.shift();
      try {
        if (event.type === "benito_answer") await showAnswer(event);
        else if (event.type === "benito_command") {
          const target = event.target ? " (" + event.target + ")" : "";
          showCallout((event.user || "Chat") + ": " + event.command + " → " + event.keybind + target);
        } else if (event.type === "benito_control") showControl(event);
      } catch (err) {
        console.warn(err);
        card.className = "";
      }
    }
    busy = false;
  }

  function push(event) {
    if (queue.length >= 20) return;
    queue.push(event);
    if (!busy) run();
  }

  window.benitoAnswer = { push: push };

  if (test) {
    push({
      type: "benito_answer",
      user: "River",
      question: "Who are you?",
      answer: "I am Benito, a tauren druid of Mulgore. The Earth Mother walks with me.",
      voice: "en-US-ChristopherNeural",
      rate: "-10%",
      pitch: "-60Hz",
    });
    return;
  }

  let since = -1;
  let delay = 1000;
  const seen = new Set();

  async function poll() {
    try {
      const response = await fetch(server + "/events?since=" + since, { cache: "no-store" });
      if (!response.ok) throw new Error("events " + response.status);
      const body = await response.json();
      if (since < 0) since = body.last_id || 0;
      else {
        for (const event of body.events || []) {
          since = Math.max(since, event.id || 0);
          if (event.type !== "benito_answer" && event.type !== "benito_command" && event.type !== "benito_control") continue;
          const key = event.type + ":" + event.id;
          if (seen.has(key)) continue;
          seen.add(key);
          push(event);
        }
        since = Math.max(since, body.last_id || 0);
      }
      delay = 1000;
    } catch (err) {
      delay = Math.min(delay * 2, 15000);
    }
    setTimeout(poll, delay);
  }

  poll();
})();
