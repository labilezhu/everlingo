import { $prose } from '@milkdown/kit/utils';
import { Plugin, PluginKey } from '@milkdown/prose/state';
import { Decoration, DecorationSet } from '@milkdown/prose/view';

const ghostSelectionKey = new PluginKey('ghost-selection');

const ghostSelectionPlugin = $prose(() =>
  new Plugin({
    key: ghostSelectionKey,
    state: {
      init: () => ({ focused: false }),
      apply(tr, prev) {
        const meta = tr.getMeta(ghostSelectionKey);
        return meta !== undefined ? { focused: meta } : prev;
      },
    },
    props: {
      handleDOMEvents: {
        focus: (view) => {
          view.dispatch(view.state.tr.setMeta(ghostSelectionKey, true));
          return false;
        },
        blur: (view) => {
          view.dispatch(view.state.tr.setMeta(ghostSelectionKey, false));
          return false;
        },
      },
      decorations(state) {
        const pluginState = ghostSelectionKey.getState(state);
        if (!pluginState || pluginState.focused) return null;
        const { selection, doc } = state;
        if (selection.empty) return null;
        if (!selection.$from.parent.isTextblock) return null;
        const deco = Decoration.inline(selection.from, selection.to, {
          class: 'pm-ghost-selection',
        });
        return DecorationSet.create(doc, [deco]);
      },
    },
  }),
);

export { ghostSelectionPlugin };
