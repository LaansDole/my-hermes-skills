/**
 * Covidence Full-Text Link Upload Helper
 * Usage: load in browser_console via skill_view, then call uploadQueue([...])
 *
 * uploadQueue: array of {ref_id: string, url: string}
 * Returns a results object keyed by ref_id: 'ok' | 'still Upload' | 'not found' | 'no dialog' | etc.
 *
 * Example:
 *   uploadQueue([
 *     {ref_id: '443', url: 'https://arxiv.org/pdf/2506.06574'},
 *     {ref_id: '382', url: 'https://arxiv.org/pdf/2507.22504'},
 *   ]).then(r => JSON.stringify(r));
 */

async function uploadQueue(queue) {
  const results = {};

  const findHeader = (id) =>
    Array.from(document.querySelectorAll('p'))
      .find(p => p.textContent.trim().startsWith('#' + id + ' -'));

  const checkResolved = (id) => {
    const h = findHeader(id);
    if (!h) return 'not found';
    let b = h.parentElement;
    for (let i = 0; i < 6; i++) {
      const btns = Array.from(b.querySelectorAll('button'));
      if (btns.find(b2 => b2.textContent.trim() === 'Upload full text')) return 'still Upload';
      const ft = btns.find(b2 =>
        b2.textContent.trim().startsWith('Full text') ||
        b2.textContent.trim().startsWith('Manage'));
      if (ft) return 'ok';
      b = b.parentElement;
    }
    return 'unknown';
  };

  const openUpload = (id) => {
    const h = findHeader(id);
    if (!h) return false;
    let b = h.parentElement;
    for (let i = 0; i < 6; i++) {
      const up = Array.from(b.querySelectorAll('button'))
        .find(b2 => b2.textContent.trim() === 'Upload full text');
      if (up) { up.click(); return true; }
      b = b.parentElement;
    }
    return false;
  };

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  for (const {ref_id, url} of queue) {
    // Skip if already resolved
    const precheck = checkResolved(ref_id);
    if (precheck === 'ok') { results[ref_id] = 'already resolved'; continue; }

    // Open the upload modal
    if (!openUpload(ref_id)) {
      results[ref_id] = 'not found';
      continue;
    }
    await sleep(400);

    // Find the Link to full text input inside the dialog
    const dialog = document.querySelector('[role="dialog"], dialog');
    if (!dialog) { results[ref_id] = 'no dialog'; continue; }

    const linkInput = dialog.querySelector(
      'input[type="text"], input[type="url"], ' +
      'input:not([type="checkbox"]):not([type="hidden"]):not([type="file"])'
    );
    if (!linkInput) { results[ref_id] = 'no input'; continue; }

    // Set value using React-compatible native setter
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    nativeSetter.call(linkInput, url);
    linkInput.dispatchEvent(new Event('input', {bubbles: true}));
    linkInput.dispatchEvent(new Event('change', {bubbles: true}));
    await sleep(200);

    // Click "Add link"
    const addBtn = Array.from(dialog.querySelectorAll('button'))
      .find(b => b.textContent.trim() === 'Add link');
    if (!addBtn) { results[ref_id] = 'no add-link btn'; continue; }
    addBtn.click();
    await sleep(400);

    // Click "Done"
    const doneBtn = Array.from(dialog.querySelectorAll('button'))
      .find(b => b.textContent.trim() === 'Done');
    if (!doneBtn) { results[ref_id] = 'no done btn'; continue; }
    doneBtn.click();
    await sleep(600);

    // Verify
    results[ref_id] = checkResolved(ref_id);
  }

  return results;
}
