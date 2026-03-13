from grok_sdk.sse import parse_sse_lines


def test_parse_sse_multiline_data() -> None:
    lines = [
        "event: message\n",
        "data: {\"a\": 1}\n",
        "data: {\"b\": 2}\n",
        "\n",
    ]
    events = list(parse_sse_lines(lines))
    assert len(events) == 1
    assert events[0].event == "message"
    assert events[0].data == '{"a": 1}\n{"b": 2}'


def test_parse_sse_ignores_comments_and_empty_event() -> None:
    lines = [": keep-alive\n", "\n", "data: hi\n", "\n"]
    events = list(parse_sse_lines(lines))
    assert len(events) == 1
    assert events[0].data == "hi"
