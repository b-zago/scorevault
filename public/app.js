const $ = (id) => document.getElementById(id);

async function load() {
  try {
    const res = await fetch("/scores");
    if (!res.ok) throw new Error(res.status);
    const scores = await res.json();
    const max = scores[0]?.score || 1;
    $("board").innerHTML = scores
      .map(
        (s, i) => `
    <div class="row">
      <span class="rank ${i < 3 ? "top" : ""}">${i + 1}</span>
      <span class="player">${s.player}</span>
      <div class="bar-wrap"><div class="bar" style="width:${Math.round((s.score / max) * 100)}%"></div></div>
      <span class="score">${s.score.toLocaleString()}</span>
    </div>`,
      )
      .join("");
  } catch (e) {
    $("board").innerHTML = `<div class="row">failed to load: ${e.message}</div>`;
  }
}

async function post(e) {
  e.preventDefault();
  const player = $("player").value.trim();
  const score = parseInt($("score").value);
  const st = $("status");
  if (!player || isNaN(score)) return;
  st.textContent = "posting...";
  try {
    const res = await fetch("/scores", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player, score }),
    });
    if (!res.ok) throw new Error(res.status);
    $("player").value = "";
    $("score").value = "";
    st.textContent = "submitted.";
    load();
  } catch (e) {
    st.textContent = `error: ${e.message}`;
  }
  setTimeout(() => (st.textContent = ""), 3000);
}

document.querySelector("form").addEventListener("submit", post);
load();
