from __future__ import annotations

from .contracts import ActionChunk, Observation


class MockPolicy:
    policy_id = "mock_policy"

    def reset(self, *, seed: int) -> None:
        self.seed = seed

    def predict(self, observation: Observation, *, denoising_steps: int | None) -> ActionChunk:
        return ActionChunk(
            actions=(1, 1),
            metadata={
                "denoising_steps": denoising_steps,
                "observation_sequence": observation.sequence,
            },
        )


class MockSimulator:
    simulator_id = "mock_simulator"

    def reset(self, *, seed: int) -> Observation:
        self._step = 0
        self._success = False
        return Observation(sequence=0, sim_time_s=0.0, payload={"seed": seed})

    def observe(self) -> Observation:
        return Observation(sequence=self._step, sim_time_s=self._step * 0.1)

    def step(self, action: int) -> Observation:
        self._step += 1
        self._success = self._step >= 4
        return self.observe()

    def is_done(self) -> bool:
        return self._step >= 4

    def is_success(self) -> bool:
        return self._success

    def close(self) -> None:
        pass
