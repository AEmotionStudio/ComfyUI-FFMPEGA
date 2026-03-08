/**
 * UndoManager — undo/redo stack for all editor operations.
 *
 * Takes snapshots of the full editor state and supports Ctrl+Z / Ctrl+Shift+Z.
 */

export interface EditorState {
    segments: number[][];
    cropRect: string;
    speedMap: Record<string, number>;
    volume: number;
    textOverlays: unknown[];
    transitions: unknown[];
}

export interface UndoManagerCallbacks {
    onRestore: (state: EditorState) => void;
}

const MAX_UNDO_DEPTH = 50;

export class UndoManager {
    private undoStack: EditorState[] = [];
    private redoStack: EditorState[] = [];
    private callbacks: UndoManagerCallbacks;
    private _keyHandler: ((e: KeyboardEvent) => void) | null = null;

    constructor(callbacks: UndoManagerCallbacks) {
        this.callbacks = callbacks;

        this._keyHandler = (e: KeyboardEvent) => {
            if (
                e.target instanceof HTMLInputElement ||
                e.target instanceof HTMLTextAreaElement
            ) {
                return;
            }

            if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
                e.preventDefault();
                if (e.shiftKey) {
                    this.redo();
                } else {
                    this.undo();
                }
            }
        };
        document.addEventListener('keydown', this._keyHandler);
    }

    /** Save the current state to the undo stack. */
    push(state: EditorState): void {
        this.undoStack.push(JSON.parse(JSON.stringify(state)));
        if (this.undoStack.length > MAX_UNDO_DEPTH) {
            this.undoStack.shift();
        }
        // Any new action clears the redo stack
        this.redoStack = [];
    }

    /** Undo: pop from undo stack, push current to redo. */
    undo(): boolean {
        if (this.undoStack.length < 2) return false;

        const current = this.undoStack.pop()!;
        this.redoStack.push(current);

        const prev = this.undoStack[this.undoStack.length - 1];
        this.callbacks.onRestore(JSON.parse(JSON.stringify(prev)));
        return true;
    }

    /** Redo: pop from redo stack, push to undo. */
    redo(): boolean {
        if (this.redoStack.length === 0) return false;

        const state = this.redoStack.pop()!;
        this.undoStack.push(state);
        this.callbacks.onRestore(JSON.parse(JSON.stringify(state)));
        return true;
    }

    /** Clear all history. */
    clear(): void {
        this.undoStack = [];
        this.redoStack = [];
    }

    get canUndo(): boolean {
        return this.undoStack.length > 1;
    }

    get canRedo(): boolean {
        return this.redoStack.length > 0;
    }

    destroy(): void {
        if (this._keyHandler) {
            document.removeEventListener('keydown', this._keyHandler);
            this._keyHandler = null;
        }
    }
}
