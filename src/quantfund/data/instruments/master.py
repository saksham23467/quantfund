"""Versioned instrument master store.

Permanent identity is instrument_id (preferably exchange:ISIN), never today's ticker.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from quantfund.data.identity import resolve_instrument_id
from quantfund.data.models import Instrument


class InstrumentMasterStore:
    """Persist / load a versioned instrument master."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, master_id: str, master_version: str) -> Path:
        return self.root / master_id / f"master_version={master_version}" / "instruments.json"

    def save(
        self,
        *,
        master_id: str,
        master_version: str,
        instruments: list[Instrument],
        source: str,
        notes: str = "",
    ) -> Path:
        path = self.path_for(master_id, master_version)
        if path.exists():
            raise FileExistsError(
                f"Instrument master version immutable: {path}. Bump master_version."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure stable ids
        normalized: list[Instrument] = []
        for inst in instruments:
            if not inst.instrument_id:
                iid = resolve_instrument_id(
                    exchange=inst.exchange, isin=inst.isin, symbol=inst.symbol
                )
                inst = inst.model_copy(update={"instrument_id": iid})
            normalized.append(inst)
        path.write_text(
            json.dumps([i.model_dump(mode="json") for i in normalized], indent=2),
            encoding="utf-8",
        )
        meta = {
            "master_id": master_id,
            "master_version": master_version,
            "source": source,
            "instrument_count": len(normalized),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
            "delisted_count": sum(1 for i in normalized if i.delisting_date),
        }
        (path.parent / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return path

    def load(self, master_id: str, master_version: str) -> list[Instrument]:
        path = self.path_for(master_id, master_version)
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Instrument.model_validate(row) for row in data]

    def by_instrument_id(
        self, master_id: str, master_version: str
    ) -> dict[str, Instrument]:
        return {
            (i.instrument_id or i.symbol): i
            for i in self.load(master_id, master_version)
        }

    def resolve_symbol_asof(
        self,
        master_id: str,
        master_version: str,
        instrument_id: str,
        on,
    ) -> str | None:
        mapping = self.by_instrument_id(master_id, master_version)
        inst = mapping.get(instrument_id)
        if inst is None:
            return None
        return inst.symbol_asof(on)
