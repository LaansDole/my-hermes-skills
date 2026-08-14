(() => {
  // AppSec (Format C — direct-HTML SVG deck) state probe.
  // Target: index_lms.html (no iframe). Slides are inline SVG in the page.
  const out = {};
  // buttons: csDisabled flag matters — this course greys buttons via the
  // 'cs-disabled' CSS class, NOT the HTML disabled attribute
  const btns = [...document.querySelectorAll('button')].map(b => {
    const r = b.getBoundingClientRect();
    return {text: (b.textContent||'').trim(), cls: String(b.className||'').slice(0,40),
      vis: getComputedStyle(b).display !== 'none' && r.width > 0 && r.height > 0,
      disabled: b.disabled, csDisabled: String(b.className||'').includes('cs-disabled'),
      rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}};
  }).filter(b => b.vis);
  out.nextBtn = btns.find(b => b.text === 'NEXT') || null;
  out.prevBtn = btns.find(b => b.text === 'PREV') || null;
  out.otherBtns = btns.filter(b => !['NEXT','PREV'].includes(b.text));
  // audio playing state
  const audios = [...document.querySelectorAll('audio')].filter(a => a.duration > 1);
  out.playing = audios.filter(a => !a.paused && !a.ended).map(a => Math.round(a.currentTime) + '/' + Math.round(a.duration));
  out.audioPlayingCount = audios.filter(a => !a.paused && !a.ended).length;
  // slide number in footer: "<n> Copyright" on the same line (nbsp-separated)
  const bodyText = document.body.innerText;
  const m = bodyText.match(/(\d+)\s*(?:\u00a0|\s)*Copyright/i);
  out.page = m ? m[1] : null;
  // interactive SVG elements (cursor pointer, not player bar, not hyperlinks)
  out.svgClickables = [...document.querySelectorAll('svg *')].filter(e => {
    const st = getComputedStyle(e);
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.y > 780) return false;
    if (e.closest && e.closest('a')) return false;  // external hyperlinks are not course interactions
    return st.cursor === 'pointer' || e.hasAttribute('onclick');
  }).map(e => {
    const r = e.getBoundingClientRect();
    return {text: (e.textContent||'').trim().replace(/\s+/g,' ').slice(0, 40),
      rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}};
  }).filter((c, i, arr) => arr.findIndex(x => x.rect.x === c.rect.x && x.rect.y === c.rect.y) === i);
  // quiz inputs / submit
  out.inputs = [...document.querySelectorAll('input[type="radio"], input[type="checkbox"], input[type="text"], textarea')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.y < 780;
  }).map(e => {
    const r = e.getBoundingClientRect();
    return {type: e.type, id: e.id, checked: e.checked, disabled: e.disabled,
      rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}};
  });
  out.submitBtn = btns.find(b => b.text.toUpperCase().includes('SUBMIT') && b.rect.y > 0 && b.rect.y < 780) || null;
  // instruction text mentioning click
  out.instructions = (bodyText.match(/[^\n]*(click|select|choose|tap|press)[^\n]*/gi) || []).slice(0, 4).map(s => s.trim().slice(0, 70));
  // main heading text from SVG
  out.heading = [...document.querySelectorAll('svg text, svg tspan')].map(t => t.textContent.trim()).filter(t => t.length > 6 && t.length < 60).slice(0, 2).join(' | ');
  return JSON.stringify(out);
})()
