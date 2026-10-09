/** Expand the same live table and controls without duplicating form state. */
export function addTableWorkspace(root: HTMLElement, title: string, id: string): void {
  const content = document.createElement("div");
  content.className = "table-workspace-content";
  content.append(...Array.from(root.childNodes));
  const expand = document.createElement("button");
  expand.id = `${id}-expand`;
  expand.className = "primary-button";
  expand.textContent = `Expand ${title}`;
  const dialog = document.createElement("dialog");
  dialog.id = `${id}-workspace`;
  dialog.className = "table-workspace";
  dialog.setAttribute("aria-labelledby", `${id}-workspace-title`);
  const heading = document.createElement("h2");
  heading.id = `${id}-workspace-title`;
  heading.textContent = title;
  const close = document.createElement("button");
  close.textContent = `Close ${title}`;
  const header = document.createElement("div");
  header.className = "view-actions";
  header.append(heading, close);
  dialog.append(header);
  root.append(expand, content, dialog);
  expand.addEventListener("click", () => {
    dialog.append(content);
    dialog.returnValue="";
    dialog.showModal();
    close.focus();
  });
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    root.insertBefore(content, dialog);
    if(dialog.returnValue!=="navigate")expand.focus();
  });
}
