"""Reel planning must reuse Auto's recorded clips, even on another drive."""

from __future__ import annotations

import pytest

from modules.segments.auto_pipeline import JobState, save_job
from sidecar.server import ReelRequest, _reel_sources


def test_auto_highlights_outside_destination_are_reel_sources(tmp_path):
    project = tmp_path / "project"
    source = tmp_path / "source-footage"
    source.mkdir()
    project.mkdir()
    clips = [source / "second_highlight.mp4", source / "first_highlight.mp4"]
    for clip in clips:
        clip.touch()
    save_job(JobState(job_id="completed", root=str(project),
                      highlights=[str(p) for p in clips]))

    assert _reel_sources(ReelRequest(dest_root=str(project))) == [str(p) for p in clips]


def test_explicit_sources_take_precedence_over_auto_job(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    recorded = tmp_path / "recorded_highlight.mp4"
    selected = tmp_path / "selected.mp4"
    recorded.touch()
    selected.touch()
    save_job(JobState(job_id="completed", root=str(project),
                      highlights=[str(recorded)]))

    assert _reel_sources(ReelRequest(dest_root=str(project),
                                     source_paths=[str(selected)])) == [str(selected)]


def test_explicit_single_file_ignores_other_files_and_auto_outputs(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    selected, other = source / "chosen.mp4", source / "other.mp4"
    selected.touch()
    other.touch()
    recorded = source / "auto_highlight.mp4"
    recorded.touch()
    save_job(JobState(job_id="completed", root=str(project),
                      highlights=[str(recorded)]))

    assert _reel_sources(ReelRequest(dest_root=str(project),
                                     source_paths=[str(selected)])) == [str(selected)]


def test_explicit_missing_file_never_falls_back_to_auto_or_folder(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    recorded = project / "auto_highlight.mp4"
    recorded.touch()
    save_job(JobState(job_id="completed", root=str(project),
                      highlights=[str(recorded)]))

    with pytest.raises(ValueError, match="Selected video file is missing"):
        _reel_sources(ReelRequest(dest_root=str(project),
                                  source_paths=[str(project / "gone.mp4")]))
    with pytest.raises(ValueError, match="Choose a video file"):
        _reel_sources(ReelRequest(dest_root=str(project), source_paths=[]))


def test_missing_auto_outputs_are_reported_not_silently_ignored(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    save_job(JobState(job_id="completed", root=str(project),
                      highlights=[str(tmp_path / "lost_highlight.mp4")]))

    with pytest.raises(ValueError, match="recorded highlights.*missing"):
        _reel_sources(ReelRequest(dest_root=str(project)))


def test_legacy_project_folder_without_manifest_still_works(tmp_path):
    root = tmp_path / "old-project"
    root.mkdir()
    clip = root / "saved_highlight.mp4"
    clip.touch()

    assert _reel_sources(ReelRequest(dest_root=str(root))) == [str(clip)]
