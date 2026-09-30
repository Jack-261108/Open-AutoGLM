from phone_agent.model.base import ContentDelta, ModelStreamEvent, ThinkingDelta
from phone_agent.model.stream_filter import StreamingThinkingDetector


def test_detector_no_callback():
    detector = StreamingThinkingDetector(None)
    detector.feed("hello")
    detector.flush()


def test_detector_implicit_reasoning_before_dsl_action():
    events: list[ModelStreamEvent] = []
    detector = StreamingThinkingDetector(events.append)
    detector.feed("当前在桌面，")
    detector.feed("寻找设置图标...\n")
    detector.feed("do(action='Tap', element=[100, 200])")
    detector.flush()

    thinking_text = "".join(e.text for e in events if isinstance(e, ThinkingDelta))
    content_text = "".join(e.text for e in events if isinstance(e, ContentDelta))

    assert thinking_text == "当前在桌面，寻找设置图标...\n"
    assert content_text == "do(action='Tap', element=[100, 200])"


def test_detector_implicit_reasoning_action_marker_split():
    events: list[ModelStreamEvent] = []
    detector = StreamingThinkingDetector(events.append)
    detector.feed("分析完毕，准备点击。d")
    detector.feed("o(action='Tap')")
    detector.flush()

    thinking_text = "".join(e.text for e in events if isinstance(e, ThinkingDelta))
    content_text = "".join(e.text for e in events if isinstance(e, ContentDelta))

    assert thinking_text == "分析完毕，准备点击。"
    assert content_text == "do(action='Tap')"


def test_detector_single_chunk_think():
    events: list[ModelStreamEvent] = []
    detector = StreamingThinkingDetector(events.append)
    detector.feed("<think>I should tap</think>do(action='Tap')")
    detector.flush()

    thinking_text = "".join(e.text for e in events if isinstance(e, ThinkingDelta))
    content_text = "".join(e.text for e in events if isinstance(e, ContentDelta))

    assert thinking_text == "I should tap"
    assert content_text == "do(action='Tap')"


def test_detector_split_across_chunks():
    events: list[ModelStreamEvent] = []
    detector = StreamingThinkingDetector(events.append)
    detector.feed("prefix <th")
    detector.feed("ink>thinking body</th")
    detector.feed("ink>do(action='Back')")
    detector.flush()

    thinking_text = "".join(e.text for e in events if isinstance(e, ThinkingDelta))
    content_text = "".join(e.text for e in events if isinstance(e, ContentDelta))
    assert thinking_text == "prefix thinking body"
    assert content_text == "do(action='Back')"


def test_detector_immediate_action_no_thinking():
    events: list[ModelStreamEvent] = []
    detector = StreamingThinkingDetector(events.append)
    detector.feed("do(action='Home')")
    detector.flush()

    assert not any(isinstance(e, ThinkingDelta) for e in events)
    content_text = "".join(e.text for e in events if isinstance(e, ContentDelta))
    assert content_text == "do(action='Home')"


def test_detector_xml_answer_marker():
    events: list[ModelStreamEvent] = []
    detector = StreamingThinkingDetector(events.append)
    detector.feed("寻找设置应用。<answer>")
    detector.feed("do(action='Tap')</answer>")
    detector.flush()

    thinking_text = "".join(e.text for e in events if isinstance(e, ThinkingDelta))
    content_text = "".join(e.text for e in events if isinstance(e, ContentDelta))
    assert thinking_text == "寻找设置应用。"
    assert content_text == "<answer>do(action='Tap')</answer>"
