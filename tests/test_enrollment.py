from src import enrollment


def test_normalize_strips_separators_and_uppercases() -> None:
    assert enrollment.normalize(" 22ec-1047 ") == "22EC1047"
    assert enrollment.normalize("22 EC/1047") == "22EC1047"


def test_is_valid_accepts_alphanumeric_codes() -> None:
    assert enrollment.is_valid("22EC1047")


def test_is_valid_rejects_short_or_symbol_codes() -> None:
    assert not enrollment.is_valid("ABC")
    assert not enrollment.is_valid("22EC#1047")
