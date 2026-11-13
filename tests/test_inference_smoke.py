from reva.inference_smoke import measure_inference

def test_measure_inference_records_success(monkeypatch):
    monkeypatch.setattr("reva.inference_smoke._gpu_free", lambda _=0: 123)
    result = measure_inference(lambda: {"action": 1})
    assert result.status == "completed"
    assert result.output_type == "dict"
    assert result.gpu_memory_before_bytes == 123
    assert result.gpu_memory_after_bytes == 123
    assert result.elapsed_ns >= 0

def test_measure_inference_records_failure(monkeypatch):
    monkeypatch.setattr("reva.inference_smoke._gpu_free", lambda _=0: None)
    result = measure_inference(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert result.status == "failed"
    assert "boom" in result.error
