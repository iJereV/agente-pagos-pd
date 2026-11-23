"""Random image variants, drawn in code so the model never chooses them.

PLACEHOLDER DATA: the lists below are a first draft meant to be refined. Keep them
as plain data; the drawing logic does not depend on their contents or lengths.
"""

import random
from dataclasses import asdict, dataclass

ANIMAL_SUBJECTS: dict[str, str] = {
    "dog": "a dog",
    "penguin": "a penguin",
    "capybara": "a capybara",
}

# --- PLACEHOLDER: settings -------------------------------------------------------
SETTINGS: list[str] = [
    "a sunny beach",
    "a snowy mountain cabin",
    "a busy city street",
    "a cozy library",
    "a vegetable garden",
    "a space station",
]

# --- PLACEHOLDER: times of day ---------------------------------------------------
TIMES_OF_DAY: list[str] = [
    "early morning",
    "midday",
    "golden hour",
    "night under the stars",
]

# --- PLACEHOLDER: art styles -----------------------------------------------------
ART_STYLES: list[str] = [
    "watercolor illustration",
    "photorealistic photo",
    "3D clay render",
    "retro comic book",
    "pixel art",
]

# --- PLACEHOLDER: funny twists ---------------------------------------------------
TWISTS: list[str] = [
    "wearing tiny sunglasses",
    "proudly holding a mate gourd",
    "riding a small skateboard",
    "wearing a chef hat",
    "reading a newspaper upside down",
]

PROMPT_TEMPLATE = (
    "A {art_style} of {subject} in {setting} at {time_of_day}, {twist}. "
    "Single subject, centered, friendly and family-safe, no text or watermarks."
)


@dataclass(frozen=True)
class Variant:
    animal: str
    setting: str
    time_of_day: str
    art_style: str
    twist: str

    @property
    def prompt(self) -> str:
        return PROMPT_TEMPLATE.format(
            subject=ANIMAL_SUBJECTS[self.animal],
            setting=self.setting,
            time_of_day=self.time_of_day,
            art_style=self.art_style,
            twist=self.twist,
        )

    def as_manifest_entry(self) -> dict[str, str]:
        return asdict(self) | {"prompt": self.prompt}


def draw_variant(animal: str, rng: random.Random) -> Variant:
    return Variant(
        animal=animal,
        setting=rng.choice(SETTINGS),
        time_of_day=rng.choice(TIMES_OF_DAY),
        art_style=rng.choice(ART_STYLES),
        twist=rng.choice(TWISTS),
    )


def draw_variants(animals: list[str], rng: random.Random) -> list[Variant]:
    """One independent variant per image, in the given order."""
    return [draw_variant(animal, rng) for animal in animals]
