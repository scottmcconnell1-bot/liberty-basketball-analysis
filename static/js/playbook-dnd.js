/**
 * Playbook list: multi-select + drag-and-drop.
 *
 * Within list: reorder plays / progressions
 * Onto category tree: move top-level plays into that category
 *
 * Click name/row to select · Ctrl/Cmd toggle · Shift range
 * Drag to reorder or drop on a category · Double-click to open
 */
(function () {
  function initPlaybookDragDrop(root, options) {
    if (!root || root.dataset.dndReady === '1') return;
    if (root.dataset.readonly === '1') return;
    root.dataset.dndReady = '1';

    const opts = options || {};
    const treeEl = opts.categoryTree || document.getElementById('playbookCategoryTree');
    const selected = new Set();
    let lastAnchor = null;
    let dragIds = [];

    function groupKey(el) {
      return el.dataset.group || 'root';
    }

    function containerFor(group) {
      if (group === 'root') {
        return root.querySelector('.playbook-list-items[data-group="root"]') || root;
      }
      return root.querySelector(`.play-progressions[data-group="${group}"]`);
    }

    function itemsInGroup(group, { visibleOnly = false } = {}) {
      const container = containerFor(group);
      if (!container) return [];
      return Array.from(container.querySelectorAll(':scope > .play-dnd-item')).filter(
        (el) => !visibleOnly || el.style.display !== 'none'
      );
    }

    function clearSelection() {
      selected.clear();
      root.querySelectorAll('.play-dnd-item.is-selected').forEach((el) => {
        el.classList.remove('is-selected');
      });
    }

    function setSelected(el, on) {
      const id = String(el.dataset.playId);
      if (on) {
        selected.add(id);
        el.classList.add('is-selected');
      } else {
        selected.delete(id);
        el.classList.remove('is-selected');
      }
    }

    function selectOnly(el) {
      clearSelection();
      setSelected(el, true);
      lastAnchor = el;
    }

    function toggle(el) {
      const id = String(el.dataset.playId);
      setSelected(el, !selected.has(id));
      lastAnchor = el;
    }

    function selectRange(el) {
      const group = groupKey(el);
      const items = itemsInGroup(group, { visibleOnly: true });
      if (!lastAnchor || groupKey(lastAnchor) !== group) {
        selectOnly(el);
        return;
      }
      const a = items.indexOf(lastAnchor);
      const b = items.indexOf(el);
      if (a < 0 || b < 0) {
        selectOnly(el);
        return;
      }
      clearSelection();
      const [lo, hi] = a < b ? [a, b] : [b, a];
      for (let i = lo; i <= hi; i += 1) setSelected(items[i], true);
      lastAnchor = el;
    }

    function rootDragIds() {
      return dragIds.filter((pid) => {
        const el = root.querySelector(`.play-dnd-item[data-play-id="${pid}"]`);
        return el && groupKey(el) === 'root';
      });
    }

    function persistOrder(group) {
      const parentId = group === 'root' ? null : Number(group.replace('parent:', ''));
      const orderedIds = itemsInGroup(group).map((el) => Number(el.dataset.playId));
      return fetch('/api/playbook/reorder', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          parent_play_id: parentId,
          ordered_ids: orderedIds,
        }),
      }).then(async (resp) => {
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error || 'Reorder failed');
        return data;
      });
    }

    function applyOrder(group, nextOrder) {
      const container = containerFor(group);
      if (!container) return;
      nextOrder.forEach((el) => container.appendChild(el));
    }

    function updateCategoryChip(row, path) {
      const chip = row.querySelector('.play-cat-chip');
      if (!chip) return;
      const parts = String(path || '')
        .replace(/_/g, ' ')
        .split('/')
        .filter(Boolean);
      if (!parts.length) {
        chip.innerHTML = '<span>uncategorized</span>';
        return;
      }
      if (parts.length === 1) {
        chip.innerHTML = `<span>${parts[0]}</span>`;
        return;
      }
      chip.innerHTML = `<span class="muted">${parts.slice(0, -1).join(' · ')}</span><span>·</span><span>${parts[parts.length - 1]}</span>`;
      chip.title = parts.join(' · ');
    }

    function moveToCategory(categoryId) {
      const playIds = rootDragIds().map(Number);
      if (!playIds.length) return Promise.resolve(null);
      return fetch('/api/playbook/move-category', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
          play_ids: playIds,
          category_id: Number(categoryId),
        }),
      }).then(async (resp) => {
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error || 'Move failed');
        (data.moved_ids || []).forEach((id) => {
          const row = root.querySelector(`.play-dnd-item[data-play-id="${id}"]`);
          if (!row) return;
          row.dataset.categoryId = String(data.category_id);
          row.dataset.categoryPath = data.category_path || '';
          updateCategoryChip(row, data.category_path || '');
        });
        if (typeof opts.onCategoryMoved === 'function') {
          opts.onCategoryMoved(data);
        }
        return data;
      });
    }

    function clearCategoryDragOver() {
      if (!treeEl) return;
      treeEl.querySelectorAll('.drag-over-category').forEach((el) => {
        el.classList.remove('drag-over-category');
      });
    }

    root.addEventListener('click', (e) => {
      const item = e.target.closest('.play-dnd-item');
      if (!item || !root.contains(item)) return;

      const action = e.target.closest('a, button, form, input, select, textarea');
      if (action && !action.classList.contains('play-dnd-handle')) {
        return;
      }

      e.preventDefault();
      if (e.shiftKey) selectRange(item);
      else if (e.metaKey || e.ctrlKey) toggle(item);
      else selectOnly(item);
    });

    root.addEventListener('dblclick', (e) => {
      if (e.target.closest('a, button, form, input, select, textarea')) return;
      const item = e.target.closest('.play-dnd-item');
      if (!item || !root.contains(item)) return;
      const href = item.dataset.viewHref;
      if (href) window.location.href = href;
    });

    root.querySelectorAll('.play-dnd-item').forEach((item) => {
      item.setAttribute('draggable', 'true');

      item.addEventListener('dragstart', (e) => {
        if (e.target.closest('.play-row-actions, button, form, input, select, textarea')) {
          e.preventDefault();
          return;
        }
        const sourceItem = e.target.closest('.play-dnd-item');
        if (sourceItem && sourceItem !== item) return;

        e.stopPropagation();
        const id = String(item.dataset.playId);
        if (!selected.has(id)) selectOnly(item);
        const group = groupKey(item);
        dragIds = itemsInGroup(group)
          .map((el) => String(el.dataset.playId))
          .filter((pid) => selected.has(pid));
        dragIds = dragIds.filter((pid) => {
          const el = root.querySelector(`.play-dnd-item[data-play-id="${pid}"]`);
          return el && groupKey(el) === group;
        });
        root.classList.add('is-dnd-active');
        document.body.classList.add('playbook-dragging-plays');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', dragIds.join(','));
        e.dataTransfer.setData('application/x-liberty-play-ids', dragIds.join(','));
        dragIds.forEach((pid) => {
          const el = root.querySelector(`.play-dnd-item[data-play-id="${pid}"]`);
          if (el) el.classList.add('is-dragging');
        });
      });

      item.addEventListener('dragend', () => {
        root.classList.remove('is-dnd-active');
        document.body.classList.remove('playbook-dragging-plays');
        root.querySelectorAll('.is-dragging, .drag-over').forEach((el) => {
          el.classList.remove('is-dragging', 'drag-over');
        });
        clearCategoryDragOver();
        dragIds = [];
      });

      item.addEventListener('dragover', (e) => {
        e.preventDefault();
        if (!dragIds.length) return;
        const group = groupKey(item);
        const first = root.querySelector(`.play-dnd-item[data-play-id="${dragIds[0]}"]`);
        if (!first || groupKey(first) !== group) return;
        e.dataTransfer.dropEffect = 'move';
        root.querySelectorAll('.drag-over').forEach((el) => el.classList.remove('drag-over'));
        item.classList.add('drag-over');
      });

      item.addEventListener('dragleave', () => {
        item.classList.remove('drag-over');
      });

      item.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        item.classList.remove('drag-over');
        const group = groupKey(item);
        if (!dragIds.length) return;
        const first = root.querySelector(`.play-dnd-item[data-play-id="${dragIds[0]}"]`);
        if (!first || groupKey(first) !== group) return;

        const items = itemsInGroup(group);
        const movingSet = new Set(dragIds);
        const targetId = String(item.dataset.playId);
        let insertAt = items.findIndex((el) => String(el.dataset.playId) === targetId);
        if (insertAt < 0) return;

        const rect = item.getBoundingClientRect();
        const before = e.clientY < rect.top + rect.height / 2;
        if (!before) insertAt += 1;

        const movedBefore = items
          .slice(0, insertAt)
          .filter((el) => movingSet.has(String(el.dataset.playId))).length;
        insertAt -= movedBefore;

        const moving = dragIds
          .map((pid) => root.querySelector(`.play-dnd-item[data-play-id="${pid}"]`))
          .filter(Boolean);
        const rest = items.filter((el) => !movingSet.has(String(el.dataset.playId)));
        const nextOrder = [...rest.slice(0, insertAt), ...moving, ...rest.slice(insertAt)];

        applyOrder(group, nextOrder);
        persistOrder(group).catch((err) => {
          alert(err.message || 'Could not save new order');
          window.location.reload();
        });
      });
    });

    // Category sidebar: drop plays onto leaf categories — reorder within list is
    // cosmetic only while the browse index is A–Z by name.
    if (treeEl && treeEl.dataset.playDropReady !== '1') {
      treeEl.dataset.playDropReady = '1';

      treeEl.addEventListener('dragover', (e) => {
        const target = e.target.closest('.playbook-tree-item[data-droppable="1"]');
        if (!target || !rootDragIds().length) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        clearCategoryDragOver();
        target.classList.add('drag-over-category');
      });

      treeEl.addEventListener('dragleave', (e) => {
        const target = e.target.closest('.playbook-tree-item');
        if (target) target.classList.remove('drag-over-category');
      });

      treeEl.addEventListener('drop', (e) => {
        const target = e.target.closest('.playbook-tree-item[data-droppable="1"]');
        if (!target) return;
        e.preventDefault();
        e.stopPropagation();
        clearCategoryDragOver();
        const categoryId = target.dataset.categoryId;
        if (!categoryId || !rootDragIds().length) return;
        moveToCategory(categoryId).catch((err) => {
          alert(err.message || 'Could not move play(s)');
        });
      });
    }
  }

  window.PlaybookDragDrop = { init: initPlaybookDragDrop };
})();
