/* Apply the companion's shared identity to static and dynamically-created UI text. */
(() => {
  'use strict';
  const fallback = { name: 'AIVA', tagline: 'Talk, reflect, and be understood.' };

  function replaceName(value, name) {
    return String(value)
      .replace(/\bAIVA\b/g, name.toUpperCase())
      .replace(/\bAIVA\b/g, name);
  }

  function updateTree(root, name, includeTextarea = false) {
    function updateNode(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        const parent = node.parentElement;
        if (parent && !['SCRIPT', 'STYLE'].includes(parent.tagName)
            && (includeTextarea || parent.tagName !== 'TEXTAREA')) {
          const updated = replaceName(node.nodeValue, name);
          if (updated !== node.nodeValue) node.nodeValue = updated;
        }
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        for (const attribute of ['aria-label', 'title', 'alt', 'placeholder']) {
          const value = node.getAttribute(attribute);
          if (value) {
            const updated = replaceName(value, name);
            if (updated !== value) node.setAttribute(attribute, updated);
          }
        }
      }
    }
    if (root.nodeType === Node.TEXT_NODE || root.nodeType === Node.ELEMENT_NODE) {
      updateNode(root);
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) updateNode(walker.currentNode);
    if (root === document) document.title = replaceName(document.title, name);
  }

  /*
   * The name replacement follows nodes added by page scripts so generated
   * chat rows, flow annotations, and status text use the same identity.
   */
  function apply(identity) {
    const name = typeof identity?.name === 'string' && identity.name.trim()
      ? identity.name.trim() : fallback.name;
    window.AGIIdentity = { ...fallback, ...identity, name };
    updateTree(document, name, true);
    document.querySelectorAll('[data-identity-name]').forEach((element) => {
      if (element.textContent !== name) element.textContent = name;
    });
    document.querySelectorAll('[data-identity-field="tagline"]').forEach((element) => {
      const tagline = window.AGIIdentity.tagline || fallback.tagline;
      if (element.textContent !== tagline) element.textContent = tagline;
    });
    const description = document.querySelector('meta[name="description"]');
    if (description && window.AGIIdentity.bio) description.setAttribute('content', window.AGIIdentity.bio);
    window.dispatchEvent(new CustomEvent('agi-identity-ready', { detail: window.AGIIdentity }));
  }

  apply(fallback);
  const observer = new MutationObserver((records) => {
    const name = window.AGIIdentity?.name || fallback.name;
    for (const record of records) {
      if (record.type === 'characterData') updateTree(record.target, name);
      else record.addedNodes.forEach((node) => updateTree(node, name));
    }
  });
  observer.observe(document.documentElement, {
    subtree: true, childList: true, characterData: true,
  });

  fetch('/api/identity', { cache: 'no-store' })
    .then((response) => { if (!response.ok) throw new Error(`Identity request returned ${response.status}`); return response.json(); })
    .then(apply)
    .catch((error) => console.debug('Companion identity is not available:', error));
})();
