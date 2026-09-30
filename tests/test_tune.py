"""Тюнинг: сбор параметров, objective, отсутствие ухудшения, валидность результата."""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sintgame.schema import simulate, validate  # noqa: E402
from sintgame.search import declared_endings  # noqa: E402
from sintgame.tune import _get, _set, collect_params, objective, tune  # noqa: E402

WORLD = json.load(open(os.path.join(ROOT, "examples", "station", "world.json")))


def test_pointer_get_set():
    d = copy.deepcopy(WORLD)
    p = collect_params(d)[0]["path"]
    v = _get(d, p)
    _set(d, p, v + 3)
    assert _get(d, p) == v + 3


def test_collect_params_nonempty():
    assert len(collect_params(WORLD)) > 0


def test_objective_positive_when_dominated():
    sim = {"endings_reached": {"a": 900, "b": 100}, "dead_ends": 0, "trials": 1000}
    assert objective(sim, n_endings=2) > 0


def test_tune_never_worsens_and_stays_valid():
    tuned, info = tune(WORLD, trials=120, iters=15, seed=0)
    assert info["after"] <= info["before"]
    assert validate(tuned) == []
    assert len(declared_endings(tuned)) == len(declared_endings(WORLD))


if __name__ == "__main__":
    for fn in [test_pointer_get_set, test_collect_params_nonempty,
               test_objective_positive_when_dominated, test_tune_never_worsens_and_stays_valid]:
        fn()
        print("ok", fn.__name__)
