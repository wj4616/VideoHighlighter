"""Custom and score-derived highlight lengths for long Linux source videos."""

import numpy as np
import pytest

from modules.segments.highlight_select import (
    select_fixed_window_segments, select_optimal_segments,
)
from modules.segments.simple_run import apply_simple_run


def duration(segments):
    return sum(end - start for start, end in segments)


def test_custom_duration_over_one_hour_is_exact():
    config = apply_simple_run({}, "custom", custom_seconds=5400)
    assert config["exact_duration"] == 5400
    assert config["optimal_length"] is False
    score = np.zeros(7201)
    score[100:160] = 10
    cut = select_fixed_window_segments(
        score, video_duration=7200, clip_time=10,
        target_duration=config["exact_duration"], duration_mode="EXACT",
    )
    assert duration(cut) == 5400
    assert all(0 <= start < end <= 7200 for start, end in cut)


def test_exact_fills_short_gaps_when_target_is_full_source():
    score = np.zeros(35)
    score[5] = 7
    cut = select_fixed_window_segments(
        score, video_duration=35, clip_time=10,
        target_duration=35, duration_mode="EXACT",
    )
    assert duration(cut) == 35


def test_optimal_strictness_shortens_sparse_long_source():
    score = np.zeros(7201)
    score[np.arange(25, 7000, 25)] = np.arange(1, len(np.arange(25, 7000, 25)) + 1)
    loose = select_optimal_segments(score, video_duration=7200, clip_time=10, strictness=0)
    balanced = select_optimal_segments(score, video_duration=7200, clip_time=10, strictness=50)
    strict = select_optimal_segments(score, video_duration=7200, clip_time=10, strictness=100)
    assert 0 < duration(strict) < duration(balanced) < duration(loose) < 7200
    assert all(0 <= start < end <= 7200 for start, end in loose)


def test_optimal_no_signal_does_not_pad():
    assert select_optimal_segments(np.zeros(7201), video_duration=7200, clip_time=10) == []


@pytest.mark.parametrize("seconds", [0, -1, 604801])
def test_custom_invalid_length_rejected(seconds):
    with pytest.raises(ValueError):
        apply_simple_run({}, "custom", custom_seconds=seconds)


def test_presets_keep_previous_duration_and_do_not_inherit_exact():
    config = apply_simple_run({"exact_duration": 3600}, "medium")
    assert config["max_duration"] == 240
    assert config["exact_duration"] is None
    assert apply_simple_run({}, "optimal", strictness=80)["optimal_strictness"] == 80


def test_simple_page_shows_only_the_relevant_length_control():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QWidget
    from modules.ui.simple_start import SimpleStartPage

    class Host(QWidget):
        def get_file_list(self):
            return []

        def cancel_pipeline(self):
            pass

        def open_timeline_viewer(self):
            pass

        def open_why_report(self):
            pass

    app = QApplication.instance() or QApplication([])
    host = Host()
    page = SimpleStartPage(host)
    try:
        host.show()
        page.show()
        assert page.length_key() == "medium"
        page.length.setCurrentIndex(page.length.findData("custom"))
        assert page.custom_seconds.isVisible()
        assert not page.strictness.isVisible()
        page.custom_seconds.setValue(3600)
        assert apply_simple_run({}, page.length_key(),
                                custom_seconds=page.custom_seconds.value())["exact_duration"] == 3600
        page.length.setCurrentIndex(page.length.findData("optimal"))
        assert page.strictness.isVisible()
        assert not page.custom_seconds.isVisible()
    finally:
        page.close()
        host.close()
