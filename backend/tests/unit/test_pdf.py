from unittest.mock import MagicMock

from pycrdt import Doc, XmlElement, XmlFragment, XmlText

from app.modules.exports.pdf import inline, register_fonts, render_pdf


def test_pdf_escapes_text_and_formats_supported_marks():
    doc = Doc()
    fragment = doc.get("default", type=XmlFragment)
    fragment.children.append(XmlElement("paragraph", contents=[XmlText("<tag> & текст")]))
    text = fragment.children[0].children[0]
    text.format(0, len(text.to_py().encode("utf-8")), {"bold": {}, "italic": {}})
    assert inline(fragment) == "<i><b>&lt;tag&gt; &amp; текст</b></i>"


def test_pdf_builds_headings_lists_and_empty_paragraph(tmp_path, monkeypatch):
    doc = Doc()
    fragment = doc.get("default", type=XmlFragment)
    for node in [
        XmlElement("heading", attributes={"level": "2"}, contents=[XmlText("Заголовок")]),
        XmlElement(
            "paragraph",
            contents=[XmlText("Кириллица"), XmlElement("hardBreak"), XmlText("строка")],
        ),
        XmlElement("paragraph"),
        XmlElement("bulletList", contents=[XmlElement("listItem", contents=[XmlText("Пункт")])]),
        XmlElement("orderedList", contents=[XmlElement("listItem", contents=[XmlText("Номер")])]),
    ]:
        fragment.children.append(node)
    monkeypatch.setattr("app.modules.exports.pdf.register_fonts", lambda _: None)
    build = MagicMock()
    monkeypatch.setattr("app.modules.exports.pdf.SimpleDocTemplate", build)
    # Здесь проверяем структуру; реальную запись со шрифтами проверяет Compose-сценарий.
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.modules.exports.pdf.Paragraph",
        lambda text, style: SimpleNamespace(text=text, style=style),
    )
    render_pdf(doc.get_update(), "<Название>", tmp_path / "result.pdf", tmp_path)
    story = build.return_value.build.call_args.args[0]
    assert len(story) == 7
    assert story[0].text == "&lt;Название&gt;"
    assert any("• " in getattr(item, "text", "") for item in story)


def test_registers_all_four_font_faces(tmp_path, monkeypatch):
    font = MagicMock()
    register = MagicMock()
    monkeypatch.setattr("app.modules.exports.pdf.TTFont", font)
    monkeypatch.setattr("app.modules.exports.pdf.pdfmetrics.getRegisteredFontNames", lambda: [])
    monkeypatch.setattr("app.modules.exports.pdf.pdfmetrics.registerFont", register)
    register_fonts(tmp_path)
    assert register.call_count == 4
    assert any("Oblique" in call.args[1] for call in font.call_args_list)
