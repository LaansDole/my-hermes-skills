(() => {
  const iframe = document.querySelector('iframe');
  if (!iframe) {
    const continueBtn = [...document.querySelectorAll('button, a')].find(b =>
      (b.textContent || '').toLowerCase().includes('continue course')
    );
    return JSON.stringify({
      page: 'parent', hostname: location.hostname,
      hasIframe: false, hasContinueBtn: !!continueBtn, url: location.href, title: document.title
    });
  }
  const doc = iframe.contentDocument;
  const win = iframe.contentWindow;
  if (!doc || !win) return JSON.stringify({ page: 'error', error: 'iframe not accessible', url: location.href });

  // Storyline data-store state
  let sl = {};
  try {
    const wm = win.DS?.appState?.windowManager;
    const slide = wm?.getCurrentWindowSlide?.();
    sl.slideId = slide?.id;
    sl.slideTitle = slide?.attributes?.title;
    sl.slideKind = slide?.attributes?.kind;
    sl.sceneId = slide?.parent?.id;
    const sceneSlides = slide?.parent?.attributes?.slides;
    if (sceneSlides?.models) {
      sl.sceneSlides = sceneSlides.models.map(m => ({ id: m.id, title: m.attributes?.title, kind: m.attributes?.kind }));
      sl.currentIdx = sceneSlides.models.findIndex(m => m.id === slide.id);
      sl.totalSlides = sceneSlides.models.length;
    }
    const proj = slide?.parent?.parent;
    sl.projectSlideCount = proj?.attributes?.slideCount;
  } catch(e) { sl.err = e.message; }

  // Audio playback (primary progress indicator — NOT video)
  const audios = [...doc.querySelectorAll('audio')];
  const playing = audios.filter(a => !a.paused && !a.ended);
  const ended = audios.filter(a => a.ended);

  // Play / Pause / Next button visibility (Storyline toggles aria-hidden)
  const playBtn = doc.querySelector('[data-acc-text="Play Button"]');
  const pauseBtn = doc.querySelector('[data-acc-text="Pause Button"]');
  const nextBtn = doc.querySelector('[data-acc-text="Next Button"]');
  const continueBtn = doc.querySelector('[data-acc-text*="continue" i], [data-acc-text*="completed" i], [data-acc-text="Next Button"]');

  // Visible, meaningful clickable slide objects — viewport-filtered
  // (offscreen decoy layers sit at x>=1920 and must be excluded).
  const visibleClickables = [...doc.querySelectorAll('.slide-object')].filter(e => {
    const st = getComputedStyle(e);
    if (st.visibility !== 'visible' || st.opacity === '0' || st.display === 'none') return false;
    const r = e.getBoundingClientRect();
    return r.width > 5 && r.height > 5 &&
           r.x >= -10 && r.y >= -10 &&
           r.x + r.width <= win.innerWidth + 10 &&
           r.y + r.height <= win.innerHeight + 10;
  }).map(e => {
    const r = e.getBoundingClientRect();
    // Real click targets are often the ancestor stategroup (e.g. a circular
    // button whose label is a child div). Prefer its rect.
    let clickRect = null;
    let clickMid = null;
    let p = e.parentElement;
    while (p && p.classList) {
      if (String(p.className).includes('slide-object-stategroup')) {
        const pr = p.getBoundingClientRect();
        if (pr.width > 5 && pr.height > 5) {
          clickRect = { x: Math.round(pr.x), y: Math.round(pr.y), w: Math.round(pr.width), h: Math.round(pr.height) };
          clickMid = p.getAttribute('data-model-id');
        }
        break;
      }
      p = p.parentElement;
    }
    return {
      accText: e.getAttribute('data-acc-text'),
      modelId: e.getAttribute('data-model-id'),
      cursor: getComputedStyle(e).cursor,
      cls: String(e.className).slice(0, 40),
      rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      clickRect, clickMid
    };
  }).filter(e => e.accText && !['Pause Button','Play Button'].includes(e.accText));

  // Slide-level click instructions (e.g. "Click on each term to know its definition")
  const instructions = visibleClickables
    .map(c => c.accText)
    .filter(t => /click (on )?(each|all|the|any|every)|click each|click on|select (each|all|the|any)|choose (each|all|the|any)|tap (each|on)|press (each|on)|to (know|see|view|learn) (the|its|their)? ?(definition|meaning|details?)/i.test(t));

  // Quiz inputs
  const quizInputs = [...doc.querySelectorAll('input[type="radio"], input[type="checkbox"]:not(.acc-shadow-el), input[type="text"], textarea')]
    .map(i => {
      const lb = i.getAttribute('aria-labelledby');
      return { type: i.type, id: i.id, checked: i.checked, disabled: i.disabled,
               label: lb ? doc.getElementById(lb)?.textContent?.trim()?.slice(0, 80) : null };
    });

  return JSON.stringify({
    page: 'iframe', hostname: location.hostname, sl,
    playing: playing.length, ended: ended.length, totalAudio: audios.length,
    playAriaHidden: playBtn?.getAttribute('aria-hidden'),
    pauseAriaHidden: pauseBtn?.getAttribute('aria-hidden'),
    hasNext: !!nextBtn, nextAriaHidden: nextBtn?.getAttribute('aria-hidden'),
    continueAccText: continueBtn?.getAttribute('data-acc-text'),
    visibleClickables, instructions, quizInputs, url: location.href
  });
})()
