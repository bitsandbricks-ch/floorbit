/* Shared tabs for the Jinja pages: an underline that slides to the active tab, and arrow keys.
 *
 * Mark a tab strip with class "ui-tabs" (or role="tablist"); its buttons are the tabs. The page
 * keeps deciding which tab is active (aria-selected="true" or class "active"); this only follows
 * it, so existing tab code needs no change. Arrow keys, Home and End move between tabs and
 * click the one they land on, as WAI-ARIA tabs do.
 */
(function () {
  'use strict';
  const UI = window.UI = window.UI || {};

  const isActive = (tab) => tab.getAttribute('aria-selected') === 'true' || tab.classList.contains('active');
  const tabsOf = (strip) => [...strip.children].filter((c) => c.matches('button, [role="tab"]') && !c.hidden && !c.classList.contains('hidden'));

  function place(strip, animate) {
    const bar = strip.uiTabsBar;
    const tab = tabsOf(strip).find(isActive);
    if (!tab || !strip.offsetWidth) { bar.style.opacity = '0'; return; }
    if (!animate) bar.style.transition = 'none';
    bar.style.opacity = '1';
    bar.style.width = `${tab.offsetWidth}px`;
    bar.style.transform = `translateX(${tab.offsetLeft}px)`;
    if (!animate) { void bar.offsetWidth; bar.style.removeProperty('transition'); }
  }

  UI.tabs = function (strip) {
    if (!strip || strip.uiTabsBar) return;
    strip.classList.add('ui-tabs');
    if (!strip.getAttribute('role')) strip.setAttribute('role', 'tablist');
    for (const tab of tabsOf(strip)) {
      if (!tab.getAttribute('role')) tab.setAttribute('role', 'tab');
      if (!tab.hasAttribute('type')) tab.type = 'button';
    }
    const bar = strip.uiTabsBar = document.createElement('span');
    bar.className = 'ui-tabs-bar';
    bar.setAttribute('aria-hidden', 'true');
    strip.appendChild(bar);

    let first = true;
    const update = () => { place(strip, !first); first = false; };
    new MutationObserver(update).observe(strip, {subtree: true, attributes: true, attributeFilter: ['aria-selected', 'class', 'hidden']});
    new ResizeObserver(() => place(strip, false)).observe(strip);
    update();

    strip.addEventListener('keydown', (e) => {
      const tabs = tabsOf(strip).filter((b) => !b.disabled);
      const i = tabs.indexOf(document.activeElement);
      if (i < 0) return;
      let j = null;
      if (e.key === 'ArrowRight') j = (i + 1) % tabs.length;
      else if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
      else if (e.key === 'Home') j = 0;
      else if (e.key === 'End') j = tabs.length - 1;
      if (j === null) return;
      e.preventDefault(); e.stopPropagation();
      tabs[j].focus();
      tabs[j].click();
    });
  };

  UI.enhanceTabs = function (root = document) {
    root.querySelectorAll?.('.ui-tabs, [role="tablist"]').forEach((s) => UI.tabs(s));
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => UI.enhanceTabs());
  else UI.enhanceTabs();
})();
