import random

from image_generator.variants import (
    ART_STYLES,
    SETTINGS,
    TIMES_OF_DAY,
    TWISTS,
    draw_variants,
)


def test_same_seed_draws_the_same_variants():
    animals = ["dog", "penguin", "capybara"]

    assert draw_variants(animals, random.Random(42)) == draw_variants(animals, random.Random(42))


def test_variants_come_from_the_data_lists_and_keep_animal_order():
    variants = draw_variants(["penguin", "dog"], random.Random(1))

    assert [v.animal for v in variants] == ["penguin", "dog"]
    for variant in variants:
        assert variant.setting in SETTINGS
        assert variant.time_of_day in TIMES_OF_DAY
        assert variant.art_style in ART_STYLES
        assert variant.twist in TWISTS


def test_prompt_is_built_from_template_and_animal():
    (variant,) = draw_variants(["capybara"], random.Random(3))

    assert "a capybara" in variant.prompt
    assert variant.setting in variant.prompt
    assert variant.as_manifest_entry()["prompt"] == variant.prompt
