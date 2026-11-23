"""Catalog: what can be ordered and what it costs. Prices are integer cents."""

from dataclasses import dataclass
from enum import StrEnum


class Animal(StrEnum):
    DOG = "dog"
    PENGUIN = "penguin"
    CAPYBARA = "capybara"


PRICES_CENTS: dict[Animal, int] = {
    Animal.DOG: 100,
    Animal.PENGUIN: 300,
    Animal.CAPYBARA: 500,
}

MIN_QTY = 1
MAX_QTY = 5


@dataclass(frozen=True)
class OrderLine:
    animal: Animal
    qty: int

    def __post_init__(self) -> None:
        if not MIN_QTY <= self.qty <= MAX_QTY:
            raise ValueError(f"qty must be between {MIN_QTY} and {MAX_QTY}")

    @property
    def total_cents(self) -> int:
        return PRICES_CENTS[self.animal] * self.qty


def order_total_cents(lines: tuple[OrderLine, ...]) -> int:
    return sum(line.total_cents for line in lines)
