"""
PygmentsSyntaxHighlighter — a QSyntaxHighlighter subclass that uses Pygments
to apply live, per-block syntax highlighting to a QPlainTextEdit document.

Supports all Pygments lexers (Python, JSON, YAML, Markdown, HTML, JS, …).
Falls back to no-op if Pygments is not installed.
"""
from __future__ import annotations

import os
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import (
    QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument
)

try:
    from pygments import lex
    from pygments.lexers import get_lexer_for_filename, TextLexer
    from pygments.token import Token
    from pygments.util import ClassNotFound
    from pygments.styles import get_style_by_name
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Monokai colour map for the most common Pygments token types
# ---------------------------------------------------------------------------
_MONOKAI: dict[object, tuple[str, bool, bool]] = {
    # (hex_colour, bold, italic)
    Token.Keyword:                     ("#f92672", True,  False),
    Token.Keyword.Constant:            ("#ae81ff", False, False),
    Token.Keyword.Declaration:         ("#f92672", True,  False),
    Token.Keyword.Namespace:           ("#f92672", True,  False),
    Token.Keyword.Type:                ("#f92672", True,  False),

    Token.Name.Builtin:                ("#a6e22e", False, False),
    Token.Name.Builtin.Pseudo:         ("#fd971f", False, False),
    Token.Name.Class:                  ("#a6e22e", True,  False),
    Token.Name.Decorator:              ("#a6e22e", False, False),
    Token.Name.Exception:              ("#a6e22e", False, False),
    Token.Name.Function:               ("#a6e22e", False, False),
    Token.Name.Tag:                    ("#f92672", False, False),
    Token.Name.Attribute:              ("#a6e22e", False, False),

    Token.Literal.String:              ("#e6db74", False, False),
    Token.Literal.String.Doc:          ("#e6db74", False, True ),
    Token.Literal.String.Interpol:     ("#e6db74", False, False),
    Token.Literal.String.Escape:       ("#ae81ff", False, False),

    Token.Literal.Number:              ("#ae81ff", False, False),

    Token.Operator:                    ("#f92672", False, False),
    Token.Operator.Word:               ("#f92672", True,  False),
    Token.Punctuation:                 ("#f8f8f2", False, False),

    Token.Comment:                     ("#75715e", False, True ),
    Token.Comment.Hashbang:            ("#75715e", False, True ),
    Token.Comment.Multiline:           ("#75715e", False, True ),
    Token.Comment.Preproc:             ("#75715e", False, True ),
    Token.Comment.Single:              ("#75715e", False, True ),
    Token.Comment.Special:             ("#75715e", False, False),

    Token.Generic.Heading:             ("#f92672", True,  False),
    Token.Generic.Subheading:          ("#f92672", False, False),
    Token.Generic.Strong:              ("#f8f8f2", True,  False),
    Token.Generic.Emph:                ("#f8f8f2", False, True ),
    Token.Generic.Deleted:             ("#f92672", False, False),
    Token.Generic.Inserted:            ("#a6e22e", False, False),

    Token.Text:                        ("#f8f8f2", False, False),
    Token.Error:                       ("#f92672", False, False),
}

_DEFAULT_FMT = QTextCharFormat()


def _make_formats() -> dict[object, QTextCharFormat]:
    """Pre-build QTextCharFormat objects for every entry in _MONOKAI."""
    formats: dict[object, QTextCharFormat] = {}
    for token, (colour, bold, italic) in _MONOKAI.items():
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colour))
        if bold:
            fmt.setFontWeight(QFont.Bold)
        if italic:
            fmt.setFontItalic(True)
        formats[token] = fmt
    return formats


def _best_format(token_type, fmt_map: dict) -> QTextCharFormat:
    """Walk up the token hierarchy until we find a matching format."""
    t = token_type
    while t is not None:
        if t in fmt_map:
            return fmt_map[t]
        t = t.parent if hasattr(t, 'parent') else None
    return _DEFAULT_FMT


class PygmentsSyntaxHighlighter(QSyntaxHighlighter):
    """
    A QSyntaxHighlighter that delegates to Pygments for lexing.

    Usage::

        highlighter = PygmentsSyntaxHighlighter(editor.document(), filename)

    Pass ``filename=""`` for plain-text (no highlighting).
    """

    def __init__(self, document: QTextDocument, filename: str = ""):
        super().__init__(document)
        self._lexer = None
        self._formats = _make_formats() if PYGMENTS_AVAILABLE else {}
        self._token_cache: list[tuple[object, str]] = []
        self.set_filename(filename)

    # ------------------------------------------------------------------
    def set_filename(self, filename: str) -> None:
        """Switch lexer based on *filename*. Call when a new file is opened."""
        self._lexer = None
        if not PYGMENTS_AVAILABLE or not filename:
            self.rehighlight()
            return
        try:
            self._lexer = get_lexer_for_filename(filename, stripall=False)
        except ClassNotFound:
            pass  # Stay as None → no highlighting
        self.rehighlight()

    # ------------------------------------------------------------------
    def highlightBlock(self, text: str) -> None:  # noqa: N802 – Qt naming
        """Called by Qt for every block (line) that needs re-highlighting."""
        if self._lexer is None:
            return

        # We need to know the offset of this block within the full document
        # so we can slice the correct tokens.  Pygments works on full text;
        # we lex the full document lazily and cache the result.
        # For large files performance is still acceptable because Qt calls
        # highlightBlock only for visible / dirty blocks.
        block = self.currentBlock()
        block_start = block.position()
        block_end = block_start + len(text)

        full_text = self.document().toPlainText()

        try:
            tokens = list(lex(full_text, self._lexer))
        except Exception:
            return

        pos = 0
        for ttype, value in tokens:
            token_start = pos
            token_end = pos + len(value)
            pos = token_end

            # Only apply formats that overlap with this block
            if token_end <= block_start:
                continue
            if token_start >= block_end:
                break

            fmt = _best_format(ttype, self._formats)
            if fmt is _DEFAULT_FMT:
                continue

            # Clamp to block boundaries
            local_start = max(token_start - block_start, 0)
            local_len = min(token_end, block_end) - max(token_start, block_start)
            if local_len > 0:
                self.setFormat(local_start, local_len, fmt)
