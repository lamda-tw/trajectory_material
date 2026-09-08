from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from .models import TrajectoryMessage


def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    value = next((value for key, value in attrs if key == "class"), "") or ""
    return set(value.split())


def _clean(parts: list[str]) -> str:
    text = "".join(parts).replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class _ExportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.messages: list[TrajectoryMessage] = []
        self._message: dict[str, object] | None = None
        self._message_div_depth = 0
        self._element_depth = 0
        self._captures: list[tuple[str, int]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._element_depth += 1
        classes = _classes(attrs)
        if tag == "div" and "message" in classes and self._message is None:
            role_class = next(
                (name for name in ("user", "assistant", "system") if name in classes),
                "",
            )
            self._message = {
                "role_class": role_class,
                "role": [],
                "time": [],
                "text": [],
            }
            self._message_div_depth = 1
        elif self._message is not None and tag == "div":
            self._message_div_depth += 1

        if self._message is None:
            return
        if tag == "span" and "role" in classes:
            self._captures.append(("role", self._element_depth))
        elif tag == "span" and "time" in classes:
            self._captures.append(("time", self._element_depth))
        elif tag == "div" and "msg-text" in classes:
            self._captures.append(("text", self._element_depth))
        elif self._captures and self._captures[-1][0] == "text" and tag in {
            "p",
            "li",
            "tr",
            "br",
            "pre",
            "h1",
            "h2",
            "h3",
            "h4",
        }:
            cast_parts = self._message["text"]
            assert isinstance(cast_parts, list)
            cast_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._message is None or not self._captures:
            return
        target = self._captures[-1][0]
        parts = self._message[target]
        assert isinstance(parts, list)
        parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._message is not None and self._captures:
            target, start_depth = self._captures[-1]
            if start_depth == self._element_depth:
                self._captures.pop()
                if target == "text":
                    parts = self._message["text"]
                    assert isinstance(parts, list)
                    parts.append("\n")

        if self._message is not None and tag == "div":
            self._message_div_depth -= 1
            if self._message_div_depth == 0:
                role_parts = self._message["role"]
                time_parts = self._message["time"]
                text_parts = self._message["text"]
                assert isinstance(role_parts, list)
                assert isinstance(time_parts, list)
                assert isinstance(text_parts, list)
                role = _clean(role_parts) or str(self._message["role_class"])
                text = _clean(text_parts)
                self.messages.append(
                    TrajectoryMessage(
                        index=len(self.messages) + 1,
                        role=role,
                        timestamp=_clean(time_parts),
                        text=text,
                    )
                )
                self._message = None
                self._captures.clear()
        self._element_depth = max(0, self._element_depth - 1)


def parse_trajectory(path: str | Path) -> tuple[TrajectoryMessage, ...]:
    source = Path(path)
    parser = _ExportParser()
    parser.feed(source.read_text(encoding="utf-8"))
    parser.close()
    if not parser.messages:
        raise ValueError(f"no exported messages found in {source}")
    return tuple(parser.messages)
