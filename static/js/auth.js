'use strict';

// When the session runs out, API calls answer 401: send the person to the
// sign-in page and bring them back here afterwards, instead of failing silently.
(function () {
  const originalFetch = window.fetch.bind(window);
  let redirecting = false;
  window.fetch = async function (...args) {
    const resp = await originalFetch(...args);
    if (resp.status === 401 && !redirecting) {
      const body = await resp.clone().json().catch(() => null);
      if (body && body.login_url) {
        redirecting = true;
        const here = location.pathname + location.search + location.hash;
        location.assign(body.login_url + '?next=' + encodeURIComponent(here));
      }
    }
    return resp;
  };
})();
