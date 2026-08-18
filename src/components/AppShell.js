import {createElement} from "npm:react";
import {createRoot} from "npm:react-dom/client";

function AppShell({plotNode}) {
  return createElement(
    "div",
    {className: "starter-layout"},
    createElement(
      "div",
      {className: "starter-layout__plot"},
      plotNode
    )
  );
}

export function renderAppShell(props) {
  const container = document.createElement("div");
  const root = createRoot(container);
  root.render(createElement(AppShell, props));
  return container;
}
