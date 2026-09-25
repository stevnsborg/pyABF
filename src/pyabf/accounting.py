"""
accounting.py — Accounting entries (notes) and annual reports for a housing cooperative.

A Danish housing cooperative's annual report is structured around numbered
notes (noter), each grouping related income or expense line items.

Contains:
    AccountEntry   — A single accounting note with line items
    AnnualReport   — A full annual report composed of notes
    DEFAULT_NOTES  — A common 10-note layout, used when no layout is given

Note layouts differ between administrators, so ``DEFAULT_NOTES`` is only a
starting point: pass your own ``{note_id: (name, is_expense)}`` mapping to
:meth:`AnnualReport.from_defaults` to match your cooperative's report.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class AccountEntry:
    """An accounting note (e.g. 'Revenue', 'Maintenance', etc.).

    Attributes:
        id: Note number/identifier (e.g. '01', '02')
        name: Descriptive name for the note
        is_expense: True if this note represents an expense, False for income
        items: Dict of {item_id: amount} for individual line items
    """

    id: str
    name: str = ""
    is_expense: bool = True
    items: dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        """Sum of all line items in this note."""
        return sum(self.items.values())

    def add_item(self, item_id: str, amount: float) -> None:
        """Add or update a line item.

        Args:
            item_id: Identifier for the line item
            amount: Amount in DKK
        """
        self.items[item_id] = amount

    def remove_item(self, item_id: str) -> None:
        """Remove a line item.

        Args:
            item_id: Identifier for the line item to remove
        """
        self.items.pop(item_id, None)


#: A common 10-note layout for a Danish housing cooperative's annual report,
#: as ``{note_id: (name, is_expense)}``. Override per cooperative as needed.
DEFAULT_NOTES: dict[str, tuple[str, bool]] = {
    "01": ("Revenue", False),
    "02": ("Personnel expenses", True),
    "03": ("Insurance and subscriptions", True),
    "04": ("Taxes and utilities", True),
    "05": ("Cleaning", True),
    "06": ("Maintenance", True),
    "07": ("Restoration", True),
    "08": ("Administration", True),
    "09": ("Depreciation", True),
    "10": ("Financial expenses", True),
}


@dataclass
class AnnualReport:
    """Annual report for a housing cooperative.

    Collects a set of accounting notes for a given fiscal year
    and computes the result (income minus expenses).

    Income and expense notes are both stored as positive amounts; the
    ``is_expense`` flag on each note decides which side it counts towards.

    Attributes:
        year: The fiscal year
        notes: List of accounting notes in the report
    """

    year: int
    notes: list[AccountEntry] = field(default_factory=list)

    @classmethod
    def from_defaults(
        cls,
        year: int,
        notes: dict[str, tuple[str, bool]] | None = None,
    ) -> "AnnualReport":
        """Create an annual report pre-populated with empty notes.

        Args:
            year: The fiscal year
            notes: Note layout as ``{note_id: (name, is_expense)}``.
                Defaults to :data:`DEFAULT_NOTES`.

        Returns:
            An AnnualReport with one empty AccountEntry per note
        """
        layout = DEFAULT_NOTES if notes is None else notes
        entries = [
            AccountEntry(id=nid, name=name, is_expense=is_expense)
            for nid, (name, is_expense) in layout.items()
        ]
        return cls(year=year, notes=entries)

    def add_note(self, note: AccountEntry) -> None:
        """Add a note to the report.

        Args:
            note: The AccountEntry to add

        Raises:
            ValueError: If a note with the same id already exists
        """
        if self.find_note(note.id) is not None:
            raise ValueError(f"Note '{note.id}' already exists in the report.")
        self.notes.append(note)

    def find_note(self, note_id: str) -> AccountEntry | None:
        """Find a note by its id.

        Args:
            note_id: The note number (e.g. '01')

        Returns:
            The AccountEntry if found, otherwise None
        """
        for note in self.notes:
            if note.id == note_id:
                return note
        return None

    @property
    def total_income(self) -> float:
        """Total income (notes where is_expense=False)."""
        return sum(n.total for n in self.notes if not n.is_expense)

    @property
    def total_expenses(self) -> float:
        """Total expenses (notes where is_expense=True)."""
        return sum(n.total for n in self.notes if n.is_expense)

    @property
    def result(self) -> float:
        """Net result for the year (income minus expenses)."""
        return self.total_income - self.total_expenses
