(() => {
  const hover = matchMedia('(hover: hover) and (pointer: fine)');
  const triggerSelector = '.price-history-trigger';
  const popupSelector = '.price-history-popup';
  let hoverClose;

  const position = (popup, trigger) => {
    const anchor = trigger.getBoundingClientRect();
    const width = popup.offsetWidth;
    const height = popup.offsetHeight;
    popup.style.left = Math.max(8, Math.min(anchor.left, innerWidth - width - 8)) + 'px';
    const top = anchor.bottom + height <= innerHeight - 8
      ? anchor.bottom
      : Math.max(8, anchor.top - height);
    popup.style.top = top + 'px';
  };

  document.addEventListener('beforetoggle', (event) => {
    const popup = event.target;
    if (!popup.matches(popupSelector) || event.newState !== 'open') return;
    const trigger = popup.previousElementSibling;
    requestAnimationFrame(() => {
      if (popup.matches(':popover-open')) position(popup, trigger);
    });
  }, true);

  document.addEventListener('pointerover', (event) => {
    if (!hover.matches || event.pointerType !== 'mouse') return;
    const area = event.target.closest(triggerSelector + ', ' + popupSelector);
    if (!area || area.contains(event.relatedTarget)) return;
    clearTimeout(hoverClose);
    if (area.matches(triggerSelector)) {
      const popup = area.nextElementSibling;
      if (!popup.matches(':popover-open')) popup.showPopover();
      position(popup, area);
    }
  });

  document.addEventListener('pointerout', (event) => {
    const area = event.target.closest(triggerSelector + ', ' + popupSelector);
    if (!hover.matches || event.pointerType !== 'mouse' || !area || area.contains(event.relatedTarget)) return;
    const popup = area.matches(popupSelector) ? area : area.nextElementSibling;
    hoverClose = setTimeout(() => {
      if (popup.matches(':popover-open') && !popup.contains(document.activeElement)) popup.hidePopover();
    }, 180);
  });

  const close = () => {
    const popup = document.querySelector(popupSelector + ':popover-open');
    if (popup) popup.hidePopover();
  };
  addEventListener('resize', close);
  addEventListener('scroll', (event) => {
    if (!(event.target instanceof Element) || !event.target.closest(popupSelector)) close();
  }, true);
})();
