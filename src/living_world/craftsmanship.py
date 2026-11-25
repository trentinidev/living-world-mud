"""Deterministic quality and per-tool records in civilian saves."""

from dataclasses import asdict, replace
from random import Random

from . import blacksmith, farm_tools, routes
from .model import IRON_HAMMER, IRON_HOE, CraftedTool, ForgeIntent, Movement, PersonalForge, World, WorldError

HAMMER_LIFETIME = 6
TOOL_FIELDS = {IRON_HOE: "crafted_hoes", IRON_HAMMER: "crafted_hammers"}


def quality(seed: int, serial: int, rank: int, fatigue: int, fatigue_limit: int) -> int:
    roll = Random(f"living-world:hoe-quality:{seed}:{serial}")
    variation = 18 - rank * 2
    return 50 + rank * 4 + roll.randint(-variation, variation) - fatigue * 10 // fatigue_limit


def make_tool(world: World, intent: ForgeIntent, serial: int, bonus: int = 0) -> tuple[str, CraftedTool]:
    worker = intent.actor
    personal = isinstance(intent, PersonalForge)
    materials = worker if personal else blacksmith.FORGE_INPUTS
    rank = blacksmith.skill_rank(world.blacksmithing_xp.get(worker, 0))
    hammer = intent.kind == "forge_hammer"
    name = "hammer" if hammer else "hoe"
    score = quality(world.seed, serial, rank, world.actors[worker].fatigue, world.config.village.fatigue_limit)
    return f"{name}-{serial}", CraftedTool(
        maker=worker,
        account=worker if personal else routes.TOOL_STOCK,
        quality=score + bonus - (4 if hammer else 0),
        uses_left=HAMMER_LIFETIME if hammer else farm_tools.HOE_LIFETIME,
        iron_source=materials,
        fuel_source=materials,
        made_at=world.minute,
    )


def update_inventory(
    world: World, movements: tuple[Movement, ...], made: tuple[str, CraftedTool] | None,
    *, selected: str | None = None, reserved: frozenset[str] = frozenset(),
) -> dict[str, list[dict[str, object]]]:
    changes: dict[str, list[dict[str, object]]] = {}
    for move in movements:
        field = TOOL_FIELDS.get(move.good)
        if field is None:
            continue
        records = world.crafted_hoes if move.good == IRON_HOE else world.crafted_hammers
        updates = changes.setdefault(field, [])
        if move.source is None:
            if made is None or move.quantity != 1 or made[1].account != move.destination:
                raise WorldError("missing provenance for a newly forged tool")
            item, record = made
            records[item] = record
            updates.append({"id": item, **asdict(record)})
            continue
        items = sorted(
            (key for key, record in records.items()
             if record.account == move.source and key not in reserved and (selected is None or key == selected)),
            key=lambda key: int(key.rsplit("-", 1)[1]),
        )[:move.quantity]
        if len(items) != move.quantity:
            raise WorldError(f"missing {move.good} records at {move.source}")
        for item in items:
            if move.destination is None:
                del records[item]
            else:
                records[item] = replace(records[item], account=move.destination)
            updates.append({"id": item, "source": move.source, "destination": move.destination})
    return changes


def use_hammer(world: World, actor: str) -> tuple[str, int, int] | None:
    item = min((key for key, record in world.crafted_hammers.items() if record.account == actor),
               key=lambda key: int(key.removeprefix("hammer-")), default=None)
    if item is None:
        return None
    record = world.crafted_hammers[item]
    remaining = record.uses_left - 1
    world.crafted_hammers[item] = replace(record, uses_left=remaining)
    return item, remaining, min(6, record.quality // 10)


def record_wear(world: World, farm: str) -> str:
    item, record = next((key, record) for key, record in world.crafted_hoes.items()
                        if record.account == routes.pantry(farm))
    world.crafted_hoes[item] = replace(record, uses_left=world.hoe_uses[farm])
    return item
