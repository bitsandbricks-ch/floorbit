// Big-screen rotation (templates/screen.html, docs/kiosk.md): shows one view at a time and moves
// on every SCREEN_EVERY seconds. The next view loads in the background before it fades in, and
// views stay loaded afterwards so they keep their live updates.
'use strict';

(function () {
  const views = [...document.querySelectorAll('.view')];
  const bar = document.getElementById('progress');
  const every = (window.SCREEN_EVERY || 30) * 1000;
  let current = 0;

  function load(frame) {
    if (!frame.getAttribute('src')) frame.setAttribute('src', frame.dataset.src);
  }

  function show(index) {
    views.forEach((f, i) => f.classList.toggle('on', i === index));
    current = index;
    load(views[(index + 1) % views.length]);   // warm up the next one
    bar.style.transition = 'none';
    bar.style.width = '0';
    void bar.offsetWidth;
    bar.style.transition = `width ${every}ms linear`;
    bar.style.width = '100%';
  }

  if (views.length) {
    show(0);
    if (views.length > 1) setInterval(() => show((current + 1) % views.length), every);
  }
  // A reload now and then picks up a new deployment, like /kiosk does.
  setTimeout(() => location.reload(), 6 * 3600 * 1000);
})();
