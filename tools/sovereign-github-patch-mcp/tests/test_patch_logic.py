from server import PatchBlock, _apply_blocks


def test_apply_single_block():
    out, applied = _apply_blocks(
        "hello old world",
        [PatchBlock(search="old", replace="new")],
        require_unique=True,
    )
    assert out == "hello new world"
    assert applied == ["block 0: 1 match(es)"]


def test_multiple_blocks():
    out, _ = _apply_blocks(
        "a b c",
        [
            PatchBlock(search="a", replace="A"),
            PatchBlock(search="c", replace="C"),
        ],
        require_unique=True,
    )
    assert out == "A b C"
