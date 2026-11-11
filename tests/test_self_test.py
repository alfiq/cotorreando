"""`--self-test` is what the build and the release workflow run on the packaged exe."""

import subprocess
import sys

from cotorreando import selftest


def test_tiny_model_is_valid_protobuf_for_onnxruntime():
    import numpy as np
    import onnxruntime as ort

    session = ort.InferenceSession(selftest.tiny_onnx_model(), providers=["CPUExecutionProvider"])
    (y,) = session.run(None, {"x": np.array([1, 2, 3], dtype=np.float32)})
    assert y.tolist() == [2, 4, 6]


def test_self_test_passes(tmp_path):
    log = tmp_path / "selftest.log"
    result = subprocess.run(
        [sys.executable, "-m", "cotorreando", "--self-test", "--self-test-log", str(log)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    text = log.read_text(encoding="utf-8")
    assert "self-test passed" in text
    assert "FAIL" not in text
