from floorpro.domain.customers import display_name, format_reference, parse_reference, sort_name


def test_display_name():
    assert display_name("Jane", "Smith", None) == "Jane Smith"
    assert display_name(None, None, "Acme Flooring") == "Acme Flooring"
    assert display_name("Jane", "Smith", "Acme Flooring") == "Acme Flooring (Jane Smith)"
    assert display_name(None, "Smith", None) == "Smith"


def test_sort_name():
    assert sort_name("Jane", "Smith", None) == "Smith, Jane"
    assert sort_name(None, None, "Acme Flooring") == "Acme Flooring"
    assert sort_name("Jane", None, None) == "Jane"


def test_reference_format_and_parse():
    assert format_reference(42) == "C-00042"
    assert format_reference(123456) == "C-123456"
    assert parse_reference("C-00042") == 42
    assert parse_reference("c42") == 42
    assert parse_reference("C42") == 42
    assert parse_reference("Carol") is None
    assert parse_reference("C-0") is None
