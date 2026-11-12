"""jsonl_loader: Load every record from a folder of .jsonl files into a pydantic model, failing loudly (file and line) on any bad record or repeated id.

See SPEC.md in this folder (ADR 0003).
"""

from pathlib import Path

from pydantic import BaseModel, ValidationError

from quizkit.blocks.base import BlockSpec

BLOCK_SPEC = BlockSpec(
    name="jsonl_loader",
    kind="script",
    goal="Load every record from a folder of .jsonl files into a pydantic model, failing loudly (file and line) on any bad record or repeated id.",
    inputs=["folder", "model", "id_field", "what"],
    outputs=["load_jsonl_dir"],
)


def load_jsonl_dir[M: BaseModel](
    folder: Path, model: type[M], id_field: str | None = "id", what: str = "records"
) -> list[M]:
    """Every record in folder/*.jsonl (name order, then line order) as `model`."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(folder)
    records: list[M] = []
    for path in sorted(p for p in folder.glob("*.jsonl") if p.is_file()):
        try:
            text = path.read_text(encoding="utf-8-sig")  # -sig: a BOM is ignored
        except UnicodeDecodeError as err:
            raise ValueError(f"{path.name}: not valid UTF-8 ({err})") from err
        # Split on "\n" only: splitlines() also breaks on U+2028 etc., which JSON
        # allows inside strings, and would shift every later line number.
        for number, line in enumerate(text.split("\n"), start=1):
            line = line.removesuffix("\r")
            if not line.strip():
                continue
            try:
                records.append(model.model_validate_json(line))
            except ValidationError as err:
                raise ValueError(f"{path.name} line {number}: {err}") from err
    if not records:
        raise ValueError(f"no {what} found in {folder}")
    if id_field is not None:
        if id_field not in type(records[0]).model_fields:
            raise ValueError(f"{model.__name__} has no field {id_field!r}")
        seen: set[object] = set()
        repeated: set[object] = set()
        for record in records:
            value = getattr(record, id_field)
            try:
                (repeated if value in seen else seen).add(value)
            except TypeError as err:  # a list or dict can't be compared for repeats
                raise ValueError(f"{id_field} values must be hashable ({err})") from err
        if repeated:
            raise ValueError(f"repeated {id_field} values: {sorted(repeated, key=str)}")
    return records
