"""The two ways the pet talks back to you when a bubble isn't enough.

`CommandBar` — you tell it what you want.
`Picker`     — it doesn't know, so it asks. This is the never-guess rule made
               visible: the pet would rather interrupt you once than guess
               wrong silently.

Both are frameless and dark, to match the speech bubble rather than look like
a stray Windows dialog.
"""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QVBoxLayout)

import config

SHEET = """
QDialog { background: #1E1714; border: 1px solid #52413A; border-radius: 12px; }
QLabel { color: #E8DCD4; font-size: 12px; }
QLabel#hint { color: #8C7A70; font-size: 11px; }
QLineEdit {
    background: #2C221D; color: #FBF3EE; border: 1px solid #5E4A40;
    border-radius: 8px; padding: 8px 10px; font-size: 14px;
}
QLineEdit:focus { border: 1px solid #D97757; }
QListWidget {
    background: #2C221D; color: #FBF3EE; border: 1px solid #4A3A33;
    border-radius: 8px; outline: none; font-size: 13px;
}
QListWidget::item { padding: 6px 8px; border-radius: 5px; }
QListWidget::item:selected { background: #D97757; color: #1E1714; }
QCheckBox { color: #B9A99F; font-size: 11px; }
QPushButton {
    background: #3A2D27; color: #F0E6E0; border: 1px solid #5E4A40;
    border-radius: 7px; padding: 6px 14px; font-size: 12px;
}
QPushButton:hover { background: #4A3A32; }
QPushButton#primary { background: #D97757; color: #241812; border: none; font-weight: 600; }
QPushButton#primary:hover { background: #E88A6B; }
"""


class _Frameless(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.Dialog
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(SHEET)
        self.setModal(True)

    def place_above(self, anchor: QPoint) -> None:
        """Sit just above the pet, nudged back on-screen if it would overflow."""
        self.adjustSize()
        screen = self.screen().availableGeometry()
        x = anchor.x() - self.width() // 2
        y = anchor.y() - self.height() - 12
        x = max(screen.left() + 8, min(screen.right() - self.width() - 8, x))
        y = max(screen.top() + 8, y)
        self.move(x, y)


class CommandBar(_Frameless):
    """Single line: 'open brave'."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        lay.addWidget(QLabel(f"What do you need, boss?"))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("open brave")
        self.edit.setMinimumWidth(400)
        self.edit.returnPressed.connect(self.accept)
        lay.addWidget(self.edit)

        hint = QLabel("open <app>  ·  fill <form>  ·  teach <form> <url>"
                      "\nEsc to cancel.")
        hint.setObjectName("hint")
        lay.addWidget(hint)

    @staticmethod
    def ask(anchor: QPoint, parent=None) -> str | None:
        dlg = CommandBar(parent)
        dlg.place_above(anchor)
        dlg.edit.setFocus()
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.edit.text().strip() or None
        return None


class Confirm(_Frameless):
    """'I think you meant this — shall I?'

    Shown for anything the *model* interpreted rather than the plain parser.
    The model will invent a task from a sentence that wasn't a request, so it
    never gets to act on its own conclusion.
    """

    def __init__(self, heard: str, proposal: str, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)

        said = QLabel(f"You said: “{heard}”")
        said.setObjectName("hint")
        said.setWordWrap(True)
        said.setMaximumWidth(380)
        lay.addWidget(said)

        prop = QLabel(proposal)
        prop.setWordWrap(True)
        prop.setMaximumWidth(380)
        prop.setStyleSheet("font-size: 15px; padding: 6px 0 2px;")
        lay.addWidget(prop)

        why = QLabel("I worked this out rather than being told it, so I'll ask first.")
        why.setObjectName("hint")
        why.setWordWrap(True)
        why.setMaximumWidth(380)
        lay.addWidget(why)

        row = QHBoxLayout()
        row.addStretch(1)
        no = QPushButton("No")
        no.clicked.connect(self.reject)
        row.addWidget(no)
        yes = QPushButton("Do it")
        yes.setObjectName("primary")
        yes.setDefault(True)
        yes.clicked.connect(self.accept)
        row.addWidget(yes)
        lay.addLayout(row)

    @staticmethod
    def ask(heard: str, proposal: str, anchor: QPoint, parent=None) -> bool:
        dlg = Confirm(heard, proposal, parent)
        dlg.place_above(anchor)
        return dlg.exec() == QDialog.DialogCode.Accepted


class Waiting(_Frameless):
    """Up while YOU fill the form in Brave.

    The pet has deliberately stepped back here — this is the teaching session,
    and the whole point is that it watches rather than attempts.
    """

    def __init__(self, name: str, questions, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        head = QLabel(f"Fill in “{name}” in Brave — I'm watching.")
        head.setStyleSheet("font-size: 15px;")
        head.setWordWrap(True)
        head.setMaximumWidth(400)
        lay.addWidget(head)

        listing = QListWidget()
        listing.setMinimumWidth(400)
        listing.setMaximumHeight(200)
        for q in questions:
            listing.addItem(QListWidgetItem(str(q)))
        listing.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        lay.addWidget(listing)

        hint = QLabel("Don't submit it. Click below when the answers are in, "
                      "and I'll remember them for next time.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        hint.setMaximumWidth(400)
        lay.addWidget(hint)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Forget it")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = QPushButton("I've filled it in")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        lay.addLayout(row)

    @staticmethod
    def show_for(name: str, questions, anchor: QPoint, parent=None) -> bool:
        dlg = Waiting(name, questions, parent)
        dlg.place_above(anchor)
        return dlg.exec() == QDialog.DialogCode.Accepted


class Approval(_Frameless):
    """The last gate before something irreversible happens."""

    def __init__(self, name: str, filled: list, skipped: list, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        head = QLabel(f"“{name}” is filled in. Submit it?")
        head.setStyleSheet("font-size: 15px;")
        head.setWordWrap(True)
        head.setMaximumWidth(400)
        lay.addWidget(head)

        listing = QListWidget()
        listing.setMinimumWidth(400)
        listing.setMaximumHeight(200)
        for t in filled:
            listing.addItem(QListWidgetItem(f"✓  {t}"))
        for s in skipped:
            item = QListWidgetItem(f"!  {s}")
            item.setForeground(QColor("#E0A03C"))
            listing.addItem(item)
        listing.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        lay.addWidget(listing)

        if skipped:
            warn = QLabel(f"{len(skipped)} field(s) I couldn't fill — check "
                          f"them in Brave before submitting.")
            warn.setWordWrap(True)
            warn.setMaximumWidth(400)
            warn.setStyleSheet("color: #E0A03C; font-size: 12px;")
            lay.addWidget(warn)
        else:
            hint = QLabel("Have a look in Brave first. Nothing has been sent.")
            hint.setObjectName("hint")
            lay.addWidget(hint)

        row = QHBoxLayout()
        row.addStretch(1)
        no = QPushButton("Don't submit")
        no.clicked.connect(self.reject)
        row.addWidget(no)
        yes = QPushButton("Submit it")
        yes.setObjectName("primary")
        # Deliberately NOT the default button: submitting is irreversible, and
        # a stray Enter shouldn't do it.
        yes.clicked.connect(self.accept)
        row.addWidget(yes)
        lay.addLayout(row)

    @staticmethod
    def ask(name: str, filled: list, skipped: list, anchor: QPoint,
            parent=None) -> bool:
        dlg = Approval(name, filled, skipped, parent)
        dlg.place_above(anchor)
        return dlg.exec() == QDialog.DialogCode.Accepted


class Picker(_Frameless):
    """'I don't know that one — which did you mean?'"""

    def __init__(self, prompt: str, options: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        lay.addWidget(QLabel(prompt))

        self.list = QListWidget()
        self.list.setMinimumWidth(360)
        self.list.setMaximumHeight(240)
        for label, target in options:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, target)
            item.setToolTip(target)
            self.list.addItem(item)
        if options:
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(self.accept)
        lay.addWidget(self.list)

        self.remember = QCheckBox("Remember this, so you don't ask again")
        self.remember.setChecked(True)
        lay.addWidget(self.remember)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Not this time")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = QPushButton("Open it")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        lay.addLayout(row)

    @staticmethod
    def choose(prompt: str, options: list[tuple[str, str]], anchor: QPoint,
               parent=None) -> tuple[str, bool] | None:
        """Returns (target, remember) or None if you backed out."""
        if not options:
            return None
        dlg = Picker(prompt, options, parent)
        dlg.place_above(anchor)
        dlg.list.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        item = dlg.list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole), dlg.remember.isChecked()
