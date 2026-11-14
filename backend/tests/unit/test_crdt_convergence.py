from hypothesis import given, settings
from hypothesis import strategies as st
from pycrdt import Doc, Text


@settings(max_examples=100)
@given(
    st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=80),
    st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=80),
)
def test_concurrent_edits_converge(left, right):
    first, second = Doc(), Doc()
    first.get("text", type=Text).insert(0, left)
    second.get("text", type=Text).insert(0, right)
    one, two = first.get_update(), second.get_update()
    first.apply_update(two)
    second.apply_update(one)
    assert str(first.get("text", type=Text)) == str(second.get("text", type=Text))


@settings(max_examples=100)
@given(
    st.lists(st.tuples(st.integers(0, 2), st.integers(0, 200)), min_size=1, max_size=35),
    st.booleans(),
)
def test_inserts_deletes_reordering_and_duplicates_converge(operations, reverse):
    base = Doc()
    base.get("text", type=Text).insert(0, "Начальный текст")
    clients = [Doc(), Doc(), Doc()]
    for client in clients:
        client.apply_update(base.get_update())
    updates = []
    for index, (which, value) in enumerate(operations):
        client = clients[which]
        text = client.get("text", type=Text)
        length = len(str(text).encode("utf-8"))
        if value % 2 and length:
            # Удаляем целиком: не режем многобайтовый символ на границе UTF-8.
            del text[:]
        else:
            text.insert(length, f"{index}:{value};")
        updates.append(client.get_update())
    delivery = list(reversed(updates)) if reverse else updates
    for client in clients:
        for update in delivery + delivery:
            client.apply_update(update)
    assert len({str(client.get("text", type=Text)) for client in clients}) == 1
