import json

from governed_ap.schemas import BenchmarkCase


def case_input_json(
    case: BenchmarkCase,
) -> str:
    payload = case.model_dump(mode="json")

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
