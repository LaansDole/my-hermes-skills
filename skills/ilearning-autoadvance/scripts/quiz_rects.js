(() => {
  // Map quiz radio inputs to their real click targets.
  // Each option radio has id "acc-<modelId>"; the clickable element is the
  // .slide-object with data-model-id="<modelId>". Option labels in the DOM are
  // usually useless ("Rectangle 3") — screenshot + vision to read the text.
  const iframe = document.querySelector('iframe');
  if (!iframe) return JSON.stringify({ok:false, err:'no iframe'});
  const doc = iframe.contentDocument;
  const radios = [...doc.querySelectorAll('input[type="radio"]')];
  const out = [];
  for (const r of radios) {
    const mid = r.id.replace(/^acc-/, '');
    const el = doc.querySelector(`[data-model-id="${mid}"]`);
    if (!el) { out.push({mid, found:false, id: r.id}); continue; }
    const r2 = el.getBoundingClientRect();
    out.push({mid, found:true, id: r.id, checked: r.checked,
              rect: {x: Math.round(r2.x), y: Math.round(r2.y), w: Math.round(r2.width), h: Math.round(r2.height)}});
  }
  return JSON.stringify({ok:true, out});
})()
