"""End-to-end synthetic component ablation; no learned model or environment."""
import asyncio
import benchstudio as bs


def component(fn, name, revision):
    return bs.System.from_callable(fn, name=name, revision=revision)


async def main():
    # Pure arithmetic fixtures illustrate plumbing, not forecasting capability.
    reference = bs.Workflow("predictor-and-planner", "r1", stages={
        "predictor": component(lambda x: x, "predictor", "identity-r1"),
        "planner": component(lambda prediction: prediction, "planner", "fixed-r1"),
    })
    candidate = reference.replace(
        "predictor", component(lambda x: 2*x, "predictor", "double-r1"), revision="r2"
    )
    benchmark = bs.Benchmark(
        "synthetic-arithmetic", "fixtures-r1", inputs=[1, 2, 3, 4], targets=[2, 4, 6, 8],
        scorer=lambda output, target: bs.Score(
            success=output == target, metrics={"absolute_error": abs(output-target)}
        ),
        evaluator_revision="exact-and-absolute-error-r1", authoritative=True,
    )
    experiment = bs.pipeline(
        "ablation", reference=reference.as_system(), candidate=candidate.as_system(),
        benchmark=benchmark, changed_components=("predictor",), metrics=("absolute_error",),
    )
    result = await experiment.arun()
    print("Synthetic API demonstration; no model performance or causal research claim")
    print(result.summary())
    print("Recorded arm order:", result.arm_order)


if __name__ == "__main__":
    asyncio.run(main())
