// FloorPro's only custom script (Principle IV, research.md §7): open server-rendered
// <dialog> modals, and guard forms with unsaved changes. Keep this under 40 lines.
(function () {
  let dirty = null, pending = null;
  const discardDialog = () => document.getElementById("discard-dialog");
  document.addEventListener("htmx:load", () => {
    document.querySelectorAll("#modal dialog:not([open])").forEach((d) => d.showModal());
  });
  document.addEventListener("click", (e) => {
    const close = e.target.closest("[data-close-dialog]");
    if (close) { close.closest("dialog").close(); return; }
    if (e.target.closest("[data-discard-confirm]")) {
      dirty = null; discardDialog().close();
      if (pending) { const link = pending; pending = null; link.click(); }
      return;
    }
    const link = e.target.closest("a[href]");
    if (!dirty || !link || dirty.contains(link)) return;
    e.preventDefault(); e.stopPropagation();
    pending = link; discardDialog().showModal();
  }, true);
  document.addEventListener("input", (e) => {
    const form = e.target.closest("form[data-guard-unsaved]");
    if (form) dirty = form;
  });
  document.addEventListener("submit", () => { dirty = null; });
  document.addEventListener("htmx:afterSettle", () => {
    if (dirty && !document.body.contains(dirty)) dirty = null;
  });
  window.addEventListener("beforeunload", (e) => { if (dirty) e.preventDefault(); });
})();
