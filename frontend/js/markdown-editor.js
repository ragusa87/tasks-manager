// Reusable <markdown-editor> custom element: a minimal Milkdown WYSIWYG editor
// for the Item description.
//
// Usage (light DOM so surrounding Tailwind styles apply and the wrapped
// <textarea> keeps participating in the enclosing <form>):
//
//   <markdown-editor>
//     <textarea name="description" id="id_description">**hello**</textarea>
//   </markdown-editor>
//
// It progressively enhances the child <textarea>: the textarea stays the real
// form control (so it still works with JS disabled and submits exactly as
// before), but is visually hidden and kept in sync with the editor's Markdown
// on every edit. The custom toolbar offers a deliberately small set -- bold,
// italic, strikethrough, links and bullet/ordered lists -- matching what the
// server sanitizer keeps. Other blocks (headings, tables, code, ...) are stripped
// server-side on save. Being a custom element, it auto-upgrades whenever HTMX
// swaps the modal in -- no manual init needed.

import {
    Editor,
    defaultValueCtx,
    editorStateCtx,
    editorViewCtx,
    editorViewOptionsCtx,
    rootCtx,
    schemaCtx,
} from '@milkdown/kit/core';
import {
    commonmark,
    liftListItemCommand,
    linkSchema,
    sanitizeLinkHref,
    toggleEmphasisCommand,
    toggleStrongCommand,
    wrapInBulletListCommand,
    wrapInOrderedListCommand,
} from '@milkdown/kit/preset/commonmark';
import { gfm, toggleStrikethroughCommand } from '@milkdown/kit/preset/gfm';
import { listener, listenerCtx } from '@milkdown/kit/plugin/listener';
import { $inputRule, $prose, callCommand, getMarkdown } from '@milkdown/kit/utils';
import { InputRule } from '@milkdown/kit/prose/inputrules';
import { Plugin, PluginKey, TextSelection } from '@milkdown/kit/prose/state';
import { Fragment } from '@milkdown/kit/prose/model';
import { getMarkRange } from '@milkdown/kit/prose';
import { AUTOLINK_RE, isUrlLike, resolveLinkEdit } from './markdown-editor-utils.js';
import '@milkdown/kit/prose/view/style/prosemirror.css';

// Turn a bare URL into a link as soon as the user types a whitespace after it,
// so typing "https://example.com " renders as a link (stored as <...>). Bare
// URLs already loaded from storage are autolinked by remarkGFM on parse; this
// rule covers live typing, which Milkdown does not handle out of the box.
const autolinkInputRule = $inputRule(
    (ctx) =>
        new InputRule(AUTOLINK_RE, (state, match, start, end) => {
            const [, url, trigger] = match;
            const href = sanitizeLinkHref(url);
            if (!href) return null;
            const linkType = linkSchema.type(ctx);
            // Don't re-link a URL that is already (partly) a link.
            if (state.doc.rangeHasMark(start, end, linkType)) return null;
            const tr = state.tr;
            tr.addMark(start, end, linkType.create({ href }));
            tr.insertText(trigger, end);
            tr.removeMark(end, end + trigger.length, linkType);
            return tr.removeStoredMark(linkType);
        })
);

// Keep a link's href in sync with its visible text -- but only when that text
// IS a URL. Typing inside "https://example.com" re-derives the href from the
// text on the next transaction, so what you see is always what you click.
// Label-style links ([docs](https://...)) are standard markdown and left alone:
// editing the label never touches the href. Runs only on doc changes, so
// links loaded from storage are untouched until edited, and it converges in
// one pass (the derived href equals the text, which is already URL-like).
const linkTextSyncPlugin = $prose((ctx) => {
    const linkType = linkSchema.type(ctx);
    return new Plugin({
        key: new PluginKey('MARKDOWN_EDITOR_LINK_SYNC'),
        appendTransaction(transactions, _oldState, newState) {
            if (!transactions.some((tr) => tr.docChanged)) return null;

            const updates = [];
            newState.doc.descendants((node, pos) => {
                if (!node.isTextblock) return true;
                let start = null;
                let text = '';
                let href = null;
                const flush = (endPos) => {
                    if (start == null) return;
                    if (isUrlLike(text)) {
                        const desired = sanitizeLinkHref(text.trim()) || text.trim();
                        if (desired && href !== desired) {
                            updates.push({ from: start, to: endPos, href: desired });
                        }
                    }
                    start = null;
                    text = '';
                    href = null;
                };
                node.forEach((child, offset) => {
                    const childPos = pos + 1 + offset;
                    const mark = child.isText && child.marks.find((m) => m.type === linkType);
                    if (mark) {
                        if (start == null) {
                            start = childPos;
                            href = mark.attrs.href;
                        }
                        text += child.text;
                    } else {
                        flush(childPos);
                    }
                });
                flush(pos + 1 + node.content.size);
                return false;
            });

            if (!updates.length) return null;
            const tr = newState.tr;
            updates.forEach(({ from, to, href }) => {
                tr.removeMark(from, to, linkType);
                tr.addMark(from, to, linkType.create({ href }));
            });
            return tr.docChanged ? tr : null;
        },
    });
});

// lucide icons (inlined so the element is self-contained in the JS bundle).
const ICONS = {
    bold: '<path d="M6 12h9a4 4 0 0 1 0 8H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h7a4 4 0 0 1 0 8"/>',
    italic: '<line x1="19" x2="10" y1="4" y2="4"/><line x1="14" x2="5" y1="20" y2="20"/><line x1="15" x2="9" y1="4" y2="20"/>',
    strikethrough:
        '<path d="M16 4H9a3 3 0 0 0-2.83 4"/><path d="M14 12a4 4 0 0 1 0 8H6"/><line x1="4" x2="20" y1="12" y2="12"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    'loader-circle': '<path d="M21 12a9 9 0 1 1-6.219-8.56"/>',
    list: '<line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/>',
    'list-ordered':
        '<line x1="10" x2="21" y1="6" y2="6"/><line x1="10" x2="21" y1="12" y2="12"/><line x1="10" x2="21" y1="18" y2="18"/><path d="M4 6h1v4"/><path d="M4 10h2"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/>',
};

const svg = (name) =>
    `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;

// Toolbar actions. Active state comes from a `mark` (inline) or a `node`
// (block) name in the schema; a `divider` entry renders a separator.
const ACTIONS = [
    { name: 'bold', icon: 'bold', title: 'Bold (Ctrl+B)', mark: 'strong', command: toggleStrongCommand },
    { name: 'italic', icon: 'italic', title: 'Italic (Ctrl+I)', mark: 'emphasis', command: toggleEmphasisCommand },
    {
        name: 'strikethrough',
        icon: 'strikethrough',
        title: 'Strikethrough',
        mark: 'strike_through',
        command: toggleStrikethroughCommand,
    },
    { name: 'link', icon: 'link', title: 'Link', mark: 'link', isLink: true },
    { divider: true },
    {
        name: 'bulletList',
        icon: 'list',
        title: 'Bullet list',
        node: 'bullet_list',
        command: wrapInBulletListCommand,
    },
    {
        name: 'orderedList',
        icon: 'list-ordered',
        title: 'Numbered list',
        node: 'ordered_list',
        command: wrapInOrderedListCommand,
    },
];

/** Whether a mark type is active in the current selection. */
function isMarkActive(state, type) {
    if (!type) return false;
    const { from, $from, to, empty } = state.selection;
    if (empty) {
        return Boolean(type.isInSet(state.storedMarks || $from.marks()));
    }
    return state.doc.rangeHasMark(from, to, type);
}

/** Whether the selection is inside a node of the given type (e.g. a list). */
function isNodeActive(state, type) {
    if (!type) return false;
    const { $from } = state.selection;
    for (let depth = $from.depth; depth > 0; depth--) {
        if ($from.node(depth).type === type) return true;
    }
    return false;
}

if (typeof HTMLElement !== 'undefined' && typeof customElements !== 'undefined') {
    class MarkdownEditorElement extends HTMLElement {
        connectedCallback() {
            if (this._initialized) return;
            this.textarea = this.querySelector('textarea');
            if (!this.textarea) return; // nothing to enhance
            this._initialized = true;
            this._buttons = new Map();
            this._render();
            this._createEditor(this.textarea.value || '');

            // The markdownUpdated listener is debounced, so a fast save right
            // after typing could submit a stale value. Pull the markdown
            // synchronously when the enclosing form submits (capture phase so
            // it runs before HTMX serializes the form).
            this._form = this.closest('form');
            this._onSubmit = () => this._syncTextareaNow();
            this._form?.addEventListener('submit', this._onSubmit, true);
        }

        disconnectedCallback() {
            this._form?.removeEventListener('submit', this._onSubmit, true);
            this._form = null;
            // Modal is swapped out by HTMX -- release the ProseMirror view.
            if (this._editor) {
                this._editor.destroy();
                this._editor = null;
            }
            this._initialized = false;
        }

        _syncTextareaNow() {
            if (!this._editor) return;
            this.textarea.value = this._editor.action(getMarkdown());
        }

        _render() {
            const wrapper = document.createElement('div');
            wrapper.className =
                'markdown-editor border border-line rounded-md shadow-sm focus-within:ring-1 focus-within:ring-accent focus-within:border-accent overflow-hidden bg-surface';

            const toolbar = document.createElement('div');
            toolbar.className =
                'markdown-toolbar flex items-center gap-1 px-2 py-1 border-b border-line bg-ground';

            ACTIONS.forEach((action) => {
                if (action.divider) {
                    const sep = document.createElement('span');
                    sep.className = 'w-px h-5 bg-line mx-1';
                    toolbar.appendChild(sep);
                    return;
                }
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.title = action.title;
                btn.className =
                    'markdown-btn p-1.5 rounded text-muted hover:bg-line hover:text-body transition-colors';
                btn.innerHTML = svg(action.icon);
                btn.addEventListener('mousedown', (e) => e.preventDefault()); // keep selection
                btn.addEventListener('click', () => this._runAction(action));
                toolbar.appendChild(btn);
                this._buttons.set(action.name, btn);
            });

            // Loader shown while a pasted attachment uploads (see
            // _interceptFilePaste); documents.js hides it via detail.done().
            this._uploadIndicator = document.createElement('span');
            this._uploadIndicator.className =
                'hidden items-center gap-1.5 ml-auto text-xs text-muted';
            this._uploadIndicator.innerHTML = `${svg('loader-circle').replace(
                '<svg ',
                '<svg class="animate-spin" '
            )}Uploading attachment\u2026`;
            toolbar.appendChild(this._uploadIndicator);

            this._host = document.createElement('div');
            this._host.className = 'markdown-host';

            wrapper.appendChild(toolbar);
            wrapper.appendChild(this._host);

            // Keep the textarea in the form but hide it; insert the editor next to it.
            this.textarea.classList.add('hidden');
            this.insertBefore(wrapper, this.textarea);
        }

        async _createEditor(initialValue) {
            const onSelectionChange = () => this._syncToolbar();
            this._editor = await Editor.make()
                .config((ctx) => {
                    ctx.set(rootCtx, this._host);
                    ctx.set(defaultValueCtx, initialValue);
                    ctx.update(editorViewOptionsCtx, (prev) => ({
                        ...prev,
                        attributes: {
                            class: 'markdown-prose',
                            spellcheck: 'true',
                        },
                        handlePaste: (_view, event) => this._interceptFilePaste(event),
                    }));
                    ctx.get(listenerCtx)
                        .markdownUpdated((_, markdown) => {
                            this.textarea.value = markdown;
                        })
                        .selectionUpdated(onSelectionChange)
                        .focus(onSelectionChange);
                })
                .use(commonmark)
                .use(gfm)
                .use(listener)
                .use(autolinkInputRule)
                .use(linkTextSyncPlugin)
                .create();
            this._syncToolbar();
        }

        _runAction(action) {
            if (!this._editor) return;

            if (action.isLink) {
                this._runLink();
            } else if (action.node) {
                this._toggleList(action.node);
            } else {
                this._editor.action(callCommand(action.command.key));
            }
            this._focusEditor();
            this._syncToolbar();
        }

        _focusEditor() {
            this._editor?.action((ctx) => ctx.get(editorViewCtx).focus());
        }

        /** Pasted files don't belong in the markdown (the sanitizer would drop
         *  them anyway) -- offer them to the page as attachments instead. Emits
         *  a cancelable event; if a listener claims it (documents.js routes the
         *  files through the dropzone upload), the paste is swallowed and a
         *  loader shows until the listener calls detail.done(). With no
         *  listener (e.g. unsaved item, no upload target) the default paste
         *  proceeds. */
        _interceptFilePaste(event) {
            const files = Array.from(event.clipboardData?.files || []);
            if (!files.length) return false;

            const claimed = !this.dispatchEvent(
                new CustomEvent('markdown-editor:attach', {
                    detail: { files, done: () => this._setUploading(false) },
                    bubbles: true,
                    cancelable: true,
                })
            );
            if (!claimed) return false;

            event.preventDefault();
            this._setUploading(true);
            return true;
        }

        _setUploading(on) {
            this._uploadIndicator.classList.toggle('hidden', !on);
            this._uploadIndicator.classList.toggle('flex', on);
        }

        /** The link mark (with range) covering the cursor, or null. */
        _activeLink() {
            let result = null;
            this._editor?.action((ctx) => {
                const state = ctx.get(editorStateCtx);
                const linkType = ctx.get(schemaCtx).marks.link;
                const range = getMarkRange(state.selection.$from, linkType);
                if (range) {
                    result = { href: range.mark.attrs.href, from: range.from, to: range.to };
                }
            });
            return result;
        }

        /** Add / edit / remove a link. Prefills the prompt with the current URL
         *  when the cursor is already on a link. Follows the policy in
         *  markdown-editor-utils.js: URL-shaped text tracks the href (what you
         *  see is what you click), label text ([docs](url)) keeps its label and
         *  only the href changes. Clearing the field unlinks, keeping the text. */
        _runLink() {
            const link = this._activeLink();
            const input = window.prompt('Link URL', link ? link.href : '');
            if (input === null) return; // cancelled
            const raw = input.trim();
            const href = raw ? sanitizeLinkHref(raw) : '';

            this._editor.action((ctx) => {
                const view = ctx.get(editorViewCtx);
                const { state } = view;
                const linkType = ctx.get(schemaCtx).marks.link;
                const tr = state.tr;

                // The range to (re)write: the whole existing link, else the
                // selection clamped to inline positions (Ctrl+A yields an
                // AllSelection whose endpoints sit on block boundaries; using
                // them raw would link one char short).
                let { from, to } = link ?? {};
                if (!link) {
                    const sel = TextSelection.between(
                        state.selection.$from,
                        state.selection.$to
                    );
                    from = sel.from;
                    to = sel.to;
                }

                if (!href) {
                    // Clearing the URL: unlink but keep the text.
                    if (link) view.dispatch(tr.removeMark(from, to, linkType));
                    return;
                }

                const currentText = state.doc.textBetween(from, to);
                const { text } = resolveLinkEdit(currentText, link ? link.href : '', href);

                if (text !== currentText) tr.insertText(text, from, to);
                const end = from + text.length;
                tr.removeMark(from, end, linkType);
                tr.addMark(from, end, linkType.create({ href }));
                tr.removeStoredMark(linkType);
                view.dispatch(tr);
            });
        }

        /** Wrap the selection in a list, convert between list types, or (when
         *  already the target type) lift the items back out. */
        _toggleList(nodeName) {
            const handled = this._editor.action((ctx) => {
                const view = ctx.get(editorViewCtx);
                const schema = ctx.get(schemaCtx);
                const target = schema.nodes[nodeName];
                const bullet = schema.nodes.bullet_list;
                const ordered = schema.nodes.ordered_list;
                const { state } = view;
                const { $from } = state.selection;

                for (let depth = $from.depth; depth > 0; depth--) {
                    const node = $from.node(depth);
                    if (node.type !== bullet && node.type !== ordered) continue;
                    if (node.type === target) return false; // toggle off below
                    // Switch list type by rebuilding the list and its items with
                    // the target type's attrs. Never copy attrs verbatim:
                    // Milkdown's markdown parser stamps `spread` as a *string*
                    // ("true"/"false") while the schema validates a boolean, so
                    // recreating nodes from copied attrs throws -- which is what
                    // silently broke ordered->bullet. Coerce and set explicitly.
                    const isOrdered = target === ordered;
                    const items = [];
                    node.content.forEach((item, _offset, index) => {
                        items.push(
                            item.type.create(
                                {
                                    spread:
                                        item.attrs.spread === true ||
                                        item.attrs.spread === 'true',
                                    listType: isOrdered ? 'ordered' : 'bullet',
                                    label: isOrdered ? `${index + 1}.` : '\u2022',
                                },
                                item.content,
                                item.marks
                            )
                        );
                    });
                    const newList = target.createChecked(null, Fragment.from(items));
                    const before = $from.before(depth);
                    const after = $from.after(depth);
                    view.dispatch(state.tr.replaceWith(before, after, newList));
                    return true;
                }
                return null; // not in a list
            });

            if (handled === null) {
                const cmd =
                    nodeName === 'bullet_list' ? wrapInBulletListCommand : wrapInOrderedListCommand;
                this._editor.action(callCommand(cmd.key));
            } else if (handled === false) {
                this._editor.action(callCommand(liftListItemCommand.key));
            }
        }

        /** Reflect active marks on the toolbar buttons. */
        _syncToolbar() {
            if (!this._editor) return;
            this._editor.action((ctx) => {
                const state = ctx.get(editorStateCtx);
                const schema = ctx.get(schemaCtx);
                ACTIONS.forEach((action) => {
                    const btn = this._buttons.get(action.name);
                    if (!btn) return;
                    const on = action.node
                        ? isNodeActive(state, schema.nodes[action.node])
                        : isMarkActive(state, schema.marks[action.mark]);
                    btn.classList.toggle('bg-accent/15', on);
                    btn.classList.toggle('text-accent', on);
                });
            });
        }
    }

    if (!customElements.get('markdown-editor')) {
        customElements.define('markdown-editor', MarkdownEditorElement);
    }
}
