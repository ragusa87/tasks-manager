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
import { Decoration, DecorationSet } from '@milkdown/kit/prose/view';
import {
    AUTOLINK_RE,
    convertedListItemAttrs,
    isUrlLike,
    resolveLinkEdit,
} from './markdown-editor-utils.js';
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

// Renders the textarea's placeholder while the document is empty (styled by
// `p.is-empty::before` in main.css); enhancing the textarea would otherwise
// silently drop its placeholder.
const placeholderPlugin = (text) =>
    $prose(
        () =>
            new Plugin({
                key: new PluginKey('MARKDOWN_EDITOR_PLACEHOLDER'),
                props: {
                    decorations(state) {
                        const { doc } = state;
                        const empty =
                            doc.childCount === 1 &&
                            doc.firstChild.isTextblock &&
                            doc.firstChild.content.size === 0;
                        if (!empty) return null;
                        return DecorationSet.create(doc, [
                            Decoration.node(0, doc.firstChild.nodeSize, {
                                class: 'is-empty',
                                'data-placeholder': text,
                            }),
                        ]);
                    },
                },
            })
    );

// Toolbar behavior, keyed by the buttons' data-action in the server-rendered
// chrome (templates/partials/item_form_detail.html) — the markup, labels and
// icons live there. Active state comes from a `mark` (inline) or a `node`
// (block) name in the schema.
const ACTIONS = {
    bold: { mark: 'strong', command: toggleStrongCommand },
    italic: { mark: 'emphasis', command: toggleEmphasisCommand },
    strikethrough: { mark: 'strike_through', command: toggleStrikethroughCommand },
    link: { mark: 'link', isLink: true },
    bulletList: { node: 'bullet_list', command: wrapInBulletListCommand },
    orderedList: { node: 'ordered_list', command: wrapInOrderedListCommand },
};

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
            this._chromeTemplate = this.querySelector('template[data-editor-chrome]');
            // Without the server-rendered chrome there is nothing to enhance;
            // the plain textarea keeps working as-is.
            if (!this.textarea || !this._chromeTemplate) return;
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
            // Drop the cloned chrome and reveal the textarea again, so a
            // re-connect re-enhances cleanly from the (kept) template.
            if (this._wrapper) {
                this._wrapper.remove();
                this._wrapper = null;
            }
            this.textarea?.classList.remove('hidden');
            this._initialized = false;
        }

        _syncTextareaNow() {
            if (!this._editor) return;
            this.textarea.value = this._editor.action(getMarkdown());
        }

        _render() {
            // The chrome (wrapper, toolbar buttons, upload indicator, host)
            // is display markup and comes server-rendered from the template;
            // this only clones it and wires behavior onto data-action. The
            // template itself stays in place so a disconnect/re-connect
            // cycle (HTMX moving nodes) can enhance again.
            const wrapper = this._chromeTemplate.content.firstElementChild.cloneNode(true);
            this._wrapper = wrapper;

            const toolbar = wrapper.querySelector('[role="toolbar"]');
            wrapper.querySelectorAll('button[data-action]').forEach((btn, index) => {
                const action = ACTIONS[btn.dataset.action];
                if (!action) return;
                btn.tabIndex = index === 0 ? 0 : -1; // roving tabindex
                btn.addEventListener('mousedown', (e) => e.preventDefault()); // keep selection
                btn.addEventListener('click', () => this._runAction(action));
                this._buttons.set(btn.dataset.action, btn);
            });

            // Toolbar keyboard pattern: one Tab stop, arrows move between buttons.
            toolbar.addEventListener('keydown', (e) => {
                const delta = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
                if (!delta) return;
                e.preventDefault();
                const buttons = [...this._buttons.values()];
                const current = buttons.indexOf(document.activeElement);
                const next = buttons[(current + delta + buttons.length) % buttons.length];
                buttons.forEach((b) => { b.tabIndex = b === next ? 0 : -1; });
                next.focus();
            });

            // Loader shown while a pasted attachment uploads (see
            // _interceptFilePaste); documents.js hides it via detail.done().
            this._uploadIndicator = wrapper.querySelector('[data-upload-indicator]');
            this._host = wrapper.querySelector('.markdown-host');

            // Keep the textarea in the form but hide it; insert the editor next to it.
            this.textarea.classList.add('hidden');
            this.insertBefore(wrapper, this.textarea);
        }

        async _createEditor(initialValue) {
            const onSelectionChange = () => this._syncToolbar();
            const builder = Editor.make()
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
                .use(linkTextSyncPlugin);
            if (this.textarea.placeholder) {
                builder.use(placeholderPlugin(this.textarea.placeholder));
            }
            this._editor = await builder.create();
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
                    // Switch list type by rebuilding the list and its items
                    // with the target type's attrs (see convertedListItemAttrs
                    // for why attrs are never copied verbatim).
                    const isOrdered = target === ordered;
                    const items = [];
                    node.content.forEach((item, _offset, index) => {
                        items.push(
                            item.type.create(
                                convertedListItemAttrs(item.attrs, isOrdered, index),
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
                this._buttons.forEach((btn, name) => {
                    const action = ACTIONS[name];
                    const on = action.node
                        ? isNodeActive(state, schema.nodes[action.node])
                        : isMarkActive(state, schema.marks[action.mark]);
                    btn.classList.toggle('bg-accent/15', on);
                    btn.classList.toggle('text-accent', on);
                    btn.setAttribute('aria-pressed', String(on));
                });
            });
        }
    }

    if (!customElements.get('markdown-editor')) {
        customElements.define('markdown-editor', MarkdownEditorElement);
    }
}
