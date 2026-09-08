from __future__ import annotations


class RecordingResource:
    def __init__(self, name: str, events: list[str]):
        self.name = name
        self.events = events

    def __enter__(self):
        self.events.append(f"enter {self.name}")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.events.append(f"exit {self.name}")


def test_frame_exits_resource_and_continues_after_cleanup_callback_failure(test_frame):
    events: list[str] = []
    expected_events = [
        "enter later",
        "enter failing",
        "cleanup failing",
        "exit failing",
        "cleanup later",
        "exit later",
    ]
    later_resource = RecordingResource("later", events)
    failing_resource = RecordingResource("failing", events)

    def clean_later_resource(resource):
        resource.events.append("cleanup later")

    def fail_to_clean_resource(resource):
        resource.events.append("cleanup failing")
        raise RuntimeError("cleanup failed")

    test_frame.append(later_resource, clean_later_resource)
    test_frame.append(failing_resource, fail_to_clean_resource)

    try:
        test_frame.destroy()
        assert events == expected_events
    finally:
        test_frame.resources.clear()
