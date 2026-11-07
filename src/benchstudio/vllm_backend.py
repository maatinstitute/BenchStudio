"""Optional upstream vLLM integration. No engine or model is loaded on import."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.metadata import version
import math
import re
from threading import Lock

from .system_spec import Component, SystemSpec, _canonical
import hashlib


@dataclass(frozen=True)
class GenerationConfig:
    max_tokens: int = 128
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 0

    def __post_init__(self):
        if type(self.max_tokens) is not int or self.max_tokens < 1:
            raise ValueError("max_tokens must be a positive integer")
        if type(self.seed) is not int:
            raise ValueError("seed must be an integer")
        for name, lower, upper in (("temperature", 0, None), ("top_p", 0, 1)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value < lower or (
                upper is not None and (value <= 0 or value > upper)
            ):
                raise ValueError(f"invalid {name}")


@dataclass(frozen=True)
class VLLMConfig:
    model: str
    revision: str
    dtype: str = "auto"
    tensor_parallel_size: int = 1
    gpu_memory_utilization: float = 0.9
    max_model_len: int | None = None

    def __post_init__(self):
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must be a Hugging Face model identifier")
        if not isinstance(self.revision, str) or re.fullmatch(r"[0-9a-f]{40}", self.revision) is None:
            raise ValueError("revision must pin a full lowercase Hugging Face commit SHA")
        if self.dtype not in {"auto", "half", "float16", "bfloat16", "float", "float32"}:
            raise ValueError("unsupported dtype")
        if type(self.tensor_parallel_size) is not int or self.tensor_parallel_size < 1:
            raise ValueError("tensor_parallel_size must be positive")
        value = self.gpu_memory_utilization
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 1:
            raise ValueError("gpu_memory_utilization must be in (0, 1]")
        if self.max_model_len is not None and (type(self.max_model_len) is not int or self.max_model_len < 1):
            raise ValueError("max_model_len must be positive")


class VLLMRuntime:
    """Lazy persistent engine; batches go unchanged to upstream LLM.generate.

    Calls are serialized. This blocking backend is intended for run(), not
    event-loop concurrency. Process exit owns native engine teardown.
    """
    def __init__(self, config: VLLMConfig, generation: GenerationConfig):
        self.config, self.generation = config, generation
        self._engine = self._sampling = None
        self._lock = Lock()

    def _load(self):
        if self._engine is not None:
            return
        try:
            if version("vllm") != "0.33.0":
                raise ImportError("this adapter targets vllm==0.33.0")
            from vllm import LLM, SamplingParams
        except ImportError as exc:
            raise ImportError("Install BenchStudio's [vllm] extra in a vLLM-compatible environment") from exc
        sampling = SamplingParams(**asdict(self.generation), n=1)
        options = asdict(self.config)
        if options["max_model_len"] is None:
            del options["max_model_len"]
        engine = LLM(**options, tokenizer_revision=self.config.revision,
                     trust_remote_code=False, generation_config="vllm")
        self._sampling, self._engine = sampling, engine

    def generate_batch(self, prompts):
        prompts = list(prompts)
        if any(not isinstance(prompt, str) for prompt in prompts):
            raise TypeError("vLLM text backend requires string prompts")
        if not prompts:
            return []
        with self._lock:
            self._load()
            outputs = self._engine.generate(prompts, self._sampling, use_tqdm=False)
            if len(outputs) != len(prompts):
                raise ValueError("vLLM returned a different number of requests")
            texts = []
            for prompt, result in zip(prompts, outputs):
                if result.prompt != prompt or len(result.outputs) != 1:
                    raise ValueError("vLLM request order or completion count mismatch")
                text = result.outputs[0].text
                if not isinstance(text, str):
                    raise ValueError("vLLM completion must be text")
                texts.append(text)
            return texts

    def __call__(self, prompt):
        return self.generate_batch([prompt])[0]

    def system_spec(self):
        identity = {"engine": asdict(self.config), "generation": asdict(self.generation),
                    "backend": "vllm", "vllm_version": "0.33.0", "generation_config": "vllm", "trust_remote_code": False}
        digest = hashlib.sha256(_canonical(identity)).hexdigest()
        return SystemSpec(self.config.model, self.config.revision, (
            Component("model", "language_model", "vllm.LLM", self.config.revision, config_digest=digest),
        ), metadata=identity)
