from scripts.render_urdf_studio_episode import _sample_frames_for_fps


def test_trace_downsampling_preserves_simulation_time_at_twenty_fps():
    frames = [(t_ms, {"joint": t_ms}, {"cube": t_ms}) for t_ms in range(20, 8020, 20)]
    sampled = _sample_frames_for_fps(frames, 20)

    assert sampled[0][0] == 20
    assert sampled[-1][0] == 7980
    assert len(sampled) == 160
    assert len(sampled) / 20 == 8.0
