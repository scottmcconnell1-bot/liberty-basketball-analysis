(function () {
  function flattenTree(nodes, depth = 0, out = []) {
    (nodes || []).forEach((node) => {
      out.push({ node, depth });
      flattenTree(node.children, depth + 1, out);
    });
    return out;
  }

  function renderTree(container, tree, selectedId, onSelect) {
    if (!container) return;
    const storageKey = 'liberty.playbook.treeExpanded';
    let expanded = {};
    try {
      expanded = JSON.parse(sessionStorage.getItem(storageKey) || '{}') || {};
    } catch (err) {
      expanded = {};
    }

    function isExpanded(node) {
      const key = String(node.id);
      if (Object.prototype.hasOwnProperty.call(expanded, key)) {
        return !!expanded[key];
      }
      // Default: open parents that contain the selection or have plays under them.
      if (selectedId) {
        const ids = collectDescendantIds([node], selectedId) || [];
        if (ids.map(String).includes(String(selectedId))) return true;
      }
      return (node.play_count || 0) > 0;
    }

    function setExpanded(nodeId, value) {
      expanded[String(nodeId)] = value;
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(expanded));
      } catch (err) {
        /* ignore quota */
      }
    }

    container.innerHTML = '';
    const allItem = document.createElement('div');
    allItem.className = 'playbook-tree-item' + (selectedId ? '' : ' active');
    allItem.textContent = 'All Plays';
    allItem.addEventListener('click', () => onSelect(null));
    container.appendChild(allItem);

    function renderNode(node, parentEl, depth) {
      const children = node.children || [];
      const hasChildren = children.length > 0;
      const open = hasChildren && isExpanded(node);

      const item = document.createElement('div');
      const droppable = !node.nav_href && !hasChildren;
      item.className = 'playbook-tree-item'
        + (String(node.id) === String(selectedId) ? ' active' : '')
        + (hasChildren ? ' has-children' : '')
        + (open ? ' is-open' : '')
        + (droppable ? ' playbook-tree-drop' : '');
      item.style.setProperty('--tree-depth', String(depth));
      item.dataset.categoryId = String(node.id);
      item.dataset.droppable = droppable ? '1' : '0';
      if (node.slug_path) item.dataset.slugPath = node.slug_path;
      if (droppable) {
        item.title = 'Drop plays here to move them into this category';
      }
      const label = document.createElement('span');
      label.className = 'playbook-tree-label';

      if (hasChildren) {
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'playbook-tree-toggle';
        toggle.setAttribute('aria-label', open ? 'Collapse' : 'Expand');
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggle.textContent = open ? '▾' : '▸';
        toggle.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          setExpanded(node.id, !open);
          renderTree(container, tree, selectedId, onSelect);
        });
        label.appendChild(toggle);
      } else {
        const spacer = document.createElement('span');
        spacer.className = 'playbook-tree-toggle-spacer';
        label.appendChild(spacer);
      }

      const name = document.createElement('span');
      name.className = 'playbook-tree-name';
      name.textContent = node.name;
      label.appendChild(name);

      const count = document.createElement('span');
      count.className = 'count';
      count.textContent = String(node.play_count || 0);

      item.appendChild(label);
      item.appendChild(count);
      item.addEventListener('click', () => {
        if (node.nav_href) {
          window.location.href = node.nav_href;
          return;
        }
        if (hasChildren && !open) {
          setExpanded(node.id, true);
        }
        onSelect(node.id, node);
      });
      parentEl.appendChild(item);

      if (hasChildren && open) {
        const childWrap = document.createElement('div');
        childWrap.className = 'playbook-tree-children';
        children.forEach((child) => renderNode(child, childWrap, depth + 1));
        parentEl.appendChild(childWrap);
      }
    }

    (tree || []).forEach((node) => renderNode(node, container, 0));
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function collectDescendantIds(tree, categoryId) {
    if (!categoryId) return null;
    let ids = [];
    function walk(nodes) {
      (nodes || []).forEach((node) => {
        if (String(node.id) === String(categoryId)) {
          ids = gatherIds(node);
        } else {
          walk(node.children);
        }
      });
    }
    function gatherIds(node) {
      const collected = [node.id];
      (node.children || []).forEach((child) => {
        collected.push(...gatherIds(child));
      });
      return collected;
    }
    walk(tree);
    return ids.length ? ids : [categoryId];
  }

  function fillCategorySelect(select, tree, selectedId) {
    if (!select) return;
    select.innerHTML = '';
    flattenTree(tree).forEach(({ node, depth }) => {
      const opt = document.createElement('option');
      opt.value = String(node.id);
      opt.textContent = `${'— '.repeat(depth)}${node.name}`;
      if (String(node.id) === String(selectedId)) opt.selected = true;
      select.appendChild(opt);
    });
  }

  function fillLeafCategorySelect(select, tree, selectedId) {
    if (!select) return;
    select.innerHTML = '';
    flattenTree(tree).forEach(({ node, depth }) => {
      if (node.children && node.children.length) return;
      const opt = document.createElement('option');
      opt.value = String(node.id);
      const path = (node.slug_path || '').replace(/\//g, ' · ').replace(/_/g, ' ');
      opt.textContent = path || node.name;
      if (String(node.id) === String(selectedId)) opt.selected = true;
      select.appendChild(opt);
    });
  }

  function pickCategory(tree, options = {}) {
    const {
      title = 'Choose category',
      excludeId = null,
      allowBlank = false,
      blankLabel = '— Top level —',
    } = options;

    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px;';

      const panel = document.createElement('div');
      panel.style.cssText = 'background:#fff;border-radius:12px;padding:20px;max-width:420px;width:100%;box-shadow:0 20px 40px rgba(0,0,0,0.2);';

      const heading = document.createElement('h4');
      heading.textContent = title;
      heading.style.marginBottom = '12px';

      const select = document.createElement('select');
      select.className = 'form-control';
      if (allowBlank) {
        const blank = document.createElement('option');
        blank.value = '';
        blank.textContent = blankLabel;
        select.appendChild(blank);
      }
      flattenTree(tree).forEach(({ node, depth }) => {
        if (excludeId && String(node.id) === String(excludeId)) return;
        const opt = document.createElement('option');
        opt.value = String(node.id);
        const path = (node.slug_path || node.name || '').replace(/\//g, ' · ').replace(/_/g, ' ');
        opt.textContent = `${'— '.repeat(depth)}${path}`;
        select.appendChild(opt);
      });

      const actions = document.createElement('div');
      actions.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;margin-top:16px;';

      const cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'btn btn-secondary btn-sm';
      cancelBtn.textContent = 'Cancel';

      const okBtn = document.createElement('button');
      okBtn.type = 'button';
      okBtn.className = 'btn btn-primary btn-sm';
      okBtn.textContent = 'OK';

      function close(value) {
        overlay.remove();
        resolve(value);
      }

      cancelBtn.addEventListener('click', () => close(undefined));
      okBtn.addEventListener('click', () => {
        const raw = select.value;
        close(raw ? parseInt(raw, 10) : null);
      });
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close(undefined);
      });

      actions.appendChild(cancelBtn);
      actions.appendChild(okBtn);
      panel.appendChild(heading);
      panel.appendChild(select);
      panel.appendChild(actions);
      overlay.appendChild(panel);
      document.body.appendChild(overlay);
      select.focus();
    });
  }

  async function apiJson(url, options) {
    const resp = await fetch(url, options);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || 'Request failed');
    return data;
  }

  window.PlaybookTaxonomy = {
    renderTree,
    fillCategorySelect,
    fillLeafCategorySelect,
    pickCategory,
    collectDescendantIds,
    async createCategory(parentId, name) {
      return apiJson('/api/playbook/categories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_id: parentId, name }),
      });
    },
    async renameCategory(categoryId, name) {
      return apiJson(`/api/playbook/categories/${categoryId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
    },
    async moveCategory(categoryId, parentId) {
      return apiJson(`/api/playbook/categories/${categoryId}/move`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_id: parentId }),
      });
    },
    async deleteCategory(categoryId, reassignTo) {
      return apiJson(`/api/playbook/categories/${categoryId}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reassign_to: reassignTo || null }),
      });
    },
  };
})();
