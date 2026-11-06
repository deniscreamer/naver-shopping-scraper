"""Offline tests for captcha_watch.py: a fake client hands out /captcha states.

    .venv/bin/python -m pytest scripts/test_captcha_watch.py -q
"""
import pytest

from captcha_watch import event, watch

WAITING = {"status": "waiting", "at": "t1", "step": "search", "attempt": 1, "wait_s": 600, "url": "u",
           "question": "What is the first number of the store's phone number?", "screenshot": "/x/search-captcha.png"}


class States:
    def __init__(self, *states):
        self.states = list(states)

    def captcha(self):
        if not self.states:
            raise KeyboardInterrupt
        return self.states.pop(0)


def test_events_once_each():
    lines = []
    again = {**WAITING, "attempt": 2, "at": "t2", "question": "What is the price?"}
    solved = {"status": "solved", "at": "t3", "step": "search", "attempt": 2, "after_s": 95}
    with pytest.raises(KeyboardInterrupt):
        watch(States({"status": "none"}, WAITING, WAITING, again, solved, solved), sleep=lambda s: None,
              out=lines.append)
    assert lines == [
        "captcha_watch: CAPTCHA #1 at search: What is the first number of the store's phone number? | screenshot "
        "/x/search-captcha.png | answer within 600 s",
        "captcha_watch: CAPTCHA #2 at search: What is the price? | screenshot /x/search-captcha.png | answer within 600 s",
        "captcha_watch: solved at search after 95 s"]


def test_an_old_end_state_is_not_news():
    lines = []
    with pytest.raises(KeyboardInterrupt):                # started after the last captcha was solved: quiet
        watch(States({"status": "solved", "at": "t0", "step": "x", "attempt": 1, "after_s": 5}),
              sleep=lambda s: None, out=lines.append)
    assert lines == []
    assert event({"status": "timed_out", "step": "product", "after_s": 600}) == "timed out at product after 600 s"
